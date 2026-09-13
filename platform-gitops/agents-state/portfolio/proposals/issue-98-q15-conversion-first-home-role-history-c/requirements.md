# Q15: conversion-first home — role, history, capabilities and a visible contact

## Context

The home page of `dmitriimashkov.com` (`src/pages/index.astro`) renders a name,
a thesis sentence, a subline, four platform counters, two CTA links
(`/work/`, `/colophon/`) and three `<details>` disclosures. It says what the
site is about and nothing about the person behind it. A recruiter or a CTO
landing on it cannot answer the three questions they arrived with: who is
this, what can he do, what has he actually built. There is no role, no
seniority, no years, no domain, no employment history, no capability
statement, and the only contact is an email address inside a disclosure
widget.

This cycle makes the home page answer those three questions in both
languages without inventing a single number: an eyebrow line carrying the
role, a primary "Get in touch" CTA, a plain (non-`<details>`) identity
section with nine years of history, a plain capability section with three
areas, a plain contact section with four links, and `Person` + `WebSite`
JSON-LD on the home route only. It also corrects one project link on
`/work/` (`mctl-loyalty` now has a brand host) and records its own journal
entry. Every claim added is either a plain statement of employment history
or verifiable from a linked source; every number on the page still comes
from `src/data/metrics.json`.

## User stories

- AS an HR screener landing on the home page I WANT the role and one-line
  value in the first screen SO THAT I can decide in seconds whether this
  profile matches the vacancy.
- AS a hiring CTO I WANT nine years of employment history and three named
  capability areas on the page itself, without opening a disclosure widget,
  SO THAT I can judge depth and domain fit before clicking anything.
- AS an interested reader I WANT four visible ways to make contact with a
  stated working mode SO THAT I can reach the person through the channel I
  already use.
- AS a Russian-speaking reader I WANT every new sentence in Russian SO THAT
  the page reads as written rather than translated.
- AS a search engine or a social crawler I WANT `Person` and `WebSite`
  structured data on the home route SO THAT the identity behind the site is
  machine-readable.
- AS the owner of the repository I WANT the copy carried in `src/i18n/ui.ts`
  and asserted by tests SO THAT a future edit that drops a string fails the
  build instead of shipping.

## Acceptance criteria (EARS)

### A. Hero

- WHEN `src/i18n/ui.ts` is loaded THE SYSTEM SHALL expose a new key
  `heroEyebrow` whose `en` is exactly
  `Senior platform engineer · AI-native delivery`
  and whose `ru` is exactly
  `Старший платформенный инженер · доставка с AI-агентами`.
- WHEN `src/i18n/ui.ts` is loaded THE SYSTEM SHALL expose a new key
  `ctaContact` whose `en` is exactly `Get in touch` and whose `ru` is exactly
  `Написать`.
- WHEN the home page renders THE SYSTEM SHALL render the eyebrow line above
  the existing `<h1>`, as an `.l.en` / `.l.ru` pair.
- WHILE the home page renders THE SYSTEM SHALL keep `heroName`, `heroThesis`
  and `heroSubline` at their current values and in their current order.
- WHEN the home page renders THE SYSTEM SHALL render the `.ctas` nav with
  exactly two links, in this order: first `ctaContact` pointing at
  `#contact` and carrying the class `cta cta-primary`; second `ctaWork`
  pointing at `/work/` and carrying the class `cta`.
- WHEN the home page renders THE SYSTEM SHALL NOT render `ctaColophon`
  anywhere on the home page.
- WHILE `ctaColophon` is absent from the home page THE SYSTEM SHALL keep the
  colophon link in `src/components/Nav.astro` and in the footer unchanged, and
  `test/nav.test.ts` and `test/footer.test.ts` SHALL still pass.
- WHEN the home page renders THE SYSTEM SHALL place the `.ctas` nav (and its
  `#ctas-label` visually hidden label) directly after the hero subline and
  before the identity section, so that the eyebrow, the name, the thesis and
  both CTAs form one uninterrupted block at the top of `<main>`.

