# Tasks: issue-79-q11-every-cycle-s-journal-entry-is-born

- [ ] 1. Add the status helpers to `src/lib/journal.ts`, keeping the module
      import-free — DoD: exports `JournalStatus`, `isComplete(data)`,
      `statusCounts(entries)` returning `{ complete, in_progress, abandoned }`
      with all three keys present for an empty input, `isRealTimestamp(value)`
      (ISO shape plus a real instant), `journalEntryProblems(data)` (status
      evidence rules and nondecreasing lifecycle order over
      `issue_opened_at` → `proposal_approved_at` → `merged_at` →
      `released_at` → `deployed_at`, skipping absent stages, equal instants
      allowed) and `checkJournalCollection(entries)` (throws
      `Journal validation failed:` naming the ids when more than one entry is
      `in_progress`). No new imports appear in the file.

- [ ] 2. Make `leadTimeHours()` status-aware (depends on 1) — DoD: returns
      `null` unless `isComplete(entry)`; for complete entries the existing
      `deployed_at`-then-`released_at` precedence, unrounded hours, exact `0`
      for identical instants, and `RangeError` on a reversed pair or an
      unparseable value are unchanged; `cycleEndTimestamp`, `cycleTimestamp`,
      `byNewestFirst`, `interventionCount` and `totalInterventions` keep their
      current behaviour.

- [ ] 3. Enforce the lifecycle in the real journal schema in
      `src/content.config.ts` (depends on 1) — DoD: required
      `status: z.enum(['in_progress', 'complete', 'abandoned'])`; optional
      `abandoned_reason` with `en`/`ru` strings rejected when whitespace-only;
      `stamp` rejects an ISO-shaped string that denotes no real instant; a
      `.superRefine` maps `journalEntryProblems` onto `ctx.addIssue` with the
      offending field in `path`, so `complete` requires `pr`/`release`/
      `merged_at`/`released_at`, `in_progress` forbids `release`/
      `released_at`/`deployed_at`, `abandoned` requires `abandoned_reason` and
      forbids `merged_at`/`release`/`released_at`/`deployed_at` while allowing
      a known `pr`, `merged_at` requires `pr`, `abandoned_reason` implies
      `abandoned`, and timestamps are nondecreasing. `astro check` passes on
      the repository's own content.

- [ ] 4. Add `journalLoader()` to `src/content.config.ts` (depends on 1, 3) —
      DoD: mirrors `projectsLoader()`/`adrLoader()` (wrap the existing glob
      loader, `await base.load(ctx)`, then check `ctx.store.entries()`), calls
      `checkJournalCollection` over all entries including private ones, allows
      zero `in_progress`, adds no ordering or issue-age rule, and the
      collection's display sort is untouched.

- [ ] 5. Add the ten `ui` keys to `src/i18n/ui.ts` — DoD: `cycleColStatus`
      (`Status` / `Статус`), `journalStatusLabel` (`Status` / `Статус`),
      `statusComplete` (`complete` / `завершён`), `statusInProgress`
      (`in progress` / `в работе`), `statusAbandoned` (`abandoned` /
      `прерван`), `colophonTotalComplete` (`complete` / `завершённых`),
      `colophonTotalInProgress` (`in progress` / `в работе`),
      `colophonTotalAbandoned` (`abandoned` / `прерванных`),
      `leadTimeAbandoned` (`not measured: this cycle was abandoned` /
      `не измерено: этот цикл был прерван`), `journalAbandonedHeading`
      (`Why this cycle was abandoned` / `Почему этот цикл был прерван`), each
      character for character; `colophonTotalCycles`,
      `colophonTotalInterventions` and `leadTimeMissing` unchanged.

