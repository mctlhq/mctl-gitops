# P7: Colophon page, journal and ADR routes, cycle table and backfill

## Context

The site already carries a typed content model (`src/content.config.ts` defines
the `projects`, `journal` and `adr` collections) and three pages that consume it
or the metrics snapshot: `/` (`src/pages/index.astro`), `/work/`
(`src/pages/work.astro`) and `/approach/` (`src/pages/approach.astro`). Nothing
renders the `journal` or the `adr` collection yet: the entries exist on disk,
are schema-validated on every build, and are invisible to a reader. The home
page already links `/colophon/`, which today resolves to the 404 page.

This proposal builds `/colophon/` — the page that makes the site its own
evidence. It states how the site is built and deployed, renders a table of
DevLoop cycles read from `src/content/journal/` with lead time and intervention
counts computed at build time, indexes the architecture decision records, and
gives every public journal entry and every public ADR its own page. It also
completes the journal itself: the P3 cycle has no entry at all, and the P4, P5
and P6 entries are missing the `pr`, `release`, `merged_at` and `released_at`
values that GitHub now knows. Lead time and intervention count are never written
into frontmatter; they are derived from the five timestamps and the
`interventions` array by `leadTimeHours` and `interventionCount` in
`src/lib/journal.ts`, which already exist and are already unit-tested.

## User stories

- AS a reader evaluating the claim "software built the agentic way" I WANT a
  page that lists every DevLoop cycle with its issue, pull request, release,
  lead time and number of manual interventions SO THAT I can check the claim
  against records instead of taking it on trust.
- AS a reader I WANT each cycle and each architecture decision to have its own
  page SO THAT I can read the full record and link to it.
- AS the site owner I WANT the cycle count, the totals and the release tag to be
  computed at build time from the journal and from `package.json` SO THAT the
  page cannot drift from the repository and cannot be quietly hand-edited.
- AS the site owner I WANT entries marked `visibility: private` to produce no
  page and to leave no trace in `dist/` SO THAT the public record stays a
  deliberate subset of the journal.
- AS a Russian-speaking reader I WANT every user-facing string on the new pages
  to exist in both languages and to be set in a face that covers Cyrillic SO
  THAT the two languages look like the same design.

## Acceptance criteria (EARS)

### Routes and visibility

- WHEN the site is built THE SYSTEM SHALL emit `dist/colophon/index.html` from
  `src/pages/colophon/index.astro`.
- WHEN the site is built THE SYSTEM SHALL emit exactly one page under
  `dist/colophon/journal/<id>/index.html` for every entry of the `journal`
  collection whose `visibility` is `public`, where `<id>` is the entry id (the
  filename stem, e.g. `2026-09-11-home-page`), and no page for any other entry.
- WHEN the site is built THE SYSTEM SHALL emit exactly one page under
  `dist/colophon/adr/<id>/index.html` for every entry of the `adr` collection
  whose `visibility` is `public`, where `<id>` is the filename stem (e.g.
  `0002-static-astro-no-client-bundles`), and no page for any other entry.
- IF a journal or ADR entry has `visibility: private` THEN THE SYSTEM SHALL
  emit no page for it and SHALL NOT write its id, title or body text into any
  file under `dist/`.
- WHEN `node scripts/check-dist.mjs` runs after a build THE SYSTEM SHALL fail
  with a named reason if the set of generated journal page directories differs
  from the set of ids of the public files in `src/content/journal/`, or if the
  set of generated ADR page directories differs from the set of ids of the
  public files in `src/content/adr/`.

### Cycle table

- WHEN `/colophon/` renders THE SYSTEM SHALL render one table row per public
  journal entry, with the columns: date, service, title, issue link, pull
  request link, release, lead time in hours, intervention count.
- WHILE rows are rendered THE SYSTEM SHALL order them newest first, by the
  entry id's `YYYY-MM-DD` prefix descending, ties broken by `issue_opened_at`
  descending and then by entry id descending.
- WHEN a row's lead time is rendered THE SYSTEM SHALL take it from
  `leadTimeHours` in `src/lib/journal.ts` and render it with one decimal place.
- IF `leadTimeHours` returns `null` for an entry THEN THE SYSTEM SHALL render an
  em dash (`—`) in that row's lead time cell.
- WHEN a row's intervention count is rendered THE SYSTEM SHALL take it from
  `interventionCount` in `src/lib/journal.ts`.
