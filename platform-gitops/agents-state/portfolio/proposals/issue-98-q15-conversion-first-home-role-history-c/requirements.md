# Q15: conversion-first home — role, history, capabilities and a visible contact

## Context

The home page of `dmitriimashkov.com` (`src/pages/index.astro`) renders a name
(`ui.heroName`), a thesis sentence (`ui.heroThesis`), a subline
(`ui.heroSubline`), four metric tiles fed from `src/data/metrics.json`, two
CTAs (`/work/` and `/colophon/`) and three `<Details>` disclosures, the last of
which holds a GitHub link and an email address. A recruiter, an HR screener or
a CTO landing on the page cannot answer the three questions they arrive with:
who is this person, what can he do, and what has he actually built. There is no
role, no seniority, no years, no domain, no employment history, no capability
statement, and the only contact route is hidden inside a disclosure widget.

This cycle rewrites the home page so the first screen states the role and the
one-line value, and the rest of the page states nine years of history, three
capability areas, and four contact routes — all of it visible without
interaction, in both languages, with no invented number. It also corrects one
service link on `/work/` (`mctl-loyalty` now points at its brand host) and adds
`Person` and `WebSite` JSON-LD on the home route only.

Every user-facing string this cycle introduces is fixed copy and is reproduced
character for character in **Appendix A** of this file. The implementer must
copy from Appendix A; no string may be paraphrased, translated, re-cased or
re-punctuated.

## User stories

- AS an HR screener landing on the home page I WANT the role and seniority
  above the name SO THAT I can decide in five seconds whether to keep reading.
- AS a hiring CTO I WANT a readable employment history and three capability
  areas SO THAT I can judge depth without opening another page.
- AS an interested reader I WANT four visible contact routes SO THAT I can
  reach the author without expanding a disclosure widget.
- AS a Russian-speaking reader I WANT every new section in Russian SO THAT the
  page reads as written rather than translated, with JavaScript disabled.
- AS a search engine or a link preview I WANT `Person` and `WebSite` structured
  data on the home route SO THAT the identity behind the site is machine-readable.
- AS a visitor of `/work/` I WANT the `mctl-loyalty` service link to point at
  the live brand host SO THAT the link I click is the product's real address.
- AS the maintainer I WANT every existing mechanical gate (CSP hash, bilingual
  parity, dist checks, link check, title budget) to keep passing SO THAT this
  cycle proves itself the way every other cycle does.

## Acceptance criteria (EARS)

### A. Hero

- WHEN the home page renders THE SYSTEM SHALL emit an eyebrow line bound to the
  new `ui.heroEyebrow` key directly above the existing `<h1 class="hero-name">`,
  as an `.l.en` / `.l.ru` pair.
- WHILE the hero renders THE SYSTEM SHALL keep `heroName`, `heroThesis` and
  `heroSubline` at their current values and in their current order.
- WHEN the home page renders THE SYSTEM SHALL emit the `.ctas` nav containing
  exactly two links, in this order: `ctaContact` pointing at `#contact` and
  carrying `class="cta cta-primary"`, then `ctaWork` pointing at `/work/` and
  carrying `class="cta"`.
- WHEN the home page renders THE SYSTEM SHALL NOT render `ui.ctaColophon`
  anywhere on the home page.
- WHILE `Nav.astro` and `Footer.astro` are unchanged THE SYSTEM SHALL keep the
  colophon reachable from the navigation and the footer, and
  `test/nav.test.ts` and `test/footer.test.ts` SHALL still pass.
- WHEN the home page renders THE SYSTEM SHALL place the `.ctas` nav (and its
  `#ctas-label` visually-hidden label) directly after the hero subline and
  before the identity section, so the document order is: eyebrow, `<h1>`,
  thesis, subline, CTAs, identity, capabilities, stats, the two remaining
  disclosures, contact.

### B. Identity section

