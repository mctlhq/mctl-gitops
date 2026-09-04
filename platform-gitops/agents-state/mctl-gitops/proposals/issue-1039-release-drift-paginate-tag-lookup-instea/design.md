# Design: issue-1039-release-drift-paginate-tag-lookup-instea

## Current state

`.github/scripts/release-drift.sh` is a single self-contained bash script
(`set -euo pipefail`), triggered daily by `.github/workflows/release-drift.yml`
(cron `17 7 * * *` plus `workflow_dispatch`). The workflow's `check` job
runs two steps in order:

1. `Self-test the classifiers` — `.github/scripts/release-drift.sh --self-test`
2. `Compare merged / released / deployed` — `.github/scripts/release-drift.sh`
   (the live run), authenticated with a short-lived GitHub App token scoped
   to read every `mctlhq` repo.

The function in question, `latest_release()` (lines 114-135), returns the
newest release/tag of a source repo:

```bash
latest_release() {
  local repo="$1" rel tags
  if rel=$(gh api "repos/$ORG/$repo/releases/latest" 2>/dev/null); then
    jq -r '[.tag_name, .published_at] | @tsv' <<<"$rel"
    return 0
  fi
  tags=$(gh api "repos/$ORG/$repo/tags?per_page=100" --jq '.[].name' 2>/dev/null) || return 1
  local t best="" best_v=""
  while read -r t; do
    [ -n "$t" ] && is_release_tag "$t" || continue
    if [ -z "$best" ] || [ "$(printf '%s\n%s\n' "$best_v" "$(strip_v "$t")" | sort -V | tail -1)" != "$best_v" ]; then
      best="$t"; best_v="$(strip_v "$t")"
    fi
  done <<<"$tags"
  [ -n "$best" ] || return 1
  local date
  date=$(gh api "repos/$ORG/$repo/commits/$best" --jq '.commit.committer.date' 2>/dev/null) || return 1
  printf '%s\t%s\n' "$best" "$date"
}
```

It is called from `check_image()` (line 154), whose failure path already
degrades to a `skip: no release tag under $ORG/$repo` verdict (line 155) —
this is the existing "fail closed" behavior the acceptance criteria say
must be preserved, not introduced.

The tags call has no `--paginate`. `gh api` with `per_page=100` and no
`--paginate` fetches exactly one page — up to 100 tags — and silently
stops there; it does not error when more pages exist. For a repo whose
tag history exceeds 100 entries, any release-shaped tag that only appears
on page 2+ is invisible to the `while read -r t; do ... done <<<"$tags"`
selection loop, and the newest-by-`sort -V` result can be wrong in either
direction (missing a newer tag → false `NOT_DEPLOYED_*` drift, or landing
on a tag `deployed` already matches by coincidence → false `ok`).

The script's only test surface today is `self_test()` (lines 207-254),
run via `--self-test`. It is pure and offline: it calls
`is_releasable_subject`, `is_release_tag`, `unreleased_from_compare`, and
`image_block_fields` directly against inline string/heredoc fixtures.
None of the three `gh api` call sites in the file (`releases/latest`,
`tags?per_page=100`, `commits/$best`, plus `compare/...` and
`actions/workflows/.../runs` in `check_image()`) are exercised by
`self_test()` today — there is no precedent in this file for stubbing
`gh` itself. The nearest precedent in the repo for testing a script by
intercepting what it shells out to, rather than only testing pure
functions, is `tests/test_release_deploy_bump.py`, which extracts an
embedded script from a workflow YAML and runs it against a fixture
filesystem (fake `values.yaml` / CWFT files) with `subprocess.run` and a
controlled `cwd`/env — same principle (drive the real code path against a
substitute for the real external state), different mechanism (filesystem
fixtures, not a command stub), because that script's only "external"
dependency is the filesystem, not an API client.

## Proposed solution

