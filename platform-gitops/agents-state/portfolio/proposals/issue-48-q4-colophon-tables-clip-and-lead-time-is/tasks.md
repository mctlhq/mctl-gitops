# Tasks: issue-48-q4-colophon-tables-clip-and-lead-time-is

- [ ] 1. Add `cycleEndTimestamp(entry)` to `src/lib/journal.ts` and rewrite
  `leadTimeHours` over it — DoD: a private `present(v)` helper collapses the
  `undefined | null | ''` check; `cycleEndTimestamp` returns the `deployed_at`
  date when present, else the `released_at` date when present, else `null`;
  `leadTimeHours` returns `null` for a `null` end, the unrounded hour difference
  otherwise, and still throws `RangeError` when the end precedes
  `issue_opened_at`; the module's import list is still empty; every existing
  assertion in `test/journal.test.ts` passes unchanged.
- [ ] 2. Add `formatStamp(value, months)` to `src/lib/journal.ts` (depends on 1)
  — DoD: returns `'11 Sep, 05:20 UTC'` for `('2026-09-11T05:20:48Z', ui.monthAbbrev.en)`
  and `'11 сен, 05:20 UTC'` for the `ru` array; day not zero-padded, hour and
  minute padded to two characters, all values read through the `getUTC*`
  accessors so no local zone can leak in; the `UTC` suffix is a literal and is
  not translated.
- [ ] 3. Add `intervalMinutes(from, to)` and `formatInterval(from, to, units)` to
  `src/lib/journal.ts` (depends on 1) — DoD: `intervalMinutes` floors to whole
  minutes and throws `RangeError` when `to` precedes `from`; `formatInterval`
  returns `'+6 h 32 min'` / `'+6 ч 32 мин'` when the hour part is non-zero,
  `'+44 min'` when it is zero, `'+0 min'` for an identical pair, and `'+32 h 9 min'`
  for a gap over 24 hours — hours are never rolled into days.
- [ ] 4. Add the five new keys to `src/i18n/ui.ts` (independent of 1-3) — DoD:
  `tableScrollHint`, `leadTimeMissing`, `unitHour`, `unitMinute` and
  `monthAbbrev` are present with exactly the copy fixed in `design.md`, section
  2, character for character in both languages; `monthAbbrev.en` and
  `monthAbbrev.ru` each have twelve items; `npm test`'s `test/ui.test.ts` passes.
- [ ] 5. Render the lead-time cell through one shared branch in
  `src/components/CycleTable.astro` and `src/pages/colophon/journal/[...slug].astro`
  (depends on 1, 4) — DoD: a `null` lead time renders
  `<span class="lead-time-missing">—</span>` followed by
  `<span class="visually-hidden"><Lang en={ui.leadTimeMissing.en} ru={ui.leadTimeMissing.ru} /></span>`;
  a computed value renders `formatLeadTime(hours)` with neither; `0` renders
  `0.0`.
- [ ] 6. Rewrite the journal timeline in
  `src/pages/colophon/journal/[...slug].astro` (depends on 2, 3, 4) — DoD: the
  frontmatter fence builds a `steps` array carrying `iso`, `en`, `ru` and, for
  every step after the first, `interval.en` / `interval.ru`; each `<li>` renders
  the label pair, then `<time datetime={step.iso}><Lang en ru /></time>`, then
  `<span class="step-interval"><Lang en ru /></span>` when an interval exists; no
  raw ISO string is printed as visible text in the timeline; the intervention
  records' `.intervention-at` stamps are left exactly as they are.
- [ ] 7. Add the bilingual hint line to both tables (depends on 4) — DoD:
  `<p class="table-hint"><Lang en={ui.tableScrollHint.en} ru={ui.tableScrollHint.ru} /></p>`
  renders once under the cycle table (from `src/components/CycleTable.astro`) and
  once under the ADR table (from `src/pages/colophon/index.astro`), as a sibling
  of the `<table>` and not inside it; `data-cycle-row`, `data-cycle-count` and
  `data-intervention-count` are untouched.
- [ ] 8. Replace the table-wide `nowrap` with per-column rules in
  `src/styles/site.css` (independent of 1-7) — DoD: the shared
  `table.cycles, table.adr-index` block no longer declares `white-space: nowrap`;
  `th` in both tables declares `white-space: normal; overflow-wrap: normal;
  word-break: normal; hyphens: manual`; `white-space: nowrap` is declared for
  `table.cycles td:nth-child(1|2|4|5|6|7|8)` and
  `table.adr-index td:nth-child(1|3|4)`; only the two title columns wrap.
