# P7: Colophon page, journal and ADR routes, cycle table and backfill

## Context

The site already carries a typed `journal` and `adr` content collection
(`src/content.config.ts`, added in P3) and a computed lead time / intervention
helper (`src/lib/journal.ts`), but nothing renders them: `src/pages/` has
`index.astro`, `work.astro`, `approach.astro`, `404.astro` and a dev-only
`dev/[check].astro`. The home page already links to `/colophon/`
(`src/pages/index.astro`, `ui.ctaColophon`) and `src/i18n/ui.ts` already
declares `navColophon` and `footerColophonLabel`, so the site currently ships a
call to action that resolves to the 404 page.

This cycle makes the site its own evidence. `/colophon/` explains how the site
is built and deployed, lists every public DevLoop cycle in a table computed from
the journal frontmatter (lead time in hours, intervention count), lists the
ADRs, and gives every public journal entry and every public ADR its own page.
Four cycles that already happened (P3, P4, P5, P6) are backfilled from GitHub so
the table is a record rather than a sketch — including the seven manual
interventions of the P5 cycle, which are the point of the page: that cycle is
the one where the loop needed a human, and the page says so in the loop's own
data.

## User stories

- AS a visitor evaluating the claim "built by an agent loop" I WANT one page
  that lists every cycle with its issue, pull request, release and manual
  intervention count SO THAT I can verify the claim against GitHub instead of
  trusting the prose.
- AS a visitor reading a single cycle I WANT its own page with the timeline and
  the verbatim record of each manual intervention SO THAT I can see where the
  loop needed a human and why.
- AS a visitor auditing the engineering decisions I WANT an ADR index and one
  page per ADR SO THAT I can read the Nygard record behind each decision.
- AS a Russian-reading visitor I WANT every explanatory string on these pages in
  Russian SO THAT the colophon reads as written rather than translated.
- AS the repository owner I WANT the cycle count, the intervention total, the
  lead time and the release tag to be derived at build time SO THAT no number on
  the page can drift from the files it is supposed to describe.

## Acceptance criteria (EARS)

### Routes and visibility

- WHEN `astro build` runs THE SYSTEM SHALL emit `dist/colophon/index.html` from
  `src/pages/colophon/index.astro`.
- WHEN `astro build` runs THE SYSTEM SHALL emit
  `dist/colophon/journal/<id>/index.html` for every entry of the `journal`
  collection whose `visibility` is `public`, where `<id>` is the entry id
  (the filename stem, e.g. `2026-09-11-work-page`), via `getStaticPaths` in
  `src/pages/colophon/journal/[...slug].astro`.
- WHEN `astro build` runs THE SYSTEM SHALL emit
  `dist/colophon/adr/<id>/index.html` for every entry of the `adr` collection
  whose `visibility` is `public`, via `getStaticPaths` in
  `src/pages/colophon/adr/[...slug].astro`.
- IF an entry of either collection has `visibility: private` THEN THE SYSTEM
  SHALL emit no page for it, SHALL omit it from the cycle table and the ADR
  index, and SHALL leave its id absent from every file under `dist/`.
- WHILE the site is served by nginx THE SYSTEM SHALL resolve
  `/colophon/journal/<id>/` and `/colophon/adr/<id>/` through the existing
  `try_files $uri $uri/index.html $uri.html =404` rule in `nginx.conf`, with no
  change to `nginx.conf`.

### Computed numbers

- WHEN `src/pages/colophon/index.astro` renders the cycle total THE SYSTEM SHALL
  use the number of `journal` entries with `visibility: public`, computed from
  the collection, with no integer literal for that total anywhere in `src/`.
- WHEN `src/pages/colophon/index.astro` renders the intervention total THE
  SYSTEM SHALL use the sum of `interventionCount(entry.data)` over those same
  entries, with no integer literal for that total anywhere in `src/`.
- WHEN a row's lead time is rendered THE SYSTEM SHALL use
  `leadTimeHours(entry.data)` from `src/lib/journal.ts`, formatted to one
  decimal place.
- IF `leadTimeHours` returns `null` for an entry THEN THE SYSTEM SHALL render an
  em dash (`—`) in that row's lead time cell.
