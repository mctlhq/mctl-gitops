# Design: issue-83-q12-the-journal-checkpoint-tests-pin-one

## Current state

**The rule.** `docs/journal.md` states the collection-wide rule as "At most
one entry is `in_progress`, including private entries; zero is valid." Two
pieces of production code enforce it:

- `checkJournalCollection()` in `src/lib/journal.ts` throws
  `Journal validation failed: ...`, naming every offending id, when more than
  one entry is `in_progress`.
- `journalLoader()` in `src/content.config.ts` (lines 174-193) wraps the base
  `glob` loader and calls `checkJournalCollection` after every file has
  synced, so the guard runs on `astro sync`, `astro check`, `astro dev` and
  `astro build` alike.

Per-entry evidence rules live in `statusEvidenceProblems()` /
`journalEntryProblems()` in `src/lib/journal.ts` and are mapped onto zod
issues by the `superRefine` on `journalSchema` in `src/content.config.ts`
(lines 159-163). For `status: in_progress` the schema already forbids
`release`, `released_at` and `deployed_at` while permitting a known `pr` and
`merged_at`.

**The defect.** `test/journal-status.test.ts` mixes two kinds of test in one
file. Lines 29-249 are unit tests over hand-built fixtures
(`statusCounts`, `isComplete`, `leadTimeHours`, `isRealTimestamp`,
`statusEvidenceProblems`, `timestampOrderProblems`, `journalEntryProblems`,
`checkJournalCollection`) -- these are fine. Lines 251-356 are source-level
assertions over the committed tree, read through a local `frontmatterOf(name)`
helper (lines 255-268) that hard-codes `JOURNAL_DIR` (line 25) and parses
top-level `key: value` lines out of the frontmatter block. Two of those
source-level tests state more than the invariant:

- Line 288-291:
  `test('at most one journal entry is in_progress -- at this implementation-PR checkpoint, exactly one', ...)`
  asserts `assert.equal(inProgress.length, 1, ...)`.
- Line 348-356:
  `test("this cycle's own entry is in_progress with no invented evidence", ...)`
  calls `frontmatterOf('2026-09-13-journal-lifecycle-and-release-closure.md')`
  and asserts `data.status === 'in_progress'` plus five `undefined` checks.

Both fail the moment cycle 79's entry is closed, which is what
`scripts/close-journal.mjs` did in pull request #82:
`applyClosure()` (lines 168-180) sets `status: complete` and inserts `pr`,
`release`, `merged_at`, `released_at`, and `closureDiffProblems()` proves the
diff touches nothing else. A grep across the repository shows
`2026-09-13-journal-lifecycle-and-release-closure` is referenced from exactly
one place in code or tests: `test/journal-status.test.ts:349`. So the blast
radius of the fix is that one file plus content.

**The content.** `src/content/journal/` holds 23 entries, all
`visibility: public`; 22 are `complete` and one --
`2026-09-13-journal-lifecycle-and-release-closure.md`, 15 lines, frontmatter
only -- is `in_progress`. Counting the `interventions[]` items across the tree
gives 21 (2 + 3 + 3 + 2 + 4 + 7 spread over the four 2026-09-10 entries,
`2026-09-11-production-cutover.md` and `2026-09-11-work-page.md`). The
colophon computes its five totals from the collection --
`src/pages/colophon/index.astro` lines 12-16 and 52-66 bind `cycleCount`,
`counts.complete`, `counts.in_progress`, `counts.abandoned` and
`interventionsTotal` (`totalInterventions`) into
`data-cycle-count` / `data-complete-count` / `data-in-progress-count` /
`data-abandoned-count` / `data-intervention-count` -- so adding one
intervention and one entry moves those numbers with no template change.

