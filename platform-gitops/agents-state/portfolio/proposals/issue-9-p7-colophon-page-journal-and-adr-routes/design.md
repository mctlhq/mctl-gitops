# Design: issue-9-p7-colophon-page-journal-and-adr-routes

## Current state

Read in the clone at `9bc36de` (release 0.1.5):

- `src/content.config.ts` defines three collections. `journal` is a
  `z.strictObject` with `service`, `issue`, `proposal_slug`, optional `pr`,
  optional `release`, `visibility: 'public' | 'private'`, bilingual `title` and
  `decided`, the five timestamps (`issue_opened_at` required, the other four
  optional, each parsed by `stamp` into a `Date`) and
  `interventions: [{what, why, at}]` defaulting to `[]`. `adr` is a
  `strictObject` with `id`, bilingual `title`, `status`, `date`, optional
  `supersedes` and `visibility`, wrapped by `adrLoader()` which runs
  `checkAdrBodies` over every entry. Entry ids come from
  `idFromFile` — the filename with `.md` stripped.
- `src/lib/journal.ts` is a deliberately import-free module (so
  `node --test test/journal.test.ts` can exercise it with no build step)
  exporting `ISO_WITH_OFFSET`, `yyyyMmDd`, `isoWithOffset`, `leadTimeHours`
  (returns `null` when `deployed_at` is absent/null/empty, throws `RangeError`
  when it precedes `issue_opened_at`) and `interventionCount`.
- `src/lib/adr.ts` exports `ADR_SECTIONS`, `adrBodyProblems`, `checkAdrBodies`.
  `src/lib/metrics.ts` exports `EM_DASH`, `formatStat`, `snapshotDate`,
  `metricProblems`, and documents the rule that a module in `src/lib` keeps its
  import list empty by duplicating a constant rather than importing a sibling.
- `src/pages/` has `index.astro`, `work.astro`, `approach.astro`, `404.astro`
  and `dev/[check].astro`. `dev/[check].astro` is the only existing
  `getStaticPaths` example: it returns `[]` outside `astro dev`, so the route
  never reaches `dist/`. There is no `colophon` route, so the home page's
  `ctaColophon` link to `/colophon/` currently 404s.
- `src/pages/work.astro` is the model for a collection-driven page:
  `await getCollection('projects')`, filter, sort, map to a component.
  `src/components/ProjectCard.astro` is the model for rendering a collection
  body: `const { Content } = await render(entry)`.
- `src/i18n/Lang.astro` emits
  `<span class="l en">{en}</span><span class="l ru" lang="ru">{ru}</span>`;
  `src/styles/site.css` hides one half per `:root[data-lang]`.
  `src/i18n/ui.ts` is the single string dictionary; `test/ui.test.ts` asserts
  every `ui` value is an `{en, ru}` pair of the same kind.
- `src/components/Footer.astro` already does
  `import pkg from '../../package.json'` and renders
  `<span data-release>{pkg.version}</span>`, with a stale comment saying the
  release source is "tracked for a later issue". `Nav.astro` links Home, Work
  and Approach only.
- `scripts/check-dist.mjs` walks `dist/` post-build and fails on any `.js`
  file, on unequal `class="l en"` / `class="l ru"` counts in any HTML, on a
  missing or oversized `dist/index.html` (40 KB cap), and on the P6
  approach-page SVG rules. It runs in the `Dockerfile` builder stage
  (`npm run build && node scripts/check-dist.mjs && node scripts/csp-hash.mjs`),
  which the `build` job of `.github/workflows/build.yml` exercises on every
  pull request. `npm test` enumerates its test files explicitly in
  `package.json`.
- `nginx.conf`'s catch-all location already does
  `try_files $uri $uri/index.html $uri.html =404`, and `astro.config.mjs` sets
  `trailingSlash: 'always'`, so nested directory routes need no server change.