1. **Add `--paginate` to the one call site that needs it.** Change line
   120 from:
   ```bash
   tags=$(gh api "repos/$ORG/$repo/tags?per_page=100" --jq '.[].name' 2>/dev/null) || return 1
   ```
   to:
   ```bash
   tags=$(gh api --paginate "repos/$ORG/$repo/tags?per_page=100" --jq '.[].name' 2>/dev/null) || return 1
   ```
   `gh api --paginate` walks the `Link: rel="next"` header GitHub returns
   on this endpoint and concatenates each page's `--jq`-filtered output,
   so the rest of the function (the `while read -r t` selection loop) is
   unchanged — it just now sees the full tag set instead of page 1. This
   is a one-line diff; no other `gh api` call in the file is a paginated
   list endpoint (`releases/latest` and `commits/$best` return single
   objects; `compare/...` is a single comparison object; the
   `actions/workflows/.../runs` call already limits itself to
   `per_page=1` and only reads `.workflow_runs[0]`, which is
   deliberately not exhaustive — it only wants the *latest* run, so it is
   out of scope here per the requirements).

2. **Add a `gh`-stubbing fixture to `self_test()`** that proves a tag
   beyond the first 100 entries participates in selection. Bash has no
   built-in mocking, but `gh` is invoked by bare name (`gh api ...`), so
   a fake `gh` placed earlier on `$PATH` than the real one is picked up
   transparently — no change to `latest_release()` is needed to make it
   testable, keeping the diff to the one line in step 1 plus test code.
   Concretely, add a new self-test case:

   ```bash
   # latest_release(): tags beyond page 1 must still win selection, and
   # dropping --paginate must make this fail (that IS the mutation test).
   local ghstub; ghstub=$(mktemp -d)
   cat >"$ghstub/gh" <<'STUB'
   #!/usr/bin/env bash
   # Fixture gh: repo "paginated-fixture" has no GitHub Release (so
   # latest_release falls through to the tags path) and 105 tags; the
   # newest, 9.9.9, is tag #105 -- beyond a single per_page=100 page.
   case "$*" in
     *"releases/latest"*) exit 1 ;;
     *"tags?per_page=100"*"--paginate"*)
       for i in $(seq 1 104); do printf '0.0.%s\n' "$i"; done
       printf '9.9.9\n'
       ;;
     *"tags?per_page=100"*)
       # No --paginate: only page 1 (first 100 of the 105 tags), so 9.9.9
       # (the 105th) is truncated away -- this is the bug being fixed.
       for i in $(seq 1 100); do printf '0.0.%s\n' "$i"; done
       ;;
     *"commits/9.9.9"*) printf '{"commit":{"committer":{"date":"2026-08-01T00:00:00Z"}}}\n' ;;
     *) exit 1 ;;
   esac
   STUB
   chmod +x "$ghstub/gh"
   out=$(PATH="$ghstub:$PATH" latest_release "paginated-fixture")
   rm -rf "$ghstub"
   [ "$out" = $'9.9.9\t2026-08-01T00:00:00Z' ] || {
     echo "self-test: latest_release did not select the tag beyond page 1, got '$out'"
     return 1
   }
   ```

   This is deliberately black-box against the *source line*, not the
   stub: the stub's page-1-vs-paginated branching mirrors what the real
   GitHub API does (return only 100 entries when `--paginate` is absent),
   so the test's pass/fail is driven entirely by whether
   `latest_release()`'s `gh api` invocation actually carries
   `--paginate`. If a future edit removes `--paginate` from line 120, the
   stub's second `case` arm matches instead of the first, `9.9.9` is
   never emitted, `best`/`best_v` top out at `0.0.100`, and the assertion
   fails — this is the "remove `--paginate` and the test must fail"
   mutation check the issue asks for, and it requires no change to the
   test itself to verify: it is inherent in how the stub discriminates on
   the literal `--paginate` argument.

