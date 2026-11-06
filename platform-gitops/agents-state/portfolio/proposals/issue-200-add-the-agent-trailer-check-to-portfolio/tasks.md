# Tasks: issue-200-add-the-agent-trailer-check-to-portfolio

- [ ] 1. Confirm no journal entry is `status: in_progress`
  (`grep '^status: in_progress' src/content/journal/*` is empty) — DoD: the
  check is empty; if not, stop rather than open a second cycle.
- [ ] 2. Create `.github/workflows/agent-trailer-check.yml` with the exact
  content in design.md section 1 (including the two comment lines, ending
  with a single trailing newline) — DoD: file matches design.md byte for
  byte; it has no `with:` and no `enforce`.
- [ ] 3. Add `test/agent-trailer-workflow.test.ts` with the assertions in
  design.md section 2, and append `test/agent-trailer-workflow.test.ts` to
  the `test` script in `package.json` (depends on 2) — DoD: `npm test`
  runs the new file and it passes; `package-lock.json` unchanged.
- [ ] 4. In `src/content/adr/0001-bootstrap-boundary.md`, replace the
  English and Russian Decision paragraphs with the exact copy in design.md
  section 4; change nothing else in the file — DoD: diff touches only those
  two lines; `test/adr.test.ts` and the ADR collection build pass.
- [ ] 5. Add `src/content/journal/2026-11-06-q25-agent-trailer-check.md`
  with the exact frontmatter in design.md section 5 — DoD: the journal
  schema and loader accept it; it is the only `in_progress` entry.
- [ ] 6. Run `npm run build` (vendor + `npm test` + astro build) — DoD:
  exits 0; `dist/` contains the updated ADR-0001 page with both language
  blocks.
- [ ] 7. Commit with a conventional message (for example
  `ci: add the Agent trailer check`) whose final paragraph is a trailer
  block containing `Agent: claude`; every later commit in this pull request
  does the same (depends on 2-5) — DoD: `git log --format=%B origin/main..`
  shows `Agent: claude` as a line of the last paragraph of every commit, and
  every line of that paragraph is `Key: value`.

## Tests

- [ ] T1. `npm test` passes, including the new
  `test/agent-trailer-workflow.test.ts`.
- [ ] T2. Negative check of T1 (local, not committed): adding
  `    with:\n      enforce: true` to the caller, or changing the ref to a
  tag, makes `test/agent-trailer-workflow.test.ts` fail; revert afterwards.
- [ ] T3. `cmp` of the new caller against
  `gh api repos/mctlhq/mctl-web/contents/.github/workflows/agent-trailer-check.yml`
  (base64-decoded) reports no difference. Reviewer step if the implementer
  has no GitHub API access.
- [ ] T4. Reviewer step: on the pull request, the "Agent trailers" check
  ran and did not fail, and the pull request carries an `agent:*` label
  (expected `agent:claude`).
- [ ] T5. Reviewer step: `AGENTS.md`, `claude-review.yml`,
  `release-please.yml`, `dependabot.yml` and `build.yml` are not in the
  diff.

## Rollback

Revert the merge commit through a normal pull request: this removes the
caller, the test and its `package.json` entry, restores the previous
ADR-0001 Decision text, and drops the journal entry (or mark the entry
`abandoned` with a bilingual reason if the cycle is cancelled before
merge). No deployed state or gitops values change, so there is nothing to
roll back on the platform. `agent:*` labels created by the workflow can be
left in place or deleted from repository settings by a human (labels are
human wiring under AGENTS.md).