### B. Identity section

- WHEN `src/i18n/ui.ts` is loaded THE SYSTEM SHALL expose a new key
  `aboutHeading` whose `en` is exactly `Who I am` and whose `ru` is exactly
  `Кто я`.
- WHEN `src/i18n/ui.ts` is loaded THE SYSTEM SHALL expose a new key
  `aboutParagraphs` holding an array of exactly three strings per language,
  in this order, character for character:

  en:

  1. `Nine years of production engineering. Since 2021, backend and platform work for a global retail-trading fintech: high-availability services on AWS EKS and ECS, Kafka event streaming for market data and order flow, and transaction processing that cannot double-count a balance update. Since 2024 I also review architecture and code for several core financial microservices as the team's Java and Spring component mentor.`
  2. `Before that, four years of Python at a large retail chain — forecasting services and spatial data pipelines over PostGIS — the last of them leading a team of four engineers end to end, from prioritisation with the business to production rollout.`
  3. `Since early 2026 I build and operate mctl.ai in the open: a multi-tenant Kubernetes platform where AI agents carry the delivery work and humans hold the gates. This site is one of the services running on it, and every cycle that changed it is recorded on the colophon.`

  ru:

  1. `Девять лет продакшн-инженерии. С 2021 года — бэкенд и платформа для глобального финтеха розничного трейдинга: высокодоступные сервисы на AWS EKS и ECS, потоковая обработка рыночных данных и потока ордеров через Kafka, обработка транзакций, в которой изменение баланса невозможно применить дважды. С 2024 года дополнительно ревьюю архитектуру и код нескольких ключевых финансовых микросервисов как component mentor команды по Java и Spring.`
  2. `До этого — четыре года Python в крупной розничной сети: сервисы прогнозирования и конвейеры пространственных данных на PostGIS. Последний из них — с командой из четырёх инженеров, от приоритизации с бизнесом до выката в продакшн.`
  3. `С начала 2026 года строю и эксплуатирую mctl.ai в открытую: мультитенантную платформу на Kubernetes, где доставку ведут AI-агенты, а люди стоят на контрольных точках. Этот сайт — один из сервисов на ней, и каждый изменивший его цикл записан в колофоне.`

- WHEN the home page renders THE SYSTEM SHALL render a `<section id="about">`
  directly after the CTAs and before the stats, containing a visible `<h2>`
  bound to `aboutHeading` and each `aboutParagraphs` entry as its own `<p>`,
  in both languages.
- WHILE the identity section renders THE SYSTEM SHALL NOT wrap it in a
  `<details>` element and SHALL NOT require interaction to read it.
- WHILE the identity copy renders THE SYSTEM SHALL NOT name, link or
  otherwise identify the employer referred to in paragraph 1, and SHALL NOT
  add a company name, a logo or a link there.

### C. Capability section

- WHEN `src/i18n/ui.ts` is loaded THE SYSTEM SHALL expose a new key
  `capabilitiesHeading` whose `en` is exactly `What I do` and whose `ru` is
  exactly `Что я умею`.
