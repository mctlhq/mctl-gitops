# Design: issue-83-q12-the-journal-checkpoint-tests-pin-one

## Current state

**The invariant, as the code actually enforces it.**
`src/lib/journal.ts` exports `checkJournalCollection(entries)`, which throws
only when *more than one* entry carries `status: 'in_progress'`, naming every
offending id:

```ts
export function checkJournalCollection(entries: readonly JournalCollectionEntry[]): void {
  const inProgress = entries.filter((entry) => entry.data.status === 'in_progress');
  if (inProgress.length > 1) {
    throw new Error(`Journal validation failed:\n- two entries are in_progress: ${...}`);
  }
}
```

`src/content.config.ts` wraps the base glob loader in `journalLoader()` and
calls that function after every file has synced, so the rule runs on
`astro sync`, `astro check`, `astro dev` and `astro build` alike. Its comment
says "at most one entry, public or private, may be `status: in_progress`".
`docs/journal.md` says the same in words: "At most one entry is `in_progress`,
including private entries; zero is valid."

**The two tests that contradict it.** `test/journal-status.test.ts` reads the
committed tree directly (`readdirSync(JOURNAL_DIR)` plus a small
`frontmatterOf()` regex parser) and, at lines 288-291, asserts equality:

```ts
test('at most one journal entry is in_progress -- at this implementation-PR checkpoint, exactly one', () => {
  const inProgress = journalFiles.filter((name) => frontmatterOf(name).status === 'in_progress');
  assert.equal(inProgress.length, 1, `expected exactly one in_progress entry at this checkpoint, got: ${inProgress.join(', ')}`);
});
```

and at lines 348-356 names one file:

```ts
test("this cycle's own entry is in_progress with no invented evidence", () => {
  const data = frontmatterOf('2026-09-13-journal-lifecycle-and-release-closure.md');
  assert.equal(data.status, 'in_progress');
  ...
});
```

Both are source-level assertions over live content, in a file whose other
source-level tests (`every journal file carries a status`, `every complete
entry carries pr, release, merged_at and released_at`, `no portfolio journal
entry carries a deployed_at`) are correctly written as loops over
`journalFiles` with no filename or count pinned.

**Why closing a cycle turns them red.** `scripts/close-journal.mjs` (out of
scope here) opens a closure PR that changes exactly five fields of the single
in-progress entry: `status`, `pr`, `release`, `merged_at`, `released_at`. PR
#82 does exactly that for
`src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md` —
its diff adds `pr: https://github.com/mctlhq/portfolio/pull/80`,
`release: 0.1.21`, flips `status: in_progress` to `status: complete`, and adds
`merged_at: '2026-09-13T07:23:38Z'` and `released_at: '2026-09-13T07:33:33Z'`.
That makes the in-progress count 0 (legal) and that file's status `complete`
(legal), so the two pinned tests fail and the closure PR's `test` job is red.

**The rest of the journal suite is already fixture-based and unaffected.**
`test/journal-build.test.ts` copies `src/` into a `mkdtemp` tree, replaces
`src/content/journal` with its own fixture files and spawns the astro CLI, so
its case at line 264 ("astro sync passes with exactly one in_progress entry")
never reads committed content. `test/journal-closure.test.ts` builds its own
entry strings. `test/colophon.test.ts` loops over every journal file for
required keys, single-quoted ISO timestamps and balanced
`what`/`why`/`at` intervention items, with no filename pinned. Nothing else in
`test/`, `src/`, `scripts/` or `.github/` mentions
`journal-lifecycle-and-release-closure`.

**Counts today.** 23 journal files, all `visibility: public`; 21 intervention
items across 6 files (`grep -rn "^\s*- what:" src/content/journal/*.md | wc -l`).
`src/pages/colophon/index.astro` computes
`const interventionsTotal = totalInterventions(journal.map((entry) => entry.data));`
and renders `<span data-intervention-count={interventionsTotal}>`, so the total
follows the data with no template change.

**Evidence verified for this proposal** (GitHub REST, read-only):
`pulls/80.merged_at = 2026-09-13T07:23:38Z`; release tag `0.1.21`
`published_at = 2026-09-13T07:33:33Z`; issue 83 `created_at =
2026-09-13T07:37:51Z`; PR #82 is OPEN, head `fix/journal-close-79`, touching
only that one journal file.

## Proposed solution

Three edits, all data and tests; no production source, script, workflow,
schema or loader changes.

### 1. `test/journal-status.test.ts`: one invariant, exercised by fixtures

Introduce a small pure helper in the test file, above the source-level
section, so the same code path can be run over the committed tree and over
synthetic fixture sets:

