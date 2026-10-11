# Tasks: issue-125-test-e2e-add-an-approval-gate-note-to-th

- [ ] 1. In `docs/mcp/tools-reference.md`, `### mctl_trigger_shepherd` section, insert one new paragraph between the numbered list (ending with step 4, "...flips the status to `status: rejected`.") and the paragraph starting "The shepherd also runs autonomously". Text: "In this repository (mctl-docs), the platform may require an explicit human approval (an action-approval receipt) before it merges an agent-authored PR." — DoD: exactly one sentence is added, surrounded by blank lines, with no other edits to the file.
- [ ] 2. Commit with the message `docs: note that agent-authored PR merges may require human approval` (depends on 1) — DoD: `git diff --stat` against the base shows only `docs/mcp/tools-reference.md`, with 2 or fewer added lines (sentence plus blank line) and 0 removed lines.

## Tests
- [ ] T1. `bun install && bun run build` succeeds, and the built `mcp/tools-reference.html` contains the new sentence.
- [ ] T2. `git diff --name-only origin/main...HEAD` prints only `docs/mcp/tools-reference.md`. In particular, `CHANGELOG.md`, `release-please-config.json`, `.release-please-manifest.json`, `package.json`, `bun.lock` and `docs/public/llms-full.txt` do not appear.
- [ ] T3. The added text contains no emoji and no links, and it is a single sentence (one terminal period).

## Rollback
Revert the single commit (`git revert <sha>`) through a normal PR. Static docs only, so a later tag rebuild removes the sentence from docs.mctl.ai, and nothing else depends on it.