- WHEN `src/i18n/ui.ts` is loaded THE SYSTEM SHALL expose a new key
  `capabilityItems` holding an array of exactly three `{ term, body }`
  objects per language, in this order, character for character:

  en:

  1. term `Platform and GitOps delivery`, body `Multi-tenant Kubernetes from bare cloud up: OpenTofu, ArgoCD app-of-apps, Argo Workflows and Argo Rollouts, one Helm delivery contract that every service uses, Vault with External Secrets, CloudNativePG, Traefik and cert-manager, Backstage golden paths. Tenant isolation, RBAC, quotas and network policies. Every change is committed, reviewable and reversible.`
  2. term `Agentic delivery systems`, body `Role-specific agents that turn an issue into a proposal, an approved proposal into a pull request, and a clean review into a merge — with explicit human gates before implementation and before merge. Remote MCP servers in production: OAuth 2.1 with PKCE, tenant-scoped RBAC, durable workflow execution and tamper-evident audit logs.`
  3. term `Backend under load`, body `Python and Java on Spring Boot, FastAPI, Kafka, PostgreSQL and Redis. Event-driven microservices for real-time market data and order flow, idempotent transaction processing with correlation-key deduplication, and fraud-prevention workflows under regulatory constraints.`

  ru:

  1. term `Платформа и GitOps-доставка`, body `Мультитенантный Kubernetes с нуля: OpenTofu, ArgoCD в схеме app-of-apps, Argo Workflows и Argo Rollouts, единый Helm-контракт доставки для всех сервисов, Vault с External Secrets, CloudNativePG, Traefik и cert-manager, golden paths в Backstage. Изоляция тенантов, RBAC, квоты и сетевые политики. Любое изменение закоммичено, обозримо и обратимо.`
  2. term `Агентские системы доставки`, body `Ролевые агенты, которые превращают issue в предложение, одобренное предложение — в pull request, а чистое ревью — в мерж, с явными человеческими контрольными точками перед реализацией и перед мержем. Удалённые MCP-серверы в проде: OAuth 2.1 с PKCE, RBAC в границах тенанта, устойчивое выполнение воркфлоу и журнал аудита с защитой от подмены.`
  3. term `Бэкенд под нагрузкой`, body `Python и Java на Spring Boot, FastAPI, Kafka, PostgreSQL и Redis. Событийные микросервисы для рыночных данных и потока ордеров в реальном времени, идемпотентная обработка транзакций с дедупликацией по корреляционному ключу, антифрод-сценарии в условиях регуляторных требований.`

- WHEN the home page renders THE SYSTEM SHALL render a
  `<section id="capabilities">` directly after the identity section,
  containing a visible `<h2>` bound to `capabilitiesHeading` and three items,
  each item being an `<h3>` carrying the term followed by one `<p>` carrying
  the body, in both languages.
- WHILE the capability section renders THE SYSTEM SHALL NOT wrap it in a
  `<details>` element.

### D. Contact section

- WHEN `src/i18n/ui.ts` is loaded THE SYSTEM SHALL expose a new key
  `contactHeading` whose `en` is exactly `Get in touch` and whose `ru` is
  exactly `Связаться`.
- WHEN `src/i18n/ui.ts` is loaded THE SYSTEM SHALL expose a new key
  `contactIntro` whose `en` is exactly
  `Fully remote, Central European hours. Open to relocation in the EU. Email is the fastest way through.`
  and whose `ru` is exactly
  `Полностью удалённо, по центральноевропейскому времени. Открыт к релокации в ЕС. Быстрее всего — почта.`
- WHEN `src/i18n/ui.ts` is loaded THE SYSTEM SHALL expose a new key
  `contactItems` holding an array of exactly four `{ label, href, text }`
  objects per language, where `href` and `text` are identical in both
  languages and only `label` differs, in this order, character for character:

  1. label en `Email`, ru `Почта`; href `mailto:hello@dmitriimashkov.com`; text `hello@dmitriimashkov.com`
  2. label en `LinkedIn`, ru `LinkedIn`; href `https://www.linkedin.com/in/dmitriimashkov`; text `linkedin.com/in/dmitriimashkov`
  3. label en `GitHub`, ru `GitHub`; href `https://github.com/mctlhq`; text `github.com/mctlhq`
  4. label en `Telegram`, ru `Telegram`; href `https://t.me/dmitriimashkov`; text `@dmitriimashkov`

- WHEN the home page renders THE SYSTEM SHALL render a
  `<section id="contact">` with a visible `<h2>` bound to `contactHeading`, a
  paragraph bound to `contactIntro`, and a list of the four links, replacing
  the existing `detailsContactSummary` disclosure.