```ts
/** The journal's collection-wide invariant, at source level: at most one
 * entry may be `status: in_progress`; zero is valid (docs/journal.md, and
 * checkJournalCollection in src/lib/journal.ts, which throws only above one).
 * Takes the file list and a status lookup rather than reading the directory
 * itself, so the mutation cases below exercise this exact assertion against
 * fixture sets instead of a paraphrase of it. */
function assertAtMostOneInProgress(
  names: readonly string[],
  statusOf: (name: string) => string | undefined,
): void {
  const inProgress = names.filter((name) => statusOf(name) === 'in_progress');
  assert.ok(
    inProgress.length <= 1,
    `at most one journal entry may be in_progress, found ${inProgress.length}: ${inProgress.join(', ')}`,
  );
}
```

Replace the checkpoint test with the invariant over the real tree:

```ts
test('at most one journal entry is in_progress', () => {
  assertAtMostOneInProgress(journalFiles, (name) => frontmatterOf(name).status);
});
```

Commit the mutation evidence beside it, in the same file, as acceptance
criterion 2 requires (the PR body cannot carry it — `AGENTS.md` forbids
criteria that need text in a pull request description, and the implementer
cannot edit its own PR body):

```ts
// Mutation evidence for the invariant above: the same assertion, run over
// fixture sets rather than the committed tree, goes red for two in-progress
// entries (naming both) and green for zero. Without this, an assertion that
// happens to be vacuous -- e.g. a lookup returning undefined for every file
// -- would pass unnoticed, the defect class issue #71 closed five of.
const FIXTURE_STATUS: Record<string, string> = {
  'two-a.md': 'in_progress',
  'two-b.md': 'in_progress',
  'done.md': 'complete',
};
const fixtureStatusOf = (name: string) => FIXTURE_STATUS[name];

test('the at-most-one invariant fails for two in_progress fixtures, naming both', () => {
  assert.throws(
    () => assertAtMostOneInProgress(['two-a.md', 'two-b.md', 'done.md'], fixtureStatusOf),
    /found 2: two-a\.md, two-b\.md/,
  );
});

test('the at-most-one invariant passes for zero in_progress fixtures', () => {
  assert.doesNotThrow(() => assertAtMostOneInProgress(['done.md'], fixtureStatusOf));
});
```

Delete the filename-keyed test entirely, and replace its intent with a
status-driven guard over all files — the shape the issue mandates if a guard
is kept at all. It deliberately does not assert the absence of `pr` or
`merged_at`: `docs/journal.md` allows an in-progress entry to record a known
implementation PR and merge time.

```ts
test('no in_progress entry carries release or deployment evidence', () => {
  for (const name of journalFiles) {
    const data = frontmatterOf(name);
    if (data.status !== 'in_progress') continue;
    for (const field of ['release', 'released_at', 'deployed_at']) {
      assert.ok(!data[field], `${name}: in_progress entry carries ${field}`);
    }
  }
});
```

Finally, update the file's header comment so its list of source-level
assertions reads "at most one entry is in_progress" with no checkpoint
wording.

Why a helper plus fixtures rather than calling `checkJournalCollection` from
the source-level test: the source-level tests in this file deliberately parse
the committed Markdown with their own `frontmatterOf()` instead of going
through the schema, so a frontmatter typo that the loader would reject is
still caught here by reading bytes. Keeping that property while making the
check itself mutation-provable means parameterising the assertion on a status
lookup, which is what the helper does. `checkJournalCollection`'s own
unit tests (zero / one / two, lines 221-249) stay untouched.

### 2. Close cycle 79's entry (supersedes #82)

Edit `src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md`
to the exact values in requirements B, placing the new keys where #82 places
them and where every other complete entry (e.g.
`2026-09-12-q9-six-review-findings.md`) has them: `pr` and `release` after
`proposal_slug` and before `visibility`; `merged_at` and `released_at` after
`issue_opened_at` and before `interventions`. The resulting frontmatter:

```yaml
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/79
proposal_slug: issue-79-q11-every-cycle-s-journal-entry-is-born
pr: https://github.com/mctlhq/portfolio/pull/80
release: 0.1.21
visibility: public
status: complete
title:
  (unchanged)
decided:
  (unchanged)
issue_opened_at: '2026-09-13T05:29:22Z'
merged_at: '2026-09-13T07:23:38Z'
released_at: '2026-09-13T07:33:33Z'
interventions:
  - what: "Merged pull request #80 by hand (merge commit) after the review had approved it with no P1/P2 findings and CI was green."
    why: "The deployed shepherd (mctl-agents 1.42.0) re-fed a round-1 P2 that GitHub had re-anchored to the new head and the reviewer had already confirmed closed; the implementer correctly refused (exit 42) and review_attempts reached 3. The fix (mctl-agents#359, merge on the head's verdict) was on mctl-agents main but unreleased."
    at: '2026-09-13T07:23:38Z'
---
```