- IF an entry has no `pr` or no `release` THEN THE SYSTEM SHALL render an em
  dash (`—`) in that cell rather than an empty cell or a broken link.
- WHEN an issue or pull request cell is rendered THE SYSTEM SHALL render a link
  whose href is the frontmatter URL and whose text is `<repo>#<number>` derived
  from that URL (e.g. `portfolio#12`, `mctl-api#282`), so a cross-repository
  cycle is legible.
- WHEN `/colophon/` renders THE SYSTEM SHALL show, below the table, the number
  of public cycles and the total number of interventions across those cycles,
  both computed from the collection.
- WHILE the totals are rendered THE SYSTEM SHALL carry the count of public
  cycles in a `data-cycle-count` attribute and the intervention total in a
  `data-interventions-total` attribute, so a post-build script can check them.
- WHEN `node scripts/check-dist.mjs` runs after a build THE SYSTEM SHALL fail
  with a named reason if `data-cycle-count` differs from the number of public
  files in `src/content/journal/`, or if `data-interventions-total` differs from
  the number of `interventions` items in those files.

### Journal frontmatter stays free of computed fields

- WHILE any journal entry exists in `src/content/journal/` THE SYSTEM SHALL
  contain no `lead_time`, `lead_time_hours`, `leadTime`, `intervention_count` or
  `interventions_count` key in its frontmatter, and `npm test` SHALL fail with a
  named reason if one appears.
- WHILE any journal entry exists THE SYSTEM SHALL use only the keys the `journal`
  schema in `src/content.config.ts` declares, and `npm test` SHALL fail with a
  named reason if an entry carries any other key.

### Backfill

- WHEN the backfill lands THE SYSTEM SHALL contain a public journal entry for the
  P3 cycle (issue 5) at
  `src/content/journal/2026-09-11-content-collections-for-projects-journal-and-adrs.md`
  with the frontmatter given in "Copy: P3 journal entry" below.
- WHEN the backfill lands THE SYSTEM SHALL add `pr`, `release`, `merged_at` and
  `released_at` to the three existing entries `2026-09-11-home-page.md`,
  `2026-09-11-work-page.md` and `2026-09-11-approach-page.md` with the values
  given in "Copy: backfilled timestamps" below, changing no other field.
- WHILE backfilling THE SYSTEM SHALL add no `interventions` entry and no
  `deployed_at` value to any entry, because none of the four cycles has a
  recorded manual intervention or a recorded deployment.
- WHEN the backfill has landed THE SYSTEM SHALL show a cycle count of 8 and an
  intervention total of 10 on `/colophon/`.

### Entry pages

- WHEN a journal entry page renders THE SYSTEM SHALL show the entry's bilingual
  `title` and `decided`, its service, its issue and pull request links, its
  release, each of the five timestamps that is present, the computed lead time,
  and one item per intervention with its `what`, `why` and `at`.
- IF a timestamp is absent from an entry THEN THE SYSTEM SHALL render an em dash
  (`—`) for it rather than omitting the row.
- WHEN an ADR page renders THE SYSTEM SHALL show `ADR-<four-digit id>`, the
  bilingual title, the status, the date, the `supersedes` reference when present,
  and the rendered markdown body.
- WHEN an entry page renders THE SYSTEM SHALL include a link back to `/colophon/`.

### Footer, navigation and copy

- WHEN any page renders THE SYSTEM SHALL show in the footer the version read at
  build time from `package.json` via `import pkg from '../../package.json'`,
  rendered as a semver string with no leading `v`.
- WHEN `node scripts/check-dist.mjs` runs after a build THE SYSTEM SHALL fail
  with a named reason if the text inside the footer's `data-release` element
  differs from `package.json`'s `version`, or if it starts with `v`.
- WHEN the primary navigation renders THE SYSTEM SHALL include a link to
  `/colophon/` labelled from `ui.navColophon`.
- WHILE any new page renders THE SYSTEM SHALL take every user-facing string from
  `src/i18n/ui.ts` as an `{ en, ru }` pair rendered through
  `src/i18n/Lang.astro`, so no copy is typed into a template.
- WHILE any new page renders THE SYSTEM SHALL NOT set any translated string in
  `var(--font-editorial)` (Instrument Serif ships no Cyrillic subset); translated
  headings and body text use the Onest-backed display face.
