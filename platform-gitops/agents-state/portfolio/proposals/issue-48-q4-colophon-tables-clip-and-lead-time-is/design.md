# Design: issue-48-q4-colophon-tables-clip-and-lead-time-is

## Current state

**The tables.** `src/pages/colophon/index.astro` renders three sections; the
second mounts `src/components/CycleTable.astro`, the third an inline
`table.adr-index`. Both tables sit inside `<div class="table-scroll"
role="region" tabindex="0" aria-label="…">`. `src/styles/site.css` styles them
together:

```css
table.cycles,
table.adr-index {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-display);
  font-size: var(--mctl-typography-font-size-sm);
  white-space: nowrap;      /* line 384 -- the clipping cause */
}
```

`--content-max: 768px` (line 38) caps `main`, so the eight `nowrap` columns
overflow at every viewport; `.table-scroll { overflow-x: auto }` (line 370) makes
the overflow reachable but invisible. `table.cycles td:nth-child(1|7|8)` already
carries `font-variant-numeric: tabular-nums`, so per-column selectors are the
established idiom in this file. `.visually-hidden` already exists (line 211) and
is used by `src/components/Details.astro`.

**The journal page.** `src/pages/colophon/journal/[...slug].astro` builds a
`timeline` array of `{ label, value }` from the five optional frontmatter stamps,
filters out absent ones, and renders each as
`<Lang …/>: {isoStamp(row.value)}` — plain text, no `<time>`, no interval, no
localisation. Interventions render `isoStamp(item.at)` inside
`<p class="intervention-at">`.