- [ ] 6. Add the Status column to `src/components/CycleTable.astro` (depends
      on 2, 5) — DoD: column order is Date, Service, Title, Status, Issue,
      Pull request, Release, Lead time (h), Interventions; the status cell
      renders the bilingual label through a status→`ui` map; the lead-time
      cell renders the number for `complete`, the em dash plus
      `.visually-hidden` `leadTimeMissing` for `in_progress` and
      `leadTimeAbandoned` for `abandoned`, keeping the `lead-time-missing`
      class; known PR links still render for in-progress rows; absent
      `pr`/`release` stay em dashes; no journal literal is introduced.

- [ ] 7. Add the Status row and abandonment block to
      `src/pages/colophon/journal/[...slug].astro` (depends on 2, 5) — DoD:
      `Status` is the first `dt`/`dd` pair in `dl.journal-meta`; the lead-time
      `dd` branches exactly as the table does; an abandoned entry renders a
      heading from `journalAbandonedHeading` and its bilingual reason
      paragraph under the list; private entries still get no page.

- [ ] 8. Render the five computed totals in `src/pages/colophon/index.astro`
      (depends on 1, 5) — DoD: `statusCounts` is computed from the same
      public-only collection as the table and `totalInterventions`; spans
      carry `data-cycle-count`, `data-complete-count`,
      `data-in-progress-count`, `data-abandoned-count`,
      `data-intervention-count`, all five rendered including zeros; the
      sentence takes `:`, `,` and `;` from the template and every word from
      `ui`; no number literal is added (`node scripts/check-no-metrics.mjs`
      passes).

- [ ] 9. Update `src/styles/site.css` (depends on 6, 7) — DoD: the
      `@media (max-width: 599px)` block hides `table.cycles`
      `th/td:nth-child(2)` and `th/td:nth-child(6)`; the `.table-scroll`
      region, hint and `::after` fade are unchanged; a `.journal-abandoned`
      rule styles the reason paragraph; no `animation`/`transition` is
      introduced.

- [ ] 10. Backfill the 22 historical entries in `src/content/journal/`
      (depends on 3) — DoD: every file carries `status: complete`; the eight
      already-complete entries (issues 281, 330, 3, 4, 8, 5, 6, 7) are
      otherwise unchanged; the fourteen open entries receive exactly the `pr`,
      `merged_at`, `release`, `released_at` values from the table in
      `requirements.md` section D, timestamps single-quoted;
      `2026-09-11-metrics-provenance-and-no-analytics.md` gains
      `proposal_approved_at: '2026-09-11T11:15:37Z'` and
      `2026-09-12-symlink-safe-check-no-metrics-entry-guard.md` gains
      `proposal_approved_at: '2026-09-12T19:03:02Z'`; no `deployed_at` is
      added anywhere; the two cross-repository entries keep their existing
      evidence including `deployed_at`.

- [ ] 11. Create this cycle's own entry (depends on 3, 4, 10) — DoD:
      `src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md`
      with `service: portfolio`,
      `issue: https://github.com/mctlhq/portfolio/issues/79`,
      `proposal_slug: issue-79-q11-every-cycle-s-journal-entry-is-born`,
      `visibility: public`, `status: in_progress`,
      `issue_opened_at: '2026-09-13T05:29:22Z'`, bilingual `title` and
      `decided`, `interventions: []`, and no `pr`, `merged_at`, `release`,
      `released_at` or `deployed_at`. The collection now has exactly one
      `in_progress` entry and 22 complete ones.

- [ ] 12. Write `scripts/close-journal.mjs` (depends on 1) — DoD: exported
      pure helpers (`parseFrontmatter`, `selectClosableEntry`,
      `earliestContainingRelease`, `applyClosure`, `closureDiffProblems`,
      `branchName`) plus `run({ tag, github, repoRoot, dryRun, log })` with
      every GitHub call behind an injectable client; resolves the tag to a
      published stable release; validates a recorded `pr` or identifies the
      unique merged PR that introduced the entry file and verifies its issue
      association, never using a release PR; verifies the merge commit is an
      ancestor of the tag's commit rather than comparing timestamps; picks the
      earliest containing stable release and fails with diagnostics on a tie;
      updates only `service: portfolio` entries and matches against current
      `main`; sets `pr`, `merged_at`, `release`, `released_at` (always R, never
      R2) and `status: complete`; never sets `deployed_at`; `--dry-run`
      reports the match and diff with no writes; a top-level
      `if (isEntryPoint()) { await main(); }` in the hybrid
      `import.meta.main` / `realpathSync(process.argv[1])` form required by
      `test/entry-point.test.ts`.

