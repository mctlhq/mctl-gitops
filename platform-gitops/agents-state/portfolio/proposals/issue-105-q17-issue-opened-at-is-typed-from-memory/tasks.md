# Tasks: issue-105-q17-issue-opened-at-is-typed-from-memory

- [ ] 1. Correct the three wrong `issue_opened_at` values in
  `src/content/journal/`, each to its issue's `created_at`, single-quoted,
  changing nothing else in those files:
  `2026-09-13-q13-link-hit-areas-titles-indexing-and-share-image-alt.md` ->
  `issue_opened_at: '2026-09-13T10:35:00Z'`;
  `2026-09-13-q14-ten-projects-and-service-links.md` ->
  `issue_opened_at: '2026-09-13T10:39:03Z'`;
  `2026-09-13-q16-compact-segmented-language-and-theme.md` ->
  `issue_opened_at: '2026-09-13T21:26:33Z'`.
  — DoD: `git diff` on those three files shows exactly three changed lines;
  `npm test` and `npm run build` pass; `/colophon/` renders lead times `1.1`,
  `2.1` and `0.9` for those rows instead of `0.9`, `0.7` and `8.3`.

- [ ] 2. Add the pure helpers to `src/lib/journal.ts`, keeping the module
  import-free: `issueRef(url)` returning `{ repo, number }` for a
  `https://github.com/<owner>/<repo>/issues/<n>` URL and `null` otherwise;
  `issueStampOrderProblems(entries)` which groups entries by `issueRef().repo`,
  sorts each group by issue number, and returns one `JournalProblem`-shaped
  item per adjacent pair whose `issue_opened_at` decreases, naming both entry
  ids, both issue numbers and both ISO instants; `checkIssueStampOrder(entries)`
  which throws `Journal validation failed:` with the aggregated list, mirroring
  `checkJournalCollection()`. Accept `Date | string` stamps and skip entries
  whose URL does not parse. — DoD: functions exported with doc comments in the
  module's existing style; equal instants produce no problem; `node --test`
  green.

- [ ] 3. Wire the check into `journalLoader()` in `src/content.config.ts`
  (depends on 2): call `checkIssueStampOrder(...)` immediately after the
  existing `checkJournalCollection(...)` call, passing `id`, `data.issue` and
  `data.issue_opened_at` from `ctx.store.entries()`, and widen the entry type
  the loader casts to. — DoD: `astro sync`, `astro check` and `astro build` all
  run the check; the real collection passes after task 1.

- [ ] 4. Resolve `issue_opened_at` from the API in `scripts/close-journal.mjs`
  (independent of 2-3): add the pure helper `entryIssueRef(data)` returning
  `{ owner, repo, number }`; add `getIssue(number)` to `createGitHubClient()`;
  in `run()`, after the implementation PR is verified, resolve the issue's
  `created_at` only when `entryIssueRef()` names `mctlhq/portfolio`, add it to
  the `evidence` object, and log both instants when it differs from the
  recorded value. Log an explicit non-resolution and keep the recorded value
  when the issue is in another repository or the lookup returns null; never
  throw on it. — DoD: closure of a portfolio entry writes the resolved value;
  closure of a cross-repo entry completes unchanged with a logged skip.

- [ ] 5. Extend the closure write surface (depends on 4): add
  `issue_opened_at` to `CLOSURE_FIELDS` and a `setFrontmatterLine(lines,
  'issue_opened_at', "'" + evidence.issue_opened_at + "'", ['proposal_slug'])`
  call in `applyClosure()`. Update the module header comment and
  `applyClosure()`'s doc comment, both of which enumerate the four fields
  written today. — DoD: `closureDiffProblems()` still reports any change
  outside the six allowed keys and any body change; `--dry-run` still writes
  nothing.

- [ ] 6. Update `docs/journal.md` (independent): change the closure bullet's
  "It records `pr`, `merged_at`, `release` and `released_at`" to "It records
  `issue_opened_at`, `pr`, `merged_at`, `release` and `released_at`", and add
  this bullet immediately after the first bullet, verbatim:

  ```
  - `issue_opened_at` is the `created_at` of the GitHub issue the entry's
    `issue` field names, copied verbatim to the second from the proposal, which
    inlines it; the closure workflow re-resolves it against the GitHub API for
    a `mctlhq/portfolio` issue, and the journal loader requires entries whose
    issues share a repository to carry stamps that increase with their issue
    numbers.
  ```

  — DoD: the file states what the field means and where the value comes from;
  no other line changes.

