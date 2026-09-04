# release-drift: suppress UNRELEASED_* when the aggregate post-release diff is repo/CI metadata only

## Context
`.github/scripts/release-drift.sh` (run daily by `.github/workflows/release-drift.yml`)
compares, per pinned image in `platform-gitops/services/*/*/values.yaml`, the
deployed tag against the source repo's newest release and against `main`. It
flags `UNRELEASED_<n>_commits_since_<date>` when `unreleased_from_compare()`
finds one or more commits on `<released>...main` whose subject matches
`RELEASABLE_RE` (`feat|fix|perf|revert`, or any `!:` breaking change).

That classifier reads only the Conventional Commit type of each commit
subject, never the files the commit touched. `fix(ci): ...` matches
`RELEASABLE_RE` (`fix` + `(ci)` scope) exactly like `fix(app): ...` does, so
a repo whose only unreleased commits are CI/reviewer-workflow maintenance is
reported exactly as "drifted" as one with real unreleased product changes.
Deep-checking #1035 found three tenants (`mctl-loyalty`, `mctl-pairdesk`,
`pfeifenpatenschaft-backend`) currently red for this reason alone: their
`released...main` compares are dozens of commits "ahead" by count, but the
aggregate set of changed file paths across the whole range is nothing but
`.github/workflows/*.yml` and `CLAUDE.md`. Tagging a product release to
absorb a CI file edit is noise, and the alternative the tool already
supports -- the per-tenant `# release-drift: ignore` comment in
`values.yaml` -- is worse, because it would also hide the next *real* drift
for that tenant indefinitely.

`mctl-docs` is the control case: it is also currently red, but its
post-release diff is `docs/api/index.md` and `docs/public/llms-full.txt` --
shipped site content, not CI plumbing -- so it must stay red until a real
release is cut. This means the fix cannot be "ignore commit subjects" or
"ignore any non-code path"; it must be a narrow, explicit allowlist of paths
that are provably never product-affecting, applied to the *aggregate* tree
delta (`released...main` as a whole), not to individual commits -- the issue
explicitly notes that a reverted runtime change must not force a release
either.

## User stories
- AS the platform operator watching `release-drift` output, I WANT tenants
  whose only unshipped changes are CI/repo-metadata files to report clean,
  SO THAT I only cut and review product releases that actually change what
  ships, and the daily job's `::error::` annotations stay meaningful.
- AS a tenant owner who edits `.github/workflows/*.yml` or `CLAUDE.md` on
  main, I WANT that edit to not force a version bump for my service, SO
  THAT I don't have to choose between an unnecessary release and adding a
  `release-drift: ignore` marker that would also hide real future drift.
- AS the platform operator, I WANT the allowlist kept deliberately narrow
  (`.github/**`, `CLAUDE.md` only) and NOT extended to `docs/**`, README, or
  config paths, SO THAT genuinely product-affecting changes (like
  `mctl-docs`'s shipped site content) keep surfacing as drift.

## Acceptance criteria (EARS)
- WHEN `check_image` finds `count > 0` releasable commits on
  `<released>...main` AND the oldest one is older than `RELEASE_LAG_HOURS`,
  THE SYSTEM SHALL inspect the aggregate set of changed file paths in the
  `<released>...main` compare (not per-commit paths) before deciding whether
  to emit `UNRELEASED_<count>_commits_since_<oldest>`.
- IF every changed path in that aggregate set matches the metadata allowlist
  (`.github/**`, exact file `CLAUDE.md`) THEN THE SYSTEM SHALL suppress the
  `UNRELEASED_*` verdict component for that image and report an explicit
  status (e.g. `ok: metadata-only changes (<count> commits)`) instead of a
  bare `ok`, so the report distinguishes "nothing unreleased" from
  "unreleased but immaterial".
- IF the aggregate changed-path set contains at least one path outside the
  allowlist THEN THE SYSTEM SHALL emit `UNRELEASED_*` exactly as it does
  today, unchanged.
- WHILE the changed-path list for a compare cannot be determined (e.g. the
  compare payload has no usable `files` data) THE SYSTEM SHALL treat the
  diff as NOT metadata-only and fall back to today's subject-only behavior,
  so an API/data gap never silently suppresses a real drift signal.
- THE SYSTEM SHALL keep the metadata allowlist limited to `.github/**` and
  `CLAUDE.md` at the top level; `docs/**`, `README*`, and other config or
  source paths SHALL NOT be treated as metadata-only by this change.
- THE SYSTEM SHALL leave `RELEASE_PLEASE_FAILED` and `NOT_DEPLOYED_*`
  verdict components computed exactly as today; metadata-only suppression
  applies only to the `UNRELEASED_*` component.
- WHEN `--self-test` runs, THE SYSTEM SHALL exercise the new path-classifier
  and aggregate-diff-classifier functions in isolation (mirroring the
  existing `is_releasable_subject` / `is_release_tag` / `image_block_fields`
  self-tests), including: an all-`.github/**` fixture classified
  metadata-only; the same fixture plus one runtime file classified NOT
  metadata-only; and `CLAUDE.md` alongside `.github/**` classified
  metadata-only.
- THE SYSTEM SHALL continue to exit 1 from `report()` (and log
  `::error::`) for any verdict that is not `ok`, `ok: ...`, or `skip:...`,
  so `RELEASE_PLEASE_FAILED`, `NOT_DEPLOYED_*`, and non-metadata-only
  `UNRELEASED_*` still fail the workflow.

## Out of scope
- Changing `RELEASABLE_RE` / `is_releasable_subject` (the per-commit
  Conventional Commit classifier) itself -- it stays subject-based; only the
  aggregate-diff gate is added on top of it.
- Extending the allowlist beyond `.github/**` and `CLAUDE.md` (e.g. to
  `docs/**`, `*.md` generally, `renovate.json`, `.gitignore`). The issue is
  explicit that the allowlist must stay tiny and that `mctl-docs` must
  remain red.
- Adding a per-path override/ignore mechanism analogous to
  `# release-drift: ignore` scoped to individual paths.
- Changing `NOT_DEPLOYED_*` or `RELEASE_PLEASE_FAILED` semantics.
- Handling compares with more than GitHub's per-page file cap (see Open
  questions) beyond failing safe (not suppressing).
- Any change to `argocd-freshness.sh` or `deploy-signal.py`, which are
  separate drift-adjacent checks in the same directory but not implicated
  by this issue.

## Open questions
- GitHub's compare API caps the `files` array (historically 300 entries)
  for very large diffs and does not always expose an explicit
  "truncated" flag in the same response shape the script already parses
  with `jq`. This proposal's fail-safe default (treat an empty/unusable
  `files` list as NOT metadata-only) covers this, but a repo with >300
  changed files across the compare range would need this verified against
  live `gh api` output. Recorded as a risk in design.md rather than blocking
  the proposal; none of the three false positives or `mctl-docs` are anywhere
  near that file count.
- Whether `CLAUDE.md` should match only at the repository root or also
  nested `CLAUDE.md` files (e.g. `services/foo/CLAUDE.md`) in source repos
  that have them. The issue's examples only show a root-level `CLAUDE.md`
  change on `mctl-pairdesk`. This proposal matches the exact literal path
  `CLAUDE.md` (root only) to keep the allowlist as narrow as the issue
  requests; nested `CLAUDE.md` files would need `.github/**`-style prefix
  matching, which is a deliberate non-goal here and can be widened later if
  it produces a false positive in practice.
