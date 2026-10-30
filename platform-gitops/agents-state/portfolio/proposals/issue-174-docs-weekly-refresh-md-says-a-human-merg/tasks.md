# Tasks: issue-174-docs-weekly-refresh-md-says-a-human-merg

- [ ] 1. In `docs/weekly-refresh.md`, "Snapshot pull request" section, replace the sentence "release-please then opens a patch release pull request, which a human still merges, so the deploy decision stays manual." with the AC1 text from requirements.md, verbatim, wrapped at about 78 columns, keeping it in the same paragraph — DoD: the AC1 text is present (ignoring line breaks), "which a human still merges" is gone, and `git diff` shows no other change to the file.
- [ ] 2. Create `src/content/journal/2026-10-25-q23-snapshot-releases-merge-themselves.md` with the frontmatter from requirements.md, character for character, and no body — DoD: file exists, `status: in_progress`, no `pr`, `merged_at`, `release`, `released_at` or `deployed_at`, `issue_opened_at: '2026-10-25T00:09:44Z'`.
- [ ] 3. (depends on 1, 2) Run `npm test` and `npm run build` — DoD: both pass; no file under `.github/` is changed; the diff touches only the two files above.

## Tests

- [ ] T1. `npm test` passes, including the journal tests and `test/title.test.ts` (title "Q23: Snapshot releases merge themselves" is under 65 characters).
- [ ] T2. `npm run build` passes: the content loader accepts the new entry (`journalSchema`, `checkJournalCollection` with exactly one `in_progress`, `checkIssueStampOrder` with #174 after #150).
- [ ] T3. `grep -c "which a human still merges" docs/weekly-refresh.md` prints 0.
- [ ] T4. Reviewer step (human, not an acceptance criterion): confirm mctlhq/portfolio#173 has merged to `main` before merging this PR, and that its classification matches the AC1 text.

## Rollback

Revert the merge commit of this PR. That restores the old sentence and removes
the in-progress journal entry; nothing is deployed differently, since `docs/`
is not built into the site and the entry is `noindex`. If #173 is reverted
later, revert this PR too so the doc does not describe auto-merge.
