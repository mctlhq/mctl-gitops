# release-drift: paginate tag lookup instead of silently truncating at 100

## Context

`.github/scripts/release-drift.sh` compares three states per pinned
service image (merged / released / deployed) and fails the daily
`release-drift` workflow when they disagree for longer than a release
should take. When a source repo has no GitHub Releases, `latest_release()`
falls back to reading tags directly:

```bash
tags=$(gh api "repos/$ORG/$repo/tags?per_page=100" --jq '.[].name' 2>/dev/null) || return 1
```

`per_page=100` without `--paginate` returns only the first page of the
tags API. `gh api` does not auto-paginate unless told to. For any
`mctlhq` repo whose tag history has grown past 100 entries, the newest
tag can already be off page 2+ (tags are typically returned reverse
of creation order by the GitHub API's default ordering behavior on this
endpoint, but the exact order is not contractually the newest-first, and
long-lived repos accumulate old pre-release / hotfix / preview tags that
push the current release tag further from page 1 over time). The script
then sorts whatever partial set it received via `sort -V` and reports
that as `released`, which can produce a false `NOT_DEPLOYED_*` drift
verdict (comparing against a stale tag) or a false `ok` (missing the real
newest tag that would have shown drift). This was raised by Agy as a P2
follow-up on #1038, filed here as #1039 after #1038 already merged.

The existing `--self-test` mode in the script exercises the pure
classifier functions (`is_releasable_subject`, `is_release_tag`,
`unreleased_from_compare`, `image_block_fields`) against inline fixtures
with no network access. `latest_release()` itself is the one function in
the file that shells out to `gh api` and currently has no self-test
coverage at all, static or otherwise.

## User stories

- AS the release-drift workflow I WANT `latest_release()` to read every
  page of a repository's tags SO THAT repos with more than 100 tags are
  not silently truncated to their first page when selecting the
  newest release.
- AS a reviewer of a future change to this script I WANT a self-test that
  exercises tag selection across a page boundary SO THAT a regression
  (e.g. someone dropping `--paginate` again) is caught by `--self-test`
  before it reaches the daily cron, not by a human noticing a bad verdict
  in production.
- AS an operator reading the `release-drift` job output I WANT an
  unreachable tags API to still surface as the existing `skip: no release
  tag under <org>/<repo>` verdict (never a false `ok`) SO THAT pagination
  failures do not get silently reported as a clean drift check.

## Acceptance criteria (EARS)

- WHEN `latest_release()` falls back to the tags endpoint (no GitHub
  Release exists) THE SYSTEM SHALL request every page of
  `repos/$ORG/$repo/tags` via `gh api ... --paginate` before selecting
  the newest release-shaped tag.
- WHEN the tags API is reachable and returns more than 100 tags with the
  highest-version release tag beyond the first 100 entries THE SYSTEM
  SHALL select that tag as `released`, not a lower-version tag from page
  1 alone.
- WHILE running `.github/scripts/release-drift.sh --self-test` THE SYSTEM
  SHALL exercise `latest_release()` (or equivalent tag-selection logic)
  against a fixture with more than 100 tags and assert the correct
  beyond-page-1 tag is chosen, using a stubbed `gh` so the test needs no
  network access or `GH_TOKEN`.
- IF `--paginate` is removed from the tags lookup (or otherwise stops
  requesting subsequent pages) THEN THE SYSTEM's `--self-test` SHALL fail,
  detecting the regression without requiring a live drift run against a
  real >100-tag repository.
- IF the `gh api` tags call fails (auth error, rate limit, network) THEN
  THE SYSTEM SHALL propagate that failure out of `latest_release()`
  (return non-zero) exactly as it does today, so `check_image()` reports
  its existing `skip: no release tag under <org>/<repo>` verdict rather
  than treating a failed or partial page fetch as `ok` or a clean
  released tag.
- WHEN the tags fallback succeeds normally (repo with a small tag count,
  or a repo with a GitHub Release so the tags fallback is not used) THE
  SYSTEM SHALL produce byte-for-byte the same `report()` table output as
  before this change (deployed / released / released_at / verdict
  columns unaffected).

## Out of scope

- Changing how `releases/latest` is queried — it is already a single
  request against an endpoint that returns one object, not a paginated
  list.
- Changing how `compare/$released...main` or the `release-please.yml`
  workflow-runs lookup are queried — neither is implicated by this issue.
- Changing the tag *ordering*/selection algorithm itself (`sort -V` over
  `strip_v`); the issue is strictly about reading the full input set, not
  about how the best tag is chosen from a complete set.
- Rate-limit backoff or retry logic for `gh api --paginate` — out of
  scope for this fix; the acceptance criteria only require that a failure
  stay fail-closed, not that it retry.
- Any change to `.github/workflows/release-drift.yml` — the workflow
  already runs `--self-test` as a separate step before the live check, so
  no workflow wiring changes are needed for this fix to take effect.

## Open questions

- None. The issue is fully specified: add `--paginate` to the one `gh
  api` tags call in `latest_release()`, and add a self-test that fails
  under the described mutation. The only implementation judgment call —
  how to stub `gh` for an offline, deterministic self-test — is a design
  decision, not an open requirement question, and is resolved in
  design.md (a PATH-prepended fake `gh` executable, following the
  approach `tests/test_release_deploy_bump.py` already uses of exercising
  script logic against fixtures rather than the real external service).