- [ ] 7. Move the byte-for-byte pin with the doc (depends on 6): update
  `EXPECTED_DOCS` in `test/journal-workflow.test.ts` so the "matches section F
  byte for byte" test passes against the new text. — DoD: `node --test
  test/journal-workflow.test.ts` green.

- [ ] 8. Narrow the stale tap-target comment in `src/styles/site.css`
  (independent): replace the comment above the `.site-nav a, .site-footer a`
  rule with, verbatim:

  ```
  /* Tap targets: the navigation and footer links are at least 44px tall at any
   * viewport width, per the 360px acceptance criterion. This is not a
   * page-wide floor -- the standalone-link rule below is 24px, and the
   * header's .icon-toggle controls are a fixed 32px box -- and 24px is the
   * floor test/a11y.test.ts enforces for every selector in TARGET_SELECTORS. */
  ```

  — DoD: no comment in `site.css` claims a 44px floor for every interactive
  element; the rule's declarations are untouched; `npm test` green.

- [ ] 9. Create this cycle's journal entry,
  `src/content/journal/YYYY-MM-DD-q17-issue-opened-at-from-a-recorded-source.md`,
  with `service: portfolio`,
  `issue: https://github.com/mctlhq/portfolio/issues/105`,
  `proposal_slug: issue-105-q17-issue-opened-at-is-typed-from-memory`,
  `status: in_progress`, `visibility: public`, bilingual `title` and `decided`,
  `interventions: []`, and — copied, not derived —
  `issue_opened_at: '2026-09-13T22:07:31Z'`. — DoD: the entry passes the schema
  and both loader checks; its stamp equals issue #105's `created_at` to the
  second. Note: `checkJournalCollection()` rejects a second `in_progress`
  entry, so the previous cycle's entry must already be closed.

## Tests

- [ ] T1. `test/journal-status.test.ts`: `issueStampOrderProblems()` returns no
  problem for stamps increasing with issue number, none for equal instants,
  none for a decrease across two *different* repositories, none for an
  unparseable `issue` URL, and one problem naming both ids, both numbers and
  both instants for a decrease within one repository.
- [ ] T2. `test/journal-build.test.ts`: an `astro sync` fixture with two
  same-repository entries whose stamps decrease with issue number fails
  non-zero with a diagnostic naming both entries; a fixture where the decrease
  spans two repositories passes; and the existing "newer issue, ran first"
  fixture still passes, proving execution order is not constrained.
- [ ] T3. `test/journal-build.test.ts`: a mutation control in the style of the
  existing `checkJournalCollection` mutant — removing the
  `checkIssueStampOrder(...)` call from a copied `content.config.ts` lets the
  T2 negative fixture build, proving the loader call is what fails it.
- [ ] T4. `test/journal-closure.test.ts`: `makeFakeGithub()` gains an `issue`
  fixture and `getIssue()`; `run()` writes the resolved `created_at` into the
  closure content when it differs from the recorded value, and the captured
  `createOrUpdateBranchFile` content carries the corrected, single-quoted
  stamp.
- [ ] T5. `test/journal-closure.test.ts`: a cross-repository `issue` URL and a
  null `getIssue()` result each leave `issue_opened_at` untouched while the
  closure still completes; neither path throws.
- [ ] T6. `test/journal-closure.test.ts`: `closureDiffProblems()` still reports
  a problem for a frontmatter change outside the six `CLOSURE_FIELDS` and for a
  body change, and reports none for an `issue_opened_at`-only change.
- [ ] T7. `test/journal-workflow.test.ts`: a targeted assertion that
  `docs/journal.md` contains a sentence naming both `issue_opened_at` and the
  issue's `created_at`, so a future rewrite cannot drop the definition while
  keeping the byte-for-byte constant in sync.
- [ ] T8. `test/a11y.test.ts` (or `test/header.test.ts`, whichever the
  implementer finds cheaper): assert `src/styles/site.css` contains no comment
  claiming every interactive element is at least 44px, e.g. the stylesheet does
  not match `/every interactive element[\s\S]{0,80}44px/`.
- [ ] T9. Full `npm test` and `npm run build` pass with no network beyond
  `npm ci`; `scripts/check-links.mjs` still passes over `dist/`.

## Reviewer steps (not acceptance criteria)

- Add "the issue's `created_at`, verbatim" as item 6 of the issue contract in
  `AGENTS.md` — a human-edited file under ADR-0001's bootstrap boundary.
- Make the issue-investigator prompt in `mctlhq/mctl-agents` inline the issue's
  `created_at` in every proposal, so Layer 1 holds for cycles after this one.

## Rollback

Every change is a source-file edit in one PR with no migration, no generated
artifact and no deployment step, so `git revert` of the merge commit restores
the previous behaviour completely.

- Data only: reverting task 1 restores the three published lead times; nothing
  else depends on those values.
- Check only: if the loader check proves too strict for a case not foreseen
  here, delete the `checkIssueStampOrder(...)` call from `journalLoader()` (one
  statement) and the T2/T3 fixtures; the helpers can stay, unused and unit
  tested. The build goes green immediately.
- Closure only: if resolution misbehaves in a real run, remove
  `issue_opened_at` from `CLOSURE_FIELDS` and from `applyClosure()`; closure
  returns to writing the four fields it writes today, and a partially written
  closure branch is discarded by deleting `fix/journal-close-<n>`, which the
  next release recreates deterministically.
- The `docs/journal.md`, `EXPECTED_DOCS` and `site.css` comment changes carry
  no runtime behaviour and never need an urgent revert.
