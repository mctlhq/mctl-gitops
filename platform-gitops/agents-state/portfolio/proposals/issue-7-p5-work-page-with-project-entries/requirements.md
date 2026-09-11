# P5: Work page with project entries

## Context

The portfolio site currently has one real page (`src/pages/index.astro`, shipped
by P4/#6) whose "See the work" call to action points at `/work/`, a route that
does not exist. The `projects` content collection and its loader already exist
in `src/content.config.ts` — including a parity check that every project slug
has exactly one `*.en.md` and one `*.ru.md` file agreeing on `group`, `order`,
`repo`, `stack` and each link URL — but only one project (`mctl-api`) has been
authored, and nothing renders the collection outside the throwaway
`src/pages/dev/[check].astro` counter.

This proposal builds `/work/`: fourteen projects in two ordered groups
(Platform, Products), each rendered as a card whose closed state shows the
project name, a one-line bilingual summary and stack chips, and whose open
state shows the rendered markdown body, the repository link and a per-repository
metrics row. The metrics row is a forward-compatible reader: the per-repository
numbers come from a `per_repo` entry in `src/data/metrics.json` that P8b will
add, and until then every value renders as an em dash through the existing
`formatStat` helper. This matters because `/work/` is the page the whole site
exists to lead to — the evidence that the DevLoop produced real software — and
because it is the first page that renders content-collection bodies, which sets
the pattern for the journal and ADR pages that follow.

## User stories

- AS a visiting engineer or hiring manager I WANT a single page listing every
  project with a one-line summary and its stack SO THAT I can scan the whole
  body of work in under a minute without opening fourteen GitHub repositories.
- AS the same visitor, once a project catches my eye, I WANT to expand that one
  card to read its details and follow its repository link SO THAT depth is
  available on demand instead of paid for up front.
- AS a Russian-speaking reader I WANT every summary, detail and label on
  `/work/` in Russian, with tool and language names left untranslated, SO THAT
  the page reads as written rather than translated.
- AS a reader with JavaScript disabled, on a keyboard, or on a screen reader I
  WANT the cards to expand and the language switch to work SO THAT the page is
  usable without client-side code.
- AS the site's maintainer I WANT project copy, stack chips and links to live in
  content frontmatter and `src/i18n/ui.ts` rather than in the template SO THAT
  adding or editing a project never touches a `.astro` file.
- AS the site's maintainer I WANT the per-project numeric facts to read from the
  metrics snapshot and render as an em dash while absent SO THAT no number is
  ever typed into content or a template, per `AGENTS.md`.

## Acceptance criteria (EARS)

### Page and grouping

- WHEN `astro build` runs THE SYSTEM SHALL emit `dist/work/index.html` from
  `src/pages/work.astro` (the project's `trailingSlash: 'always'` setting in
  `astro.config.mjs` makes `/work/` the served path).
- WHEN `/work/` renders THE SYSTEM SHALL show exactly fourteen project cards.
- WHEN `/work/` renders THE SYSTEM SHALL show exactly two group sections, the
  Platform section first with six cards and the Products section second with
  eight cards.
- WHEN `/work/` renders THE SYSTEM SHALL order the cards inside each group by
  the frontmatter `order` field ascending, producing `mctl-api`, `mctl-gitops`,
  `mctl-agents`, `mctl-agent`, `mctl-portal`, `mctl-design` under Platform and
  `mctl-telegram`, `seerrsense`, `mctl-academy`, `mctl-loyalty`,
  `mctl-pairdesk`, `pelican-libertex-social`, `pfeifenpatenschaft-backend`,
  `mctl-openclaw` under Products.
- WHEN `/work/` renders THE SYSTEM SHALL emit the group heading as an `.l.en` /
  `.l.ru` pair reading `Platform` / `Платформа` and `Products` / `Продукты`,
  both strings sourced from `src/i18n/ui.ts`.
- IF a project slug is missing either its `*.en.md` or its `*.ru.md` file THEN
  THE SYSTEM SHALL fail the build with a message naming the slug (already
  enforced by `checkProjectParity` in `src/content.config.ts`).

### Card structure

- WHEN a card renders THE SYSTEM SHALL make the card a native `<details>`
  element whose `<summary>` carries the project name, the one-line summary as an
  `.l.en` / `.l.ru` pair, and the stack chips.
- WHEN a card renders THE SYSTEM SHALL render the project name once, from the
  frontmatter `name` field, untranslated, as an identifier.
- WHEN a card is expanded THE SYSTEM SHALL show the rendered markdown body of
  the English entry inside a `<div class="l en">` and of the Russian entry
  inside a `<div class="l ru" lang="ru">`.
- WHEN a card is expanded THE SYSTEM SHALL show a link whose `href` is the
  frontmatter `repo` value and whose text is that URL with the `https://`
  scheme removed.
- WHEN a project's frontmatter carries a `links` array THE SYSTEM SHALL render
  one link per entry, pairing the English and Russian `label` values by array
  index as an `.l.en` / `.l.ru` pair and using the English entry's `url` as the
  `href`.
- WHILE `/work/` is rendered THE SYSTEM SHALL keep every card closed by default
  (no `open` attribute on any `<details>` on the page).

### Stack chips

- WHEN a card renders its chips THE SYSTEM SHALL produce one chip per element of
  the frontmatter `stack` array, in array order, by iterating that array.
- WHILE `src/components/ProjectCard.astro` is the template rendering chips THE
  SYSTEM SHALL contain no chip text as a literal in that file; every chip string
  comes from frontmatter or, for its Russian form, from `src/i18n/ui.ts`.
- WHEN a chip string has a Russian form registered in `src/i18n/ui.ts` THE
  SYSTEM SHALL render the chip as an `.l.en` / `.l.ru` pair using that form.
- IF a chip string has no Russian form registered THEN THE SYSTEM SHALL render
  the same string on both sides of the `.l.en` / `.l.ru` pair, so language names
  and tool names stay untranslated.

### Bilingual parity and typography

- WHEN `scripts/check-dist.mjs` runs after a build THE SYSTEM SHALL report equal
  counts of `class="l en"` and `class="l ru"` in `dist/work/index.html`.
- WHEN any element on `/work/` carries translated text THE SYSTEM SHALL set it
  in `var(--font-display)` (Onest) or `var(--font-mono)` (JetBrains Mono), never
  in `var(--font-editorial)` (Instrument Serif, which ships no Cyrillic subset —
  carried from #4).
- WHILE `/work/` is rendered THE SYSTEM SHALL leave every proper noun, tool
  name, language name, hostname and repository identifier untranslated.

### Keyboard and no-JavaScript

- WHEN a reader tabs through `/work/` THE SYSTEM SHALL give each card's
  `<summary>` keyboard focus with a visible focus ring (the existing
  `:focus-visible` rule in `src/styles/site.css`).
- WHEN a focused `<summary>` receives Enter or Space THE SYSTEM SHALL toggle
  that card open or closed.
- WHILE JavaScript is disabled THE SYSTEM SHALL keep every card expandable and
  every link followable; `/work/` shall add no inline script and no `onclick`,
  `tabindex` or `role` attribute to any `<summary>`.
- WHEN `scripts/csp-hash.mjs` runs after a build THE SYSTEM SHALL still find
  exactly one distinct inline script body across all of `dist/`, the existing
  preference script from `src/layouts/Base.astro`.

### Metrics slot

- WHEN a card is expanded THE SYSTEM SHALL show a per-repository metrics row
  rendered through `formatStat` from `src/lib/metrics.ts`.
- IF `src/data/metrics.json` carries no `sources.github.per_repo` entry for a
  project slug THEN THE SYSTEM SHALL render each value in that project's metrics
  row as the em dash `—`.
- WHILE `src/pages/work.astro` and `src/components/ProjectCard.astro` are the
  templates THE SYSTEM SHALL contain no numeric metric value as a literal; every
  number displayed originates in `src/data/metrics.json`.

### Build gates

- WHEN `npm test` runs THE SYSTEM SHALL execute the new `test/projects.test.ts`
  and `test/work.test.ts` files, both registered in the `test` script of
  `package.json`.
- WHEN `astro check` runs THE SYSTEM SHALL report no type error for
  `src/pages/work.astro`, `src/components/ProjectCard.astro`,
  `src/lib/projects.ts` and `src/i18n/ui.ts`.
- WHEN `scripts/check-dist.mjs` runs after a build THE SYSTEM SHALL find no
  `.js` file anywhere under `dist/`.
- WHEN the pull request is opened THE SYSTEM SHALL carry, in its description, the
  output of a script that requests every `href` appearing in
  `dist/work/index.html` and reports the HTTP status of each, with every status
  200.
- WHEN the pull request is opened THE SYSTEM SHALL carry, in its description, a
  statement that a HAR capture of `/work/` shows same-origin requests only, and
  a statement that Tab plus Enter and Tab plus Space were used to open and close
  a card with JavaScript disabled.

### Exact project copy

Every string below is the copy to write into frontmatter and bodies. It is
reproduced here character for character and must not be paraphrased,
translated, shortened, reordered or extended.

Common frontmatter rules for all fourteen projects:

- `slug` equals the project name in the list below; `lang` is `en` in the
  `*.en.md` file and `ru` in the `*.ru.md` file; `name` is the project name,
  identical in both files.
- `group` is `platform` for projects 1-6 and `product` for projects 7-14 (these
  are the two values the `z.enum(['platform', 'product'])` in
  `src/content.config.ts` accepts; the group *headings* are `Platform` and
  `Products`).
- `order` is the number shown below, identical in both files.
- `repo` is `https://github.com/mctlhq/<slug>`, except
  `pelican-libertex-social`, whose `repo` is
  `https://github.com/mashkoffdmitry/pelican-libertex-social`.
- `stack` is the array shown below, identical in both files.
- `summary` is the EN line in the `*.en.md` file and the RU line in the
  `*.ru.md` file.
- The markdown body is the bullet list shown below, one `-` list item per
  bullet, EN bullets in the `*.en.md` file and RU bullets in the `*.ru.md` file.

#### Platform

**1. `mctl-api`** — order 1. Extends the two files that already exist.

`stack: ["Go", "chi", "mcp-go", "OAuth 2.0 PKCE", "OpenAPI"]`

EN summary:
`Control-plane API and MCP server of the mctl platform: every operation exists as REST and as an MCP tool.`

RU summary:
`API управляющего контура и MCP-сервер платформы mctl: каждая операция существует как REST и как MCP-инструмент.`

EN body bullets:
1. `writes never touch the cluster directly — they submit Argo Workflows that commit to the GitOps repository`
2. `GitHub-token, Dex OIDC and OAuth PKCE authentication`
3. `audit log in PostgreSQL`

RU body bullets:
1. `записи никогда не трогают кластер напрямую — они запускают Argo Workflows, которые коммитят в GitOps-репозиторий`
2. `аутентификация по GitHub-токену, Dex OIDC и OAuth PKCE`
3. `журнал аудита в PostgreSQL`

The `links` block already present in `src/content/projects/mctl-api.en.md`
(`label: "Docs"`, `url: https://docs.mctl.ai`) and in
`src/content/projects/mctl-api.ru.md` (`label: "Документация"`, same URL) is
kept unchanged.

**2. `mctl-gitops`** — order 2.

`stack: ["ArgoCD", "Argo Workflows", "Helm", "OpenTofu", "Vault", "k3s"]`

EN summary:
`The ArgoCD source of truth: App-of-Apps, tenant and service charts, workflow templates, infrastructure as code.`

RU summary:
`Источник истины для ArgoCD: App-of-Apps, чарты тенантов и сервисов, шаблоны воркфлоу, инфраструктура как код.`

EN body bullets:
1. `self-healing sync every 60 seconds`
2. `Vault with External Secrets as the only secret path`
3. `SOC 2 documentation kit and operational runbooks`
4. `platform skills catalog served over MCP`

RU body bullets:
1. `самовосстанавливающаяся синхронизация каждые 60 секунд`
2. `Vault с External Secrets как единственный путь секретов`
3. `комплект документации SOC 2 и эксплуатационные runbook'и`
4. `каталог платформенных навыков, отдаваемый через MCP`

**3. `mctl-agents`** — order 3.

`stack: ["Python", "Claude Agent SDK", "Temporal", "Argo Workflows"]`

EN summary:
`The DevLoop: durable Temporal workflows that turn an issue into a proposal, an approved proposal into a pull request, and a merged pull request into a deployment.`

RU summary:
`DevLoop: устойчивые Temporal-воркфлоу, превращающие issue в предложение, одобренное предложение — в pull request, а смерженный pull request — в деплой.`

EN body bullets:
1. `investigator, implementer, shepherd and mentor roles`
2. `proposals stored as git state`
3. `replay tests against recorded workflow histories`
4. `architecture decision records`

RU body bullets:
1. `роли investigator, implementer, shepherd и mentor`
2. `предложения хранятся как git-состояние`
3. `replay-тесты на записанных историях воркфлоу`
4. `записи архитектурных решений`

**4. `mctl-agent`** — order 4.

`stack: ["Go", "SQLite", "AlertManager", "Claude API"]`

EN summary:
`Self-healing GitOps agent: an alert becomes a ticket, a matching skill diagnoses it, and a targeted fix lands as a pull request.`

RU summary:
`Самовосстанавливающийся GitOps-агент: алерт становится тикетом, подходящий навык диагностирует его, и точечное исправление приходит как pull request.`

EN body bullets:
1. `compiled built-in skills for OOM, image pull, rollback, drift, probes, throttling, quota and scale`
2. `hot-reloadable YAML skills`
3. `Telegram notifications`

RU body bullets:
1. `встроенные скомпилированные навыки для OOM, image pull, отката, дрейфа, проб, троттлинга, квот и масштабирования`
2. `YAML-навыки с горячей перезагрузкой`
3. `уведомления в Telegram`

**5. `mctl-portal`** — order 5.

`stack: ["Backstage", "TypeScript", "React", "Playwright"]`

EN summary:
`Developer portal on Backstage with custom backend plugins for workflows, custom domains and GitHub App connection.`

RU summary:
`Портал разработчика на Backstage с собственными backend-плагинами для воркфлоу, кастомных доменов и подключения GitHub App.`

EN body bullets:
1. `multi-tenancy`
2. `OIDC federation`
3. `Vault-delivered secrets`
4. `live Kubernetes resource views`

RU body bullets:
1. `мультитенантность`
2. `федерация OIDC`
3. `доставка секретов из Vault`
4. `живые представления ресурсов Kubernetes`

**6. `mctl-design`** — order 6.

`stack: ["CSS", "design tokens", "Vue 3", "Storybook", "pnpm", "Turborepo"]`

EN summary:
`The shared design system: tokens, CSS themes, a Tailwind preset and Vue components, versioned in lockstep and served from a CDN.`

RU summary:
`Общая дизайн-система: токены, CSS-темы, пресет Tailwind и Vue-компоненты, версионируемые синхронно и отдаваемые с CDN.`

EN body bullets:
1. `immutable versioned stylesheets`
2. `CI refuses to change a published version`
3. `this site vendors version 0.5.0`

RU body bullets:
1. `неизменяемые версионированные таблицы стилей`
2. `CI отказывается менять опубликованную версию`
3. `этот сайт вендорит версию 0.5.0`

#### Products

**7. `mctl-telegram`** — order 7.

`stack: ["Go", "MTProto", "MCP", "OAuth 2.0"]`

EN summary:
`Remote MCP server that exposes a user's own Telegram account to AI clients, with an opt-in send gate, audit log and encrypted sessions.`

RU summary:
`Удалённый MCP-сервер, открывающий AI-клиентам собственный Telegram-аккаунт пользователя, с opt-in шлюзом отправки, журналом аудита и шифрованными сессиями.`

EN body bullets:
1. `per-tool read-only and destructive annotations`
2. `three-condition send gate`
3. `SSRF-guarded media`
4. `submissions to ChatGPT Apps and Claude connectors`

RU body bullets:
1. `аннотации read-only и destructive на каждом инструменте`
2. `трёхусловный шлюз отправки`
3. `защита от SSRF при загрузке медиа`
4. `заявки в каталоги ChatGPT Apps и коннекторов Claude`

**8. `seerrsense`** — order 8.

`stack: ["TypeScript", "Fastify", "MCP", "PostgreSQL"]`

EN summary:
`Natural-language media requests for Seerr, Radarr and Sonarr over MCP: the model interprets intent, provider IDs stay the source of truth.`

RU summary:
`Запросы медиа на естественном языке для Seerr, Radarr и Sonarr через MCP: модель интерпретирует намерение, идентификаторы провайдеров остаются источником истины.`

EN body bullets:
1. `OAuth for both Claude and ChatGPT`
2. `per-user connections`
3. `directory submissions`

RU body bullets:
1. `OAuth для Claude и ChatGPT`
2. `подключения на пользователя`
3. `заявки в каталоги`

**9. `mctl-academy`** — order 9.

`stack: ["TypeScript", "Hono", "PostgreSQL", "Vue", "Playwright"]`

EN summary:
`A learning product with an evidence audit that quarantined and re-authored question banks after fabricated citations were found.`

RU summary:
`Обучающий продукт с аудитом доказательств, который поместил в карантин и переписал банки вопросов после обнаружения выдуманных цитат.`

EN body bullets:
1. `better-auth with GitHub sign-in`
2. `schema-validated content`
3. `a content-quality report as the ongoing check`

RU body bullets:
1. `better-auth со входом через GitHub`
2. `контент, проверяемый по схеме`
3. `отчёт о качестве контента как постоянная проверка`

**10. `mctl-loyalty`** — order 10.

`stack: ["TypeScript", "Express", "PostgreSQL", "Telegram Mini App"]`

EN summary:
`Loyalty system as a Telegram Mini App with anti-fraud QR: rotating codes, one-time hashed tokens, atomic burn and daily limits enforced in the database.`

RU summary:
`Программа лояльности как Telegram Mini App с защитой от мошенничества через QR: ротация кодов, одноразовые хешированные токены, атомарное погашение и дневные лимиты на уровне БД.`

No detail bullets are supplied for this project. Its markdown body is the single
paragraph below, which is its summary reproduced verbatim (see Open questions).

EN body: `Loyalty system as a Telegram Mini App with anti-fraud QR: rotating codes, one-time hashed tokens, atomic burn and daily limits enforced in the database.`

RU body: `Программа лояльности как Telegram Mini App с защитой от мошенничества через QR: ротация кодов, одноразовые хешированные токены, атомарное погашение и дневные лимиты на уровне БД.`

**11. `mctl-pairdesk`** — order 11.

`stack: ["TypeScript", "PostgreSQL", "Telegram Mini App"]`

EN summary:
`P2P exchange bulletin board without custody: contact reveal enforced in the backend, racing accepts blocked by a row lock and a partial unique index.`

RU summary:
`Доска P2P-обмена без кастодиального хранения: раскрытие контактов контролируется backend'ом, гонка принятий блокируется блокировкой строки и частичным уникальным индексом.`

No detail bullets are supplied. Markdown body is the summary reproduced
verbatim:

EN body: `P2P exchange bulletin board without custody: contact reveal enforced in the backend, racing accepts blocked by a row lock and a partial unique index.`

RU body: `Доска P2P-обмена без кастодиального хранения: раскрытие контактов контролируется backend'ом, гонка принятий блокируется блокировкой строки и частичным уникальным индексом.`

**12. `pelican-libertex-social`** — order 12.
`repo: https://github.com/mashkoffdmitry/pelican-libertex-social`

`stack: ["Node.js", "OIDC PKCE", "Cloudflare Workers", "R2"]`

EN summary:
`Read-only proxy for a copy-trading catalog with autonomous OIDC token rotation and an edge cache; also published as a Vue package.`

RU summary:
`Read-only прокси для каталога копитрейдинга с автономной ротацией OIDC-токенов и edge-кешем; также опубликован как Vue-пакет.`

No detail bullets are supplied. Markdown body is the summary reproduced
verbatim:

EN body: `Read-only proxy for a copy-trading catalog with autonomous OIDC token rotation and an edge cache; also published as a Vue package.`

RU body: `Read-only прокси для каталога копитрейдинга с автономной ротацией OIDC-токенов и edge-кешем; также опубликован как Vue-пакет.`

**13. `pfeifenpatenschaft-backend`** — order 13.

`stack: ["TypeScript", "Express", "PostgreSQL"]`

EN summary:
`Organ-pipe sponsorship backend: race-safe 15-minute reservations, integer-cent money, payment confirmation webhooks, versioned migrations.`

RU summary:
`Backend спонсорства органных труб: безопасные к гонкам 15-минутные брони, деньги в целых центах, вебхуки подтверждения оплаты, версионированные миграции.`

No detail bullets are supplied. Markdown body is the summary reproduced
verbatim:

EN body: `Organ-pipe sponsorship backend: race-safe 15-minute reservations, integer-cent money, payment confirmation webhooks, versioned migrations.`

RU body: `Backend спонсорства органных труб: безопасные к гонкам 15-минутные брони, деньги в целых центах, вебхуки подтверждения оплаты, версионированные миграции.`

**14. `mctl-openclaw`** — order 14.

`stack: ["TypeScript", "pnpm", "upstream fork"]`

EN summary:
`Maintained fork of an open-source assistant gateway: owner-gated OAuth connect flow, weekly upstream-sync pipeline with a review gate, hosted deployment into platform tenants.`

RU summary:
`Поддерживаемый форк open-source шлюза ассистента: OAuth-подключение под контролем владельца, еженедельный пайплайн синхронизации с upstream через ревью-гейт, размещение в тенантах платформы.`

The issue states the requirement for this project's details rather than quoting
card copy, so the exact strings to write are these two bullets per language:

EN body bullets:
1. `repository totals reflect the upstream project`
2. `the owner's contribution is the fork layer and the deployment pipeline`

RU body bullets:
1. `итоги репозитория отражают upstream-проект`
2. `вклад владельца — слой форка и пайплайн развёртывания`

### Exact `src/i18n/ui.ts` additions

Added keys, with both sides of each pair exactly as written here:

- `workTitle: { en: 'Work — Dmitrii Mashkov', ru: 'Work — Dmitrii Mashkov' }` —
  the `<title>` holds one string and stays Latin, per `AGENTS.md`; both sides
  are the Latin form, mirroring the existing `homeTitle` entry.
- `workGroupPlatform: { en: 'Platform', ru: 'Платформа' }`
- `workGroupProducts: { en: 'Products', ru: 'Продукты' }`
- `workRepoLabel: { en: 'Repository', ru: 'Репозиторий' }` — the accessible
  name of the repository link group.
- `workMetricsLabel: { en: 'Repository metrics', ru: 'Метрики репозитория' }`
- `chipDesignTokens: { en: 'design tokens', ru: 'дизайн-токены' }`
- `chipUpstreamFork: { en: 'upstream fork', ru: 'форк upstream' }`

The page heading reuses the existing `ui.navWork` entry (`Work` / `Работы`);
the metrics row reuses the existing `ui.statCommits` (`Commits` / `Коммиты`)
and `ui.statReleases` (`Releases` / `Релизы`) entries. `chipDesignTokens` and
`chipUpstreamFork` are the only chips in the fourteen stack arrays that are
plain words rather than a language, tool, protocol or product name; every other
chip renders untranslated on both sides of the pair.

## Out of scope

- Collecting per-project numeric metrics. The `per_repo` entry of
  `src/data/metrics.json` is P8b's work; this proposal only adds a defensive
  reader that renders an em dash while the entry is absent, and does not change
  `src/data/metrics.json` itself.
- Screenshots, images, logos or any binary asset for any project.
- The `/colophon/` and `/approach/` pages, and the `/#colophon` call to action
  on the home page.
- Any change to `src/pages/index.astro`, `src/layouts/Base.astro`,
  `src/components/Details.astro`, `src/components/Stat.astro`,
  `src/i18n/Lang.astro`, `nginx.conf`, `Dockerfile`,
  `scripts/vendor-assets.mjs`, `scripts/csp-hash.mjs` or
  `scripts/check-dist.mjs`.
- Any new client-side JavaScript, any second inline script, and any change to
  the existing preference script or its CSP hash.
- Filtering, sorting, searching or tag navigation across projects.
- An ADR. This proposal introduces no decision that contradicts or extends
  ADR-0001, ADR-0002 or ADR-0005.
- The journal entry for this cycle, which the shepherd writes at merge time with
  the real timestamps.

## Open questions

- **Four projects have no detail bullets.** The issue supplies detail bullets
  for ten of the fourteen projects; `mctl-loyalty`, `mctl-pairdesk`,
  `pelican-libertex-social` and `pfeifenpatenschaft-backend` have a summary
  only, while acceptance criterion 2 requires every card to have both a summary
  and details. Inventing copy is explicitly forbidden, so this proposal resolves
  the conflict by making those four bodies the summary sentence reproduced
  verbatim. The visible cost is that the sentence appears twice in an expanded
  card, because `<summary>` stays visible when a `<details>` opens. The reviewer
  should decide whether to accept that duplication, to supply four detail
  bullet sets in a follow-up, or to let those four bodies be empty (the
  `<details>` would then hold only the repository link and the metrics row,
  which still satisfies bilingual parity). Proceeding with verbatim duplication.
- **Two Russian chip strings are not supplied by the issue.** The issue asks for
  "chip words that are plain words" to be translated and gives `self-healing` →
  `самовосстановление` as an illustration, but that chip appears in no stack
  array. The two plain-word chips that do appear are `design tokens` and
  `upstream fork`; their Russian forms above (`дизайн-токены`,
  `форк upstream`) are the only copy in this proposal not taken from the issue.
  Proceeding with them.
- **Card shape.** "a card with a one-line summary and stack chips, expanding to
  details" plus acceptance criterion 5's reference to *the* `<summary>` is read
  as one `<details>` per card, with name, summary and chips inside the
  `<summary>`. The alternative reading — an always-visible card header plus a
  nested `<details>` labelled "Details" — would put two focusable summaries on
  some cards and is not taken. Proceeding with one `<details>` per card.
- **`Nav.astro`'s Work link.** `src/components/Nav.astro` links Work to
  `/#work`, an anchor that `test/home.test.ts` asserts no longer exists in
  `src/pages/index.astro`. `Nav.astro` is not in the issue's list of files
  expected to change, but the nav renders on `/work/` itself, so the page would
  link to a dangling fragment on a page that now exists as a route. This
  proposal repoints that one `href` to `/work/` and leaves the Approach link
  alone. Flagging it as a deliberate, one-line addition to the issue's file
  list.
- **`https://docs.mctl.ai`.** The existing `mctl-api` `links` entry points at
  it, so acceptance criterion 3 makes the page's status depend on that host. If
  the link-check script reports anything other than 200, the implementer removes
  the `links` block from both `mctl-api` files rather than shipping a failing
  criterion, and says so in the pull request description.
- **`0.5.0` in `mctl-design`'s details.** `AGENTS.md` forbids typing numbers
  into content, but this string is a version identifier rather than a metric,
  and the issue supplies it verbatim. It duplicates `MCTL_VERSION` in
  `scripts/vendor-assets.mjs`; a test asserts the two agree so the string cannot
  drift silently. Proceeding.
- **Page weight.** `scripts/check-dist.mjs` caps `dist/index.html` at 40 KB and
  does not cap any other page. `/work/` carries twenty-eight bodies and will be
  several times that. No cap is added here, because inventing a threshold the
  issue did not ask for could block the page on a number nobody agreed to; the
  pull request description reports the built size of `dist/work/index.html` so a
  cap can be chosen with evidence in a later cycle.
