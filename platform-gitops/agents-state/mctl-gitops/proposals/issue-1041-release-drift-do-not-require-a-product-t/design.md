# Design: issue-1041-release-drift-do-not-require-a-product-t

## Current state
All logic lives in one file, `.github/scripts/release-drift.sh`, invoked by
`.github/workflows/release-drift.yml` (daily cron `17 7 * * *` plus
`workflow_dispatch`). Read end-to-end while investigating this issue:

- `pinned_images()` (lines 84-92) walks `platform-gitops/services/*/*/values.yaml`
  and, via `image_block_fields()` (lines 98-108, an `awk` scoped to the
  top-level `image:` block only), extracts `<repo>\t<tag>` for every
  `ghcr.io/mctlhq/...` image.
- `check_image()` (lines 141-191) is the per-image state machine. For a
  release-tag-pinned, non-`ignore`-marked image it:
  1. Resolves `latest_release()` (GitHub release or newest semver tag).
  2. Fetches the compare payload once:
     `cmp=$(gh api "repos/$ORG/$repo/compare/$released...main")` (line 163).
  3. Feeds that same `$cmp` into `unreleased_from_compare()` (lines 62-74),
     which pipes `.commits[]` through `jq` into `<date>\t<subject>` pairs and
     classifies each subject with `is_releasable_subject()` (lines 56-58),
     itself built on `RELEASABLE_RE`/`BREAKING_RE` (lines 52-55) -- a pure
     Conventional-Commit-type regex with **no path awareness**. This is
     exactly the gap the issue reports: `fix(ci): bump claude-review action`
     matches `^fix(\([^)]*\))?!?: ` the same as `fix(app): ...` would.
  4. If `count > 0` and the oldest releasable commit is older than
     `RELEASE_LAG_HOURS` (24h, line 182-184), appends
     `UNRELEASED_<count>_commits_since_<oldest>` to `verdict`.
  5. Separately checks `rp_run` (release-please's last run conclusion) and
     the deployed-vs-released tag mismatch (`NOT_DEPLOYED_*`), appending to
     the same `verdict` string.
  6. Prints one TSV row; falls back to literal `ok` when `verdict` is empty
     (line 190).
- `report()` (lines 193-205) renders the TSV as a markdown table into
  `$GITHUB_STEP_SUMMARY` and decides pass/fail per row with
  `case "$verdict" in ok|skip:*) ;; *) failed=1; ...; esac` (line 202) --
  **this exact-match `ok` is a detail the fix must not break.**
- `self_test()` (lines 207-254) unit-tests the four pure classifier/parser
  functions (`is_releasable_subject`, `is_release_tag`,
  `unreleased_from_compare`, `image_block_fields`) against inline fixtures,
  run as a workflow step (`release-drift.yml` line 36-37) before the real
  cross-repo check. This is the established pattern for adding new logic
  that must be independently testable without live `gh api` access.

Confirmed by reading `RELEASABLE_RE` and the three reported false positives
in the issue: `mctl-loyalty` (ahead 12, only
`.github/workflows/claude-review.yml` changed), `mctl-pairdesk` (ahead 16,
only two `.github/workflows/*.yml` + `CLAUDE.md`),
`pfeifenpatenschaft-backend` (ahead 10, only three
`.github/workflows/*.yml`) -- all three are red purely because commit
subjects like `fix(ci): ...` satisfy `RELEASABLE_RE`, while the GitHub
compare API's `files` array for the same `released...main` range (already
fetchable from the very same `$cmp` payload `check_image` holds) would show
only files under `.github/` (and one `CLAUDE.md`).

## Proposed solution
Add a second, independent classifier that operates on the **aggregate
changed-path set** of the same compare payload already fetched, and use it
to gate -- not replace -- the existing subject-based `UNRELEASED_*` verdict.
Concretely, in `.github/scripts/release-drift.sh`:

1. **`is_metadata_path()`** -- a tiny, explicit allowlist matcher:
   ```sh
   is_metadata_path() {
     case "$1" in
       .github/*) return 0 ;;
       CLAUDE.md) return 0 ;;
       *) return 1 ;;
     esac
   }
   ```
   Kept as a `case` glob, matching the style of `is_release_tag`/
   `is_releasable_subject` (single-purpose predicate, testable in
   isolation). Root-only `CLAUDE.md` per the Open Question in
   requirements.md.

2. **`is_metadata_only_diff()`** -- stdin: the same compare JSON already
   bound to `$cmp` in `check_image`. Extracts `.files[]?.filename` via `jq`
   (the same tool the script already depends on for `unreleased_from_compare`)
   and returns success only if the set is non-empty and every path passes
   `is_metadata_path`:
   ```sh
   is_metadata_only_diff() {
     local p seen=0
     while IFS= read -r p; do
       [ -z "$p" ] && continue
       seen=1
       is_metadata_path "$p" || return 1
     done < <(jq -r '.files[]?.filename')
     [ "$seen" -eq 1 ]
   }
   ```
   An empty/absent `files` list is treated as "not metadata-only" (`seen=0`
   -> return 1) -- fail safe per the WHILE clause in requirements.md, rather
   than assuming absence means "nothing to worry about".

3. **Wire into `check_image()`** at the existing `UNRELEASED_*` decision
   point (current lines 182-184). Reuse `$cmp`, which is already in scope --
   **no extra `gh api` call**, since GitHub's compare endpoint already
   returns `files` alongside `commits` in one response:
   ```sh
   local metadata_note=""
   if [ "$count" -gt 0 ] && [ $((now - $(to_epoch "$oldest"))) -gt $((RELEASE_LAG_HOURS * 3600)) ]; then
     if is_metadata_only_diff <<<"$cmp"; then
       metadata_note="ok: metadata-only changes (${count} commits since ${oldest})"
     else
       verdict="${verdict:+$verdict,}UNRELEASED_${count}_commits_since_${oldest}"
     fi
   fi
   ```
   and change the final `printf` fallback from `"${verdict:-ok}"` to
   `"${verdict:-${metadata_note:-ok}}"` -- i.e. metadata-only status is only
   surfaced when nothing else (a real `UNRELEASED_*`, `RELEASE_PLEASE_FAILED`,
   or `NOT_DEPLOYED_*`) already made `verdict` non-empty. This preserves the
   existing "verdict wins" composition: a tenant with both a metadata-only
   diff and a failing release-please run still shows
   `RELEASE_PLEASE_FAILED`, not a falsely-reassuring `ok: ...`.

4. **Update `report()`'s pass/fail match** (line 202) from
   `ok|skip:*` to `ok|ok:*|skip:*`, so the new explicit note does not trip
   `failed=1`/`::error::`. This is the one place outside `check_image` that
   must change, and is called out explicitly because it is easy to miss --
   the acceptance criteria depend on this string staying in the "does not
   fail the job" bucket while still being distinguishable in the rendered
   table from a bare `ok`.

5. **Extend `self_test()`** with fixtures mirroring the existing style
   (inline heredoc JSON / case-by-case assertions), covering:
   - `is_metadata_path` true for `.github/workflows/x.yml`, `CLAUDE.md`;
     false for `docs/api/index.md`, `README.md`, `src/app.py`.
   - `is_metadata_only_diff` true for a `files` list that is only
     `.github/**` + `CLAUDE.md`; false for the same list plus one runtime
     path (`src/app.py`); false for an empty/missing `files` key (the
     fail-safe case).
   This is the same battery of pure-function tests the acceptance criteria
   ask for, and it is what makes "mutation removing the path-aware
   suppression" observable: deleting the `is_metadata_only_diff` call (or
   inlining `return 0` in it) flips the "plus one runtime path" assertion
   from pass to fail, since that fixture is specifically constructed to
   differ only in the presence of the gate.

No changes to `pinned_images`, `image_block_fields`, `latest_release`,
`is_releasable_subject`/`RELEASABLE_RE`, or the workflow YAML's permissions
(the compare payload's `files` field is already covered by the existing
`contents: read` / App `permission-contents: read` scope used for
`compare`).

