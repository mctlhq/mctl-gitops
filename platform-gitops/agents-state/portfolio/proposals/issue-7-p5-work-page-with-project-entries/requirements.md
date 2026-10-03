# P5: Work page with project entries

## Context

The site currently has a home page (`src/pages/index.astro`) whose first call
to action links to `/work/`, a route that does not exist yet: the build emits
`dist/index.html`, `dist/404.html` and nothing else, so the primary navigation
path off the landing page is a 404. A `projects` content collection already
exists (`src/content.config.ts`, `src/content/projects/mctl-api.{en,ru}.md`)
with a strict schema and an en/ru parity check, but no page reads it.

This proposal adds `/work/`: fourteen projects in two ordered groups, each
rendered as a card carrying a one-line bilingual summary, stack chips read from
frontmatter, and a native `<details>` block that expands into the rendered
markdown body plus links and a placeholder for the per-repository metrics that
issue P8b will supply. Every string is authored in both English and Russian,
the page ships no JavaScript, and it makes no third-party request. The point of
the page is that the work is visible and checkable: each card names a real
repository, and every link on the page resolves.

The copy in this document is normative and complete. The implementer must copy
each summary, detail bullet and stack array from the tables below character for
character. Nothing here may be paraphrased, translated, shortened or invented.

## User stories

- AS a visitor reading in English I WANT `/work/` to list every project in two
  labelled groups SO THAT I can see the scope of the platform and the products
  in one screen.
- AS a visitor reading in Russian I WANT the same page, with every summary and
  every detail bullet in Russian SO THAT I read a page that was written rather
  than translated.
- AS a visitor scanning quickly I WANT a one-line summary and a row of stack
  chips per project SO THAT I can judge relevance without expanding anything.
- AS a visitor who wants depth I WANT each card to expand into detail bullets
  and links SO THAT I can go from the summary to the repository in one step.
- AS a keyboard-only visitor I WANT each card's summary to take focus and
  toggle with Enter and Space SO THAT the page is usable without a pointer.
- AS a visitor with JavaScript disabled I WANT the page to render and expand
  normally SO THAT the content does not depend on a client bundle.
- AS the site owner I WANT numbers about a repository to come from the metrics
  snapshot, never from typed content SO THAT no figure on the site is a claim
  without provenance.

## Acceptance criteria (EARS)

### Page and structure

- WHEN `astro build` runs THE SYSTEM SHALL emit `dist/work/index.html` from a
  new `src/pages/work.astro`.
- WHEN `/work/` renders THE SYSTEM SHALL show exactly 14 project cards: 6 under
  the `Platform` / `Платформа` heading and 8 under the `Products` / `Продукты`
  heading.
- WHEN `/work/` renders THE SYSTEM SHALL order the Platform group as
  `mctl-api`, `mctl-gitops`, `mctl-agents`, `mctl-agent`, `mctl-portal`,
  `mctl-design`, and the Products group as `mctl-telegram`, `seerrsense`,
  `mctl-academy`, `mctl-loyalty`, `mctl-pairdesk`, `pelican-libertex-social`,
  `pfeifenpatenschaft-backend`, `mctl-openclaw`.
- WHILE the page is rendered THE SYSTEM SHALL derive the card order from each
  entry's `order` frontmatter field, not from the order `getCollection` happens
  to return.
- WHEN a card renders THE SYSTEM SHALL show the project name, the one-line
  summary, the stack chips and a `<details>` element whose open state carries
  the rendered markdown body, the project's links and the metrics slot.

### Content and bilingual parity

- WHEN the `projects` collection loads THE SYSTEM SHALL contain exactly 28
  entries: one `<slug>.en.md` and one `<slug>.ru.md` per project for the
  fourteen projects named above.
- WHEN a card renders THE SYSTEM SHALL emit the English and Russian summary as
  an `.l.en` / `.l.ru` pair, and the English and Russian rendered bodies as an
  `.l.en` / `.l.ru` pair.
- WHILE any page of the site is in `dist/` THE SYSTEM SHALL keep the count of
  `class="l en"` equal to the count of `class="l ru"` in that file, as enforced
  by `scripts/check-dist.mjs`.