- WHEN a row's intervention cell is rendered THE SYSTEM SHALL use
  `interventionCount(entry.data)`, rendering `0` as `0` and never as an em dash.
- WHILE the `journal` collection schema is in force THE SYSTEM SHALL keep lead
  time and intervention count out of frontmatter: `grep -rn "lead_time" src/content`
  and `grep -rn "intervention_count" src/content` SHALL both produce no output.
- WHEN `src/components/Footer.astro` renders the release THE SYSTEM SHALL read
  it from `package.json` via `import pkg from '../../package.json'` and render
  `pkg.version` unchanged (semver with no `v` prefix), with no version literal
  typed into the component.

### Page content

- WHEN `/colophon/` renders THE SYSTEM SHALL show the intro paragraph as an
  `.l.en` / `.l.ru` pair with exactly this text:
  - EN: `This site is built only through the DevLoop and deployed only through the platform's MCP tools. The table below is generated from the journal at build time; nothing in it is typed by hand.`
  - RU: `Этот сайт собирается только через DevLoop и деплоится только через MCP-инструменты платформы. Таблица ниже генерируется из журнала при сборке; ничего в ней не вписано вручную.`
- WHEN `/colophon/` renders THE SYSTEM SHALL show a section headed
  `Build and deploy chain` / `Цепочка сборки и деплоя` containing exactly these
  five bullets, in this order:
  - EN: `Source: github.com/mctlhq/portfolio`
  - EN: `Image: ghcr.io/mctlhq/portfolio, built by mctl-gitops from a release tag`
  - EN: `Runtime: Astro static output served by nginx on k3s, tenant labs`
  - EN: `Release: release-please; deploy dispatched to release-deploy in mctl-gitops; ArgoCD syncs the image tag`
  - EN: `Onboarding, rollbacks and custom domains: mctl MCP tools only`
  - RU: `Исходники: github.com/mctlhq/portfolio`
  - RU: `Образ: ghcr.io/mctlhq/portfolio, собирается mctl-gitops из тега релиза`
  - RU: `Рантайм: статический вывод Astro, отдаваемый nginx на k3s, тенант labs`
  - RU: `Релиз: release-please; деплой запускается через release-deploy в mctl-gitops; ArgoCD синхронизирует тег образа`
  - RU: `Онбординг, откаты и кастомные домены: только MCP-инструменты mctl`
- WHEN `/colophon/` renders THE SYSTEM SHALL show a section headed
  `Cycles` / `Циклы` containing the cycle table, newest first, followed by two
  totals: the number of public cycles and the total number of interventions.
- WHEN `/colophon/` renders THE SYSTEM SHALL show a section headed
  `Decisions` / `Решения` containing an ADR index table with the columns id,
  title, status and date, each row linking to that ADR's page.
