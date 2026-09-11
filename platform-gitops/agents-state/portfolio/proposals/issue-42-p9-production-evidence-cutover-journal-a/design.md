# Design: issue-42-p9-production-evidence-cutover-journal-a

## Current state

**Content collections.** `src/content.config.ts` defines three collections.
`journal` globs `[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-*.md` out of
`src/content/journal` with a `z.strictObject` schema: `service` (enum
`portfolio | mctl-agents | mctl-api`), `issue` (a `https://github.com/...`
regex), `proposal_slug`, optional `pr`, optional `release` (semver, no `v`),
`visibility`, bilingual `title` and `decided`, a required `issue_opened_at` and
optional `proposal_approved_at` / `merged_at` / `released_at` / `deployed_at`,
plus `interventions: [{what, why, at}]` defaulting to `[]`. Every timestamp goes
through the `stamp` refinement, which requires `isoWithOffset` — an ISO 8601
string with `Z` or `±HH:MM` — and whose error message spells out why the value
must be quoted in YAML ("quote it so YAML does not parse it into a Date").
`strictObject` means an unexpected key is a build error, so the set of keys in a
new entry is not a free choice.

`adr` globs `[0-9][0-9][0-9][0-9]-*.md` with `id` (positive int), bilingual
`title`, `status`, `date` (`yyyyMmDd` regex, hence quoted in every existing
file), optional `supersedes`, and `visibility`. Its loader is wrapped by
`adrLoader()`, which after the base sync calls `checkAdrBodies()` from
`src/lib/adr.ts`. That function aggregates `adrBodyProblems()` across every
entry and additionally asserts that the frontmatter `id` padded to four digits
equals the filename's four-digit prefix. `adrBodyProblems()` splits the body on
`^##[ \t]+(.*)$`, identifies each section **only** from its
`<span class="l en">…</span>` text against
`ADR_SECTIONS = ['Context', 'Decision', 'Consequences', 'Drivers', 'Revisit criteria']`,
and reports: a missing section, the five present but out of order, a heading
without a `class="l ru"` span, and any section body missing a `class="l en"` or
`class="l ru"` block. This runs on `astro sync`, `check`, `dev` and `build`
alike.

**Existing content.** `src/content/journal/` holds eleven files, all
`visibility: public`, carrying seventeen `- what:` intervention items between
them (three in `2026-09-10-astro-static-skeleton-and-nginx-image.md`, three in
`2026-09-10-base-layout-vendored-tokens-and-fonts.md`, two in each of the two
non-`portfolio` entries, seven in `2026-09-11-work-page.md`, zero in the rest).
Nine of the eleven are `service: portfolio`. **Every one of the eleven has an
empty markdown body** — frontmatter, closing `---`, nothing after it. The most
recent, `2026-09-11-p8-production-hardening-accessibility-wc.md`, carries
`issue_opened_at` and `proposal_approved_at` only: no `pr`, no `release`, no
`merged_at`. It is the exact precedent for the entry this cycle adds.
`src/content/adr/` holds `0001-bootstrap-boundary.md`,
`0002-static-astro-no-client-bundles.md`, `0004-no-analytics.md` and
`0005-self-contained-runtime-assets.md` — all `visibility: public`, all
`status: accepted`, all with `date: '2026-09-11'`-style quoted dates. `0003` is
free.

**The colophon.** `src/pages/colophon/index.astro` calls
`publicEntries(await getCollection('journal')).sort(byNewestFirst)` and the same
for `adr` with `byAdrId`, then computes `cycleCount = journal.length` and
`interventionsTotal = totalInterventions(journal.map((e) => e.data))` from
`src/lib/journal.ts`. Both land in the markup as
`data-cycle-count={cycleCount}` / `data-intervention-count={interventionsTotal}`
next to the bilingual `ui.colophonTotalCycles` / `ui.colophonTotalInterventions`
labels — no number is typed. The page renders three sections: the chain list
(two `<ul>`s, `.l.en` and `.l.ru`, mapped straight off
`ui.colophonChainItems`), `<CycleTable entries={journal} />`, and the ADR index
table, whose every row is `padAdrId(entry.data.id)` plus a link to
`/colophon/adr/${entry.id}/`. Adding a public ADR file is therefore the whole of
"list it in the decisions table".

