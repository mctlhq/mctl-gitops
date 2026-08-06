# Tasks: issue-14-smoke-test-verify-temporal-dev-loop-pipe

- [ ] 1. Branch from `main` with a name that does not start with `_`
      (e.g. `docs/content-policy-pointer-timing`) — DoD: branch exists,
      checked out, no other pending changes.
- [ ] 2. Edit `CONTRIBUTING.md`, `## Clean-room rules` section: change
      "If you contribute anything under `content/`, read
      [`CONTENT-POLICY.md`](CONTENT-POLICY.md) first. It is binding." to
      "Before you open a content pull request, read
      [`CONTENT-POLICY.md`](CONTENT-POLICY.md). It is binding." (depends on 1)
      — DoD: `git diff` shows exactly one file changed, `CONTRIBUTING.md`,
      with the sentence above as the only substantive change; the markdown
      link target and surrounding paragraph (attestation summary) are
      untouched.
- [ ] 3. Verify no other file references the old sentence verbatim (depends
      on 2) — DoD: `git grep -n "read \[.CONTENT-POLICY.md" -- . ':!CONTRIBUTING.md'`
      (or equivalent) returns nothing, confirming this is not duplicated
      elsewhere and nothing else needs updating in lockstep.
- [ ] 4. Run local checks (depends on 2) — DoD: `npm ci && npm run
      lint:content && npm run test:content` exit 0 (expected: unaffected,
      since neither reads `CONTRIBUTING.md`, but run to confirm no
      unexpected coupling).
- [ ] 5. Commit with a conventional-commit subject under 72 characters, e.g.
      `docs: point to CONTENT-POLICY.md before opening a content PR`, body
      explaining why (closes the gap between "read this first" and the
      issue's "before you open a content PR" framing) (depends on 2, 3, 4)
      — DoD: one commit, subject line matches `^(feat|fix|docs|chore|ci|refactor|test)(\(.+\))?: .{1,70}$`
      informally, no `Co-Authored-By` trailer per `CLAUDE.md`.
- [ ] 6. Open the PR against `main`, referencing issue #14, and note in the
      PR description that this is a throwaway pipeline smoke test per
      `PLAN.md` section 10 and will be closed without merging (depends on 5)
      — DoD: PR opened; `.github/pull_request_template.md`'s "Content
      attestation" section is deleted from the PR body per the template's
      own instruction, since no file under `content/` is touched.

## Tests

- [ ] T1. `npm run lint:content` passes unchanged (proves the content lint
      is untouched by this docs-only diff).
- [ ] T2. `npm run test:content` passes unchanged (same reasoning; the 15
      rule-violation tests in `tests/content-lint.test.mjs` do not reference
      `CONTRIBUTING.md`).
- [ ] T3. Manual read-through: confirm the edited sentence in
      `CONTRIBUTING.md` renders correctly as markdown (link intact, no
      broken syntax) and still appears before the `## Workflow` section.
- [ ] T4. Confirm `git diff --stat` reports exactly one file
      (`CONTRIBUTING.md`) with a small number of changed lines, matching the
      issue's "keep the diff minimal" instruction.

## Rollback

Revert the single commit (`git revert <sha>`) or close the PR unmerged — the
issue states explicitly that the PR will be closed without merging
regardless of its content, so the default outcome already is "no lasting
change." If it were merged and needed undoing later, a one-line revert PR
restores the prior wording ("read ... first") with no downstream impact,
since nothing else in the repo references this sentence (verified in task 3).