- WHILE the contact section renders THE SYSTEM SHALL render exactly one `<a>`
  per contact item, carrying that item's `href` and its `text` as the link
  text, with the item's `label` rendered as an `.l.en` / `.l.ru` pair
  (hostnames, handles and an email address are identifiers and stay
  untranslated, per `AGENTS.md`).
- WHILE the contact section renders THE SYSTEM SHALL NOT wrap it in a
  `<details>` element.
- WHILE the home page renders THE SYSTEM SHALL keep the other two uses of the
  `Details` component (`detailsRunSummary`, `detailsWorkSummary`) unchanged in
  content and order.

### E. One link correction on /work/

- WHEN `src/content/projects/mctl-loyalty.en.md` and
  `src/content/projects/mctl-loyalty.ru.md` are read THE SYSTEM SHALL carry
  the link line `    url: https://rewards.mctl.ai` in place of
  `    url: https://labs-mctl-loyalty.mctl.ai`, with the `Service` / `Сервис`
  labels unchanged.
- WHEN `test/projects.test.ts` (via `test/support/expected-projects.ts` or its
  own `EXPECTED_LINKS` table, wherever the row lives) is read THE SYSTEM SHALL
  carry the row
  `  { slug: 'mctl-loyalty', url: 'https://rewards.mctl.ai', en: 'Service', ru: 'Сервис' },`
  in place of
  `  { slug: 'mctl-loyalty', url: 'https://labs-mctl-loyalty.mctl.ai', en: 'Service', ru: 'Сервис' },`.
- WHEN `npm run build` completes THE SYSTEM SHALL render
  `https://rewards.mctl.ai` for `mctl-loyalty` on `/work/`, and no file under
  `dist/` SHALL contain the string `labs-mctl-loyalty.mctl.ai`.
- WHILE this change lands THE SYSTEM SHALL change nothing else on `/work/`.

### F. Structured data

- WHEN the home route is built THE SYSTEM SHALL emit a `Person` and a
  `WebSite` node inside exactly one `application/ld+json` block in
  `dist/index.html`.
- WHILE the `Person` node is emitted THE SYSTEM SHALL carry exactly: `name`
  `Dmitrii Mashkov`, `url` `https://dmitriimashkov.com/`, `jobTitle`
  `Senior platform engineer`, `email` `mailto:hello@dmitriimashkov.com`, and
  `sameAs` with exactly these three entries in this order:
  `https://www.linkedin.com/in/dmitriimashkov`, `https://github.com/mctlhq`,
  `https://t.me/dmitriimashkov`.
- WHILE the `WebSite` node is emitted THE SYSTEM SHALL carry `name`
  `Dmitrii Mashkov`, `url` `https://dmitriimashkov.com/` and `inLanguage`
  `en`, and SHALL NOT carry a `SearchAction` (the site has no search).
- WHILE the structured data is emitted THE SYSTEM SHALL NOT carry
  `worksFor`, `address`, `alumniOf` or `telephone` on any node.
- IF a route other than the home route is built THEN THE SYSTEM SHALL NOT
  emit the `Person`/`WebSite` graph, and the existing `BreadcrumbList`
  emission on journal and ADR routes SHALL be untouched
  (`dist/colophon/journal/*/index.html` still contains its `BreadcrumbList`).
- WHILE the new JSON-LD is emitted THE SYSTEM SHALL leave the mechanism that
  keeps `application/ld+json` out of the CSP script hash
  (`INLINE_SCRIPT_RE` in `src/lib/csp.ts`) unchanged.

### G. Gates that must keep passing

- WHEN `npm test` runs THE SYSTEM SHALL pass `test/ui.test.ts`'s en/ru parity
  check with every new key present in both languages, character for character
  as written above.
- WHEN `test/ui.test.ts` inspects a `ui` entry whose `en`/`ru` are arrays of
  objects (`capabilityItems`, `contactItems`) THE SYSTEM SHALL check parity
  for that shape too: same kind on both sides, same length, the same key set
  on every object, and a non-empty string at every leaf — the existing
  string-array and plain-string checks unchanged.