- `src/content/journal/` holds seven public entries; four carry `interventions`
  (2 + 3 + 3 + 2 = 10) and three (`2026-09-11-home-page.md`,
  `2026-09-11-work-page.md`, `2026-09-11-approach-page.md`) carry no `pr`,
  `release`, `merged_at` or `released_at`. No entry for the P3 cycle (issue #5)
  exists. `src/content/adr/` holds `0001`, `0002` and `0005`, all public.
- `public/assets/mctl/prose.css` scopes editorial typography under
  `.mctl-prose`; nothing in `src/` opts into it yet.

## Proposed solution

### 1. Two small library additions, both unit-testable without Astro

`src/lib/content.ts` (new, import-free, mirroring the header comment style of
`src/lib/journal.ts`):

```ts
export interface HasVisibility { visibility: 'public' | 'private' }
export function isPublic<T extends { data: HasVisibility }>(entry: T): boolean
export function publicEntries<T extends { data: HasVisibility }>(entries: readonly T[]): T[]
```

Both page routes and the colophon index filter through `publicEntries`, so
"public only" is one function with one test, not three copies of
`.filter(e => e.data.visibility === 'public')`.

`src/lib/journal.ts` gains (keeping the module import-free; it defines its own
module-private `const EM_DASH = '—'` rather than importing the one in
`src/lib/metrics.ts`, for the reason that module's header already states):

```ts
export function cycleTimestamp(entry: JournalTimes & {...}): Date   // deployed ?? released ?? merged ?? approved ?? opened
export function byNewestFirst(a, b): number                          // cycleTimestamp desc, then id desc
export function isoDate(value: Date | string): string                // 'YYYY-MM-DD'
export function isoStamp(value: Date | string): string               // '2026-09-11T06:41:07Z'
export function formatLeadTime(hours: number | null): string         // em dash, else hours.toFixed(1)
export function totalInterventions(entries): number
export function githubRef(url: string): string                       // '#28' from .../pull/28
```

`githubRef` returns `#<n>` when the URL ends in a number and the full URL
otherwise, so a malformed link degrades to something readable instead of
throwing at build time.

### 2. `src/components/CycleTable.astro`

Takes `entries: CollectionEntry<'journal'>[]` already filtered and sorted by the
page, and emits one `<table class="cycles">` with a `<caption>`, a `<thead>` of
eight `<th scope="col">` cells and one `<tr data-cycle-row>` per entry:

| cell | source |
| --- | --- |
| date | `isoDate(cycleTimestamp(entry.data))` — language-neutral |
| service | `entry.data.service` — an identifier, untranslated |
| title | `<a href={`/colophon/journal/${entry.id}/`}><Lang en={title.en} ru={title.ru} /></a>` |
| issue | `<a href={entry.data.issue}>{githubRef(entry.data.issue)}</a>` |
| pull request | same, or `—` when `pr` is absent |
| release | `entry.data.release ?? '—'` |
| lead time | `formatLeadTime(leadTimeHours(entry.data))` |
| interventions | `interventionCount(entry.data)` |

Only the title cell is bilingual, so `.l.en` / `.l.ru` parity is one pair per
row and the numeric columns stay language-neutral (which is also why the unit
lives in the column header, `Lead time (h)` / `Время цикла (ч)`, not in the
cell).

The table is wrapped in
`<div class="table-scroll" role="region" tabindex="0" aria-label={`${ui.cycleTableCaption.en} / ${ui.cycleTableCaption.ru}`}>`
with `overflow-x: auto` in `src/styles/site.css`. `tabindex="0"` is required
here, not an override: a scrollable region must be reachable by keyboard
(WCAG 2.1.1). The concatenated bilingual `aria-label` follows the existing
precedent in `src/components/Nav.astro`. The alternative — a CSS
`display: block` stacked layout with `::before` labels — is rejected because
`content:` strings in CSS cannot be bilingual.

### 3. `src/pages/colophon/index.astro`

```
const journal = publicEntries(await getCollection('journal')).sort(byNewestFirst);
const adrs = publicEntries(await getCollection('adr')).sort(byAdrId);
const cycleCount = journal.length;
const interventions = totalInterventions(journal.map((e) => e.data));
```

Renders, in order: `<h1>` (`Colophon` / `Колофон`, from the existing
`ui.navColophon`), the intro paragraph, the `Build and deploy chain` section as
two `<ul>` lists (`.l.en` / `.l.ru`, the pattern already used on the home and
approach pages), the `Cycles` section with `<CycleTable entries={journal} />`
followed by

```html
<p class="cycle-totals">
  <span data-cycle-count={cycleCount}>{cycleCount}</span> <Lang .../>
  <span data-intervention-count={interventions}>{interventions}</span> <Lang .../>
</p>
```

and the `Decisions` section with the ADR index table (`id` zero-padded to four
digits, bilingual title linking to `/colophon/adr/${entry.id}/`, bilingual
status label, `date` verbatim). The `data-cycle-count` / `data-intervention-count`
attributes exist so `check-dist` can read the rendered numbers exactly, the way
`data-stat` and `data-release` are already used.

### 4. `src/pages/colophon/journal/[...slug].astro`

```
export async function getStaticPaths() {
  return publicEntries(await getCollection('journal'))
    .map((entry) => ({ params: { slug: entry.id }, props: { entry } }));
}
```

Renders the bilingual `title` as `<h1>`, a metadata list (service, issue link,
pull request link, release, lead time), a `Timeline` block listing each present
timestamp as `label: isoStamp(value)`, the bilingual `decided` paragraph, and
the interventions. Interventions render as an ordered list of
`what` / `why` / `at`, preceded by the bilingual note that the records are
quoted in the language they were written in and wrapped in a container carrying
`lang="en"`; entries with none render the bilingual
`journalNoInterventions` line. A trailing link returns to `/colophon/`.

### 5. `src/pages/colophon/adr/[...slug].astro`

Same `getStaticPaths` shape over `adr`. Renders `ADR-<padded id>`, the bilingual
title, a status/date line, an optional "supersedes" line linking to the
superseded ADR when `supersedes` is set and that ADR is public, then the
rendered body via `const { Content } = await render(entry)` inside
`<div class="mctl-prose">`. The body already carries its own balanced
`.l.en` / `.l.ru` blocks (enforced by `checkAdrBodies`), so parity holds without
extra work. `class="lede"` and `var(--font-editorial)` are not used anywhere on
these pages: `Instrument Serif` has no Cyrillic subset and every string here has
a Russian counterpart.

### 6. Strings added to `src/i18n/ui.ts`

Every string below is added verbatim. `ui.navColophon`
(`Colophon` / `Колофон`) and `ui.footerColophonLabel` already exist and are
reused.

```
colophonPageTitle:      en 'Colophon — Dmitrii Mashkov'            ru 'Colophon — Dmitrii Mashkov'
colophonIntro:
  en "This site is built only through the DevLoop and deployed only through the platform's MCP tools. The table below is generated from the journal at build time; nothing in it is typed by hand."
  ru 'Этот сайт собирается только через DevLoop и деплоится только через MCP-инструменты платформы. Таблица ниже генерируется из журнала при сборке; ничего в ней не вписано вручную.'
colophonChainHeading:   en 'Build and deploy chain'                ru 'Цепочка сборки и деплоя'
colophonChainItems:
  en [
    'Source: github.com/mctlhq/portfolio',
    'Image: ghcr.io/mctlhq/portfolio, built by mctl-gitops from a release tag',
    'Runtime: Astro static output served by nginx on k3s, tenant labs',
    'Release: release-please; deploy dispatched to release-deploy in mctl-gitops; ArgoCD syncs the image tag',
    'Onboarding, rollbacks and custom domains: mctl MCP tools only',
  ]
  ru [
    'Исходники: github.com/mctlhq/portfolio',
    'Образ: ghcr.io/mctlhq/portfolio, собирается mctl-gitops из тега релиза',
    'Рантайм: статический вывод Astro, отдаваемый nginx на k3s, тенант labs',
    'Релиз: release-please; деплой запускается через release-deploy в mctl-gitops; ArgoCD синхронизирует тег образа',
    'Онбординг, откаты и кастомные домены: только MCP-инструменты mctl',
  ]
colophonCyclesHeading:    en 'Cycles'                              ru 'Циклы'
colophonDecisionsHeading: en 'Decisions'                           ru 'Решения'
cycleTableCaption:        en 'DevLoop cycles, newest first'        ru 'Циклы DevLoop, новые сверху'
cycleColDate:             en 'Date'                                ru 'Дата'
cycleColService:          en 'Service'                             ru 'Сервис'
cycleColTitle:            en 'Cycle'                               ru 'Цикл'
cycleColIssue:            en 'Issue'                               ru 'Issue'
cycleColPr:               en 'Pull request'                        ru 'Pull request'
cycleColRelease:          en 'Release'                             ru 'Релиз'
cycleColLeadTime:         en 'Lead time (h)'                       ru 'Время цикла (ч)'
cycleColInterventions:    en 'Interventions'                       ru 'Вмешательства'
colophonTotalCycles:      en 'public cycles'                       ru 'публичных циклов'
colophonTotalInterventions: en 'manual interventions in total'     ru 'ручных вмешательств всего'
adrTableCaption:          en 'Architecture decision records'       ru 'Записи об архитектурных решениях'
adrColId:                 en 'ID'                                  ru 'ID'
adrColTitle:              en 'Title'                               ru 'Название'
adrColStatus:             en 'Status'                              ru 'Статус'
adrColDate:               en 'Date'                                ru 'Дата'
adrStatusProposed:        en 'Proposed'                            ru 'Предложено'
adrStatusAccepted:        en 'Accepted'                            ru 'Принято'
adrStatusSuperseded:      en 'Superseded'                          ru 'Заменено'
adrStatusDeprecated:      en 'Deprecated'                          ru 'Устарело'
adrSupersedesLabel:       en 'Supersedes'                          ru 'Заменяет'
journalServiceLabel:      en 'Service'                             ru 'Сервис'
journalIssueLabel:        en 'Issue'                               ru 'Issue'
journalPrLabel:           en 'Pull request'                        ru 'Pull request'
journalReleaseLabel:      en 'Release'                             ru 'Релиз'
journalLeadTimeLabel:     en 'Lead time (h)'                       ru 'Время цикла (ч)'
journalDecidedHeading:    en 'What this cycle decided'             ru 'Что решил этот цикл'
journalTimelineHeading:   en 'Timeline'                            ru 'Хронология'
journalStampIssueOpened:  en 'Issue opened'                        ru 'Issue открыт'
journalStampApproved:     en 'Proposal approved'                   ru 'Предложение одобрено'
journalStampMerged:       en 'Merged'                              ru 'Смержено'
journalStampReleased:     en 'Released'                            ru 'Релиз выпущен'
journalStampDeployed:     en 'Deployed'                            ru 'Развёрнуто'
journalInterventionsHeading: en 'Manual interventions'             ru 'Ручные вмешательства'
journalInterventionsNote:
  en 'Each record below is quoted verbatim in English, the language it was written in.'
  ru 'Каждая запись ниже приводится дословно по-английски — на языке, на котором она была написана.'
journalNoInterventions:
  en 'No manual intervention was recorded for this cycle.'
  ru 'Ручных вмешательств в этом цикле не зафиксировано.'
journalBackToColophon:    en 'Back to the colophon'                ru 'Назад к колофону'
adrBackToColophon:        en 'Back to the colophon'                ru 'Назад к колофону'
```

`cycleColIssue` and `cycleColPr` are identical in both languages on purpose:
`Issue` and `Pull request` are GitHub identifiers, already used untranslated in
the existing Russian copy of `ui.detailsWorkItems.ru`.

### 7. Backfill

Values below come from the GitHub pull request and release records for
`mctlhq/portfolio` (`merged_at` of the implementer's pull request;
`published_at` of the release), matching the convention the existing P1 and P2
entries already follow. No `deployed_at` is added: the site has not been
onboarded yet, so their lead time cells render an em dash, and P9 owns the
deploy evidence.

**New file `src/content/journal/2026-09-11-content-collections.md`** (P3):

```yaml
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/5
proposal_slug: issue-5-p3-content-collections-for-projects-jour
pr: https://github.com/mctlhq/portfolio/pull/21
release: 0.1.2
visibility: public
title:
  en: "Content collections for projects, journal and ADRs"
  ru: "Коллекции контента для проектов, журнала и ADR"
decided:
  en: "Projects, the journal and the ADRs became typed content collections validated at build time, so a malformed entry fails the build instead of reaching a page, and every later cycle has a schema to write its own record into."
  ru: "Проекты, журнал и ADR стали типизированными коллекциями контента с проверкой во время сборки: некорректная запись ломает сборку, а не попадает на страницу, и у каждого следующего цикла есть схема, в которую он записывает свой след."
issue_opened_at: '2026-09-10T22:45:34Z'
proposal_approved_at: '2026-09-11T01:54:03Z'
merged_at: '2026-09-11T03:02:47Z'
released_at: '2026-09-11T03:06:49Z'
---
```

**`src/content/journal/2026-09-11-home-page.md`** (P4) gains
`pr: https://github.com/mctlhq/portfolio/pull/24`, `release: 0.1.3`,
`merged_at: '2026-09-11T04:04:03Z'`, `released_at: '2026-09-11T04:06:16Z'`.

**`src/content/journal/2026-09-11-approach-page.md`** (P6) gains
`pr: https://github.com/mctlhq/portfolio/pull/32`, `release: 0.1.5`,
`merged_at: '2026-09-11T09:24:24Z'`, `released_at: '2026-09-11T09:26:43Z'`.

**`src/content/journal/2026-09-11-work-page.md`** (P5) gains
`pr: https://github.com/mctlhq/portfolio/pull/28`, `release: 0.1.4`,
`merged_at: '2026-09-11T06:41:07Z'`, `released_at: '2026-09-11T06:46:15Z'`
and, verbatim and in this order, the seven interventions:

```yaml
interventions:
  - what: "amended issue #7 with an explicit requirement to inline every string, then re-ran the investigator"
    why: "the first proposal pointed at the issue's wording instead of embedding it, and the implementer — which never sees the issue — correctly refused to invent fourteen projects' bilingual prose"
    at: '2026-09-11T04:35:34Z'
  - what: "deleted the failed proposal directory through a reviewed GitOps pull request"
    why: "the investigator only overwrites a proposal at status proposed, and the failed one sat at needs-triage, so the loop had no way back in"
    at: '2026-09-11T04:58:45Z'
  - what: "rewrote pull request #28's description by hand with the link-check output, the same-origin evidence and the keyboard evidence"
    why: "three acceptance criteria demanded that evidence in the pull request body, which the implementer opens from a fixed template and cannot edit"
    at: '2026-09-11T05:37:09Z'
  - what: "rewrote the equivalent criteria in issues #8, #10 and #11 so the artifact is a committed file or a script in npm test"
    why: "the same defect was waiting in three later cycles; naming human-only verification as a reviewer step instead of a criterion prevents three more deadlocks"
    at: '2026-09-11T05:37:35Z'
  - what: "added two rules to AGENTS.md: an acceptance criterion must be satisfiable by a commit, and the copy is the contract"
    why: "fixing the three issues by hand leaves the next author free to write the same unsatisfiable criterion again"
    at: '2026-09-11T05:45:53Z'
  - what: "ran the shepherd by hand for this slug"
    why: "the cron shepherd skips a slug it believes a live DevLoopWorkflow is driving, and a workflow left Running from an earlier attempt held that claim without doing any work"
    at: '2026-09-11T06:23:06Z'
  - what: "merged pull request #28 by hand"
    why: "the review was approved with no blocking findings and every check was green, but GitHub had re-anchored an already-fixed comment onto the new head, so the shepherd read it as current, exhausted its attempts and parked the proposal at review-stuck"
    at: '2026-09-11T06:41:07Z'
---
```

Frontmatter key order follows the existing files: `service`, `issue`,
`proposal_slug`, `pr`, `release`, `visibility`, `title`, `decided`,
`issue_opened_at`, `proposal_approved_at`, `merged_at`, `released_at`,
`interventions`. Every timestamp is single-quoted so YAML does not parse it into
a `Date` before the schema's `stamp` refinement sees a string — the schema's own
error message states this requirement.

After the backfill the journal holds eight public entries. The rendered totals
are computed from those files; they are not written into any source file, and no
number from the issue is copied into a test.

### 8. `scripts/check-dist.mjs`: `checkColophonPages()`

A new function, called from `main()` alongside `checkApproachPage()`, that:

1. reads `src/content/journal/*.md`, splitting them by a
   `/^visibility:\s*(public|private)\s*$/m` match, and counts `- what:` items
   (`/^\s*-\s+what:/gm`) across the public ones;
2. asserts `dist/colophon/index.html` exists, that its
   `data-cycle-count="N"` equals the number of public files, that its
   `data-intervention-count="M"` equals the `- what:` total, and that its
   `data-cycle-row` occurrences equal the number of public files;
3. asserts `dist/colophon/journal/<id>/index.html` exists for every public id
   and does not exist for any private id, and the same for
   `src/content/adr/*.md` against `dist/colophon/adr/<id>/`;
4. asserts no private id string occurs in any `dist/**/*.html`;
5. asserts `data-release` in every page equals `package.json`'s `version`;
6. asserts no `<link>`, `<script>`, `<img>` or `<source>` in any
   `dist/**/*.html` has an `href`/`src` starting with `http://`, `https://` or
   `//`, and no `dist/**/*.css` contains `url(` with an absolute URL. Anchor
   (`<a href>`) targets are deliberately exempt: a link is not a request.

Step 2 is the load-bearing one. The page derives its numbers from parsed
frontmatter through `getCollection`; `check-dist` derives them by scanning raw
text. The two paths share no code, so they can only agree when the page really
is generated from the journal.

`check-dist.mjs` already runs in the `Dockerfile` builder stage, which the
`build` job of `.github/workflows/build.yml` runs on every pull request. No
workflow change is needed.

### 9. `Nav.astro` and `Footer.astro`

`Nav.astro` gains `<a href="/colophon/"><Lang en={ui.navColophon.en} ru={ui.navColophon.ru} /></a>`
after the Approach link. `Footer.astro` gains a `/colophon/` link using the
existing `ui.footerColophonLabel`, and its stale comment about the release
source being "tracked for a later issue" is replaced by a statement that
`package.json`'s `version` — the value release-please bumps on every release —
is the source. The rendered markup (`<span data-release>{pkg.version}</span>`)
does not change, so issue criterion 4 is already met and stays met, now under a
`check-dist` rule and a unit test.

## Alternatives

1. **Write lead time and intervention count into the journal frontmatter.**
   Rejected: it contradicts `AGENTS.md` ("Lead time and the number of
   interventions are computed at build time, never written by hand") and issue
   criterion 3, and the schema is a `z.strictObject`, so the fields would fail
   validation anyway. Computing them keeps the page honest by construction.
2. **One combined `/colophon/` page with anchors instead of per-entry routes.**
   Rejected: the issue asks for one page per entry, the page would grow without
   bound as cycles accumulate, and an ADR needs a stable citable URL. The
   `[...slug].astro` routes cost nothing at runtime — Astro emits plain HTML
   files that nginx's existing `try_files` already serves.
3. **Assert the counts (8 cycles, 17 interventions) as literals in a test.**
   Rejected explicitly by the issue and by ordinary hygiene: a literal would
   have to be edited by hand on every future cycle, which is exactly the class
   of hand-typed number this page exists to eliminate. Both the page and
   `check-dist` derive the numbers, by two independent routes.
4. **A `data-har` style browser capture as an acceptance criterion.**
   Rejected per `AGENTS.md`: the implementer cannot run a browser or edit its
   own pull request body. The mechanical subset (no absolute-URL subresource in
   `dist/`) becomes a `check-dist` rule; the HAR capture is a reviewer step.
5. **Stacked `display: block` table rows on narrow viewports with `::before`
   labels.** Rejected: CSS `content:` strings cannot carry an `.l.en` / `.l.ru`
   pair, so the labels would be monolingual. A keyboard-reachable horizontal
   scroll region keeps both languages and stays accessible.

## Platform impact

- **Migrations:** none. No schema change to `src/content.config.ts`, no change
  to `src/data/metrics.json`, `nginx.conf`, `Dockerfile` or `astro.config.mjs`.
  `package.json`'s `test` script gains the new test files.
- **Backward compatibility:** purely additive at the URL level —
  `/colophon/`, `/colophon/journal/*/` and `/colophon/adr/*/` are new. The home
  page's existing `ctaColophon` link stops 404ing. Existing pages change only by
  one nav link and one footer link.
- **Resource impact:** the cycle table is eight rows and the two new route
  families are eleven small static HTML files. `dist/index.html` grows by one
  nav link and one footer link, well inside the existing 40 KB cap; that cap
  remains checked by `check-dist`. No new runtime dependency, no JavaScript, no
  new font or third-party origin.
- **Risks and mitigations:**
  - *A backfilled timestamp is wrong.* Every value is copied from the GitHub
    pull request and release records and is listed in this document, so the
    reviewer can diff it against `gh api repos/mctlhq/portfolio/pulls` and
    `.../releases` without reading code. `leadTimeHours` throws a `RangeError`
    if `deployed_at` ever precedes `issue_opened_at`, which would fail the
    build rather than render a negative number.
  - *YAML parses an unquoted timestamp into a `Date` and the schema rejects
    it.* Mitigated by quoting every timestamp, as the existing entries do and
    as the schema's error message instructs.
  - *Bilingual parity breaks on the new pages.* `check-dist` already fails the
    image build on unequal `.l.en` / `.l.ru` counts in any HTML file; the new
    pages are covered by that existing rule automatically.
  - *The intervention prose is English-only on a Russian page.* Accepted and
    made explicit by `journalInterventionsNote` plus a `lang="en"` container, so
    a screen reader announces it in the right language. Making the field
    bilingual would mean inventing Russian for seven records supplied in
    English, which the copy-is-the-contract rule forbids.
  - *The horizontal scroll region's `tabindex="0"` reads as a tabindex
    override.* Mitigated by a code comment citing WCAG 2.1.1 and by the fact
    that it is the only `tabindex` on the page.