3. **No change to `check_image()`'s failure handling.** The
   `latest_release "$repo" || return 1` failure path and its caller's
   `skip: no release tag under $ORG/$repo` verdict are untouched — this
   satisfies "API failure remains fail-closed rather than becoming
   skip/ok" by construction (nothing in this change touches that path;
   the existing `skip` verdict on failure is the fail-closed behavior,
   and it continues to fire for both "no tags API access at all" and
   "paginated fetch failed partway," since `gh api --paginate` still
   exits non-zero on a failed page fetch, same as the unpaginated call
   does today on total failure).

4. **No change to `report()` output shape.** `check_image()`'s
   `printf` verdict line format, `report()`'s markdown table, and the
   `--self-test` step in `release-drift.yml` are all untouched — the fix
   is scoped to the one `gh api` invocation plus its new test fixture.

## Alternatives

- **Bump `per_page` instead of paginating (e.g. `per_page=100` to some
  large-but-still-finite number).** Rejected: still silently truncates
  once a repo's tag count exceeds whatever number is chosen, exactly
  reproducing this bug at a higher threshold instead of fixing it. The
  issue explicitly asks for `--paginate`, not a bigger fixed page.

- **Switch to GraphQL and manually walk `pageInfo.hasNextPage` /
  `endCursor` cursors.** Rejected: `gh api --paginate` already implements
  correct, tested pagination for REST list endpoints including
  `tags`; hand-rolling cursor-walking here duplicates that logic for no
  behavioral gain and adds real complexity (cursor state, loop control)
  to a script that otherwise stays in plain `gh api` + `jq` + `awk`
  idioms throughout, per this file's existing style.

- **Test pagination against a real fixture repo under `mctlhq` seeded
  with 100+ tags, exercised with a live token in CI.** Rejected: this is
  exactly the kind of live-dependency test the existing `--self-test`
  step is designed to avoid (it runs before the live-`GH_TOKEN` step in
  `release-drift.yml` specifically so classifier regressions are caught
  without hitting the network). It would also require maintaining a
  throwaway GitHub repo indefinitely just to keep >100 tags in it, is
  slower (network round-trips instead of an in-process stub), and is
  non-deterministic if that repo's tags ever changed. The PATH-stub
  approach in step 2 gets the same proof (a tag beyond page 1 must
  participate, and removing `--paginate` must break it) fully offline
  and in the same `self_test()` function as everything else.

## Platform impact

- **Migrations / backward compatibility:** none. This is a script-only
  change to one CI workflow's helper script; no schema, no API contract,
  no service redeploy.
- **Resource impact:** `gh api --paginate` issues one HTTP request per
  page instead of one total, only for repos that (a) have no GitHub
  Release at all and (b) have more than 100 tags. This is a small,
  bounded increase in GitHub API calls (and therefore rate-limit
  consumption) against the App-installation token already used by the
  `release-drift` job (`release-drift.yml` lines 43-52), well within the
  job's existing `timeout-minutes: 15` and the App token's rate limit
  headroom (thousands of requests/hour for a GitHub App installation
  token, versus at most a few extra requests/day for this job).
- **Risks + mitigations:**
  - *Risk:* a repo with genuinely very large tag counts (thousands) could
    make `latest_release()` slower per-repo. *Mitigation:* this only
    applies to the tags-fallback path (repos with no GitHub Release);
    every `mctlhq` service repo observed in this scan uses
    release-please, which publishes GitHub Releases, so the fallback
    path is the exception, not the common case, and the existing
    15-minute job timeout has ample margin for a handful of extra
    paginated calls.
  - *Risk:* the new self-test's `gh` stub could pass even when the real
    `--paginate` behavior differs subtly (e.g. `gh` also needs an
    `Accept` header or different flag ordering) from what `gh api`
    actually sends. *Mitigation:* the stub matches on the literal
    argument list `latest_release()` passes to `gh` (via `"$*"`), so it
    is testing the actual invocation shape the script produces, not a
    paraphrase of it; combined with the existing `--self-test` step
    running in the same CI job immediately before the live run, a
    silently-wrong `gh` invocation would still be caught by the second,
    real step against actual `mctlhq` repos on every scheduled run.