- WHEN the home page is built THE SYSTEM SHALL contain the eyebrow text, the
  three identity paragraphs, the three capability terms with their bodies, and
  the four contact links, all of them in both `.l.en` and `.l.ru` variants; a
  test SHALL assert each of the three identity paragraphs and each of the
  three capability terms is present in both languages.
- WHEN a test inspects the built home page THE SYSTEM SHALL prove that no
  `<details>` element wraps the text of `aboutParagraphs`, `capabilityItems`
  or `contactItems`.
- WHEN `dist/index.html` is inspected THE SYSTEM SHALL contain exactly one
  `application/ld+json` block whose parsed content includes the `Person` with
  its five fields and three `sameAs` entries and the `WebSite` with its three
  fields; the test SHALL parse the JSON rather than match a substring.
- WHEN `node scripts/check-dist.mjs` runs against the new tree THE SYSTEM
  SHALL pass: `checkHomePage()`'s expectations of exactly one
  `<details open>` and exactly three `<summary><h2` on `dist/index.html` SHALL
  be updated to the new structure (zero `<details open>`, two
  `<summary><h2`), and the home page's single `application/ld+json` block
  SHALL be checked there or in a test as the criterion above requires.
- WHEN `node scripts/check-headers.mjs` and `test/csp.test.ts` run THE SYSTEM
  SHALL pass them unchanged — the new JSON-LD SHALL NOT alter the inline
  script hash in the CSP.
- WHEN `test/title.test.ts` runs THE SYSTEM SHALL keep the home page's
  `<title>` (exactly `Dmitrii Mashkov`) and its meta description within the
  budgets that test enforces.
- WHEN `npm run vendor && npm test`, `npm run build` and
  `node scripts/check-links.mjs` run THE SYSTEM SHALL pass all three.