**The library.** `src/lib/journal.ts` is deliberately import-free (header comment:
"Zero-import helper module … so `test/journal.test.ts` can exercise the real
logic" under plain `node --test`). It exports `toDate` (private),
`leadTimeHours`, `interventionCount`, `cycleTimestamp`, `byNewestFirst`,
`isoDate`, `isoStamp`, `formatLeadTime`, `totalInterventions`, `githubRef`.
`leadTimeHours` reads `deployed_at` only:

```ts
const { deployed_at: deployedAt } = entry;
if (deployedAt === undefined || deployedAt === null || deployedAt === '') return null;
```

`cycleTimestamp`, in the same file, already models the "latest stage present"
idea (`deployed_at ?? released_at ?? merged_at ?? proposal_approved_at ??
issue_opened_at`) — the fix reuses that shape, truncated to the two stages that
mean "the cycle ended".

**The data.** Twelve public entries in `src/content/journal/`. Two carry
`deployed_at`; six more carry `released_at` without `deployed_at`; four carry
neither. `src/content.config.ts` declares all five stamps as an optional `stamp`
(`z.string().refine(isoWithOffset).transform(s => new Date(s))`), so a present
value always reaches the template as a `Date`.

**The gates.** `scripts/check-no-metrics.mjs` walks `src/pages`,
`src/components`, `src/layouts` only — not `src/lib`, `src/i18n` or
`src/styles` — and fails on `\b[0-9]{2,}\b` unless a RULES classifier (ISO date,
year, CSS length, module specifier) or an `ALLOW` entry covers it; a stale ALLOW
entry is itself a failure. `test/a11y.test.ts` asserts site.css declares no
`animation` or `transition` anywhere. `scripts/check-dist.mjs`
(`checkColophonPages`) checks `data-cycle-count`, `data-intervention-count` and
`data-cycle-row` counts against an independent scan of the journal files, and
`checkLangParity` requires equal `class="l en"` / `class="l ru"` counts per HTML
file. `test/ui.test.ts` requires every `ui` value to be an `{ en, ru }` pair of
the same kind, arrays allowed with equal lengths (`detailsRunItems` is the
precedent).

## Proposed solution

Four files change, in the order the issue lists them.

### 1. `src/lib/journal.ts` — derivation and formatting, still import-free

Add, keeping the module's empty import list:

- `cycleEndTimestamp(entry: JournalCycleTimes): Date | null` — returns
  `toDate(deployed_at)` when that field is a non-empty value, else
  `toDate(released_at)` when that one is, else `null`. One helper `present(v)`
  collapses the `undefined | null | ''` check that `leadTimeHours` spells out
  today.
- `leadTimeHours` rewritten over `cycleEndTimestamp`: `null` when the end is
  `null`; otherwise `(end - opened) / 3_600_000`, still throwing `RangeError`
  when the end precedes `issue_opened_at`. Every existing assertion in
  `test/journal.test.ts` keeps passing unchanged: the fixtures that pass
  `deployed_at` still take the first branch, and the three "absent, null, empty"
  fixtures carry no `released_at`, so they still return `null`.
- `formatStamp(value: Date | string, months: readonly string[]): string` —
  `'11 Sep, 05:20 UTC'`. Reads `getUTCDate()`, `getUTCMonth()`, `getUTCHours()`,
  `getUTCMinutes()`; the day is not zero-padded, hour and minute are padded to
  two characters with `padStart`; the literal `UTC` suffix is language-neutral
  and is not translated. The month names arrive as an argument rather than being
  embedded, so the copy stays in `src/i18n/ui.ts` and this module stays both
  import-free and language-agnostic.
- `intervalMinutes(from, to): number` — `Math.floor((to - from) / 60_000)`,
  throwing `RangeError` when `to` precedes `from`, exactly as `leadTimeHours`
  does for a reversed pair.
- `formatInterval(from, to, units: { hour: string; minute: string }): string` —
  `+6 h 32 min` when the hour part is non-zero, `+44 min` when it is zero
  (including `+0 min`). Hours are total hours, never rolled into days. Units
  arrive as an argument for the same reason the months do.

`formatLeadTime` is untouched: it already renders `null` as the em dash and `0`
as `'0.0'`.

### 2. `src/i18n/ui.ts` — the new copy, in both languages

```ts
tableScrollHint: {
  en: 'This table scrolls sideways on a narrow screen.',
  ru: 'На узком экране эта таблица прокручивается вбок.',
},
leadTimeMissing: {
  en: 'not measured: this cycle has no end timestamp yet',
  ru: 'не измерено: у этого цикла ещё нет конечной отметки времени',
},
unitHour: { en: 'h', ru: 'ч' },
unitMinute: { en: 'min', ru: 'мин' },
monthAbbrev: {
  en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
  ru: ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'],
},
```

Both arrays are twelve items, so `test/ui.test.ts`'s equal-length rule holds.

### 3. `src/pages/colophon/journal/[...slug].astro` — `<time>` and intervals

The `timeline` array gains a precomputed `iso` and, for every row after the
first, `intervalEn` / `intervalRu`, all built in the frontmatter fence so the
template stays declarative:

```astro
const steps = timeline.map((row, index) => ({
  label: row.label,
  iso: isoStamp(row.value as Date | string),
  en: formatStamp(row.value as Date | string, ui.monthAbbrev.en),
  ru: formatStamp(row.value as Date | string, ui.monthAbbrev.ru),
  interval: index === 0 ? null : {
    en: formatInterval(timeline[index - 1].value as Date | string, row.value as Date | string,
        { hour: ui.unitHour.en, minute: ui.unitMinute.en }),
    ru: formatInterval(timeline[index - 1].value as Date | string, row.value as Date | string,
        { hour: ui.unitHour.ru, minute: ui.unitMinute.ru }),
  },
}));
```

and each `<li>` renders

```astro
<Lang en={step.label.en} ru={step.label.ru} />:
<time datetime={step.iso}><Lang en={step.en} ru={step.ru} /></time>
{step.interval && <span class="step-interval"><Lang en={step.interval.en} ru={step.interval.ru} /></span>}
```

Because `formatStamp`/`formatInterval` return strings and `<Lang>` always emits
both halves, `class="l en"` and `class="l ru"` stay balanced for
`checkLangParity`, and no numeric literal appears in the page source — every
digit is computed, so `check-no-metrics.mjs` sees nothing to classify.

The `journal-meta` lead-time `<dd>` switches to a shared render: em dash in
`<span class="lead-time-missing">` plus a `<span class="visually-hidden">` `<Lang>`
pair carrying `ui.leadTimeMissing` when `leadTimeHours` is `null`, plain
`formatLeadTime(hours)` otherwise.

### 4. `src/components/CycleTable.astro` — hint and the same lead-time cell

Directly under the `<caption>` the component renders

```astro
<p class="table-hint"><Lang en={ui.tableScrollHint.en} ru={ui.tableScrollHint.ru} /></p>
```

placed as a sibling of the table inside `.table-scroll`'s parent (a `<p>` is not
valid inside `<table>`), so the hint scrolls with nothing and stays readable. The
`Lead time` `<td>` uses the same missing/computed branch as the journal page. The
identical `<p class="table-hint">` is added under the ADR table in
`src/pages/colophon/index.astro`. `data-cycle-row`, `data-cycle-count` and
`data-intervention-count` attributes are untouched, so `checkColophonPages` still
passes.