- WHEN the site is built THE SYSTEM SHALL emit, on every page under `dist/`, an
  equal number of occurrences of `class="l en"` and `class="l ru"`, enforced by
  the existing check in `scripts/check-dist.mjs`.
- WHEN the site is built THE SYSTEM SHALL emit no `.js` file under `dist/` and
  add no inline `<script>` beyond the one preference script already in
  `src/layouts/Base.astro`, enforced by `scripts/check-dist.mjs` and
  `scripts/csp-hash.mjs`.
- WHEN `npm test` runs THE SYSTEM SHALL execute a test file covering the new
  helper functions and the new page sources, registered in the `test` script in
  `package.json`.

## Copy

Every string below is the contract. It goes into `src/i18n/ui.ts` character for
character, as an `{ en, ru }` pair.

### Intro

- `colophonIntro.en`: `This site is built only through the DevLoop and deployed only through the platform's MCP tools. The table below is generated from the journal at build time; nothing in it is typed by hand.`
- `colophonIntro.ru`: `Этот сайт собирается только через DevLoop и деплоится только через MCP-инструменты платформы. Таблица ниже генерируется из журнала при сборке; ничего в ней не вписано вручную.`

### Section headings

- `colophonChainHeading`: en `Build and deploy chain` / ru `Цепочка сборки и деплоя`
- `colophonCyclesHeading`: en `Cycles` / ru `Циклы`
- `colophonDecisionsHeading`: en `Decisions` / ru `Решения`

### Build and deploy chain bullets (`colophonChainItems`, five items, in this order)

EN:

1. `Source: github.com/mctlhq/portfolio`
2. `Image: ghcr.io/mctlhq/portfolio, built by mctl-gitops from a release tag`
3. `Runtime: Astro static output served by nginx on k3s, tenant labs`
4. `Release: release-please; deploy dispatched to release-deploy in mctl-gitops; ArgoCD syncs the image tag`
5. `Onboarding, rollbacks and custom domains: mctl MCP tools only`

RU:

1. `Исходники: github.com/mctlhq/portfolio`
2. `Образ: ghcr.io/mctlhq/portfolio, собирается mctl-gitops из тега релиза`
3. `Рантайм: статический вывод Astro, отдаваемый nginx на k3s, тенант labs`
4. `Релиз: release-please; деплой запускается через release-deploy в mctl-gitops; ArgoCD синхронизирует тег образа`
5. `Онбординг, откаты и кастомные домены: только MCP-инструменты mctl`

### Table headers, captions and totals

- `colophonPageTitle`: en `Colophon — Dmitrii Mashkov` / ru `Colophon — Dmitrii Mashkov`
- `cycleTableCaption`: en `DevLoop cycles, newest first` / ru `Циклы DevLoop, сначала новые`
- `adrTableCaption`: en `Architecture decision records` / ru `Записи архитектурных решений`
- `colDate`: en `Date` / ru `Дата`
- `colService`: en `Service` / ru `Сервис`
- `colTitle`: en `Title` / ru `Название`
- `colIssue`: en `Issue` / ru `Issue`
- `colPr`: en `PR` / ru `PR`
- `colRelease`: en `Release` / ru `Релиз`
- `colLeadTime`: en `Lead time, h` / ru `Lead time, ч`
- `colInterventions`: en `Interventions` / ru `Вмешательства`
- `colAdrId`: en `ID` / ru `ID`
- `colAdrStatus`: en `Status` / ru `Статус`
- `totalCycles`: en `Public cycles` / ru `Публичных циклов`
- `totalInterventions`: en `Interventions in total` / ru `Вмешательств всего`

### Entry page labels

- `journalKicker`: en `DevLoop cycle` / ru `Цикл DevLoop`
- `journalDecidedLabel`: en `What was decided` / ru `Что решено`
- `journalTimestampsLabel`: en `Timestamps` / ru `Таймстампы`
- `journalIssueOpened`: en `Issue opened` / ru `Issue открыт`
- `journalProposalApproved`: en `Proposal approved` / ru `Предложение одобрено`
- `journalMerged`: en `Merged` / ru `Смержено`
- `journalReleased`: en `Released` / ru `Релиз опубликован`
- `journalDeployed`: en `Deployed` / ru `Задеплоено`
- `journalInterventionWhy`: en `Why` / ru `Почему`
- `adrKicker`: en `Architecture decision record` / ru `Запись архитектурного решения`
- `adrSupersedesLabel`: en `Supersedes` / ru `Заменяет`
- `colophonBackLink`: en `Back to the colophon` / ru `Назад к колофону`