- WHILE `scripts/check-links.mjs` runs THE SYSTEM SHALL classify
  `https://rewards.mctl.ai`, `https://www.linkedin.com/in/dmitriimashkov`,
  `https://t.me/dmitriimashkov` and `mailto:hello@dmitriimashkov.com` as
  skipped off-origin/other-scheme hrefs and SHALL report every one of them by
  count and by name on a passing run, so that an unreachable external host is
  never mistaken for a checked one. The script SHALL remain network-free
  (`test/links.test.ts`'s forbidden-identifier proof stays green).
- WHEN `dist/index.html` is produced THE SYSTEM SHALL stay under
  `scripts/check-dist.mjs`'s `MAX_INDEX_BYTES` cap of 40960 bytes.
- WHILE new styles are added THE SYSTEM SHALL keep
  `node scripts/check-contrast.mjs` passing, using only the token pairs that
  script already validates (`surface-fg`, `surface-fg-muted` and `accent` over
  `surface-bg`/`surface-elevated`; `accent-fg` over `accent`), and SHALL
  declare no `animation` or `transition` (`test/a11y.test.ts`).
- IF the primary CTA carries an accent background THEN THE SYSTEM SHALL pin
  its `:hover` and `:visited:not(:hover)` colours so that the existing
  `.cta:hover` and `.cta:visited:not(:hover)` rules cannot render
  accent-on-accent or an unvalidated `surface-fg`-on-`accent` pair.

### H. Journal

- WHEN this cycle lands THE SYSTEM SHALL add one journal entry under
  `src/content/journal/` with `status: in_progress`, `service: portfolio`,
  `issue: https://github.com/mctlhq/portfolio/issues/98`,
  `proposal_slug: issue-98-q15-conversion-first-home-role-history-c`,
  `visibility: public`, bilingual `title` and `decided`, `interventions: []`,
  and none of `pr`, `merged_at`, `release`, `released_at`, `deployed_at`.
- WHILE that entry exists THE SYSTEM SHALL keep at most one entry in
  `src/content/journal/` with `status: in_progress`.

## Out of scope

- Naming the current employer anywhere on the site, in any language, or
  linking to it.
- Any availability or "open to work" statement, in any wording, in either
  language.
- Any city or country of residence. `contactIntro` states the working mode,
  the working hours and the relocation preference, and nothing beyond that.
- Version numbers on any language, framework or runtime named in the copy.
  `Java`, not `Java 21`; `Spring Boot`, not `Spring Boot 3`. A version is true
  for a year and then quietly dates the page. The one exception is a protocol
  whose version is part of its name: `OAuth 2.1`.
- A separate `/about/` page, navigation relabelling and the footer "Lab"
  grouping — those belong to the information-architecture cycle.
- Case-study pages, project schema extensions and outcome numbers with source
  URLs — a later cycle.
- A portrait, a logo or any new binary asset.
- Any new third-party runtime request, any second inline script, and any
  change to the metrics pipeline. Every number on the page still comes from
  `src/data/metrics.json`.
- Publishing any performance, revenue, user-count or percentage claim about
  the unnamed employer's systems. No number without a source the reader can
  open.

## Open questions

1. **Where the CTAs sit.** Section A says "the CTAs stay where the current
   `.ctas` nav is" (today: *after* `.stats`), while section B says the
   identity section goes "directly after the CTAs and before the stats", and
   reviewer step 1 asks for both CTAs inside the first viewport at 390x844.
   Those three cannot all hold with the current DOM order. Resolution taken:
   the `.ctas` nav element, its class and its `#ctas-label` label are
   unchanged, and the block moves up to sit directly after `heroSubline`, so
   the rendered order becomes eyebrow, `<h1>`, thesis, subline, `.ctas`,
   `#about`, `#capabilities`, `.stats`, the two remaining `<details>`,
   `#contact`. This is the only order that satisfies B and the reviewer step.
2. **`ui` entries that are arrays of objects.** `test/ui.test.ts` currently
   requires every item of a `ui` array to be a non-empty *string*, so
   `capabilityItems` and `contactItems` as specified would fail the parity
   check that acceptance criterion 1 requires to keep passing. Resolution
   taken: generalise that test to structured items (criterion G above) rather
   than flatten the keys, because the issue fixes the `{ term, body }` and
   `{ label, href, text }` shapes.
3. **`scripts/check-dist.mjs` is not in the issue's file list**, but its
   `checkHomePage()` hard-codes "exactly 1 `<details open>`" and "exactly 3
   `<summary><h2`" for `dist/index.html`, and it runs inside the `Dockerfile`
   build. Removing the contact disclosure breaks the image build unless that
   script is updated. Resolution taken: update it in this cycle and treat it
   as part of section D.
4. **External link resolution (acceptance criterion 9).**
   `scripts/check-links.mjs` is deliberately network-free (issue #55,
   `docs/link-check.md`, after the flaky external checking of #46/#54 was
   removed). It cannot "resolve" `rewards.mctl.ai`, LinkedIn or Telegram.
   Resolution taken: the script keeps its no-network property and its
   report-skipped-by-name behaviour (which is precisely "report rather than
   pass silently"); actually resolving the four contact destinations is
   reviewer step 3 after deployment. Reintroducing `fetch` would break
   `test/links.test.ts`'s forbidden-identifier proof and re-open a decision
   already made.
5. **`ui.detailsContactSummary` becomes unused** once the disclosure is
   replaced. Resolution taken: remove the key together with its only use, and
   update `test/home.test.ts`'s assertion that names it. Nothing else in the
   tree references it.
6. **Home page byte cap.** `dist/index.html` has a 40960-byte cap in
   `scripts/check-dist.mjs`; this cycle adds roughly 6-7 KB of bilingual copy
   plus the JSON-LD. The implementer must confirm headroom after the build; if
   the cap is exceeded, that is a finding for the reviewer, not a licence to
   cut the copy or raise the cap silently.
