# Tasks: issue-127-test-e2e-execution-evidence-producer-pro

Note: per issue #127 this proposal is a test fixture and is expected to be rejected, not implemented.

- [ ] 1. In `docs/mcp/tools-reference.md`, under `### mctl_trigger_shepherd`, insert the paragraph
  "Each governed agent run, including every shepherd run, records a sealed execution-evidence
  envelope in mctl-api." after the cron paragraph and before `**Parameters:** none` — DoD:
  `git diff` shows exactly one added sentence (plus surrounding blank line) and no other changes.
- [ ] 2. (depends on 1) Run `bun run generate:llms` and commit the refreshed
  `docs/public/llms-full.txt` — DoD: the new sentence appears once in the shepherd block of
  `llms-full.txt`; no unrelated diff.
- [ ] 3. (depends on 2) Open a PR from a feature branch per `CLAUDE.md` — DoD: PR references
  mctlhq/mctl-docs#127.

## Tests
- [ ] T1. `bun run build` completes with no errors.
- [ ] T2. `grep -c "sealed execution-evidence envelope" docs/mcp/tools-reference.md` returns 1, and
  the match lies between `### mctl_trigger_shepherd` and `### mctl_trigger_issue`.
- [ ] T3. Same grep against `docs/public/llms-full.txt` returns 1.
- [ ] T4. No emoji and English-only in the added line (manual review).

## Rollback
Revert the PR commit (`git revert <sha>`) and push a new patch tag (`MAJOR.MINOR.PATCH`, no `v`)
to redeploy the previous content. If never merged, simply close the PR and delete the branch.