- WHEN `src/components/CycleTable.astro` renders a row THE SYSTEM SHALL emit one
  row per public journal entry with these cells in this order: date, service,
  title (linking to that entry's page), issue link, pull request link, release,
  lead time in hours, intervention count.
- IF an entry has no `pr` or no `release` THEN THE SYSTEM SHALL render an em
  dash in that cell.
- WHEN an intervention is rendered on a journal entry page THE SYSTEM SHALL show
  its `what`, `why` and `at` verbatim, inside a container carrying `lang="en"`,
  under a bilingual note stating that these records are quoted in the language
  they were written in.

### Backfill

- WHEN this change is merged THE SYSTEM SHALL contain exactly eight `journal`
  files with `visibility: public`, being the seven that exist today plus one new
  entry for the P3 cycle (issue #5).
- WHEN the P3, P4, P5 and P6 entries are read THE SYSTEM SHALL find in each the
  `pr`, `release`, `merged_at` and `released_at` values listed in `design.md`,
  taken from the GitHub pull request and release records.
- WHEN `src/content/journal/2026-09-11-work-page.md` is read THE SYSTEM SHALL
  find exactly the seven `interventions` items listed verbatim in `design.md`,
  in that order.
- WHILE no portfolio cycle has been deployed through
  `mctl_deploy_service action=onboard` THE SYSTEM SHALL leave `deployed_at`
  absent from every portfolio journal entry, so their lead time cells render an
  em dash.

### Bilingual and payload invariants

- WHEN `node scripts/check-dist.mjs` runs after a build THE SYSTEM SHALL find an
  equal number of `class="l en"` and `class="l ru"` occurrences in every
  `dist/**/*.html`, including the colophon index and every journal and ADR page.
- WHEN `node scripts/check-dist.mjs` runs after a build THE SYSTEM SHALL find no
  file under `dist/` ending in `.js`.
- WHEN `node scripts/check-dist.mjs` runs after a build THE SYSTEM SHALL find no
  `<link>`, `<script>`, `<img>` or `<source>` element in any `dist/**/*.html`
  whose `href`/`src` points at an absolute or protocol-relative URL, and no
  `url(http...)` in any `dist/**/*.css`, so the page issues same-origin requests
  only.
- WHEN `node scripts/check-dist.mjs` runs after a build THE SYSTEM SHALL compare
  the cycle count and the intervention total rendered on
  `dist/colophon/index.html` against counts it derives independently by scanning
  `src/content/journal/*.md` (public files; `- what:` items) and SHALL exit
  non-zero when either disagrees.
- WHILE the page renders no client-side script THE SYSTEM SHALL keep the site
  usable with JavaScript disabled: the tables, both language halves and every
  link work without it.
- WHEN a string on these pages has a Russian counterpart THE SYSTEM SHALL NOT
  set it in `var(--font-editorial)` (`Instrument Serif` ships no Cyrillic
  subset); body and heading text uses `var(--font-display)` (Onest).

## Out of scope

- The metrics snapshot regeneration (P8b) and the production-evidence journal
  entries (P9). No new number is added to `src/data/metrics.json`, and no
  `deployed_at` is invented for a cycle that has not been deployed.
- A journal entry for the P7 cycle itself: it cannot carry its own merge,
  release or deploy timestamps, and belongs to the next cycle's backfill.
- Any new ADR. The ADR index renders `0001`, `0002` and `0005` as they stand;
  the gap at `0003`/`0004` is not filled here.
- Changes to `nginx.conf`, `Dockerfile`, `astro.config.mjs`,
  `.github/workflows/claude-review.yml`, `.github/workflows/release-please.yml`
  or `.github/dependabot.yml`.
- Making `interventions[].what` / `interventions[].why` bilingual. The schema
  field is a single string and the seven P5 records exist only in English; they
  are quoted verbatim.
- Pagination, filtering or sorting controls on the cycle table.

## Open questions

- The issue lists the `date` column without saying which timestamp it shows.
  Interpretation taken: the date of the last event recorded for that cycle
  (`deployed_at ?? released_at ?? merged_at ?? proposal_approved_at ??
  issue_opened_at`), rendered as `YYYY-MM-DD`, which is also the sort key — so
  the visible column and the "newest first" ordering are the same value and
  cannot disagree.
- The issue does not state an order for the ADR index. Interpretation taken:
  ascending by `id` (0001, 0002, 0005), the conventional ADR reading order,
  while the cycle table is explicitly newest first.
- The issue's file list does not mention `Nav.astro`, yet `ui.navColophon` and
  `ui.footerColophonLabel` exist unused and the home page already links to
  `/colophon/`. Interpretation taken: add the Colophon link to `Nav.astro` and
  `Footer.astro` using those existing keys — no new copy is invented. A reviewer
  who wants the nav untouched can drop tasks 9 and 10 without affecting any
  other acceptance criterion.
- No journal entry is `private` today, so the "private entries produce no page"
  criterion is proved by unit tests over the filtering helper plus a
  `check-dist` rule that is currently vacuous and becomes a real gate the moment
  a private entry is added. Shipping a fake private entry to make it non-vacuous
  would put a lie in the journal, so it is not done.
- The issue's acceptance criterion 6 asks for HAR evidence. Per `AGENTS.md`, a
  browser capture cannot be an implementer criterion; it is named as a reviewer
  step here, and the mechanical half (no absolute-URL subresource in `dist/`) is
  a `check-dist` rule instead.