- WHEN the summaries and detail bullets are authored THE SYSTEM SHALL use the
  exact strings in the copy tables of this document, byte for byte.
- IF a string in the copy tables contains an em dash, a typographic apostrophe
  or the letter `ё` THEN THE SYSTEM SHALL preserve that character rather than
  substituting an ASCII equivalent.

### Stack chips

- WHEN a card renders its chips THE SYSTEM SHALL read them from the entry's
  `stack` frontmatter array, and no chip text SHALL appear as a literal in
  `src/pages/work.astro` or `src/components/ProjectCard.astro`.
- WHEN a chip's text is a plain word rather than a language, product or tool
  name THE SYSTEM SHALL render its Russian counterpart from the chip dictionary
  in `src/i18n/ui.ts`.
- IF a chip has no entry in that dictionary THEN THE SYSTEM SHALL render the
  frontmatter string unchanged in both languages.
- WHILE the `projects` schema is in force THE SYSTEM SHALL keep the `stack`
  array identical in a project's `.en.md` and `.ru.md` files, because
  `checkProjectParity` in `src/content.config.ts` compares them by value.

### Links and repository visibility

- WHEN a project is public THE SYSTEM SHALL carry its repository URL in the
  `repo` frontmatter field and render it as a link on the card.
- WHEN the project is `pelican-libertex-social` THE SYSTEM SHALL use
  `https://github.com/mashkoffdmitry/pelican-libertex-social` as its `repo`.
- WHEN the project is `pfeifenpatenschaft-backend` THE SYSTEM SHALL omit the
  `repo` frontmatter field entirely and render the card with no repository
  link, keeping the name, summary, chips and details.
- IF an entry has no `repo` field THEN THE SYSTEM SHALL render the card without
  raising a schema error, which requires `repo` to become optional in
  `projectsSchema`.
- WHEN every link rendered on `/work/` is requested THE SYSTEM SHALL see HTTP
  200 for each one; the check script and its output go into the pull request
  description.
- WHILE any link on the page points at a repository THE SYSTEM SHALL point only
  at repositories that are public.

### Keyboard, script and network

- WHEN a visitor tabs through `/work/` THE SYSTEM SHALL give focus to each
  card's `<summary>` element with a visible focus ring.
- WHEN a focused `<summary>` receives Enter or Space THE SYSTEM SHALL toggle
  that card's `<details>` open or closed, using the browser's native behaviour
  with no script and no `tabindex` override.
- WHEN `astro build` completes THE SYSTEM SHALL leave no file ending in `.js`
  anywhere under `dist/`.
- WHILE `/work/` is loaded in a browser THE SYSTEM SHALL issue same-origin
  requests only; a HAR capture shall show no third-party host.
- WHEN `/work/` renders with JavaScript disabled THE SYSTEM SHALL show the
  English content and allow every card to expand.

### Typography

- WHILE any text on `/work/` has a Russian counterpart THE SYSTEM SHALL set it
  in Onest (`var(--font-display)`), never in Instrument Serif
  (`var(--font-editorial)`), because Instrument Serif ships no Cyrillic subset.
- WHEN `src/styles/site.css` gains rules for the work page THE SYSTEM SHALL not
  reference `--font-editorial` in any selector that styles a translated string.

### Metrics placeholder

- WHEN a card renders its metrics area and no per-repository metrics exist THE
  SYSTEM SHALL render the em dash produced by `formatStat(null)` from
  `src/lib/metrics.ts`.
- WHILE `src/data/metrics.json` carries no `per_repo` data THE SYSTEM SHALL
  type no numeric repository fact into any project markdown file or template.
- IF a number appears inside issue-supplied prose (for example `60 seconds`,
  `version 0.5.0`, `15-minute`, `SOC 2`, `OAuth 2.0`, `Vue 3`) THEN THE SYSTEM
  SHALL treat it as part of the copy, not as a metric, and keep it verbatim.

### Build gates

- WHEN `npm test` runs THE SYSTEM SHALL pass, including the new tests listed in
  `tasks.md`.
