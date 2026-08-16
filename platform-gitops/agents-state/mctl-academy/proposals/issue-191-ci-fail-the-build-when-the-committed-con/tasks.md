# Tasks: issue-191-ci-fail-the-build-when-the-committed-con

- [ ] 1. Add a new step named `Verify committed content bundle matches
      generated output` to the `content` job in `.github/workflows/ci.yml`,
      placed immediately after the existing `Content lint` step (`run: bun
      run lint:content`) and before `Content lint tests`. The step body:
      ```
      node scripts/build-content-bundle.mjs
      git diff --exit-code client/src/content-bundle.json client/src/course-catalog.json
      ```
      DoD: `ci.yml` diff shows exactly one new step in the `content` job, in
      the specified position, with no changes to any other job or step; YAML
      is valid (e.g. `yq eval . .github/workflows/ci.yml > /dev/null` or
      equivalent parses cleanly).

- [ ] 2. (depends on 1) Locally verify the new step passes against the
      current `main` state of the repo: run `node
      scripts/build-content-bundle.mjs` followed by `git diff --exit-code
      client/src/content-bundle.json client/src/course-catalog.json` from a
      clean checkout and confirm exit code 0 (no diff) — i.e. today's
      committed artefacts are already current, so the new gate does not
      immediately fail unrelated PRs.
      DoD: both commands run in sequence with a final exit code of 0 on an
      unmodified clone; if they are not 0, this task also includes
      regenerating and committing the corrected `client/src/content-bundle.json`
      and/or `client/src/course-catalog.json` in the same PR so the new gate
      starts green.

- [ ] 3. (depends on 1) Open a PR containing only the `ci.yml` change (plus
      any regenerated artefacts from task 2 if needed), following
      CLAUDE.md conventions: conventional commit subject under 72 chars,
      a branch name that does not start with `_`, no `Co-Authored-By`
      trailer, English only, no emoji. This PR is code/CI, not content-only,
      so per CLAUDE.md's "Review gates" it goes through `claude-review.yml`
      and needs no unaddressed P1/P2.
      DoD: PR opened against `main` (never committed directly to `main`),
      CI runs on it including the new step.

## Tests

- [ ] T1. Positive case (already covered by task 2, restated as an explicit
      test criterion): on a PR with no `content/` changes and no artefact
      drift, the new `content` job step passes with exit code 0 and prints
      no diff.
- [ ] T2. Negative case: on a throwaway branch, hand-edit one field inside
      `client/src/content-bundle.json` (e.g. change a `stem` string) without
      touching `content/`, push, and confirm the `content` job fails at the
      new step with a non-zero exit and a `git diff` output in the log that
      names the exact file and changed line. Revert the hand edit before
      merging or discard the branch — this is a verification-only branch,
      not a real change.
- [ ] T3. Negative case: on a throwaway branch, edit a question's `stem` (or
      any bundle-eligible field) under `content/questions/` without
      regenerating the bundle, push, and confirm the same failure mode as
      T2 — this is the realistic drift scenario the issue describes (a
      content edit that forgot to regenerate).
- [ ] T4. Fork-PR parity: confirm (by inspection of `ci.yml`, since a real
      fork-PR run isn't available in this environment) that the new step
      uses only `node scripts/build-content-bundle.mjs` and `git diff
      --exit-code`, neither of which reads `secrets.*` or requires network
      access, so `pull_request` runs from forks execute the new step
      identically to same-repo branch PRs — matching the job's documented
      fork-PR-safe property.
- [ ] T5. Confirm no existing test in `tests/build-content-bundle.test.mjs`
      or `tests/validate-generated-artifacts.test.mjs` needs updating — both
      test the builder's logic against fixture directories via
      `ACADEMY_CONTENT_DIR`/`ACADEMY_BUNDLE_OUT` overrides, which this
      change does not touch. Run `bun run test:content` locally to confirm
      the full existing suite still passes unmodified.

## Rollback

This change is additive and confined to a single CI workflow step in
`.github/workflows/ci.yml`. To roll back:

1. Revert the commit/PR that added the `Verify committed content bundle
   matches generated output` step (a single-file, single-hunk revert).
2. No data migration, no schema change, no application code, and no other
   workflow file is touched by this proposal, so reverting the `ci.yml` step
   fully restores prior behavior with no follow-up cleanup required.
3. If task 2 also regenerated and committed corrected artefact files as part
   of landing this change, evaluate those on their own merits when deciding
   whether to revert them too — they are a legitimate content-correctness
   fix independent of the CI gate and do not need to be reverted together
   with the workflow step.

If the new step turns out to be flaky (e.g. false-positive drift under some
untested environment condition), the safe interim mitigation is to revert
per above rather than to weaken the check (e.g. removing `--exit-code`),
since a silently-passing version of this step defeats the issue's purpose
entirely.
