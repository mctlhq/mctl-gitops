# Q4: Colophon tables fit or visibly scroll, timestamps are formatted, lead time is computed

## Context

The colophon page (`src/pages/colophon/index.astro`) renders two tables inside a
768px content column (`--content-max` in `src/styles/site.css`): the eight-column
`table.cycles` (`src/components/CycleTable.astro`) and the four-column
`table.adr-index`. Both are styled with `white-space: nowrap` on the whole table,
so at any viewport the rightmost columns (`Release`, `Lead time (h)`,
`Interventions`) and the ADR `Date` are pushed out of the 768px measure. The
`.table-scroll` wrapper does scroll and is keyboard-focusable (`role="region"`,
`tabindex="0"`), but nothing tells a sighted reader that content continues past
the right edge: no shadow, no hint, and the native scrollbar is hidden on macOS
and on mobile.

Two data defects sit next to the layout one. The journal entry page
(`src/pages/colophon/journal/[...slug].astro`) prints raw machine timestamps via
`isoStamp()` — `2026-09-11T05:20:48Z` — with no `<time>` element, no localised
label, and no elapsed interval between consecutive steps, so the shape of a cycle
can only be recovered by subtracting ISO strings by hand. And `leadTimeHours()`
in `src/lib/journal.ts` derives lead time from `deployed_at` alone; only two of
the twelve public journal entries carry `deployed_at`, so the `Lead time (h)`
column renders an em dash for ten of twelve cycles even though six more of them
carry both `issue_opened_at` and `released_at`. AGENTS.md already states the rule
this violates: "Lead time and the number of interventions are computed at build
time, never written by hand" — the derivation exists, it is simply reading the
wrong end timestamp.

## User stories

- AS a reader on a 1440px desktop I WANT every column of the cycle table visible
  in one view SO THAT I can compare lead times across cycles without dragging a
  hidden scrollbar.
- AS a reader on a 360px phone I WANT the table to announce that it scrolls
  sideways, and no heading cut off mid-word, SO THAT I know the data continues
  past the edge instead of assuming it is missing.
- AS a Russian-speaking reader I WANT journal timestamps in my own language with
  the machine value preserved SO THAT I can read the cycle history and still copy
  an exact instant.
- AS a reader auditing the DevLoop I WANT the elapsed time between consecutive
  steps shown SO THAT I can see where a cycle waited without arithmetic.
- AS a reader checking the loop's honesty I WANT lead time computed from the
  recorded timestamps for every cycle that has them SO THAT an em dash means
  "not recorded" rather than "not implemented".

## Acceptance criteria (EARS)

**Table fit and scroll affordance**

- WHEN the colophon page is rendered at the 768px content measure THE SYSTEM
  SHALL allow the textual cells of `table.cycles` (`Cycle` title link) and
  `table.adr-index` (`Title` link) to wrap onto more than one line, so that all
  eight cycle columns and all four ADR columns are readable without horizontal
  scrolling at a 1440px viewport.
- WHILE any cell holds a date, a release tag, a GitHub reference, a service name
  or a numeric value THE SYSTEM SHALL keep `white-space: nowrap` on that cell, so
  that `2026-09-11`, `0.1.4`, `#28`, `mctl-agents` and `0.7` never break across
  lines.
- WHILE a column heading is rendered at any viewport width THE SYSTEM SHALL allow
  it to wrap only at a space (`overflow-wrap: normal`, `word-break: normal`,
  `hyphens: manual`), so that no heading — `Pull request`, `Lead time (h)`,
  `Interventions`, `Вмешательства`, `Время цикла (ч)` — is broken or clipped
  mid-word at 360px.
- WHEN either table is rendered THE SYSTEM SHALL render a visible bilingual hint
  line directly under the table caption reading exactly, in English, `This table
  scrolls sideways on a narrow screen.` and, in Russian, `На узком экране эта
  таблица прокручивается вбок.`
- WHILE the viewport is at or below 599px THE SYSTEM SHALL additionally render a
  static gradient affordance at the right edge of the `.table-scroll` region,
  drawn with CSS only, with `pointer-events: none`, using no `animation` or
  `transition` property.
- WHILE the viewport is at or below 599px THE SYSTEM SHALL hide the `Service` and
  `Pull request` columns of `table.cycles` (heading and cells alike) with
  `display: none`, so the remaining six columns fit a phone; both values stay
  reachable on the cycle's own journal page.
- WHILE the page is rendered at any width THE SYSTEM SHALL keep the
  `.table-scroll` wrapper's `role="region"`, `tabindex="0"`, `aria-label` and
  `:focus-visible` outline exactly as they are today.

**Timestamps and intervals**

- WHEN a step of the journal timeline is rendered THE SYSTEM SHALL emit
  `<time datetime="…">` carrying the machine-readable UTC value in the existing
  `isoStamp()` form (e.g. `2026-09-11T05:20:48Z`).
- WHEN a step of the journal timeline is rendered THE SYSTEM SHALL render inside
  that `<time>` element a bilingual label pair — English `11 Sep, 05:20 UTC`,
  Russian `11 сен, 05:20 UTC` — through the existing `<Lang>` component, so the
  `.l.en` / `.l.ru` parity check in `scripts/check-dist.mjs` still balances.
- WHILE any timestamp is rendered THE SYSTEM SHALL express it in UTC and SHALL
  NOT convert it to a local time zone.