- WHEN `npm run check` runs THE SYSTEM SHALL report no type or content error.
- WHEN `node scripts/check-dist.mjs` runs after a build THE SYSTEM SHALL exit 0.

## Copy (normative, verbatim)

Field conventions for every file below:

- `slug` is the project name; `lang` is `en` or `ru`; `name` is the project
  name, identical in both languages; `group` is `platform` or `product`;
  `order` is the global number 1..14 shown below; `stack` is the array shown;
  `summary` is the one-line summary for that language; the markdown body is the
  detail bullets for that language, one `- ` bullet per line.
- `repo` is `https://github.com/mctlhq/<slug>` unless stated otherwise.

### Platform

**1. `mctl-api`** — group `platform`, order `1`, repo
`https://github.com/mctlhq/mctl-api`
stack: `["Go", "chi", "mcp-go", "OAuth 2.0 PKCE", "OpenAPI"]`

EN summary:
`Control-plane API and MCP server of the mctl platform: every operation exists as REST and as an MCP tool.`

RU summary:
`API управляющего контура и MCP-сервер платформы mctl: каждая операция существует как REST и как MCP-инструмент.`

EN details:
- `writes never touch the cluster directly — they submit Argo Workflows that commit to the GitOps repository`
- `GitHub-token, Dex OIDC and OAuth PKCE authentication`
- `audit log in PostgreSQL`

RU details:
- `записи никогда не трогают кластер напрямую — они запускают Argo Workflows, которые коммитят в GitOps-репозиторий`
- `аутентификация по GitHub-токену, Dex OIDC и OAuth PKCE`
- `журнал аудита в PostgreSQL`

**2. `mctl-gitops`** — group `platform`, order `2`, repo
`https://github.com/mctlhq/mctl-gitops`
stack: `["ArgoCD", "Argo Workflows", "Helm", "OpenTofu", "Vault", "k3s"]`

EN summary:
`The ArgoCD source of truth: App-of-Apps, tenant and service charts, workflow templates, infrastructure as code.`

RU summary:
`Источник истины для ArgoCD: App-of-Apps, чарты тенантов и сервисов, шаблоны воркфлоу, инфраструктура как код.`

EN details:
- `self-healing sync every 60 seconds`
- `Vault with External Secrets as the only secret path`
- `SOC 2 documentation kit and operational runbooks`
- `platform skills catalog served over MCP`

RU details:
- `самовосстанавливающаяся синхронизация каждые 60 секунд`
- `Vault с External Secrets как единственный путь секретов`
- `комплект документации SOC 2 и эксплуатационные runbook'и`
- `каталог платформенных навыков, отдаваемый через MCP`

**3. `mctl-agents`** — group `platform`, order `3`, repo
`https://github.com/mctlhq/mctl-agents`
stack: `["Python", "Claude Agent SDK", "Temporal", "Argo Workflows"]`

EN summary:
`The DevLoop: durable Temporal workflows that turn an issue into a proposal, an approved proposal into a pull request, and a merged pull request into a deployment.`

RU summary:
`DevLoop: устойчивые Temporal-воркфлоу, превращающие issue в предложение, одобренное предложение — в pull request, а смерженный pull request — в деплой.`

EN details:
- `investigator, implementer, shepherd and mentor roles`
- `proposals stored as git state`
- `replay tests against recorded workflow histories`
- `architecture decision records`

RU details:
- `роли investigator, implementer, shepherd и mentor`
- `предложения хранятся как git-состояние`
- `replay-тесты на записанных историях воркфлоу`
- `записи архитектурных решений`

**4. `mctl-agent`** — group `platform`, order `4`, repo
`https://github.com/mctlhq/mctl-agent`
stack: `["Go", "SQLite", "AlertManager", "Claude API"]`

EN summary:
`Self-healing GitOps agent: an alert becomes a ticket, a matching skill diagnoses it, and a targeted fix lands as a pull request.`

RU summary:
`Самовосстанавливающийся GitOps-агент: алерт становится тикетом, подходящий навык диагностирует его, и точечное исправление приходит как pull request.`

EN details:
- `compiled built-in skills for OOM, image pull, rollback, drift, probes, throttling, quota and scale`
- `hot-reloadable YAML skills`
- `Telegram notifications`