### 5. `src/styles/site.css` — wrapping, per-column `nowrap`, affordance

- Drop `white-space: nowrap` from the shared `table.cycles, table.adr-index`
  block; textual cells then wrap at the 768px measure, which is what makes all
  eight columns fit at 1440px (the measure, not the viewport, is the constraint).
- `th` in both tables: `white-space: normal; overflow-wrap: normal; word-break:
  normal; hyphens: manual` — a heading may wrap at a space but can never break
  inside a word, which is criterion 3 stated as CSS.
- Per-column `nowrap`, in the `nth-child` idiom already used for `tabular-nums`:
  `table.cycles th, table.cycles td:nth-child(1|2|4|5|6|7|8)` (date, service,
  issue, pull request, release, lead time, interventions) and
  `table.adr-index td:nth-child(1|3|4)` (id, status, date). Only
  `table.cycles td:nth-child(3)` (the cycle title link) and
  `table.adr-index td:nth-child(2)` (the ADR title link) wrap.
- `.table-hint`: muted, `--mctl-typography-font-size-xs`, small block margin.
- Affordance: `.table-scroll { position: relative }` plus a
  `@media (max-width: 599px)` `.table-scroll::after` — `position: sticky;
  inset-block: 0; inset-inline-end: 0; inline-size: var(--mctl-space-5);
  background-image: linear-gradient(to left, var(--surface-bg), transparent);
  pointer-events: none` — a static gradient, no `animation`, no `transition`, so
  `test/a11y.test.ts` stays green. It is scoped to the widths where the table can
  still overflow after the wrapping fix; the hint line carries the same message
  at every width, including for readers with images or gradients suppressed.
- `@media (max-width: 599px)`: `table.cycles th:nth-child(2), table.cycles
  td:nth-child(2), table.cycles th:nth-child(5), table.cycles td:nth-child(5)
  { display: none }` — `Service` and `Pull request` off on a phone.
- `.lead-time-missing { color: var(--surface-fg-muted) }` and
  `.step-interval { color: var(--surface-fg-muted); margin-inline-start:
  var(--mctl-space-2) }`.

No new colour token is introduced, so `scripts/check-contrast.mjs` has no new
pair to resolve; `--surface-fg-muted` over `--surface-bg` is already one of the
pairs it checks in both themes.

`npm run vendor` copies `src/styles/site.css` to `public/styles/site.css` during
`prebuild`, so the generated copy follows automatically — it must not be edited
by hand (it is gitignored; see the 2026-09-10 base-layout journal entry).

## Alternatives

1. **Widen the table region past `--content-max`** (full-bleed or a wider
   `.table-scroll`). Rejected: it breaks the single 768px measure every other
   page shares, and the issue's first-preference fix — wrapping the textual
   columns — makes the table fit inside the existing measure, which is the
   smaller change and the one the issue asked for in that order.
