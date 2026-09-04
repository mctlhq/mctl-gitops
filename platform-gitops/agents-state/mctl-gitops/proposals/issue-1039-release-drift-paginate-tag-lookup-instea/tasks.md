# Tasks: issue-1039-release-drift-paginate-tag-lookup-instea

- [ ] 1. In `.github/scripts/release-drift.sh`, add `--paginate` to the
      tags lookup inside `latest_release()` (currently line 120):
      `tags=$(gh api "repos/$ORG/$repo/tags?per_page=100" --jq '.[].name' 2>/dev/null) || return 1`
      becomes
      `tags=$(gh api --paginate "repos/$ORG/$repo/tags?per_page=100" --jq '.[].name' 2>/dev/null) || return 1`.
      Do not touch the `releases/latest` call, the `commits/$best` call,
      or anything in `check_image()` / `report()`.
      DoD: the single-line diff is the only change to production logic;
      `git diff` on the file touches no other line besides the new
      self-test block added in task 2.

- [ ] 2. Add a new fixture case to `self_test()` in
      `.github/scripts/release-drift.sh` that stubs `gh` on `$PATH` for
      the duration of one `latest_release()` call: the stub reports no
      `releases/latest`, and for the tags endpoint returns 105 tags
      (`0.0.1` .. `0.0.104`, then `9.9.9`) when invoked with `--paginate`
      but only the first 100 (`0.0.1` .. `0.0.100`, omitting `9.9.9`)
      when invoked without it; the stub also answers
      `commits/9.9.9` with a fixed committer date. Assert
      `latest_release "paginated-fixture"` (run with the stub directory
      prepended to `PATH`) returns `9.9.9<TAB>2026-08-01T00:00:00Z`.
      (depends on 1)
      DoD: `.github/scripts/release-drift.sh --self-test` passes locally
      and prints `self-test: ok`; temporarily reverting task 1's
      `--paginate` addition (leaving the new test in place) makes
      `--self-test` fail with the new assertion's error message, then
      re-apply task 1 before committing — this is the mutation check the
      issue asks for, done by hand once during development, not
      automated as a separate CI job.

- [ ] 3. Re-read `report()` and `check_image()` to confirm neither
      references the tags call or needs updating — confirm no line
      besides the one changed in task 1 depends on the old unpaginated
      shape of `$tags` (the `while read -r t; do ... done <<<"$tags"`
      loop is format-agnostic: it already reads one tag name per line
      regardless of how many pages produced them). (depends on 1)
      DoD: written confirmation in the PR description that
      `check_image()`'s `skip: no release tag under $ORG/$repo` verdict
      path (triggered by `latest_release` returning non-zero) is
      unchanged, satisfied by inspection — no code change expected from
      this task.

- [ ] 4. Run `.github/scripts/release-drift.sh --self-test` locally (or
      via the `release-drift` workflow's `Self-test the classifiers`
      step, unchanged) to confirm all existing fixture cases
      (`is_releasable_subject`, `is_release_tag`, `unreleased_from_compare`,
      `image_block_fields`) still pass alongside the new case from task 2.
      (depends on 2)
      DoD: `self-test: ok` printed, exit code 0, no changes needed to any
      pre-existing self-test fixture.

## Tests

- [ ] T1. `.github/scripts/release-drift.sh --self-test` — new case from
      task 2: `latest_release()` selects a tag beyond the first 100
      entries of a 105-tag paginated fixture, proving the fallback path
      reads every page rather than truncating at page 1.
- [ ] T2. Manual mutation check (performed once during development, not
      committed as an automated step): temporarily remove `--paginate`
      from the line touched in task 1, re-run `--self-test`, confirm it
      fails on the new assertion; then restore `--paginate` and confirm
      `--self-test` passes again. This is the concrete proof that T1
      actually exercises the fix rather than passing vacuously.
- [ ] T3. Existing self-test fixtures (`is_releasable_subject`,
      `is_release_tag`, `unreleased_from_compare` two-commit and
      empty-compare cases, `image_block_fields`) continue to pass
      unmodified — confirms this change is additive, not a rewrite of
      `self_test()`.
- [ ] T4. `helm lint` / manifest validation is not applicable — this
      change touches only `.github/scripts/release-drift.sh`, a bash
      script, not a Helm chart or Kubernetes manifest; skip
      `validate-manifests.yml`-style checks for this PR.

## Rollback

Single-file, single-line production change plus additive test code, in a
script that is not deployed anywhere (it runs inline in the
`release-drift` GitHub Actions workflow, invoked fresh from the repo
checkout on every scheduled run). Rollback is a plain `git revert` of the
commit — no state migration, no cache, no running service to restart. If
the new self-test stub turns out flaky in CI (e.g. an ordering assumption
in the fixture's `case "$*" in` matching), the safest interim rollback is
to revert only the `self_test()` addition from task 2 while keeping the
one-line `--paginate` fix from task 1, since task 1 alone already
resolves the issue's core drift-correctness bug; the test coverage can be
re-attempted separately without re-blocking the fix itself.