RU details:
- `встроенные скомпилированные навыки для OOM, image pull, отката, дрейфа, проб, троттлинга, квот и масштабирования`
- `YAML-навыки с горячей перезагрузкой`
- `уведомления в Telegram`

**5. `mctl-portal`** — group `platform`, order `5`, repo
`https://github.com/mctlhq/mctl-portal`
stack: `["Backstage", "TypeScript", "React", "Playwright"]`

EN summary:
`Developer portal on Backstage with custom backend plugins for workflows, custom domains and GitHub App connection.`

RU summary:
`Портал разработчика на Backstage с собственными backend-плагинами для воркфлоу, кастомных доменов и подключения GitHub App.`

EN details:
- `multi-tenancy, OIDC federation, Vault-delivered secrets, live Kubernetes resource views`

RU details:
- `мультитенантность, федерация OIDC, доставка секретов из Vault, живые представления ресурсов Kubernetes`

**6. `mctl-design`** — group `platform`, order `6`, repo
`https://github.com/mctlhq/mctl-design`
stack: `["CSS", "design tokens", "Vue 3", "Storybook", "pnpm", "Turborepo"]`

EN summary:
`The shared design system: tokens, CSS themes, a Tailwind preset and Vue components, versioned in lockstep and served from a CDN.`

RU summary:
`Общая дизайн-система: токены, CSS-темы, пресет Tailwind и Vue-компоненты, версионируемые синхронно и отдаваемые с CDN.`

EN details:
- `immutable versioned stylesheets`
- `CI refuses to change a published version`
- `this site vendors version 0.5.0`

RU details:
- `неизменяемые версионированные таблицы стилей`
- `CI отказывается менять опубликованную версию`
- `этот сайт вендорит версию 0.5.0`

### Products

**7. `mctl-telegram`** — group `product`, order `7`, repo
`https://github.com/mctlhq/mctl-telegram`
stack: `["Go", "MTProto", "MCP", "OAuth 2.0"]`

EN summary:
`Remote MCP server that exposes a user's own Telegram account to AI clients, with an opt-in send gate, audit log and encrypted sessions.`

RU summary:
`Удалённый MCP-сервер, открывающий AI-клиентам собственный Telegram-аккаунт пользователя, с opt-in шлюзом отправки, журналом аудита и шифрованными сессиями.`

EN details:
- `per-tool read-only and destructive annotations`
- `three-condition send gate`
- `SSRF-guarded media`
- `submissions to ChatGPT Apps and Claude connectors`

RU details:
- `аннотации read-only и destructive на каждом инструменте`
- `трёхусловный шлюз отправки`
- `защита от SSRF при загрузке медиа`
- `заявки в каталоги ChatGPT Apps и коннекторов Claude`

**8. `seerrsense`** — group `product`, order `8`, repo
`https://github.com/mctlhq/seerrsense`
stack: `["TypeScript", "Fastify", "MCP", "PostgreSQL"]`

EN summary:
`Natural-language media requests for Seerr, Radarr and Sonarr over MCP: the model interprets intent, provider IDs stay the source of truth.`

RU summary:
`Запросы медиа на естественном языке для Seerr, Radarr и Sonarr через MCP: модель интерпретирует намерение, идентификаторы провайдеров остаются источником истины.`

EN details:
- `OAuth for both Claude and ChatGPT`
- `per-user connections`
- `directory submissions`

RU details:
- `OAuth для Claude и ChatGPT`
- `подключения на пользователя`
- `заявки в каталоги`

**9. `mctl-academy`** — group `product`, order `9`, repo
`https://github.com/mctlhq/mctl-academy`
stack: `["TypeScript", "Hono", "PostgreSQL", "Vue", "Playwright"]`

EN summary:
`A learning product with an evidence audit that quarantined and re-authored question banks after fabricated citations were found.`

RU summary:
`Обучающий продукт с аудитом доказательств, который поместил в карантин и переписал банки вопросов после обнаружения выдуманных цитат.`

EN details:
- `better-auth with GitHub sign-in`
- `schema-validated content`
- `a content-quality report as the ongoing check`