## Alternatives
- **Filter compare commits by their own per-commit file list instead of
  subject.** GitHub's compare API doesn't cheaply expose per-commit file
  lists in the same call (`commits[].files` is not populated by
  `compare`; it would need one `gh api repos/.../commits/<sha>` call per
  commit). This also does not match the issue's own framing: "This is based
  on the aggregate diff, not individual commit subjects: if a runtime change
  was later reverted and the final tree equals the release, no new product
  tag is required." A per-commit path filter would still flag the
  revert-then-restore case; only an aggregate-tree check satisfies that
  acceptance criterion. Dropped.
- **Extend the allowlist to a broader "non-product" glob set (docs/**,
  *.md, config files) to catch more noise at once.** Rejected per the
  issue's explicit counter-example: `mctl-docs`'s post-release diff is
  `docs/api/index.md` + `docs/public/llms-full.txt`, which is shipped site
  content, so any `docs/**` or `*.md`-general rule would silently break that
  service's real-drift signal. The issue asks for a "deliberately tiny"
  allowlist; widening it is an explicit non-goal (see requirements.md Out of
  scope).
- **Keep using the per-tenant `# release-drift: ignore` marker and just
  document it for these three tenants.** This is the status quo escape
  hatch and is explicitly called out in the issue as worse than a real fix:
  it is a blanket, indefinite suppression that would also hide the next
  real product drift for that tenant, not a narrow "these specific commits
  don't matter" signal. Dropped in favor of a mechanism that keeps
  reporting drift the moment a non-metadata path appears.
- **Add a second `gh api` call per image dedicated to file paths (e.g.
  `compare/...?...` with different pagination) instead of reusing `$cmp`.**
  Unnecessary: the same compare response already carries `files`, so this
  would only add latency and another failure mode (a second network call
  that can itself fail) without changing behavior. Dropped in favor of
  reusing the payload already held in `$cmp`.

## Platform impact
- **Migrations / backward compatibility:** none. This is a same-file,
  same-workflow logic change with no schema, secret, or RBAC impact. The
  `values.yaml` files under `platform-gitops/services/**` are read-only
  inputs to this script and are untouched.
- **Resource impact:** negligible. No new `gh api` calls are added (the
  `files` field rides along on the existing `compare` call); the added
  `jq`/`case` work is O(files-changed) per image, run once daily.
- **Risks:**
  - *GitHub compare API file-list cap.* The compare endpoint caps `files`
    at 300 entries for very large diffs. The fail-safe design (empty/absent
    `files` => not metadata-only) means a service that legitimately crosses
    that cap simply keeps today's behavior (subject-based `UNRELEASED_*`),
    never a false "ok". Documented as an explicit Open Question rather than
    solved, since none of the four services named in the issue are close to
    300 changed files in one drift window.
  - *`report()`'s string-match on `verdict` is easy to miss.* Called out as
    its own numbered step above and covered by a task/test pairing (see
    tasks.md) specifically so a reviewer can verify the `ok:*` case doesn't
    silently start failing the workflow (or, worse, silently stop failing
    a real problem if the match is loosened too far, e.g. to a bare `ok*`
    that would also swallow a hypothetical future `okay-ish` verdict --
    hence matching `ok:*` specifically, not `ok*`).
  - *Root-only `CLAUDE.md` matching could miss a nested `CLAUDE.md` in some
    source repo.* Low risk (would only produce a false `UNRELEASED_*`, the
    safe-side failure mode, never a false `ok`), tracked as an Open
    Question rather than blocking.
  - *Self-test-only coverage of the new functions.* Consistent with how
    `check_image`'s `gh api`-dependent logic is untested today (only its
    pure helpers are); the live cross-repo effect on `mctl-loyalty`,
    `mctl-pairdesk`, `pfeifenpatenschaft-backend`, and `mctl-docs` can only
    be confirmed by the next scheduled/`workflow_dispatch` run against real
    data, called out explicitly in tasks.md.