- WHEN the home page renders THE SYSTEM SHALL emit a `<section id="about">`
  directly after the `.ctas` nav and before the stats section, carrying a
  visible `<h2>` bound to `ui.aboutHeading`.
- WHEN the identity section renders THE SYSTEM SHALL emit the three strings of
  `ui.aboutParagraphs`, in order, each as its own `<p>`, in both `.l.en` and
  `.l.ru` variants.
- IF the identity section were wrapped in a `<details>` element THEN THE SYSTEM
  SHALL fail its tests: the section is a plain `<section>`, readable without
  interaction.
- WHILE the identity copy renders THE SYSTEM SHALL NOT name the current
  employer, link to it, or show its logo.

### C. Capability section

- WHEN the home page renders THE SYSTEM SHALL emit a `<section
  id="capabilities">` directly after the identity section, carrying a visible
  `<h2>` bound to `ui.capabilitiesHeading`.
- WHEN the capability section renders THE SYSTEM SHALL emit the three entries
  of `ui.capabilityItems`, in order, each as an `<h3>` carrying the entry's
  `term` followed by one `<p>` carrying the entry's `body`, in both `.l.en` and
  `.l.ru` variants.

### D. Contact section

- WHEN the home page renders THE SYSTEM SHALL emit a `<section id="contact">`
  carrying a visible `<h2>` bound to `ui.contactHeading`, a paragraph bound to
  `ui.contactIntro`, and a list of the four `ui.contactItems` entries, in
  order, each rendering an `<a href>` equal to the entry's `href` whose visible
  text is the entry's `text`, with the entry's `label` rendered as the link's
  bilingual label.
- WHEN the home page renders THE SYSTEM SHALL NOT render the
  `ui.detailsContactSummary` disclosure, and SHALL keep the other two
  `<Details>` uses (`detailsRunSummary`, `detailsWorkSummary`) unchanged, each
  still carrying the `heading` prop.
- WHEN the home page renders THE SYSTEM SHALL emit zero `<details open>`
  elements and exactly two `<summary><h2` openings.

### E. One link correction on `/work/`

- WHEN `/work/` renders the `mctl-loyalty` card THE SYSTEM SHALL emit the
  service link `https://rewards.mctl.ai`.
- WHILE `dist/` exists THE SYSTEM SHALL contain the string
  `labs-mctl-loyalty.mctl.ai` on no page.
- WHEN `test/projects.test.ts` runs THE SYSTEM SHALL assert the `mctl-loyalty`
  row as `{ slug: 'mctl-loyalty', url: 'https://rewards.mctl.ai', en: 'Service',
  ru: 'Сервис' }`.
- WHILE section E is implemented THE SYSTEM SHALL change nothing else on
  `/work/`.

### F. Structured data

- WHEN the home route renders THE SYSTEM SHALL emit exactly one
  `application/ld+json` block from `src/layouts/Base.astro`, containing a
  `Person` node and a `WebSite` node.
- WHEN the `Person` node is parsed THE SYSTEM SHALL expose exactly these five
  fields: `name` `Dmitrii Mashkov`, `url` `https://dmitriimashkov.com/`,
  `jobTitle` `Senior platform engineer`, `email`
  `mailto:hello@dmitriimashkov.com`, and `sameAs` with exactly these three
  entries in this order: `https://www.linkedin.com/in/dmitriimashkov`,
  `https://github.com/mctlhq`, `https://t.me/dmitriimashkov`.
- WHEN the `WebSite` node is parsed THE SYSTEM SHALL expose `name` `Dmitrii
  Mashkov`, `url` `https://dmitriimashkov.com/` and `inLanguage` `en`, and no
  `SearchAction`.
- WHILE the graph is emitted THE SYSTEM SHALL carry no `worksFor`, no
  `address`, no `alumniOf` and no `telephone`.
- WHILE any non-home route renders THE SYSTEM SHALL NOT emit the `Person` or
  `WebSite` graph, and `dist/colophon/journal/*/index.html` SHALL still contain
  its `BreadcrumbList` block.
