# Tasks: issue-83-q12-the-journal-checkpoint-tests-pin-one

- [ ] 1. In `test/journal-status.test.ts`, parameterise the source-level
      reader by directory: change `frontmatterOf(name)` (lines 255-268) to
      `frontmatterOf(name, dir = JOURNAL_DIR)`, and add
      `inProgressNames(dir = JOURNAL_DIR)` returning the `.md` file names in
      `dir` whose frontmatter `status` is `in_progress`, plus
      `assertAtMostOneInProgress(dir = JOURNAL_DIR)` that asserts
      `names.length <= 1` with a message naming the offending files.
      — DoD: the helpers exist, every existing call site of `frontmatterOf`
      still compiles unchanged, and `node --test test/journal-status.test.ts`
      passes.

- [ ] 2. Replace the "exactly one" test (depends on 1). Delete lines 288-291
      (`test('at most one journal entry is in_progress -- at this
      implementation-PR checkpoint, exactly one', ...)` with
      `assert.equal(inProgress.length, 1, ...)`) and put in its place
      `test('at most one journal entry is in_progress', () => {
      assertAtMostOneInProgress(); })`.
      — DoD: no `assert.equal(...length, 1...)` over the committed journal
      directory remains anywhere in the file; the test name contains no
      "exactly one" and no "checkpoint".

- [ ] 3. Delete the filename-keyed test and add a status-driven guard
      (depends on 1). Remove lines 348-356
      (`test("this cycle's own entry is in_progress with no invented
      evidence", ...)`, which calls
      `frontmatterOf('2026-09-13-journal-lifecycle-and-release-closure.md')`)
      and add, in the same source-level block, a test that loops over every
      file in `journalFiles`, skips those whose `status` is not
      `in_progress`, and asserts the entry carries no `release`, no
      `released_at` and no `deployed_at`, naming the file and field on
      failure.
      — DoD: `grep -n "2026-09-13-journal-lifecycle-and-release-closure"
      test/*.ts` returns nothing; the new test names no filename and passes
      vacuously on a tree with zero in-progress entries.

- [ ] 4. Add the fixture evidence for the invariant, inside
      `test/journal-status.test.ts` (depends on 1, 2). Using
      `mkdtempSync`/`writeFileSync`/`rmSync` from `node:fs` and a local
      minimal-frontmatter generator, build three throwaway journal
      directories and assert: two `in_progress` files ->
      `assert.throws(() => assertAtMostOneInProgress(dir))` with the message
      naming both files; one `in_progress` file -> `assert.doesNotThrow`;
      zero `in_progress` files -> `assert.doesNotThrow`. Clean each
      directory up in a `finally`.
      — DoD: the three fixture cases live in the test file (not in the pull
      request description), pass, and the two-in-progress case fails if
      `assertAtMostOneInProgress` is temporarily weakened to a no-op.

- [ ] 5. Update the file header comment of `test/journal-status.test.ts`
      (lines 1-8, depends on 2, 3) so it describes invariants only: drop the
      claim that "at this implementation-PR checkpoint, exactly one" entry is
      in progress and the reference to this cycle's own entry; state that the
      source-level block asserts at most one `in_progress` entry, that every
      `in_progress` entry carries no release evidence, and that fixture
      directories prove those assertions can fail.
      — DoD: the comment matches the tests below it, with no checkpoint
      framing left.

- [ ] 6. Close cycle 79's entry:
      `src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md`
      (independent of 1-5). Set, character for character:
      `pr: https://github.com/mctlhq/portfolio/pull/80` (after
      `proposal_slug`), `release: 0.1.21` (after `pr`), `status: complete`
      (in place), `merged_at: '2026-09-13T07:23:38Z'` (after
      `issue_opened_at`), `released_at: '2026-09-13T07:33:33Z'` (after
      `merged_at`). Add no `deployed_at`, no `proposal_approved_at`, and
      change nothing else -- not `service`, `issue`, `proposal_slug`,
      `visibility`, `title`, `decided`, `issue_opened_at`, nor the body.
      — DoD: the frontmatter key order is
      `service, issue, proposal_slug, pr, release, visibility, status, title,
      decided, issue_opened_at, merged_at, released_at, interventions`,
      matching what `applyClosure()` in `scripts/close-journal.mjs` produces
      and what `2026-09-12-symlink-safe-check-no-metrics-entry-guard.md`
      already uses.

- [ ] 7. Record cycle 79's one manual intervention in that same file
      (depends on 6), replacing `interventions: []` with exactly:

      ```yaml
      interventions:
        - what: "Merged pull request #80 by hand (merge commit) after the review had approved it with no P1/P2 findings and CI was green."
          why: "The deployed shepherd (mctl-agents 1.42.0) re-fed a round-1 P2 that GitHub had re-anchored to the new head and the reviewer had already confirmed closed; the implementer correctly refused (exit 42) and review_attempts reached 3. The fix (mctl-agents#359, merge on the head's verdict) was on mctl-agents main but unreleased."
          at: '2026-09-13T07:23:38Z'
      ```

      — DoD: the three strings match the block above character for
      character; `at` is single-quoted; `test/colophon.test.ts`'s
      what/why/at count check passes.