`src/i18n/ui.ts` holds `colophonChainItems` as a
`{ en: string[]; ru: string[] }` pair with five items each (source, image,
runtime, release, "Onboarding, rollbacks and custom domains: mctl MCP tools
only"). `test/ui.test.ts` walks every `ui` value and requires `en`/`ru` to be
the same kind and, for arrays, the same length with no empty item — so the two
arrays must grow together.

`src/pages/colophon/journal/[...slug].astro` renders `journal-meta`
(`service`, `issue`, `pr` or an em dash, `release` or an em dash, lead time via
`formatLeadTime(leadTimeHours(data))`), the `decided` paragraph, the timeline
(filtered to the timestamps that are present), and the interventions list —
`<ol class="interventions" lang="en">`, preceded by the bilingual
`ui.journalInterventionsNote`: "Each record below is quoted verbatim in English,
the language it was written in." It **does not** import `render` and emits no
`<Content />`. `src/pages/colophon/adr/[...slug].astro`, by contrast, does
`const { Content } = await render(entry)` and wraps it in
`<div class="mctl-prose">`.

`src/lib/journal.ts` supplies `cycleTimestamp`, which dates and sorts an entry
by `deployed_at ?? released_at ?? merged_at ?? proposal_approved_at ??
issue_opened_at`; with none of the first three present, the new entry sorts and
dates on its `proposal_approved_at`. `leadTimeHours` returns `null` without a
`deployed_at`, and `formatLeadTime` renders `null` as an em dash — so the new
row shows `—` in the lead-time column, as the P8 row already does.

**Gates.** `npm test` runs `scripts/check-no-metrics.mjs`,
`scripts/check-contrast.mjs` and fourteen `node --test` suites. `prebuild` is
`npm run vendor && npm test`, so every one of them runs before `astro build`.
`scripts/check-dist.mjs` runs **after** the build and only from the `Dockerfile`
(`RUN npm run build && node scripts/check-dist.mjs && node scripts/csp-hash.mjs …`)
or by hand; it is not in `npm test` and not in
`.github/workflows/build.yml`. Its `checkColophonPages()` re-scans
`src/content/journal` and `src/content/adr` with `idsByVisibility()` —
`^visibility:\s*(public|private)\s*$` per file, `^\s*-\s+what:` counted per
public file — and fails unless `data-cycle-count`, `data-intervention-count` and
the `data-cycle-row` count all match that independent scan; it also requires one
`dist/colophon/{journal,adr}/<id>/index.html` per public entry and none per
private one. `checkSitemap()` builds the expected URL set from the same scan.
Globally it fails on any `.js` under `dist/`, any `<style` or ` style="` in a
`dist/**/*.html`, any absolute-URL subresource, and any HTML file whose
`class="l en"` and `class="l ru"` counts differ.

`scripts/check-no-metrics.mjs` scans **only** `src/pages`, `src/components` and
`src/layouts` for `\b[0-9]{2,}\b`. `src/i18n/ui.ts` is outside that scan, so the
`301` in the new chain copy needs no `RULES` or `ALLOW` change; and `src/content`
is outside it too, so the timestamps in the new markdown are unaffected. The
`ALLOW` list is self-policing — a stale entry fails the run — which is a reason
not to touch it.

**Docs.** `docs/hardening-notes.md` records issue #10's work in five sections
(response headers table, "Header set defined once", "`style-src` and the inline
script", "Open Graph image: SVG, not raster", and "Lighthouse mobile (reviewer
step, post-deployment)" with an empty four-row score table and the line "_Not
yet run — the implementer has no browser. Fill in after deployment._").
`docs/accessibility-checklist.md` is the sibling precedent for a committed
`pass` / `reviewer step` table.

**Boundary.** `AGENTS.md` (ADR-0001) reserves only `README.md`, `AGENTS.md`,
`LICENSE`, `.gitignore`, the two release-please files and three workflows to
humans; content, journal, ADRs and docs are the implementer's. It also states
that DNS and wiring changes are outside the DevLoop and must be recorded as
manual interventions in the next cycle's journal entry — which is precisely what
the fourth intervention in Copy A says about itself.

## Proposed solution

Four files change; nothing under `src/pages`, `src/components`, `src/lib`,
`scripts/` or `test/` is touched. Every acceptance criterion is already
enforced by machinery that exists.

1. **New: `src/content/journal/2026-09-11-production-cutover.md`** — Copy A
   verbatim as frontmatter, Copy B verbatim as the markdown body. The filename
   matches the journal glob; `visibility: public` makes it the twelfth public
   cycle; its four `interventions` raise the derived total from seventeen to
   twenty-one. Omitting `pr`, `release`, `merged_at`, `released_at` and
   `deployed_at` is legal (all optional) and makes `cycleTimestamp` date the row
   on `proposal_approved_at` and the lead-time cell render an em dash. The body
   is committed evidence only: the journal route renders no `<Content />` (see
   Alternatives 1 and `requirements.md` Open question 2).

2. **New: `src/content/adr/0003-custom-domain-via-mctl-registry.md`** — Copy C.
   `id: 3` matches the `0003` filename prefix, so `checkAdrBodies`' prefix
   assertion holds. The five sections appear in `ADR_SECTIONS` order, each
   heading as `## <span class="l en">X</span><span class="l ru">Y</span>` and
   each body as a `<div class="l en">` / `<div class="l ru" lang="ru">` pair with
   blank lines inside the divs so markdown still renders the prose as a
   paragraph — byte-for-byte the shape of `0004-no-analytics.md`. Being
   `visibility: public`, it appears in the decisions table
   (`src/pages/colophon/index.astro` maps every public ADR) and gets
   `/colophon/adr/0003-custom-domain-via-mctl-registry/` from
   `src/pages/colophon/adr/[...slug].astro`'s `getStaticPaths`, which
   `checkColophonPages()` and `checkSitemap()` then both require to exist. One
   `.l.en` span per heading and per body, one `.l.ru` each: parity holds.

3. **Edit: `src/i18n/ui.ts`** — append two items to `colophonChainItems.en` and
   the two corresponding items to `colophonChainItems.ru` (Copy D), keeping the
   arrays equal in length for `test/ui.test.ts` and the rendered `.l.en` /
   `.l.ru` lists balanced for `check-dist`. No other key changes; in particular
   the derived totals' labels stay as they are.

4. **Edit: `docs/hardening-notes.md`** — append one new section (Copy E) after
   the existing content, reporting the P8 reviewer-step results in the issue's
   order: HAR, CSP, the two disabled Cloudflare rewrites, and Lighthouse mobile
   still outstanding. The existing "Lighthouse mobile (reviewer step,
   post-deployment)" section and its empty score table stay exactly as they are,
   so the document says twice, in two places, that the run has not happened.

Why this shape. The cycle count and intervention total are *already* derived and
*already* cross-checked against an independent filesystem scan, so "no integer
literal in `src/`" is satisfied by changing nothing — the safest way to meet that
criterion is to leave `src/pages/colophon/index.astro` alone. "ADR-0003 is listed
in the decisions table with its own page" is likewise a property of adding a
public ADR file, not of editing a template. And the two new chain items are copy,
which belongs in `src/i18n/ui.ts` by the same rule that put the other five there.
The diff is four files, two of them new content, and every claim in it is
checkable by a gate that already runs.

### Copy A — journal frontmatter, verbatim

Two values cannot be known while this proposal is being written and are marked
with `<<…>>`; `tasks.md` task 2 gives the exact command for each. Everything
else is literal.

```yaml
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/42
proposal_slug: issue-42-p9-production-evidence-cutover-journal-a
visibility: public
title:
  en: "Production cutover: apex domain, rollback drill and edge hardening"
  ru: "Переключение в прод: апекс-домен, учебный откат и укрепление на границе"
decided:
  en: "dmitriimashkov.com serves the site through the mctl custom-domain registry with Cloudflare proxying and a Let's Encrypt certificate issued by DNS-01, and the rollback path was exercised before the domain went live rather than after."
  ru: "dmitriimashkov.com отдаёт сайт через реестр кастомных доменов mctl с проксированием Cloudflare и сертификатом Let's Encrypt, выпущенным через DNS-01, а путь отката был проверен до того, как домен стал публичным, а не после."
issue_opened_at: '<<createdAt of github.com/mctlhq/portfolio/issues/42, ISO 8601 UTC, e.g. 2026-09-11T13:05:00Z>>'
proposal_approved_at: '<<approval.approved_at from this proposal .status.yaml, ISO 8601 UTC>>'
interventions:
  - what: "rolled the service back to 0.1.3 and restored 0.1.4, running the production contract at each of the three points"
    why: "the rollback path is the one thing a site cannot claim without having used it, and the right time to use it is while the only live host is the rehearsal one"
    at: '2026-09-11T08:09:34Z'
  - what: "disabled Cloudflare Web Analytics for the zone"
    why: "the edge injected static.cloudflareinsights.com/beacon.min.js into every page against ADR-0004; the content security policy blocked it, so nothing ran, but the tag shipped in the markup and every load produced a blocked third-party request"
    at: '2026-09-11T13:28:00Z'
  - what: "disabled Cloudflare Email Obfuscation for the zone"
    why: "the edge replaced the contact mailto with a /cdn-cgi/l/email-protection link and injected a decoder script, so the contact link stopped working with JavaScript off — on a site whose promise is full usability without JavaScript"
    at: '2026-09-11T13:32:00Z'
  - what: "repointed the apex from a dead CNAME, deleted the equally dead tsvilt record, added www and a 301 redirect rule that excludes the ACME challenge path"
    why: "DNS and the redirect ruleset are wiring, outside the DevLoop by ADR-0001, so every change to them is recorded here"
    at: '2026-09-11T14:14:00Z'
---
```

No `pr`, `release`, `merged_at` or `released_at` key: they are filled in by the
next cycle's backfill, the way issue #9 backfilled four earlier entries. No
`deployed_at` either, for the same reason — which also means the lead-time cell
renders an em dash rather than a number.

### Copy B — the operational record, for the entry body

Placed immediately after the closing `---` of the frontmatter, as a markdown
table followed by the closing line:

```markdown
| at (UTC) | event | operation | result |
|---|---|---|---|
| 2026-09-11T00:17:50Z | release 0.1.0 tagged | release-please | first release |
| 2026-09-11T00:21:36Z | rehearsal domain registered | `mctl_add_custom_domain` | `preview.dmitriimashkov.com` |
| 2026-09-11T00:22:23Z | rehearsal ingress and certificate | `add-custom-domain-afc48c5f` | verified 00:22:27, active 00:22:34 |
| 2026-09-11T08:09:34Z | rollback 0.1.4 → 0.1.3 | `rollback-service-5ee1f939` | Succeeded 08:10:39 |
| 2026-09-11T08:10:43Z | contract at 0.1.3 | `scripts/prod-contract.sh` | 11 passed, 0 failed; `/work/` 404, correct for that tag |
| 2026-09-11T08:10:50Z | restore 0.1.3 → 0.1.4 | `deploy-service-8f79f8ff` | Succeeded 08:13:52 |
| 2026-09-11T08:13:53Z | contract at 0.1.4 | `scripts/prod-contract.sh` | 12 passed, 0 failed |
| 2026-09-11T14:13:55Z | apex registered | `mctl_add_custom_domain` | `dmitriimashkov.com`, TXT challenge minted |
| 2026-09-11T14:14:27Z | apex verified, workflow triggered | `add-custom-domain-7a4245fe` | verified by TXT; Succeeded 14:15:22 |
| 2026-09-11T14:16:27Z | certificate reissued | cert-manager | Ready for `preview.dmitriimashkov.com` and `dmitriimashkov.com` |
| 2026-09-11T14:16:30Z | apex first 200 | — | `https://dmitriimashkov.com/` |
| 2026-09-11T14:16:53Z | contract on the apex | `scripts/prod-contract.sh dmitriimashkov.com` | **14 passed, 0 failed** |

Time from apex registration to a green contract: under three minutes.
```

Note for the implementer: `scripts/prod-contract.sh` is named here as the
operation that was run against the deployed site. It is a record of what
happened, not an instruction to create the script — creating it is not in this
proposal's task list and not in the issue's file list.

### Copy C — ADR-0003, verbatim

File: `src/content/adr/0003-custom-domain-via-mctl-registry.md`.

Frontmatter:

```yaml
---
id: 3
title:
  en: "Custom domain through the mctl registry, proxied by Cloudflare, certificate by DNS-01"
  ru: "Кастомный домен через реестр mctl, проксирование Cloudflare, сертификат через DNS-01"
status: accepted
date: '2026-09-11'
visibility: public
---
```

Body, five sections in this order. Each heading is
`## <span class="l en">EN</span><span class="l ru">RU</span>`; each section body
is a `<div class="l en">` block and then a `<div class="l ru" lang="ru">` block,
each with a blank line after the opening tag and before the closing tag, exactly
as in `src/content/adr/0004-no-analytics.md`.

Headings: `Context` / `Контекст`, `Decision` / `Решение`, `Consequences` /
`Последствия`, `Drivers` / `Движущие факторы`, `Revisit criteria` /
`Критерии пересмотра`.

**Context — en:**

> The site had to answer on dmitriimashkov.com, a zone the owner controls, while every deployment stayed inside the platform. The platform has a custom-domain registry that no tenant had used before: this was its first end-to-end run.

**Context — ru:**

> Сайт должен был отвечать на dmitriimashkov.com — зоне, которой владелец управляет, — при том что весь деплой остаётся внутри платформы. В платформе есть реестр кастомных доменов, которым до этого не пользовался ни один тенант: это был его первый сквозной прогон.

**Decision — en:**

> Register the domain with mctl_add_custom_domain, prove ownership with the TXT challenge it mints, and let mctl_verify_domain trigger the workflow that updates the ingress and orders the certificate. Point the apex at the service with a proxied CNAME, relying on Cloudflare's flattening, and send www to the apex with a 301 redirect rule at the edge.

**Decision — ru:**

> Регистрировать домен через mctl_add_custom_domain, подтверждать владение TXT-челленджем, который он выдаёт, и позволять mctl_verify_domain запускать воркфлоу, обновляющий ingress и заказывающий сертификат. Апекс направлять на сервис проксированным CNAME, полагаясь на flattening в Cloudflare, а www отправлять на апекс редирект-правилом 301 на границе.

**Consequences — en:**

> The certificate is issued by Let's Encrypt through the DNS-01 solver against the Cloudflare API, not HTTP-01: the plan said HTTP-01 and was wrong, and the cluster issuer settles it. Because www is answered at the edge it never reaches the origin, so the origin certificate does not need that name — the 526 seen before the redirect rule existed was the correct behaviour of SSL mode strict, not a fault to fix by widening the certificate. Mail is unaffected: the zone's three MX records, DMARC, both SPF records and the DKIM key were never named in a write.

**Consequences — ru:**

> Сертификат выпускает Let's Encrypt через решатель DNS-01 к API Cloudflare, а не через HTTP-01: в плане был указан HTTP-01, и это неверно — решает конфигурация ClusterIssuer. Поскольку www отвечает на границе, он не доходит до origin, и origin-сертификату это имя не нужно: ошибка 526 до появления редирект-правила была корректным поведением режима strict, а не поводом расширять сертификат. Почта не затронута: три MX-записи зоны, DMARC, оба SPF и ключ DKIM ни разу не участвовали в запросах на изменение.

**Drivers — en:**

> Prove the platform's own registry rather than wiring DNS by hand. Rehearse on a disposable host first. Never touch mail records. Keep the rollback path exercised before the domain becomes public.

**Drivers — ru:**

> Проверить собственный реестр платформы, а не прописывать DNS руками. Сначала репетировать на одноразовом хосте. Не трогать почтовые записи. Прогнать путь отката до того, как домен станет публичным.

**Revisit criteria — en:**

> Revisit if the platform gains an apex-aware ingress that removes the need for CNAME flattening, if certificate issuance moves off DNS-01, or if a second custom domain makes a per-domain certificate preferable to one certificate carrying every name.

**Revisit criteria — ru:**

> Пересмотреть, если в платформе появится ingress, знающий про апекс, и flattening перестанет быть нужен; если выпуск сертификата уйдёт с DNS-01; или если второй кастомный домен сделает посертификатное разделение предпочтительнее одного сертификата на все имена.

The five blockquotes above are the prose only; the `>` markers are this
document's quoting and must not be copied into the ADR. Each block goes inside
its `<div class="l en">` / `<div class="l ru" lang="ru">` wrapper as a plain
paragraph.

### Copy D — the live hosts for the colophon

Append to `ui.colophonChainItems.en`, in this order, after the existing five:

```
'Live at dmitriimashkov.com; www redirects to it with a 301',
'Rehearsal host preview.dmitriimashkov.com shares the same certificate and stays until the apex has been observed',
```

Append to `ui.colophonChainItems.ru`, in the same order, after the existing
five:

```
'Работает на dmitriimashkov.com; www перенаправляется на него с кодом 301',
'Репетиционный хост preview.dmitriimashkov.com делит тот же сертификат и остаётся, пока апекс не будет отнаблюдён',
```

Quoting follows the file's existing style: single quotes, or double quotes only
where the string itself contains an apostrophe (neither of these does).

### Copy E — the reviewer-step results for `docs/hardening-notes.md`

Appended as a new final section. Wording may be formatted as prose or as a
table in the style of the existing sections, but must state these four things in
this order and must not contradict the existing Lighthouse section.

Heading: `## Reviewer-step results from #10 (post-deployment)`

1. **HAR check — pass.** A HAR capture of all four pages — `/`, `/work/`,
   `/approach/`, `/colophon/` — in both languages and both themes shows zero
   off-origin requests. Every byte the browser fetched came from the site's own
   origin, as ADR-0004 and ADR-0005 require.
2. **CSP check — pass by construction.** Zero `<style>` tags and zero `style=`
   attributes in the built markup, zero external scripts, and exactly one inline
   script per page — the language/theme bootstrap in
   `src/layouts/Base.astro` — whose SHA-256 is listed in `script-src` by
   `scripts/csp-hash.mjs` and substituted into `security-headers.conf` at image
   build time. `scripts/check-dist.mjs` fails the build on a `<style` element, a
   ` style="` attribute or any absolute-URL subresource, so this property is
   mechanically held rather than observed once.
3. **Two Cloudflare edge rewrites had to be disabled before either check could
   pass.** Cloudflare **Web Analytics** injected
   `static.cloudflareinsights.com/beacon.min.js` into every page, against
   ADR-0004; the Content-Security-Policy blocked it, so nothing executed, but
   the tag shipped in the markup and every page load produced a blocked
   third-party request. Cloudflare **Email Obfuscation** replaced the contact
   `mailto:` with a `/cdn-cgi/l/email-protection` link and injected a decoder
   script, which broke the contact link with JavaScript disabled — on a site
   whose promise is full usability without JavaScript. Both were disabled for the
   zone; both are recorded as manual interventions in the journal entry for this
   cycle, because the edge configuration is wiring and sits outside the DevLoop
   by ADR-0001.
4. **Lighthouse mobile — not run; still outstanding for a human.** The
   implementer has no browser, so the mobile Lighthouse pass over the four pages
   has not been performed and remains a reviewer step. The empty score table in
   the "Lighthouse mobile (reviewer step, post-deployment)" section above is the
   place to record it.

## Alternatives

1. **Render the journal markdown body on `/colophon/journal/<id>/`.** Add
   `const { Content } = await render(entry)` to
   `src/pages/colophon/journal/[...slug].astro` and a
   `<div class="mctl-prose"><Content /></div>` section, mirroring the ADR route,
   so the operational record is published rather than merely committed.
   Dropped for this cycle: the issue's "Files expected to change" list names
   four files and does not include the route or a new `ui` key, and an
   English-only twelve-row table on a page where every other string is a
   bilingual pair is a content-design decision that deserves its own issue — the
   interventions list needed a bilingual `ui.journalInterventionsNote` ("quoted
   verbatim in English, the language it was written in") for exactly this
   reason. It is also the highest-risk edit available here: `render()` would then
   be called for eleven entries with empty bodies, on a route that eleven
   `check-dist` page assertions depend on. Recorded as
   `requirements.md` Open question 2 with a recommended follow-up issue.
2. **Bilingualise the operational table.** Write Copy B twice, inside `.l.en` /
   `.l.ru` wrappers, so it could be rendered without breaking the site's
   bilingual rule or `check-dist`'s span-parity check. Dropped: the issue
   supplies exactly one table and the copy is the contract (AGENTS.md) — an
   implementer that invented a Russian half of twelve rows of operation names
   and workflow ids would be inventing prose, which is the failure mode that
   deadlocked issue #7. Translating `add-custom-domain-7a4245fe` or
   `11 passed, 0 failed` would also produce worse evidence, not better.
3. **Delete or privatise three journal entries to make the colophon read
   "nine public cycles" as the issue's first criterion states.** Dropped
   outright: the count is derived and cross-checked by `check-dist` against a
   filesystem scan, so the only way to reach nine is to remove real cycles from
   a public record whose entire value is that nothing was removed. The criterion's
   own second half — "the cycle count and intervention total remain derived, with
   no integer literal in `src/`" — is what is actually implemented; the "nine" is
   a stale number (see `requirements.md` Open question 1).
4. **Add a `test/` assertion that `colophonChainItems` names both hostnames and
   that ADR-0003 exists.** Dropped: it would add a fifth changed file for a
   property three existing gates already cover — `checkColophonPages()` requires
   a page per public ADR, `checkSitemap()` requires its URL, and
   `test/ui.test.ts` already enforces `en`/`ru` array parity. The repository's
   rule is one cycle at a time with the smallest diff that carries the evidence.

## Platform impact

**Migrations.** None. No schema change: every key used by the new journal entry
and the new ADR already exists in `src/content.config.ts`, and no key is added
or removed. No database, no gitops values, no `mctl_*` operation. No dependency
change, so `package-lock.json` is untouched and the
`npm install --package-lock-only` rule in AGENTS.md does not come into play.

**Backward compatibility.** Additive. The eleven existing journal entries, the
four existing ADRs and the five existing chain items are unchanged. The
`colophonChainItems` arrays grow from five to seven in both languages, which
`test/ui.test.ts` accepts as long as they grow together. `/colophon/` gains one
table row and two list items per language; two new static pages appear; the
sitemap gains two URLs. `data-cycle-count` moves from 11 to 12 and
`data-intervention-count` from 17 to 21, both computed — any reader comparing
the page against `src/content/journal/` gets the same answer, which is the point.

**Resource impact.** Two more pages in `dist/`, a handful of kilobytes. The
40 KB cap in `scripts/check-dist.mjs` applies to `dist/index.html` only, which
this cycle does not touch. `/colophon/` grows by two `<li>` pairs and one table
row and has no cap. No new font, image, script or stylesheet; zero additional
browser requests.

**Risks and mitigations.**

- *ADR body shape rejected at build time.* `checkAdrBodies` is strict about
  section identity (English span text only), order, the Russian heading span and
  the per-section `.l.en` / `.l.ru` blocks. Mitigation: copy the exact structure
  of `src/content/adr/0004-no-analytics.md` and run `npm run build`, which
  invokes the loader and prints every problem at once.
- *A YAML timestamp parsed into a `Date`.* An unquoted `issue_opened_at` or
  `at:` value becomes a `Date`, fails the `stamp` refinement's `isoWithOffset`
  string test, and separately fails `test/colophon.test.ts`, which asserts every
  such value is single-quoted. Mitigation: single-quote all six timestamps in
  Copy A, and `date: '2026-09-11'` in Copy C.
- *An unresolved `<<…>>` placeholder shipped.* Both marked values in Copy A must
  be replaced with real stamps; a literal placeholder fails `ISO_WITH_OFFSET` in
  both the schema and `test/colophon.test.ts`, so it cannot reach `main`
  silently. Mitigation: tasks 2 and T2.
- *Bilingual span parity broken on the new ADR page.* One `.l.en` and one
  `.l.ru` per heading and per section body keeps the counts equal; a stray
  unpaired span fails `scripts/check-dist.mjs`. Mitigation: T4 runs `check-dist`
  explicitly.
- *`301` in the new chain copy read as a typed metric.* It is not:
  `scripts/check-no-metrics.mjs` scans only `src/pages`, `src/components` and
  `src/layouts`, and the string lives in `src/i18n/ui.ts`. Mitigation: T1 runs
  `npm test`, which runs that gate; no `ALLOW` entry is added, since a
  needless one would itself fail the stale-entry check.
- *The published record is judged incomplete because the body does not render.*
  Real and accepted for this cycle; flagged as `requirements.md` Open question 2
  with a concrete follow-up. The record is in git either way, which is where a
  claim about provenance is actually verified.
- *AGENTS.md's "no third parties in a public entry" read strictly.* The supplied
  copy names Cloudflare and Let's Encrypt. Flagged as `requirements.md` Open
  question 4 for the human approving this proposal; the copy is used as given.