- WHEN a timeline step other than the first is rendered THE SYSTEM SHALL render
  the elapsed interval since the previous step as a bilingual pair in the form
  `+6 h 32 min` (English) / `+6 ч 32 мин` (Russian).
- IF the elapsed interval is under one hour THEN THE SYSTEM SHALL render only the
  minute part, `+44 min` / `+44 мин`, and IF it is zero THEN THE SYSTEM SHALL
  render `+0 min` / `+0 мин`.
- IF the elapsed interval is 24 hours or more THEN THE SYSTEM SHALL still express
  it in whole hours and minutes (e.g. `+32 h 9 min`), never in days, so the unit
  matches the `Lead time (h)` column.
- IF a later timeline timestamp precedes an earlier one THEN THE SYSTEM SHALL
  throw a `RangeError` at build time, matching the existing behaviour of
  `leadTimeHours()` for a `deployed_at` that precedes `issue_opened_at`.

**Lead time**

- WHEN `leadTimeHours()` is called for an entry THE SYSTEM SHALL take the cycle's
  end timestamp as `deployed_at` when present, otherwise `released_at`, treating
  `undefined`, `null` and `''` as absent in both cases.
- IF an entry has an end timestamp and `issue_opened_at` THEN THE SYSTEM SHALL
  return the difference in unrounded hours, including `0` when the two instants
  are identical.
- IF an entry has neither `deployed_at` nor `released_at` THEN THE SYSTEM SHALL
  return `null`.
- WHEN a `null` lead time is rendered in `table.cycles` or in the journal page's
  `journal-meta` list THE SYSTEM SHALL render the em dash inside
  `<span class="lead-time-missing">` styled with `var(--surface-fg-muted)`, and
  SHALL accompany it with a visually hidden bilingual explanation reading exactly,
  in English, `not measured: this cycle has no end timestamp yet` and, in
  Russian, `не измерено: у этого цикла ещё нет конечной отметки времени`, so a
  missing value is visibly and audibly distinct from a computed `0.0`.
- WHILE a lead time of zero is rendered THE SYSTEM SHALL render `0.0` with no
  `lead-time-missing` class and no hidden explanation.

**Build gates**

- WHILE `node scripts/check-no-metrics.mjs` runs THE SYSTEM SHALL report OK: no
  literal of two or more digits is introduced into `src/pages`, `src/components`
  or `src/layouts`, and no `ALLOW` entry is added to that script.
- WHEN `npm test` runs THE SYSTEM SHALL pass, including a unit test of the lead
  time computation covering a `deployed_at` entry, a `released_at`-only entry, an
  entry missing both timestamps, and a same-instant entry.
- WHEN `npm run build` runs THE SYSTEM SHALL pass, with `scripts/check-dist.mjs`
  still finding equal `class="l en"` and `class="l ru"` counts on every changed
  page and no `.js` file anywhere under `dist/`.
- WHILE `test/a11y.test.ts` runs THE SYSTEM SHALL keep `src/styles/site.css` free
  of any `animation` or `transition` declaration.

## Out of scope

- The CSP hash quoting and the header guards (`security-headers.conf`,
  `scripts/csp-hash.mjs`).
- The content link colour. The table links are blue-accented today; this cycle
  must not restyle `main a`, `.project-links a` or any `:visited` pin.
- The `/work/` page.
- Navigation state, the skip-link, `role="group"`, toggle spacing and
  default-open `<details>` blocks.
- `og:image`, font preload, `Cache-Control`, the DevLoop diagram in
  `src/components/CycleDiagram.astro`, and the hero name wrap.
- The `at` stamps of the intervention records on the journal page
  (`.intervention-at`). They stay in their present `isoStamp()` rendering: the
  records are quoted verbatim in English by design (`ui.journalInterventionsNote`),
  and the issue's requirement names the timeline.
- Widening `--content-max` or making either table full-bleed.
- Adding any client-side JavaScript. The scroll affordance is CSS-only.
- Changing `src/content/journal/*.md` frontmatter. No timestamp is added,
  corrected or removed by this cycle.

## Open questions

- The issue says `Lead time` is empty for nine of twelve cycles; a direct read of
  `src/content/journal/` shows twelve public entries, of which two carry
  `deployed_at`, so ten render the em dash today. After this change eight are
  computed (two from `deployed_at`, six from `released_at`) and four remain a
  dash because they carry neither end timestamp
  (`2026-09-11-hero-name-in-the-reader-s-script`,
  `2026-09-11-metrics-provenance-and-no-analytics`,
  `2026-09-11-p8-production-hardening-accessibility-wc`,
  `2026-09-11-production-cutover`). Proceeding on the count in the tree, not the
  count in the issue; the criterion "populated for every cycle that has both
  timestamps" is what is implemented.
- The issue's example interval `+6 h 32 min` shows no day unit. Several real
  gaps exceed 24 hours (e.g. `2026-09-11-approach-page`, issue opened
  `2026-09-10T22:48:15Z`, approved `2026-09-11T06:57:12Z`). Proceeding with whole
  hours and minutes only, never days, so the unit agrees with the `Lead time (h)`
  column.
- The issue offers "hide the secondary columns" or "render a card list" below
  ~600px. Proceeding with hiding `Service` and `Pull request`: a card list would
  duplicate every row's markup and its bilingual pairs, and both values remain
  one click away on the cycle's own journal page.
- The issue does not supply the wording for the scroll hint or for the
  missing-lead-time explanation. This proposal fixes both strings, in both
  languages, character for character, as the copy contract requires.