**Other guards the change must satisfy.** `test/colophon.test.ts` (lines
78-104) walks every public journal file and requires the eight frontmatter
keys `service`, `issue`, `proposal_slug`, `visibility`, `status`, `title`,
`decided`, `issue_opened_at`, requires every timestamp value (including an
intervention's `at`) to be single-quoted and to match `ISO_WITH_OFFSET`, and
requires the counts of `- what:`, `why:` and `at: '` lines inside an entry to
agree. Its first test forbids the strings `lead_time`, `leadTime`,
`intervention_count`, `interventionCount` anywhere under `src/content/`.
`test/journal-build.test.ts` builds isolated Astro fixture trees with
`makeFixtureTree()` (a full copy of `src/` with `src/content/journal`
replaced) and already covers zero / one / two `in_progress` entries at the
loader level, including a mutant test that removes the
`checkJournalCollection` call.

## Proposed solution

Three changes, all additive-or-local, in one commit.

**1. `test/journal-status.test.ts` -- parameterise the reader, assert the
invariant, prove it on fixtures.**

Give the existing helpers a directory parameter that defaults to the real
tree, so the same code path that checks the committed content can be pointed
at a fixture directory:

```ts
function frontmatterOf(name: string, dir: string = JOURNAL_DIR): Record<string, string>
function inProgressNames(dir: string = JOURNAL_DIR): string[]   // *.md whose status is in_progress
function assertAtMostOneInProgress(dir: string = JOURNAL_DIR): void
```

`assertAtMostOneInProgress` is one `assert.ok(names.length <= 1, ...)` whose
message names the offending files (`at most one journal entry may be
in_progress, found N: a.md, b.md`). The committed-tree test becomes:

```ts
test('at most one journal entry is in_progress', () => {
  assertAtMostOneInProgress();
});
```

The evidence that this assertion can fail lives beside it, in the test file,
because the implementer cannot edit its own pull request description
(`AGENTS.md`, "Issue contract"). Using `mkdtempSync` + `writeFileSync`, build
three throwaway journal directories from a minimal valid frontmatter
generator local to the test file and assert:

- two `in_progress` fixture files -> `assert.throws(() => assertAtMostOneInProgress(dir), /both file names/)`;
- one `in_progress` fixture file -> `assert.doesNotThrow(...)`;
- zero `in_progress` fixture files -> `assert.doesNotThrow(...)`.

`mkdtempSync`/`rmSync` (sync, `node:fs`) keeps this file free of the async
fixture machinery in `test/journal-build.test.ts`; these fixtures never invoke
Astro, they only exercise the reader, which is the unit under test. This is
the same shape as the existing in-memory `checkJournalCollection` cases at
lines 222-249, one level lower: those prove the loader guard, these prove the
file-level reader.

**2. Replace the filename-keyed test with a status-driven guard.** Delete the
`this cycle's own entry is in_progress with no invented evidence` test
entirely and add, in its place, a loop over all files:

```ts
test('every in_progress entry carries no release, released_at or deployed_at', () => {
  for (const name of journalFiles) {
    const data = frontmatterOf(name);
    if (data.status !== 'in_progress') continue;
    for (const field of ['release', 'released_at', 'deployed_at']) {
      assert.ok(!data[field], `${name}: in_progress entry unexpectedly carries ${field}`);
    }
  }
});
```

This mirrors the two source-level tests that already have the right shape --
`every journal file carries a status` (line 270) and `every complete entry
carries pr, release, merged_at and released_at` (line 278) -- and vacuously
passes on a tree with zero in-progress entries, which is a valid tree. It
names no file and pins no count, so no future cycle can break it by living its
normal life. The file's header comment (lines 1-8) is updated in the same
commit: it currently advertises "at most one entry is in_progress" alongside
the checkpoint framing, and must describe invariants only.

Nothing else in the file moves. In particular the in-memory unit test
`checkJournalCollection accepts exactly one in_progress entry` (line 231)
stays: it builds its own two-element list and asserts `doesNotThrow`, so it is
a fixture-level case, and the fixture case at
`test/journal-build.test.ts:264` stays for the same reason.

**3. Content: close cycle 79, open cycle 83.**

`src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md`
becomes the file `scripts/close-journal.mjs` would have produced, plus the one
intervention. `applyClosure()` inserts `pr` after `proposal_slug`, `release`
after `pr`, `merged_at` after `proposal_approved_at` or else `issue_opened_at`,
and `released_at` after `merged_at`, and rewrites `status` in place -- which
yields exactly the field order every already-complete entry in the tree uses
(compare `2026-09-12-symlink-safe-check-no-metrics-entry-guard.md`):

```
service / issue / proposal_slug / pr / release / visibility / status /
title / decided / issue_opened_at / merged_at / released_at / interventions
```

Writing the closure by hand in that exact order and with those exact bytes is
what makes issue acceptance criterion 4 hold: git either sees #82's diff as
already applied or reports a conflict; it can never append a second closure.
No `proposal_approved_at` is invented and no `deployed_at` is added -- the
tree's own test `no portfolio journal entry carries a deployed_at` (line 293)
would fail if one were, and `docs/journal.md` says complete means release
evidence is recorded, not that deployment succeeded.

The new entry `2026-09-13-journal-tests-assert-invariants-only.md` is
frontmatter-only, like every recent entry, with `status: in_progress`,
`interventions: []` and none of `pr` / `merged_at` / `release` /
`released_at` / `deployed_at`. It is the single `in_progress` entry after this
pull request, so `selectClosableEntry()` in `scripts/close-journal.mjs`
(lines 83-96) finds it unambiguously when this cycle's release publishes.

**Why this way.** The failure in #82 was not a bad test but a test written at
the wrong altitude: it described the tree at a moment instead of the rule. The
fix therefore moves each assertion up one level (count -> bound, filename ->
status predicate) and pushes the moment-in-time knowledge down into fixtures
that own their data. Nothing in `src/` changes, so there is no production
behaviour to regress, and the loader/schema remain the single source of truth
for the invariant with the tests now agreeing with them instead of overreaching.

## Alternatives

- **Update the two tests to the new expected values** (expect zero
  `in_progress` before this cycle's entry exists, re-key the second test to the
  new filename). Rejected: it re-creates the same defect one cycle later, which
  is exactly what issue #79's acceptance criterion 4 forbade, and it would make
  the next closure pull request red again.
- **Delete both source-level tests and rely on the schema and loader alone.**
  Rejected: `checkJournalCollection` runs only through Astro's content layer, so
  a broken loader wiring would leave nothing in `node --test` covering the
  collection-wide bound; and `test/journal-build.test.ts` proves the guard on
  fixture trees, never on the committed content. Keeping one cheap invariant
  assertion over the real tree costs milliseconds and catches a tree that two
  concurrent cycles left in a bad state before `astro sync` ever runs.
- **Assert the invariant by importing `checkJournalCollection` and feeding it
  parsed real files.** Attractive -- one rule, one implementation -- but the
  parsed frontmatter in this test file is a flat `Record<string, string>`,
  not the `{ id, data }` collection shape, and mapping it would couple the
  source-level test to the loader's input contract without adding coverage; the
  loader path is already proven by the mutant test in
  `test/journal-build.test.ts` (line 285). Dropped in favour of the local
  bound assertion, which is independent of `src/lib` and fails with file names
  rather than ids.
- **Let closure pull request #82 merge first and fix the tests afterwards.**
  Rejected: #82's `test` job is red, and merging it would require bypassing the
  pre-merge gate the loop depends on. Closing the entry inside this cycle makes
  the fix and its evidence one reviewable commit, and #82 is closed unmerged by
  the release owner.

## Platform impact

- **Migrations / data.** None beyond content. Two journal markdown files
  change (one edited, one added); the collection stays schema-valid, and
  `astro sync` enforces both the per-entry and collection-wide rules during
  `npm run build`.
- **Backward compatibility.** No production source changes: `src/lib/journal.ts`,
  `src/content.config.ts`, the colophon page, the cycle table and the journal
  detail page are untouched. Public output changes only in the computed totals
  (`data-cycle-count` 23 -> 24, `data-complete-count` 22 -> 23,
  `data-in-progress-count` stays 1, `data-intervention-count` 21 -> 22) and in
  the two entries' rendered rows and detail pages, including a new
  interventions list on cycle 79's page.
- **Resource impact.** Negligible: three extra `mkdtemp` fixture directories
  written and removed inside `node --test`, no additional Astro build.
- **Risk: the hand-written closure diverges byte-for-byte from what
  `close-journal.mjs` produces**, weakening acceptance criterion 4. Mitigation:
  the field order and quoting above are read off `applyClosure()` and
  cross-checked against an existing complete entry; the values are the verified
  GitHub facts (`pulls/80` `merged_at` = `2026-09-13T07:23:38Z`; release tag
  `0.1.21` `published_at` = `2026-09-13T07:33:33Z`).
- **Risk: the new invariant test silently covers nothing** if the directory
  scan or the parse breaks. Mitigation: the two-in-progress fixture makes the
  assertion fail on demand from inside the same file, so a scan that stops
  finding entries fails that case.
- **Risk: someone later re-pins a count.** Mitigation: the test name is the
  rule (`at most one journal entry is in_progress`), the header comment says
  the file asserts invariants only, and the fixture cases show the intended
  shape for future additions.
- **Risk: two `in_progress` entries** if the implementer adds this cycle's
  entry without closing cycle 79's. Mitigation: `astro sync` inside
  `npm run build` throws through `checkJournalCollection`, and the new
  invariant test fails in `npm test` before that.