RU details:
- `better-auth со входом через GitHub`
- `контент, проверяемый по схеме`
- `отчёт о качестве контента как постоянная проверка`

**10. `mctl-loyalty`** — group `product`, order `10`, repo
`https://github.com/mctlhq/mctl-loyalty`
stack: `["TypeScript", "Express", "PostgreSQL", "Telegram Mini App"]`

EN summary:
`Loyalty system as a Telegram Mini App with anti-fraud QR.`

RU summary:
`Программа лояльности как Telegram Mini App с защитой от мошенничества через QR.`

EN details:
- `rotating codes`
- `one-time hashed tokens`
- `atomic burn`
- `daily limits enforced in the database`

RU details:
- `ротация кодов`
- `одноразовые хешированные токены`
- `атомарное погашение`
- `дневные лимиты на уровне БД`

**11. `mctl-pairdesk`** — group `product`, order `11`, repo
`https://github.com/mctlhq/mctl-pairdesk`
stack: `["TypeScript", "PostgreSQL", "Telegram Mini App"]`

EN summary:
`P2P exchange bulletin board without custody.`

RU summary:
`Доска P2P-обмена без кастодиального хранения.`

EN details:
- `contact reveal enforced in the backend`
- `racing accepts blocked by a row lock and a partial unique index`

RU details:
- `раскрытие контактов контролируется backend'ом`
- `гонка принятий блокируется блокировкой строки и частичным уникальным индексом`

**12. `pelican-libertex-social`** — group `product`, order `12`, repo
`https://github.com/mashkoffdmitry/pelican-libertex-social`
stack: `["Node.js", "OIDC PKCE", "Cloudflare Workers", "R2"]`

EN summary:
`Read-only proxy for a copy-trading catalog.`

RU summary:
`Read-only прокси для каталога копитрейдинга.`

EN details:
- `autonomous OIDC token rotation`
- `an edge cache`
- `also published as a Vue package`

RU details:
- `автономная ротация OIDC-токенов`
- `edge-кеш`
- `также опубликован как Vue-пакет`

**13. `pfeifenpatenschaft-backend`** — group `product`, order `13`,
**no `repo` field** (the repository is private and returns 404 to an anonymous
visitor; the card carries no repository link)
stack: `["TypeScript", "Express", "PostgreSQL"]`

EN summary:
`Organ-pipe sponsorship backend.`

RU summary:
`Backend спонсорства органных труб.`

EN details:
- `race-safe 15-minute reservations`
- `integer-cent money`
- `payment confirmation webhooks`
- `versioned migrations`

RU details:
- `безопасные к гонкам 15-минутные брони`
- `деньги в целых центах`
- `вебхуки подтверждения оплаты`
- `версионированные миграции`

**14. `mctl-openclaw`** — group `product`, order `14`, repo
`https://github.com/mctlhq/mctl-openclaw`
stack: `["TypeScript", "pnpm", "upstream fork"]`

EN summary:
`Maintained fork of an open-source assistant gateway: owner-gated OAuth connect flow, weekly upstream-sync pipeline with a review gate, hosted deployment into platform tenants.`

RU summary:
`Поддерживаемый форк open-source шлюза ассистента: OAuth-подключение под контролем владельца, еженедельный пайплайн синхронизации с upstream через ревью-гейт, размещение в тенантах платформы.`