No `deployed_at`, per the entry's own rule and
`test/journal-status.test.ts`'s `no portfolio journal entry carries a
deployed_at`. The double-quoted `what`/`why` and single-quoted `at` match the
existing style in `2026-09-11-production-cutover.md` and satisfy
`test/colophon.test.ts`, which requires every timestamp value (including an
intervention's `at`) to be single-quoted and to match `ISO_WITH_OFFSET`, and
requires the counts of `- what:`, `why:` and `at: '` to agree.

Placing this closure in the implementation PR rather than leaving it to #82 is
what makes acceptance criterion 4 checkable: after this branch, #82's first
hunk is already applied (no-op) and its second hunk conflicts on the
`interventions` context line, so it can never produce a second closure.

### 3. This cycle's own entry

Add `src/content/journal/2026-09-13-journal-tests-assert-invariants-only.md`
with the exact frontmatter in requirements C: `status: in_progress`,
`issue: https://github.com/mctlhq/portfolio/issues/83`,
`proposal_slug: issue-83-q12-the-journal-checkpoint-tests-pin-one`,
`issue_opened_at: '2026-09-13T07:37:51Z'` (the issue's `created_at` from the
GitHub API), bilingual `title` and `decided`, `interventions: []`, and no
release evidence. Empty body, like every other entry. Combined with edit 2,
exactly one entry is `in_progress` afterwards, and the loader guard,
the new invariant test and the new status-driven guard all pass.

The colophon totals move on their own: 24 public cycles, 23 complete, 1 in
progress, 0 abandoned, and `data-intervention-count` 22 (21 + 1).

## Alternatives

1. **Fix only the tests; let #82 close cycle 79.** Rejected: this cycle's own
   entry must be written with `status: in_progress` anyway, and the loader
   forbids two in-progress entries — so cycle 79's entry has to be closed in
   the same commit or the branch will not even `astro sync`. Leaving it to #82
   would also leave cycle 79's one manual intervention unrecorded, since the
   closure workflow writes only the five lifecycle fields.

2. **Make the source-level invariant test call `checkJournalCollection()` on
   parsed frontmatter.** Rejected: it couples the byte-level content test to
   the collection helper's error shape, and the mutation evidence would then
   prove the helper (already unit-tested three ways at lines 221-249) rather
   than the source-level check that actually reads the committed tree.

3. **Delete both tests and rely on the loader guard alone.** Rejected: the
   loader only runs under astro (`sync`/`check`/`build`), while
   `npm test` runs `node --test` first; a source-level assertion that fails
   fast, with file names in the message, is cheaper feedback and is the
   established pattern for the other content invariants in this file.

4. **Keep the filename-keyed test but update it to the new cycle's file.**
   Rejected explicitly by the issue and by issue #79's criterion 4 — it just
   moves the landmine to the next cycle, which would then have to edit a test
   to do its ordinary work.

## Platform impact

- **Migrations / data:** none beyond journal content. No schema, loader or
  script change, so no re-validation of historical entries is needed.
- **Backward compatibility:** `test/journal-build.test.ts`,
  `test/journal-closure.test.ts` and `test/journal-workflow.test.ts` build
  their own fixtures and are untouched. `test/colophon.test.ts` iterates over
  all journal files and keeps passing for the new one.
- **Site output:** one new page under `/colophon/journal/`, computed totals
  updated. `scripts/check-links.mjs` resolves internal links only, and the new
  entry adds one internal route plus an off-origin `issue:` URL that the
  script reports as skipped, never fetched.
- **Risks + mitigations:**
  - *A vacuous invariant test.* `assert.ok(x <= 1)` passes when the status
    lookup silently returns `undefined` for everything. Mitigated by the two
    committed mutation cases, which must go red for two in-progress fixtures
    and green for zero; this is the same control-proves-itself pattern as
    `test/check-dist.test.ts`'s injected upstream throw.
  - *Regression of the deleted guard.* Mitigated by the status-driven
    replacement, which covers every file rather than one name.
  - *Wrong evidence on cycle 79's entry.* Mitigated by using the exact values
    the closure workflow computed in #82 and re-verified against GitHub REST:
    `merged_at` 2026-09-13T07:23:38Z, `released_at` 2026-09-13T07:33:33Z,
    release 0.1.21, PR 80.
  - *Two in-progress entries at merge time.* Impossible to miss: the loader
    throws during `astro sync`/`build`, and the new invariant test fails in
    `npm test`, both naming the offending files.
  - *#82 merged by mistake after this lands.* Out of this cycle's hands by
    design; the release owner closes it unmerged. Git prevents the damage
    anyway, since its second hunk conflicts.