- [ ] 9. Add the scroll affordance and the narrow-width column hiding to
  `src/styles/site.css` (depends on 8) — DoD: `.table-scroll` gains
  `position: relative`; a `@media (max-width: 599px)` block adds a sticky
  `.table-scroll::after` right-edge gradient with `pointer-events: none` and
  hides `table.cycles` columns 2 and 5 (heading and cells) with `display: none`;
  `.table-hint`, `.lead-time-missing` and `.step-interval` are styled with
  `var(--surface-fg-muted)`; the file still contains no `animation` and no
  `transition` declaration and introduces no new colour literal.
- [ ] 10. Run the full gate (depends on 1-9) — DoD: `node scripts/check-no-metrics.mjs`
  prints OK with no new `ALLOW` entry added to the script; `npm test` green;
  `npm run build` green including `scripts/check-dist.mjs` (equal `class="l en"`
  / `class="l ru"` counts on `dist/colophon/index.html` and every
  `dist/colophon/journal/*/index.html`, no `.js` under `dist/`); `npm run check`
  (`astro sync && astro check`) reports no new error.

## Tests

- [ ] T1. `test/journal.test.ts`: `leadTimeHours` falls back to `released_at`
  when `deployed_at` is absent, `null` or `''`, and prefers `deployed_at` when
  both are present and disagree.
- [ ] T2. `test/journal.test.ts`: `leadTimeHours` returns `null` for an entry
  carrying neither `deployed_at` nor `released_at` (the missing-timestamp case
  named in the issue), and `formatLeadTime` of that result is the em dash.
- [ ] T3. `test/journal.test.ts`: `leadTimeHours` returns exactly `0` when
  `issue_opened_at` and the end timestamp are the same instant (the same-instant
  case named in the issue), and `formatLeadTime(0) === '0.0'`, asserted to be
  different from the missing rendering.
- [ ] T4. `test/journal.test.ts`: `formatStamp` renders
  `'2026-09-11T05:20:48Z'` as `'11 Sep, 05:20 UTC'` with an English month array
  and `'11 сен, 05:20 UTC'` with a Russian one; a `Date` and its ISO string give
  the same output; a timestamp with a non-`Z` offset (e.g. `+02:00`) renders its
  UTC wall clock, not the offset one.
- [ ] T5. `test/journal.test.ts`: `formatInterval` renders an hours-and-minutes
  gap, a minutes-only gap, a zero gap as `'+0 min'`, a gap over 24 hours in whole
  hours, and throws `RangeError` on a reversed pair.
- [ ] T6. `test/colophon.test.ts`: `src/pages/colophon/journal/[...slug].astro`
  contains `<time datetime=`, calls `formatStamp` and `formatInterval`, and no
  longer prints `isoStamp(row.value` as visible timeline text.
- [ ] T7. `test/colophon.test.ts`: `src/components/CycleTable.astro` and
  `src/pages/colophon/index.astro` each reference `ui.tableScrollHint`, and both
  the table component and the journal route reference `ui.leadTimeMissing` and
  `lead-time-missing`.
- [ ] T8. `test/a11y.test.ts` (or `test/colophon.test.ts`, whichever already
  reads `site.css`): the shared `table.cycles, table.adr-index` block declares no
  `white-space: nowrap`; a `nowrap` rule exists for `table.cycles td:nth-child(1)`
  and for `table.adr-index td:nth-child(4)`; the `th` rule declares
  `overflow-wrap: normal` and `word-break: normal`; a `@media (max-width: 599px)`
  block hides `table.cycles` columns 2 and 5 and declares the `::after`
  affordance. The existing no-`animation`/no-`transition` assertion must still
  pass.
- [ ] T9. `test/ui.test.ts` (existing, no edit): passes with the five new keys,
  proving `monthAbbrev.en` and `monthAbbrev.ru` are twelve items each.
- [ ] T10. Reviewer step, not an acceptance criterion: open `/colophon/` at
  1440px and confirm all eight columns read without horizontal scrolling and no
  ADR date is clipped; open at 360px and confirm no heading is broken mid-word
  and the affordance is visible; tab to each `.table-scroll` region and confirm
  the focus ring still shows.

## Rollback

Every change is source-only, in four files plus the two test files; there is no
migration, no content edit and no platform state. To roll back, revert the merge
commit on `main` and let release-please cut the next patch, or — if the site is
already deployed — roll the service back to the previous image tag with
`mctl_rollback_service` (team `labs`, service `portfolio`), which is the path the
2026-09-11 production-cutover cycle already exercised. Partial rollback is safe
too, because the three concerns are independent: reverting only the
`src/styles/site.css` hunks restores today's `nowrap` clipping while keeping the
computed lead time, and reverting only the `src/lib/journal.ts`
`cycleEndTimestamp` hunk restores the `deployed_at`-only derivation while keeping
the table fix. `public/styles/site.css` is regenerated by `npm run vendor` during
`prebuild`, so it needs no separate revert.