- WHEN `scripts/csp-hash.mjs`, `node scripts/check-headers.mjs` and
  `test/csp.test.ts` run THE SYSTEM SHALL be unaffected by the new JSON-LD: the
  inline-script SHA-256 in the CSP is unchanged, because
  `INLINE_SCRIPT_RE` in `src/lib/csp.ts` already excludes
  `type="application/ld+json"` and the emission site in `Base.astro` is
  unchanged in shape.

### G. Strings and parity

- WHEN `src/i18n/ui.ts` is read THE SYSTEM SHALL contain `heroEyebrow`,
  `ctaContact`, `aboutHeading`, `aboutParagraphs`, `capabilitiesHeading`,
  `capabilityItems`, `contactHeading`, `contactIntro` and `contactItems`, each
  with `en` and `ru`, character for character as written in Appendix A.
- WHEN `test/ui.test.ts` runs THE SYSTEM SHALL still pass its en/ru parity
  check, extended so that an array of `{ term, body }` or `{ label, href, text }`
  objects is accepted: `en` and `ru` must be the same kind, the same length, and
  every object in the pair must carry the same key set with non-empty string
  values.
- WHEN `test/ui.test.ts` runs THE SYSTEM SHALL assert the nine new keys'
  EN and RU values character for character, in the style of the existing exact
  value tests in that file.

### H. Rendered-page assertions

- WHEN the built home page is inspected THE SYSTEM SHALL contain the eyebrow
  text, each of the three identity paragraphs, each of the three capability
  terms with their bodies, the contact intro, and the four contact links — all
  of them in both `.l.en` and `.l.ru` variants.
- WHEN the built home page is inspected THE SYSTEM SHALL contain no `<details>`
  element wrapping the text of `aboutParagraphs`, `capabilityItems` or
  `contactItems`.
- WHEN `dist/index.html` is parsed THE SYSTEM SHALL contain exactly one
  `application/ld+json` block, and a test SHALL `JSON.parse` it rather than
  match a substring before asserting the fields in section F.
- WHILE `scripts/check-dist.mjs` runs (it runs inside the Dockerfile build)
  THE SYSTEM SHALL expect zero `<details open>` and exactly two `<summary><h2`
  openings on `dist/index.html` instead of the current one and three, and SHALL
  additionally assert the home page's parsed JSON-LD graph.
- WHILE any built page is checked THE SYSTEM SHALL keep equal counts of
  `class="l en"` and `class="l ru"` on every `dist/**/*.html`, the bilingual
  parity rule `scripts/check-dist.mjs` already enforces.

### I. Budgets, links and the suite

- WHEN `dist/index.html` is built THE SYSTEM SHALL keep `<title>` exactly
  `Dmitrii Mashkov` and its meta description within the budgets
  `test/title.test.ts` and `scripts/check-dist.mjs` enforce (75 characters
  hard limit on a title; the description prop is not lengthened by this cycle).
- WHEN `npm run vendor && npm test`, `npm run build` and `node
  scripts/check-links.mjs` run THE SYSTEM SHALL pass.
- WHEN `node scripts/check-links.mjs` runs THE SYSTEM SHALL report
  `https://rewards.mctl.ai`, `https://www.linkedin.com/in/dmitriimashkov` and
  `https://t.me/dmitriimashkov` in its listed, counted skipped set — never
  silently dropped and never counted as `checked` — because the script makes no
  network request by design (`docs/link-check.md`). A test SHALL assert that
  each of the three off-origin hrefs is classified `skipped` with reason
  `off-origin` and appears in `run()`'s `skipped` map, so an external host the
  checker cannot reach is reported rather than passed over in silence.
- WHEN `node scripts/check-headers.mjs` runs against the built image in CI THE
  SYSTEM SHALL pass unchanged.

### J. Journal