2. **A card list below 600px instead of hiding two columns.** Rejected for this
   cycle: it duplicates every row's markup and its `<Lang>` pairs, roughly
   doubling the colophon page's bilingual span count, and it needs its own copy
   for the one-line issue/release/intervention summary. Hiding `Service` and
   `Pull request` loses nothing permanently — both render on the cycle's own
   journal page, one click from the title link that stays visible. Recorded as
   the runner-up, since the issue accepts either.
3. **The `background-attachment: local` scroll-shadow trick** (four background
   layers on `.table-scroll`, shadows that hide themselves at each end).
   Rejected: the gradients paint behind the transparent table cells rather than
   only at the edges, which puts a gradient under body text and would drag the
   contrast script's assumptions into a place it does not model. The
   sticky `::after` overlay is deterministic, assertable from the CSS source, and
   `pointer-events: none` keeps it out of the way of the focusable region.
4. **Deriving the end timestamp from `cycleTimestamp()` directly** (which falls
   all the way back to `merged_at`, `proposal_approved_at`, `issue_opened_at`).
   Rejected: it would report a lead time for a cycle that has not been released,
   turning a genuinely unknown value into a confident-looking number — the exact
   failure the "em dash only where a timestamp is genuinely missing" criterion
   guards against. `cycleEndTimestamp` stops at `released_at`.
5. **Formatting timestamps with `Intl.DateTimeFormat`.** Rejected: it would make
   `src/lib/journal.ts` depend on the build host's ICU data for Russian month
   abbreviations, so the rendered copy would no longer be reviewable in
   `src/i18n/ui.ts`, and AGENTS.md makes the copy the contract. Passing the month
   array in keeps the strings in the dictionary and the module import-free and
   deterministic.

## Platform impact

- **Migrations:** none. No content file, no frontmatter key and no schema in
  `src/content.config.ts` changes; the five timestamps already exist and are
  already typed.
- **Backward compatibility:** the public function signature of `leadTimeHours`
  is unchanged (`JournalTimes -> number | null`), so every existing call site and
  every existing assertion in `test/journal.test.ts` keeps working. Eight of
  twelve cycles begin showing a number where they showed an em dash; four still
  show the dash, now with an explanation. No URL, no route and no `data-*`
  attribute changes.
- **Resource impact:** the page gains one hint line per table, one `<time>`
  wrapper and one interval span per timeline step, and a handful of CSS rules —
  a few hundred bytes of HTML on the colophon and journal pages. The 40 KB cap in
  `scripts/check-dist.mjs` applies to `dist/index.html` (the home page), which is
  not touched. Still zero JavaScript, still zero third-party requests.
- **Risks and mitigations:**
  - *A number leaks into a scanned directory.* Mitigated by keeping every
    numeric constant (60, 3_600_000, month indices) inside `src/lib/journal.ts`,
    which `check-no-metrics.mjs` does not scan, and by adding no `ALLOW` entry —
    a stale entry is itself a failure there.
  - *Bilingual parity breaks.* Mitigated by routing every new string through
    `<Lang>`, which always emits both halves; `checkLangParity` in
    `check-dist.mjs` proves it on the built HTML.
  - *A reversed timestamp pair in future content throws at build time.* That is
    the intended behaviour, consistent with `leadTimeHours` today: a cycle whose
    `merged_at` precedes its `proposal_approved_at` is a data error, and failing
    the build is how this repository surfaces one.
  - *The `::after` overlay covers the last column's text at narrow widths.*
    Mitigated by `pointer-events: none`, a width of one space step, and the
    gradient fading to `transparent`; the hint line, not the gradient, is the
    accessible carrier of the message.
  - *The 1440px/360px criteria are visual.* A script can assert the CSS rules
    that produce them (no table-wide `nowrap`, per-column `nowrap` present,
    heading break rules present, the two hidden columns), which is what
    `npm test` will do; the final look at 1440px and 360px in a browser is a
    reviewer step, per the AGENTS.md issue contract, not an acceptance criterion
    the implementer is asked to self-certify.