- [ ] 13. Make closure idempotent and conflict-safe (depends on 12) — DoD:
      deterministic branch `fix/journal-close-<issue-number>` and one PR per
      entry; commit and PR title `fix(journal): close cycle <issue-number>`;
      an unchanged intended content reuses the existing PR with no new
      commit; an already-complete entry, a merge not contained in the release,
      or no eligible in-progress portfolio entry exits 0 as a no-op; a closure
      PR or `main` carrying conflicting evidence or unrelated edits reports the
      conflict and exits non-zero without writing; API failure, ambiguity and
      invalid evidence fail visibly with the entry, field and values named;
      the diff touches only `status`, `pr`, `merged_at`, `release`,
      `released_at` of the one entry, and no journal entry or intervention is
      manufactured.

- [ ] 14. Add `.github/workflows/journal-closure.yml` (depends on 12, 13) —
      DoD: `on: release: types: [published]` with a draft/prerelease filter,
      plus `workflow_dispatch` with a required release-tag input; top-level
      `permissions: contents: read`; `concurrency` group serializing runs for
      this repository; checkout of `main` with full history; token from
      `actions/create-github-app-token` pinned to the same SHA as
      `release-please.yml`, `owner: mctlhq`, `repositories: portfolio`,
      contents and pull-requests write only; runs
      `node scripts/close-journal.mjs --tag "$TAG"` with the event tag or the
      dispatch input; a header comment links `docs/journal.md`; the reserved
      workflows and `AGENTS.md` are untouched.

- [ ] 15. Write `docs/journal.md` and link it (depends on 14) — DoD: the file
      matches the text in `requirements.md` section F character for
      character; `README.md` gains one concise link to it; no other README
      change.

- [ ] 16. Wire the suite and the gates (depends on all above) — DoD: the four
      new test files are listed explicitly in the enumerated `test` script in
      `package.json`; `npm test` invokes Astro directly for integration builds
      and never `npm run build`; `npm run vendor && npm test`, `npm run build`
      and `node scripts/check-links.mjs` all pass locally.

## Tests

- [ ] T1. `test/journal-status.test.ts` — `statusCounts` (empty input returns
      all three zero keys; mixed statuses; public-only counting),
      `isComplete`, status-aware `leadTimeHours` (null for in-progress and
      abandoned even when timestamps exist, zero lead time renders `0.0`,
      `deployed_at` over `released_at`, `RangeError` cases),
      `journalEntryProblems` per rule, `checkJournalCollection` for zero, one
      and two open entries.

- [ ] T2. `test/journal-status.test.ts` (content assertions) — every file in
      `src/content/journal/` carries a `status`; every `complete` entry
      carries `pr`, `release`, `merged_at`, `released_at`; at most one entry is
      `in_progress`; all fourteen backfill rows and both approval stamps match
      verbatim; no portfolio entry has `deployed_at`; the mctl-api #281 and
      mctl-agents #330 entries keep their existing evidence. Migration
      checkpoint numbers are asserted as "22 complete, 1 in progress, 0
      abandoned" only through the invariants above, not as a hard-coded total
      that a future cycle must edit.

- [ ] T3. `test/journal-build.test.ts` (schema) — isolated Astro builds over
      fixture content trees prove the real schema: valid `in_progress`,
      `complete` and `abandoned` entries build; each missing required field,
      each forbidden field, a whitespace-only abandonment reason, an invalid
      date and a reversed timestamp pair fail, and the assertion names the
      entry, the field and the violation and rules out an unrelated build
      error.