- WHEN this cycle is implemented THE SYSTEM SHALL add exactly one journal entry
  under `src/content/journal/` carrying `status: in_progress`, `service:
  portfolio`, `issue: https://github.com/mctlhq/portfolio/issues/98`,
  `proposal_slug: issue-98-q15-conversion-first-home-role-history-c`,
  `visibility: public`, bilingual `title`, bilingual `decided`,
  `interventions: []` and a single-quoted ISO-8601 `issue_opened_at`.
- WHILE that entry exists THE SYSTEM SHALL carry none of `pr`, `merged_at`,
  `release`, `released_at`, `deployed_at`.
- WHILE the journal collection loads THE SYSTEM SHALL hold at most one
  `in_progress` entry (`checkJournalCollection` in `src/lib/journal.ts`).
- IF the entry's computed `<title>` (`title.en` + ` — Dmitrii Mashkov`) exceeds
  65 characters THEN THE SYSTEM SHALL carry a `seoTitle` of at most 65
  characters, as `test/title.test.ts` requires.

## Out of scope

- Naming the current employer anywhere on the site, in any language, or linking
  to it.
- Any availability or "open to work" statement, in any wording, in either
  language.
- Any city or country of residence. `contactIntro` states the working mode, the
  working hours and the relocation preference, and nothing beyond that.
- Version numbers on any language, framework or runtime named in the copy.
  `Java`, not `Java 21`; `Spring Boot`, not `Spring Boot 3`. A version is true
  for a year and then quietly dates the page. The one exception is a protocol
  whose version is part of its name: `OAuth 2.1`.
- A separate `/about/` page, navigation relabelling and the footer "Lab"
  grouping — those belong to the information-architecture cycle.
- Case-study pages, project schema extensions and outcome numbers with source
  URLs — a later cycle.
- A portrait, a logo or any new binary asset.
- Any new third-party runtime request, any second inline script, and any change
  to the metrics pipeline. Every number on the page still comes from
  `src/data/metrics.json`.
- Publishing any performance, revenue, user-count or percentage claim about the
  unnamed employer's systems. No number without a source the reader can open.
- Any change to `/work/` other than the one `mctl-loyalty` URL correction.
- Any change to `src/components/Details.astro` itself, to `Nav.astro`, to
  `Footer.astro`, or to the CSP inline-script body.

## Open questions

1. **Where the `.ctas` nav sits.** Section A says the CTAs "stay where the
   current `.ctas` nav is" (today: after the stats), while section B requires
   the identity section "directly after the CTAs and before the stats". Both
   cannot hold. Reviewer step 1 requires the eyebrow, the name, the thesis and
   both CTAs inside a 390x844 viewport, which four stat tiles between the
   subline and the CTAs would prevent. Interpretation taken: the CTAs keep
   their markup (the same `.ctas` nav element and `#ctas-label`) but move up to
   directly after the subline, giving hero -> CTAs -> identity -> capabilities
   -> stats. Recorded, not blocking.
2. **What "check-links must resolve" means for external hosts.**
   `scripts/check-links.mjs` opens no socket by design (`docs/link-check.md`;
   `test/links.test.ts` fails the build if the source ever contains `fetch(`,
   `node:http`, `retry`, ...). Interpretation taken: the three external URLs
   must appear in the counted, listed `skipped` set with reason `off-origin`,
   which is precisely "reported rather than passed silently"; no network check
   is added. Recorded, not blocking.
3. **`ui.ctaColophon` and `ui.detailsContactSummary` become unused.** The issue
   removes their only render sites but does not ask for the keys to be deleted.
   Interpretation taken: keep both keys in `src/i18n/ui.ts` (no test forbids an
   unused key; `ui.notFoundContact` is precedent for a key used on one page
   only), so the diff stays additive on the dictionary.
4. **`issue_opened_at` for the journal entry.** The exact GitHub creation
   timestamp of issue #98 is not in the proposal. Interpretation taken: the
   implementer reads it from GitHub (`gh issue view 98 --repo mctlhq/portfolio
   --json createdAt`) and writes it single-quoted; if that is unavailable, use
   an ISO-8601 `Z` timestamp on 2026-09-13 that precedes the commit, since
   `timestampOrderProblems` only requires lifecycle stamps to be nondecreasing
   and no other stamp is recorded on an `in_progress` entry.
