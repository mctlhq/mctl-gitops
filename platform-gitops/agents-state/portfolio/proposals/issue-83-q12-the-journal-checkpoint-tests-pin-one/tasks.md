# Tasks: issue-83-q12-the-journal-checkpoint-tests-pin-one

- [ ] 1. In `test/journal-status.test.ts`, add the pure helper
  `assertAtMostOneInProgress(names, statusOf)` in the source-level section
  (above the `every journal file carries a status` test), which filters the
  names whose looked-up status is `in_progress` and asserts
  `inProgress.length <= 1` with a message of the form
  `at most one journal entry may be in_progress, found ${n}: ${names}`.
  — DoD: the helper exists, takes the file list and a status lookup as
  arguments, reads no directory itself, and carries a comment citing
  `docs/journal.md` ("zero is valid") and `checkJournalCollection`.

- [ ] 2. Replace the test at lines 288-291 (depends on 1) with
  `test('at most one journal entry is in_progress', () => { assertAtMostOneInProgress(journalFiles, (name) => frontmatterOf(name).status); });`
  — DoD: no `assert.equal(inProgress.length, 1, ...)` anywhere in the file; the
  test name is exactly `at most one journal entry is in_progress` with no
  "checkpoint" or "exactly one" tail.

- [ ] 3. Add the committed mutation evidence next to it (depends on 1): a
  fixture status map with two `in_progress` names and one `complete` name;
  one test asserting `assert.throws(() => assertAtMostOneInProgress([...], fixtureStatusOf), /found 2: two-a\.md, two-b\.md/)`;
  one test asserting `assert.doesNotThrow(...)` for a name list with zero
  `in_progress` entries.
  — DoD: both tests call the same helper the real-tree test calls; the
  two-entry case asserts on a message that names both files; a comment above
  them states that this is the mutation evidence for the invariant and why it
  lives in the test file rather than in the pull request description.

- [ ] 4. Delete the test `this cycle's own entry is in_progress with no
  invented evidence` (lines 348-356) in full.
  — DoD: `grep -n "journal-lifecycle-and-release-closure" test/` returns
  nothing; no test in the repository asserts a status for a named journal file.

- [ ] 5. Add the status-driven replacement guard (depends on 4):
  `test('no in_progress entry carries release or deployment evidence', ...)`
  looping over `journalFiles`, skipping any file whose `status` is not
  `in_progress`, and asserting that `release`, `released_at` and `deployed_at`
  are absent, with a message naming the file and the field.
  — DoD: the guard is keyed to status only, never to a filename, and does not
  assert the absence of `pr` or `merged_at` (an in-progress entry may record a
  known implementation PR and merge time per `docs/journal.md`).

- [ ] 6. Update the header comment of `test/journal-status.test.ts` (depends on
  2, 4, 5) so its enumeration of source-level assertions says "at most one
  entry is in_progress" and no longer implies a fixed checkpoint count or a
  named file.
  — DoD: the comment describes the file as it now is; no occurrence of
  "checkpoint" remains in the file.

- [ ] 7. Close cycle 79's entry:
  `src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md`.
  Insert `pr: https://github.com/mctlhq/portfolio/pull/80` and
  `release: 0.1.21` after `proposal_slug:` and before `visibility:`; change
  `status: in_progress` to `status: complete`; insert
  `merged_at: '2026-09-13T07:23:38Z'` and `released_at: '2026-09-13T07:33:33Z'`
  after `issue_opened_at:` and before `interventions:`.
  — DoD: those five values are present character for character, no
  `deployed_at` is added, and `service`, `issue`, `proposal_slug`,
  `visibility`, `title`, `decided` and `issue_opened_at` are byte-identical to
  before.

- [ ] 8. In the same file (depends on 7), replace `interventions: []` with
  exactly one intervention, character for character:

```yaml
interventions:
  - what: "Merged pull request #80 by hand (merge commit) after the review had approved it with no P1/P2 findings and CI was green."
    why: "The deployed shepherd (mctl-agents 1.42.0) re-fed a round-1 P2 that GitHub had re-anchored to the new head and the reviewer had already confirmed closed; the implementer correctly refused (exit 42) and review_attempts reached 3. The fix (mctl-agents#359, merge on the head's verdict) was on mctl-agents main but unreleased."
    at: '2026-09-13T07:23:38Z'
```

  — DoD: the `what` and `why` strings are double-quoted and byte-identical to
  the above, `at` is single-quoted, and the file's intervention `- what:`,
  `why:` and `at: '` line counts are 1/1/1.

- [ ] 9. Create
  `src/content/journal/2026-09-13-journal-tests-assert-invariants-only.md`
  with the exact frontmatter given in `requirements.md` section C (service,
  issue `https://github.com/mctlhq/portfolio/issues/83`, proposal_slug
  `issue-83-q12-the-journal-checkpoint-tests-pin-one`, `visibility: public`,
  `status: in_progress`, the bilingual `title` and `decided` copy character for
  character, `issue_opened_at: '2026-09-13T07:37:51Z'`, `interventions: []`),
  and an empty body after the closing `---`.
  — DoD: the file matches the requirements block exactly; it has no `pr`,
  `merged_at`, `release`, `released_at` or `deployed_at`; the Russian copy is
  present and non-blank.

- [ ] 10. Verify the invariant holds over the tree (depends on 7, 9):
  exactly one file under `src/content/journal/` has `status: in_progress`, and
  it is `2026-09-13-journal-tests-assert-invariants-only.md`.
  — DoD: `grep -l "^status: in_progress" src/content/journal/*.md` prints that
  one path and nothing else.

- [ ] 11. Do not touch `scripts/close-journal.mjs`, `.github/workflows/`,
  `src/content.config.ts`, `src/lib/journal.ts`, any page, component or i18n
  string, and do not interact with pull request #82.
  — DoD: `git diff --name-only` lists exactly three paths:
  `test/journal-status.test.ts`,
  `src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md`,
  `src/content/journal/2026-09-13-journal-tests-assert-invariants-only.md`.

## Tests

- [ ] T1. `npm run vendor && npm test` passes, including
  `test/journal-status.test.ts`, `test/journal-build.test.ts`,
  `test/journal-closure.test.ts` and `test/colophon.test.ts`.
- [ ] T2. The new invariant test passes with one in-progress entry, and its two
  mutation cases pass: two fixture entries make the same helper throw with a
  message naming both, zero fixture entries make it not throw.
- [ ] T3. `grep -n "exactly one" test/journal-status.test.ts test/journal-build.test.ts`
  returns only fixture-level cases: `checkJournalCollection accepts exactly one
  in_progress entry` and `astro sync passes with exactly one in_progress entry,
  even when it belongs to an older backlog issue than a completed entry`.
- [ ] T4. `grep -rn "journal-lifecycle-and-release-closure" test/` returns
  nothing.
- [ ] T5. `npm run build` passes — `astro sync`/`build` run `journalLoader()`,
  so this also proves `checkJournalCollection` accepts the tree.
- [ ] T6. `node scripts/check-links.mjs` passes after the build, with the new
  journal page reachable from `/colophon/`.
- [ ] T7. The built `dist/colophon/index.html` carries
  `data-cycle-count="24"`, `data-complete-count="23"`,
  `data-in-progress-count="1"`, `data-abandoned-count="0"` and
  `data-intervention-count="22"`, all computed, none typed into a template.
- [ ] T8. The built page for cycle 79's entry renders its one intervention with
  the `what`, `why` and `at` values from task 8.

## Rollback

Every change is a test file and two journal Markdown files; there is no
schema, script, workflow or runtime code to revert. If the branch is wrong
before merge, drop the commit. If it is wrong after merge, revert the merge
commit: the journal returns to cycle 79's entry being `in_progress` with no
intervention, this cycle's entry disappears, and the two pinned tests come
back — which restores the known-red closure-PR behaviour rather than any new
failure. A partial rollback is also safe: reverting only the two content files
leaves zero in-progress entries, which the loader, the new invariant test and
the status-driven guard all accept; reverting only the test file while keeping
the content would fail `npm test`, so do not do that. No deployment, DNS or
gitops change is involved; the site redeploys from the next release exactly as
usual.