- [ ] 8. Write this cycle's own entry
      `src/content/journal/2026-09-13-journal-tests-assert-invariants-only.md`
      (independent of 1-7): frontmatter only, with `service: portfolio`,
      `issue: https://github.com/mctlhq/portfolio/issues/83`,
      `proposal_slug: issue-83-q12-the-journal-checkpoint-tests-pin-one`,
      `visibility: public`, `status: in_progress`, the bilingual `title` and
      `decided` copied character for character from `requirements.md`,
      `issue_opened_at: '2026-09-13T07:37:51Z'` and `interventions: []`. No
      `pr`, `merged_at`, `release`, `released_at` or `deployed_at`.
      — DoD: the file exists with exactly those keys in the order
      `service, issue, proposal_slug, visibility, status, title, decided,
      issue_opened_at, interventions`; the copy is byte-identical to the
      proposal's; `astro sync` accepts the collection.

- [ ] 9. Do not touch pull request #82, `scripts/close-journal.mjs`,
      `.github/workflows/journal-closure.yml`, `src/content.config.ts`,
      `src/lib/journal.ts` or any other journal entry (standing constraint
      across tasks 1-8).
      — DoD: `git diff --name-only` lists exactly
      `test/journal-status.test.ts`,
      `src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md`
      and
      `src/content/journal/2026-09-13-journal-tests-assert-invariants-only.md`.

## Tests

- [ ] T1. `at most one journal entry is in_progress` over
      `src/content/journal/` passes on the branch, and its failure message
      names the offending files (task 2).
- [ ] T2. The three fixture cases from task 4 pass: two in-progress entries
      make `assertAtMostOneInProgress` throw naming both files; one passes;
      zero passes.
- [ ] T3. Mutation evidence, run locally and then reverted: weaken
      `assertAtMostOneInProgress` to `<= 2` (or to a no-op) and confirm the
      two-in-progress fixture case fails; restore it. Likewise, temporarily
      add `release: 0.1.21` to this cycle's own in-progress entry and confirm
      the status-driven guard from task 3 fails; revert. Record both in the
      journal entry's `decided`, never in the pull request description.
- [ ] T4. `grep -n "exactly one" test/*.ts` returns only fixture-level cases:
      the `astro sync passes with exactly one in_progress entry ...` fixture
      in `test/journal-build.test.ts`, the in-memory
      `checkJournalCollection accepts exactly one in_progress entry` unit
      case in `test/journal-status.test.ts`, and the unrelated hits in
      `test/approach.test.ts`, `test/chain.test.ts`,
      `test/check-dist.test.ts`, `test/home.test.ts`, `test/nginx.test.ts`
      and `test/vendor-assets.test.ts`.
- [ ] T5. `grep -rn "2026-09-13-journal-lifecycle-and-release-closure"
      test/ scripts/ src/*.ts src/lib src/pages` returns nothing.
- [ ] T6. `npm run vendor && npm test` passes, including
      `test/journal-build.test.ts` (fixture Astro builds),
      `test/colophon.test.ts` (frontmatter keys, single-quoted timestamps,
      what/why/at parity) and `test/journal-closure.test.ts`.
- [ ] T7. `npm run build` succeeds and
      `grep -o 'data-[a-z-]*-count="[0-9]*"' dist/colophon/index.html` shows
      `data-cycle-count="24"`, `data-complete-count="23"`,
      `data-in-progress-count="1"`, `data-abandoned-count="0"` and
      `data-intervention-count="22"`. Verify by reading the built output; do
      not add a test that hard-codes these numbers against the committed
      content tree.
- [ ] T8. `node scripts/check-links.mjs` passes.
- [ ] T9. Exactly one entry is `in_progress` after the change:
      `grep -l '^status: in_progress' src/content/journal/*.md` returns only
      `2026-09-13-journal-tests-assert-invariants-only.md`.

## Rollback

Every change is confined to three files and no production source is touched,
so `git revert` of the merge commit restores the previous tree exactly. If the
revert happens after this cycle's release, cycle 79's entry returns to
`status: in_progress` and this cycle's entry disappears, which leaves the
collection valid (one in-progress entry) and reinstates the red closure job on
pull request #82 -- the original defect, not a new one.

Partial rollbacks are safe in either direction and can be taken separately:

- Reverting only the content commits (tasks 6-8) leaves the invariant tests
  green, because they pin no count and no filename; the tree would then have
  one in-progress entry (cycle 79's) and the suite would still pass.
- Reverting only the test changes (tasks 1-5) restores the two checkpoint
  assertions and turns the suite red against the closed entry, so this
  direction must not be taken on its own.

If `data-intervention-count` does not come out as 22 after the build, do not
adjust a test or a template: re-count `interventions[]` items across
`src/content/journal/*.md` and fix the data, since the number is computed by
`totalInterventions` in `src/lib/journal.ts` and can only be wrong if the
content is.