5. **`indexing` on the new journal entry.** Not specified. Interpretation
   taken: `indexing: noindex`, matching the four most recent cycle entries.

## Appendix A — Exact copy (character for character)

### A.1 `heroEyebrow`

- en: `Senior platform engineer · AI-native delivery`
- ru: `Старший платформенный инженер · доставка с AI-агентами`

### A.2 `ctaContact`

- en: `Get in touch`
- ru: `Написать`

### A.3 `aboutHeading`

- en: `Who I am`
- ru: `Кто я`

### A.4 `aboutParagraphs` (array of three, in this order)

en:

1. `Nine years of production engineering. Since 2021, backend and platform work for a global retail-trading fintech: high-availability services on AWS EKS and ECS, Kafka event streaming for market data and order flow, and transaction processing that cannot double-count a balance update. Since 2024 I also review architecture and code for several core financial microservices as the team's Java and Spring component mentor.`
2. `Before that, four years of Python at a large retail chain — forecasting services and spatial data pipelines over PostGIS — the last of them leading a team of four engineers end to end, from prioritisation with the business to production rollout.`
3. `Since early 2026 I build and operate mctl.ai in the open: a multi-tenant Kubernetes platform where AI agents carry the delivery work and humans hold the gates. This site is one of the services running on it, and every cycle that changed it is recorded on the colophon.`

ru:

1. `Девять лет продакшн-инженерии. С 2021 года — бэкенд и платформа для глобального финтеха розничного трейдинга: высокодоступные сервисы на AWS EKS и ECS, потоковая обработка рыночных данных и потока ордеров через Kafka, обработка транзакций, в которой изменение баланса невозможно применить дважды. С 2024 года дополнительно ревьюю архитектуру и код нескольких ключевых финансовых микросервисов как component mentor команды по Java и Spring.`
2. `До этого — четыре года Python в крупной розничной сети: сервисы прогнозирования и конвейеры пространственных данных на PostGIS. Последний из них — с командой из четырёх инженеров, от приоритизации с бизнесом до выката в продакшн.`
3. `С начала 2026 года строю и эксплуатирую mctl.ai в открытую: мультитенантную платформу на Kubernetes, где доставку ведут AI-агенты, а люди стоят на контрольных точках. Этот сайт — один из сервисов на ней, и каждый изменивший его цикл записан в колофоне.`

### A.5 `capabilitiesHeading`

- en: `What I do`
- ru: `Что я умею`

### A.6 `capabilityItems` (array of three `{ term, body }`, in this order)

en:

1. term: `Platform and GitOps delivery`
   body: `Multi-tenant Kubernetes from bare cloud up: OpenTofu, ArgoCD app-of-apps, Argo Workflows and Argo Rollouts, one Helm delivery contract that every service uses, Vault with External Secrets, CloudNativePG, Traefik and cert-manager, Backstage golden paths. Tenant isolation, RBAC, quotas and network policies. Every change is committed, reviewable and reversible.`
2. term: `Agentic delivery systems`
   body: `Role-specific agents that turn an issue into a proposal, an approved proposal into a pull request, and a clean review into a merge — with explicit human gates before implementation and before merge. Remote MCP servers in production: OAuth 2.1 with PKCE, tenant-scoped RBAC, durable workflow execution and tamper-evident audit logs.`
3. term: `Backend under load`
   body: `Python and Java on Spring Boot, FastAPI, Kafka, PostgreSQL and Redis. Event-driven microservices for real-time market data and order flow, idempotent transaction processing with correlation-key deduplication, and fraud-prevention workflows under regulatory constraints.`

ru:

1. term: `Платформа и GitOps-доставка`
   body: `Мультитенантный Kubernetes с нуля: OpenTofu, ArgoCD в схеме app-of-apps, Argo Workflows и Argo Rollouts, единый Helm-контракт доставки для всех сервисов, Vault с External Secrets, CloudNativePG, Traefik и cert-manager, golden paths в Backstage. Изоляция тенантов, RBAC, квоты и сетевые политики. Любое изменение закоммичено, обозримо и обратимо.`
2. term: `Агентские системы доставки`
   body: `Ролевые агенты, которые превращают issue в предложение, одобренное предложение — в pull request, а чистое ревью — в мерж, с явными человеческими контрольными точками перед реализацией и перед мержем. Удалённые MCP-серверы в проде: OAuth 2.1 с PKCE, RBAC в границах тенанта, устойчивое выполнение воркфлоу и журнал аудита с защитой от подмены.`
3. term: `Бэкенд под нагрузкой`
   body: `Python и Java на Spring Boot, FastAPI, Kafka, PostgreSQL и Redis. Событийные микросервисы для рыночных данных и потока ордеров в реальном времени, идемпотентная обработка транзакций с дедупликацией по корреляционному ключу, антифрод-сценарии в условиях регуляторных требований.`

### A.7 `contactHeading`

- en: `Get in touch`
- ru: `Связаться`

### A.8 `contactIntro`

- en: `Fully remote, Central European hours. Open to relocation in the EU. Email is the fastest way through.`
- ru: `Полностью удалённо, по центральноевропейскому времени. Открыт к релокации в ЕС. Быстрее всего — почта.`

### A.9 `contactItems` (array of four `{ label, href, text }`, in this order)

`href` and `text` are identical in both languages; only `label` differs.

1. label en: `Email`; label ru: `Почта`; href: `mailto:hello@dmitriimashkov.com`; text: `hello@dmitriimashkov.com`
2. label en: `LinkedIn`; label ru: `LinkedIn`; href: `https://www.linkedin.com/in/dmitriimashkov`; text: `linkedin.com/in/dmitriimashkov`
3. label en: `GitHub`; label ru: `GitHub`; href: `https://github.com/mctlhq`; text: `github.com/mctlhq`
4. label en: `Telegram`; label ru: `Telegram`; href: `https://t.me/dmitriimashkov`; text: `@dmitriimashkov`

### A.10 The `/work/` link correction

In `src/content/projects/mctl-loyalty.en.md` and
`src/content/projects/mctl-loyalty.ru.md`, change:

```
    url: https://labs-mctl-loyalty.mctl.ai
```

to:

```
    url: https://rewards.mctl.ai
```

and in `test/projects.test.ts`, change the expected row:

```
  { slug: 'mctl-loyalty', url: 'https://labs-mctl-loyalty.mctl.ai', en: 'Service', ru: 'Сервис' },
```

to:

```
  { slug: 'mctl-loyalty', url: 'https://rewards.mctl.ai', en: 'Service', ru: 'Сервис' },
```

### A.11 Structured-data literals

- `Person`: `name` `Dmitrii Mashkov`; `url` `https://dmitriimashkov.com/`;
  `jobTitle` `Senior platform engineer`; `email`
  `mailto:hello@dmitriimashkov.com`; `sameAs`
  `["https://www.linkedin.com/in/dmitriimashkov", "https://github.com/mctlhq", "https://t.me/dmitriimashkov"]`.
- `WebSite`: `name` `Dmitrii Mashkov`; `url` `https://dmitriimashkov.com/`;
  `inLanguage` `en`.

## Reviewer steps (not implementer criteria)

1. At 390x844 and at 360x640, confirm the eyebrow, the name, the thesis and
   both CTAs are inside the first viewport, and that the primary CTA is
   visually distinguishable from the secondary one.
2. Confirm the page reads correctly in Russian with JavaScript disabled —
   English renders first and the Russian variants are hidden by CSS alone.
3. After release and deployment, confirm the four contact links resolve and
   that the `Person` JSON-LD validates.