- [ ] T4. `test/journal-build.test.ts` (loader) — two open entries fail,
      including a public/private pair; zero open entries build; one open entry
      whose issue is older than a completed entry's builds. A variant fixture
      with the `journalLoader` guard removed builds the two-open-entry case,
      committing the mutation evidence that the guard is what fails T4's
      negative case.

- [ ] T5. `test/journal-build.test.ts` (markup) — built HTML from a mixed
      fixture (complete, in-progress, abandoned, private) contains the five
      `data-*` totals including zero values, all status labels, the table
      Status column header, the Status row first in the detail
      `journal-meta`, `leadTimeMissing` for the in-progress lead time and
      `leadTimeAbandoned` for the abandoned one in both views, the in-progress
      entry's PR link, and no row or detail page for the private entry.

- [ ] T6. `test/journal-closure.test.ts` — offline fixtures for
      `scripts/close-journal.mjs`: correct entry/implementation-PR/release
      association; a merge not contained in a candidate release;
      earliest-containing-release selection; duplicate deliveries; an
      already-completed entry; missing, draft and prerelease releases; API
      failure; ambiguous PR match and ambiguous release tie; conflicting
      evidence and unrelated edits on the branch; dry run. Every failure and
      dry-run case asserts the fake client recorded no write call.

- [ ] T7. `test/journal-closure.test.ts` (sequence) — R → closure PR → R2 →
      no-op over one fake repository state: the closure diff changes only
      `status`, `pr`, `merged_at`, `release`, `released_at`; `release` stays R
      after R2; no extra journal entry or intervention is created; a retry
      reuses the same branch and PR with no additional commit.

- [ ] T8. `test/journal-workflow.test.ts` — the workflow's `release:
      published` trigger, draft/prerelease filter, required `workflow_dispatch`
      tag input, concurrency group, SHA-pinned App token scoped to
      `portfolio`, `node scripts/close-journal.mjs` invocation and
      `docs/journal.md` link; `docs/journal.md` equals the exact expected
      text; `README.md` links it.

- [ ] T9. Updated `test/a11y.test.ts` — the narrow-viewport rule hides
      `table.cycles` columns 2 and 6 (was 2 and 5), and the scroll affordance
      assertions still pass.

- [ ] T10. Updated `test/journal.test.ts` and `test/colophon.test.ts` —
      existing timestamp fixtures carry an explicit `status`; the required
      journal frontmatter key list includes `status`; the UI reference
      assertions cover the new status and lead-time branches.

- [ ] T11. Updated `test/ui.test.ts` — the ten new keys carry exactly the
      EN/RU values in `requirements.md` section C, and the three existing keys
      are unchanged.

## Rollback

Every change is confined to one implementation PR and, later, one closure PR.

- Before merge: close the implementation PR. Nothing else is affected.
- After merge, before release R: revert the merge commit on `main`
  (`git revert -m 1 <merge-sha>`) through a normal PR. The journal files
  return to their optional-field form, `status` disappears from the schema,
  and the site builds exactly as it does at `41dc0238`.
- After release R, if the closure automation misbehaves: disable it without
  reverting the site changes by deleting `.github/workflows/journal-closure.yml`
  (or reverting that file alone) in a `fix:` PR. The schema, backfill and UI
  stay; closure falls back to a hand-written PR that sets the same five
  fields, which `docs/journal.md`'s Recovery section describes.
- If a closure PR carries wrong evidence: close it without merging and delete
  its deterministic branch. Nothing was written to `main`, the entry stays
  `in_progress`, and a corrected manual dispatch with the original stable tag
  reruns the match.
- The backfilled values are historical facts recorded in `requirements.md`
  section D and asserted by T2, so a bad edit to them is recoverable from the
  proposal alone.