### ADR status labels (`adrStatusLabel`, a separate export, not a `ui` key)

- `proposed`: en `Proposed` / ru `Предложен`
- `accepted`: en `Accepted` / ru `Принят`
- `superseded`: en `Superseded` / ru `Заменён`
- `deprecated`: en `Deprecated` / ru `Устарел`

### Copy: P3 journal entry

New file
`src/content/journal/2026-09-11-content-collections-for-projects-journal-and-adrs.md`,
frontmatter only, no body:

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
  en: "The site's content became typed: three Astro collections — projects, journal and adr — with strict schemas and loaders that check en/ru parity, ADR section order and timestamp format on every build, plus the first ADRs and journal entries, so every later page reads content instead of carrying it."
  ru: "Контент сайта стал типизированным: три коллекции Astro — projects, journal и adr — со строгими схемами и загрузчиками, которые на каждой сборке проверяют паритет en/ru, порядок разделов ADR и формат таймстампов, а также первые ADR и записи журнала, поэтому все последующие страницы читают контент, а не содержат его."
issue_opened_at: '2026-09-10T22:45:34Z'
proposal_approved_at: '2026-09-11T01:54:03Z'
merged_at: '2026-09-11T03:02:47Z'
released_at: '2026-09-11T03:06:49Z'
---
```

### Copy: backfilled timestamps

Add these four keys to each existing entry, keeping the key order used by the
other entries (`pr` and `release` directly after `proposal_slug`, `merged_at`
and `released_at` after `proposal_approved_at`). Change nothing else.

`src/content/journal/2026-09-11-home-page.md` (P4, issue 6):

```yaml
pr: https://github.com/mctlhq/portfolio/pull/24
release: 0.1.3
merged_at: '2026-09-11T04:04:03Z'
released_at: '2026-09-11T04:06:16Z'
```

`src/content/journal/2026-09-11-work-page.md` (P5, issue 7):

```yaml
pr: https://github.com/mctlhq/portfolio/pull/28
release: 0.1.4
merged_at: '2026-09-11T06:41:07Z'
released_at: '2026-09-11T06:46:15Z'
```

`src/content/journal/2026-09-11-approach-page.md` (P6, issue 8):

```yaml
pr: https://github.com/mctlhq/portfolio/pull/32
release: 0.1.5
merged_at: '2026-09-11T09:24:24Z'
released_at: '2026-09-11T09:26:43Z'
```

## Out of scope

- The metrics snapshot and its generator (P8b). `/colophon/` shows no number
  read from `src/data/metrics.json`; its two totals come from the journal
  collection.
- The production-evidence entries (P9): no `deployed_at` value is added to any
  journal entry in this cycle, and no deployment is performed.
- Any change to `src/pages/index.astro`, `src/pages/work.astro`,
  `src/pages/approach.astro`, `nginx.conf`, the `Dockerfile` or the CSP header.
- A new ADR. This cycle writes no `src/content/adr/NNNN-*.md` file.
- Changing `src/lib/journal.ts`: `leadTimeHours` and `interventionCount` are
  used as they are.
- Any deploy, rollback, DNS or custom-domain operation.

## Open questions

- The issue does not state which date the table's date column shows. This
  proposal uses the entry id's `YYYY-MM-DD` prefix, because it is the one date a
  human chose for the cycle and it is timezone-free; `issue_opened_at` is used
  only to break ties in the sort.
- The issue does not state the precision of the lead time column. This proposal
  uses one decimal place (`0.7`, `4.3`), which is what the two entries that
  currently carry a `deployed_at` need to stay readable.
- The issue does not state the order of the ADR index. This proposal sorts it by
  `id` ascending, so ADR-0001 reads first and the numbering is the reading order.
- The issue does not supply the title and `decided` copy for the missing P3
  entry, nor the column headers and entry-page labels. This proposal writes all
  of them, above, so the implementer never has to invent prose.
- The issue does not say whether the URLs inside the "Build and deploy chain"
  bullets should be clickable. They stay plain text so the supplied copy is
  reproduced character for character in both languages.
- `ui.footerColophonLabel` exists and is still unused after this cycle; the
  colophon link is added to the primary navigation (`ui.navColophon`) instead of
  the footer, to keep the footer to source and release.