The issue states the required meaning of this project's details rather than
their wording ("Details must state that repository totals reflect the upstream
project; the owner's contribution is the fork layer and the deployment
pipeline"). The wording below is therefore authored by this proposal and is
itself normative; use it verbatim.

EN details:
- `repository totals reflect the upstream project`
- `the owner's contribution is the fork layer and the deployment pipeline`

RU details:
- `итоги репозитория отражают upstream-проект`
- `вклад владельца — слой форка и пайплайн развёртывания`

### Interface strings added to `src/i18n/ui.ts`

Added to the `ui` object (each a `{ en, ru }` string pair, so
`test/ui.test.ts` keeps passing):

- `workGroupPlatform`: `{ en: 'Platform', ru: 'Платформа' }`
- `workGroupProducts`: `{ en: 'Products', ru: 'Продукты' }`
- `workDetailsSummary`: `{ en: 'Details', ru: 'Подробнее' }` (the `<summary>`
  label of each card's `<details>` element)
- `workMetricsLabel`: `{ en: 'Repository metrics', ru: 'Метрики репозитория' }`
- `workPageTitle`: `{ en: 'Work — Dmitrii Mashkov', ru: 'Work — Dmitrii Mashkov' }`
  (the `<title>` element holds one string and stays Latin, exactly as
  `homeTitle` already does)

The page heading reuses the existing `ui.navWork` pair
(`{ en: 'Work', ru: 'Работы' }`); no new heading string is introduced.

Added to `src/i18n/ui.ts` as a **separate export**, not as a key inside the
`ui` object (a nested map inside `ui` would fail `test/ui.test.ts`, which
requires every `ui` value to be an `{ en, ru }` pair):

```ts
export const stackChipRu: Record<string, string> = {
  'design tokens': 'дизайн-токены',
  'upstream fork': 'форк upstream',
};
```

Those are the only two chips in the fourteen stack arrays that are plain words.
Every other chip is a language, product or tool name and stays untranslated,
resolved by falling back to the frontmatter string.

## Out of scope

- Numeric metrics per project. The `per_repo` entry of the metrics snapshot is
  issue P8b; until it lands the card's metrics area renders an em dash.
- Screenshots, images or any other binary asset for a project.
- The `/approach/` and `/colophon/` pages (P6, P7) and the `/#approach` nav
  anchor that points at them.
- Any change to `src/data/metrics.json`, `src/lib/metrics.ts`,
  `scripts/vendor-assets.mjs`, `scripts/csp-hash.mjs`, `Dockerfile`,
  `nginx.conf` or the CSP.
- Any change to `.github/workflows/claude-review.yml`,
  `.github/workflows/release-please.yml` or `.github/dependabot.yml`
  (reserved by AGENTS.md).
- Adding a network-dependent link check to `npm test`.
- Per-project tags, filters, search or pagination on `/work/`.

## Open questions

- The issue gives no `<title>` string and no page heading for `/work/`. Decided:
  `<title>` is `Work — Dmitrii Mashkov` (one Latin string, following
  `homeTitle`), and the `<h1>` reuses the existing `ui.navWork` pair. A reviewer
  who prefers different wording can change these two strings without touching
  anything else.
- The issue gives no label for the metrics slot, only that it renders an em dash
  until P8b. Decided: a `workMetricsLabel` pair (`Repository metrics` /
  `Метрики репозитория`) followed by `formatStat(null)`. P8b replaces the value,
  not the label. The `<summary>` label (`Details` / `Подробнее`) is invented by
  this proposal for the same reason: a `<details>` element cannot render without
  one. Both are interface chrome, not project copy.
- The existing `mctl-api` entry carries an extra `links` entry (`Docs` /
  `Документация` -> `https://docs.mctl.ai`) that the issue's per-project link
  rule does not mention. Decided: keep it. The issue's rule is a minimum
  ("Links per project: the GitHub repository URL"), the link resolves, and
  removing already-reviewed content is not asked for.
- `src/components/Nav.astro` links to `/#work`, a fragment that no longer
  matches any element since P4 removed `id="work"` from the home page. Decided:
  repoint it to `/work/`, the page this proposal creates. It is a one-line
  change, it is on every page the acceptance criteria are checked against, and
  leaving a nav item pointing at a dead fragment while the real page exists
  would be a defect shipped knowingly. `/#approach` stays until P6.
- The issue says the repository link is "the GitHub repository URL" but gives no
  link text. Decided: the link text is the URL's `host + path`
  (`github.com/mctlhq/mctl-api`), derived from the `repo` field. It is an
  identifier, identical in both languages, so it needs no `.l.en` / `.l.ru`
  pair and adds no new copy.
- Detail bullets are given in the issue as semicolon-separated clauses. Decided:
  one bullet per semicolon-separated clause, with the trailing full stop
  dropped, exactly as transcribed in the copy tables above. `mctl-portal`'s
  details are a single comma-separated clause and therefore a single bullet.
