# Design: issue-89-q14-ten-projects-on-work-service-links-t

## Current state

Read in the clone at `mctlhq/portfolio` main.

### Content

`src/content/projects/` holds 28 files, `<slug>.en.md` and `<slug>.ru.md` for
fourteen slugs. Frontmatter today (`order` from the `.en.md` files):

| order | slug | group |
|---|---|---|
| 1 | `mctl-api` | platform |
| 2 | `mctl-gitops` | platform |
| 3 | `mctl-agents` | platform |
| 4 | `mctl-agent` | platform |
| 5 | `mctl-portal` | platform |
| 6 | `mctl-design` | platform |
| 7 | `mctl-telegram` | product |
| 8 | `seerrsense` | product |
| 9 | `mctl-academy` | product |
| 10 | `mctl-loyalty` | product |
| 11 | `mctl-pairdesk` | product |
| 12 | `pelican-libertex-social` | product |
| 13 | `pfeifenpatenschaft-backend` | product |
| 14 | `mctl-openclaw` | product |

`src/content.config.ts:35-46` defines `projectsSchema`: `slug`, `lang`, `name`,
`group` (`platform | product`), `order` (non-negative int), optional `repo`
(`githubUrl`), optional `private` (boolean), `stack`, one-line `summary`, and
an optional `links` array of `{ label, url }` where `url` is `httpsUrl`
(`^https:\/\/[^\s]+$`). `projectsLoader()` (`src/content.config.ts:102-118`)
wraps the glob loader and runs `checkProjectParity` over the whole store after
sync: exactly one `en` and one `ru` per slug, agreeing on `group`, `order`,
`repo`, `private`, `stack` and `links[].url` (`src/content.config.ts:74-86`).
That check runs on `astro sync`, `astro check`, `astro dev` and `astro build`
alike.

`src/content/projects/mctl-api.en.md` is the one file with a `links` array:

```yaml
links:
  - label: "Docs"
    url: https://docs.mctl.ai
```

and `mctl-api.ru.md` carries the same `url` with `label: "Документация"`.

`src/content/projects/pfeifenpatenschaft-backend.{en,ru}.md` are the only files
with `private: true` and no `repo:`.

`src/content/projects/seerrsense.en.md` currently reads
`summary: "Natural-language media requests for Seerr, Radarr and Sonarr over MCP: the model interprets intent, provider IDs stay the source of truth."`
with body bullets `- OAuth for both Claude and ChatGPT`,
`- per-user connections`, `- directory submissions`; the `.ru.md` file mirrors
it.

### Rendering

`src/pages/work.astro` reads `getCollection('projects')`, filters to `lang ===
'en'`, builds a `slug -> ru entry` map, and renders two `<section>`s —
`platform` then `product` — each sorted by `a.data.order - b.data.order`, one
`<ProjectCard en ru />` per entry. Group headings are unconditional, so an
empty group would render a bare `<h2>`.

`src/components/ProjectCard.astro`:

- line 18: `repoLabel` strips the scheme from `en.data.repo`.
- lines 19-20: `links` / `ruLinks` default to `[]`.
- line 24: `hasLinks = Boolean(en.data.repo) || links.length > 0`.
- lines 46-59: `{hasLinks && (<ul class="project-links">…)}` — the repository
  `<li>` first when `en.data.repo` is set, then one `<li>` per `links` entry,
  pairing `link.label` with `ruLinks[index]?.label ?? link.label` through
  `<Lang>`. This is exactly the shape the six new service links need: the
  service link is appended beside the repository link, not in place of it.
- lines 60-67: the metrics line, gated on `en.data.repo`.
- lines 68-72: the private chip, gated on `en.data.private`, rendering
  `ui.workPrivateRepo` (`src/i18n/ui.ts:126`:
  `{ en: 'private repo', ru: 'приватный репозиторий' }`).
- lines 26-34: every stack chip must be known to `chipIsKnown` or the build
  throws.

`src/i18n/ui.ts:203-222` holds `colophonChainItems.en` (7 items) and `.ru`
(7 items); the last item of each is the rehearsal-host note. `src/pages/
colophon/index.astro:36-44` maps both arrays through `chainSegments`
(`src/lib/chain.ts`), which linkifies only the two `CHAIN_LINKS` identifiers
`github.com/mctlhq/portfolio` and `ghcr.io/mctlhq/portfolio` — neither occurs
in the item being removed. `test/ui.test.ts:18-22` asserts every array-valued
dictionary entry is non-empty, all-string, and equal in length across
languages. `test/chain.test.ts` looks items up by `find(...)` on the two
linkified identifiers, so it does not index by position and is unaffected.

### Tests that encode the current set

`test/projects.test.ts`:

- `EXPECTED_SLUGS` (lines 11-26): the fourteen slugs, hand-typed.
- `NO_REPO_SLUGS = new Set(['pfeifenpatenschaft-backend'])` (line 28).
- line 39: `assert.equal(files.length, 28…)`; line 42: `slugs.size, 14`.
- lines 72-73: 6 platform, 8 product per language.
- line 84: `order` values are `1..14` once per language.
- lines 88-93: `pfeifenpatenschaft-backend has no repo: line…`.
- lines 95-107 and 124-140: repository-pattern and `metrics.json` per-repo-key
  assertions, both skipping `NO_REPO_SLUGS`.

`test/work.test.ts`:

- lines 461-468 (T3): reads `pfeifenpatenschaft-backend.{en,ru}.md` and asserts
  no `repo:`, no `links:`, `private: true`.
- lines 472-481 (T4): `assert.equal(names.length, 14)` and
  `new Set(names).size === 14` per language.
- lines 448-459 (T3): source-level assertions that `ProjectCard.astro` gates
  `project-links` on `hasLinks`, `project-metrics` on `en.data.repo`, and the
  private chip on `en.data.private` rather than `!repo`. These are source
  greps, not proof of rendering — which is exactly the gap the fixture closes.

### Fixture precedent

`test/journal-build.test.ts:29-61` is the repository's existing pattern for
"prove the real schema, loader and rendering, not just a pure helper":
`makeFixtureTree()` copies the committed `src/` into `mkdtemp`, replaces one
content directory with fixture files, copies `astro.config.mjs`,
`package.json` and `tsconfig.json`, symlinks `node_modules` and `public`, and
runs `node node_modules/astro/bin/astro.mjs sync|build` in that tree with
`spawnSync`. `npm run build` is never invoked from a test (its `prebuild` would
recurse). The comment there states the rule the private-chip fixture reuses:
`astro sync` for schema/loader cases, `astro build` when the case needs actual
markup.

### Adjacent gates that must keep passing

- `scripts/check-links.mjs` issues no network request at all: it walks `dist/`,
  resolves same-origin hrefs against emitted files, and reports off-origin
  hrefs as *skipped*, listed by count. Six new external service links are
  therefore skipped, never fetched — no new CI flake surface.
- `scripts/check-dist.mjs` checks `class="l en"` / `class="l ru"` parity in
  every emitted page, so a link label rendered through `<Lang>` stays balanced;
  its `work/index.html` branch only asserts zero `<summary><h2` openings.
- `scripts/check-no-metrics.mjs` scans `src/pages`, `src/components`,
  `src/layouts` only — content files are untouched by it.
- `test/a11y.test.ts` `TARGET_SELECTORS` includes `.project-links a`, which
  already carries the 24px hit-area rule; more `<li>` entries inherit it.
- `docs/journal.md` and the journal schema: at most one entry may be
  `status: in_progress`. The previous cycle's entry
  (`src/content/journal/2026-09-13-q13-link-hit-areas-titles-indexing-and-share-image-alt.md`)
  is already `status: complete` with `merged_at` and `released_at`, so nothing
  needs closing by hand and this cycle's new entry is free to be `in_progress`.

## Proposed solution

Six mechanical edits and one new test file. No change to
`src/pages/work.astro`, `src/components/ProjectCard.astro` or
`src/content.config.ts` is needed: `ProjectCard` already renders `links` beside
the repository link and already gates the private chip on `en.data.private`,
and the schema already carries `private` and `links`.

### 1. Delete eight files, renumber twenty

Delete `mctl-agent.{en,ru}.md`, `mctl-pairdesk.{en,ru}.md`,
`pfeifenpatenschaft-backend.{en,ru}.md`, `mctl-openclaw.{en,ru}.md`.

Rewrite `order` in the remaining twenty files so both language files of a slug
carry the same value (the parity check enforces it):

| slug | old order | new order | group |
|---|---|---|---|
| `mctl-api` | 1 | 1 | platform |
| `mctl-gitops` | 2 | 2 | platform |
| `mctl-agents` | 3 | 3 | platform |
| `mctl-portal` | 5 | 4 | platform |
| `mctl-design` | 6 | 5 | platform |
| `mctl-telegram` | 7 | 6 | product |
| `seerrsense` | 8 | 7 | product |
| `mctl-academy` | 9 | 8 | product |
| `mctl-loyalty` | 10 | 9 | product |
| `pelican-libertex-social` | 12 | 10 | product |

Relative order within each group is preserved and platform still precedes
product, so `work.astro`'s two sections render five and five with no gap and no
empty heading.

### 2. `seerrsense` correction

Replace the `summary` line of `src/content/projects/seerrsense.en.md` with
exactly:

```
summary: "Natural-language media requests for Seerr over MCP: the model interprets intent, provider IDs stay the source of truth."
```

and the `summary` line of `src/content/projects/seerrsense.ru.md` with exactly:

```
summary: "Запросы медиа на естественном языке для Seerr через MCP: модель интерпретирует намерение, идентификаторы провайдеров остаются источником истины."
```

Append one body bullet to each file, as the last bullet, exactly:

- `seerrsense.en.md`: `- one upstream: Seerr, which is what drives Radarr and Sonarr`
- `seerrsense.ru.md`: `- один апстрим — Seerr, и уже он управляет Radarr и Sonarr`

`summary` stays a single line (`src/content.config.ts:44` refuses a `\n`).
Nothing else in either file changes beyond the new `order: 7` and the `links`
entry from step 3.

### 3. Six `links` arrays

Add to both language files of six slugs, in the `mctl-api` shape (two-space
indented list, quoted label, bare URL, no trailing slash):

| slug | `url` | EN label | RU label |
|---|---|---|---|
| `mctl-portal` | `https://app.mctl.ai` | `Portal` | `Портал` |
| `mctl-design` | `https://ui.mctl.ai` | `Storybook` | `Storybook` |
| `mctl-telegram` | `https://tg.mctl.ai` | `Service` | `Сервис` |
| `seerrsense` | `https://seerrsense.mctl.ai` | `Service` | `Сервис` |
| `mctl-academy` | `https://academy.mctl.ai` | `Service` | `Сервис` |
| `mctl-loyalty` | `https://labs-mctl-loyalty.mctl.ai` | `Service` | `Сервис` |

`Storybook` is a product name and stays untranslated in both files.
`mctl-api` keeps its `Docs` / `Документация` entry and gains nothing;
`mctl-gitops` and `pelican-libertex-social` gain no `links` array. Each card
keeps its repository link; the service link is a second `<li>` in the same
`project-links` list, which `ProjectCard.astro:51-57` already emits.

### 4. One chain item per language

Delete exactly
`'Rehearsal host preview.dmitriimashkov.com shares the same certificate and stays until the apex has been observed',`
from `ui.colophonChainItems.en` and exactly
`'Репетиционный хост preview.dmitriimashkov.com делит тот же сертификат и остаётся, пока апекс не будет отнаблюдён',`
from `ui.colophonChainItems.ru` in `src/i18n/ui.ts`. Both arrays go from seven
items to six and stay equal in length, satisfying `test/ui.test.ts:20`. The
`www` 301 item above it stays in both languages. `src/lib/chain.ts` and
`CHAIN_LINKS` are untouched — the removed item carries neither linkified
identifier. Journal entries that mention the rehearsal host are dated records
and are not rewritten.

### 5. One expected-project table, two test files

Introduce `test/support/expected-projects.ts` — a plain module, not a test
file, so it is not added to the `npm test` file list and running it executes
nothing:

```ts
export const EXPECTED_PROJECTS = [
  { slug: 'mctl-api', group: 'platform', order: 1 },
  … one row per slug, in the order table above …
] as const;
export const EXPECTED_SLUGS = EXPECTED_PROJECTS.map((p) => p.slug);
```

`test/projects.test.ts` imports it and derives every count that is currently
hand-typed: `files.length === EXPECTED_SLUGS.length * 2` (28 -> 20),
`slugs.size === EXPECTED_SLUGS.length` (14 -> 10), the group counts from
`EXPECTED_PROJECTS.filter((p) => p.group === 'platform').length` (6 -> 5) and
`'product'` (8 -> 5), and the order range from
`EXPECTED_PROJECTS.map((p) => p.order).sort()` (1..14 -> 1..10). It also gains
a direct assertion that each file's `order` and `group` match its row, which is
what makes the table, and not a count, the single source of truth. `test/
work.test.ts`'s T4 imports the same module for its per-language name count
(14 -> 10). This is the answer to C.9: a list and a count that must agree are
no longer both hand-typed.

`NO_REPO_SLUGS` is deleted along with the two `continue` guards it feeds; the
repository-pattern and `metrics.json`-key assertions are restated as "every
project that declares a `repo:` …", reading the field and skipping a project
that declares none. Since all ten remaining projects declare a `repo:`, the
assertions keep the same coverage with no exception list. The two tests naming
`pfeifenpatenschaft-backend` (`test/projects.test.ts:88-93`,
`test/work.test.ts:461-468`) are deleted; their subject moves to the fixture.

A new assertion in `test/projects.test.ts` makes criterion 5 checkable by a
commit rather than by a human running grep: walk `src/` and `test/` and fail on
a word-bounded match of `mctl-agent`, `mctl-pairdesk`,
`pfeifenpatenschaft-backend` or `mctl-openclaw`, excluding
`src/data/metrics.json` — which the issue's own out-of-scope list says keeps
its keys — and naming that one exclusion in the test. The word boundary is what
keeps `mctl-agent` from matching inside the ten remaining `mctl-agents` files.

Also added there: an assertion that the six slugs in the link table carry
exactly the listed `url` and the listed EN/RU label, and that `mctl-gitops` and
`pelican-libertex-social` carry no `links:` line — so a later edit cannot
quietly retarget or drop a service link. And an assertion that neither
`seerrsense` file's `summary` matches `/radarr|sonarr/i`.

### 6. `test/project-card-private.test.ts` — the fixture and its mutant

A new test file, modelled on `test/journal-build.test.ts` and added to the
`npm test` file list in `package.json` (`AGENTS.md` reserves only
`claude-review.yml`, `release-please.yml` and `dependabot.yml`; `package.json`
is implementer-writable).

`makeProjectFixtureTree(cardSource?)` copies the committed `src/`, replaces
`src/content/projects/` with four fixture slugs (`en` and `ru` each, all with
a chip `chipIsKnown` already accepts, two in each group so neither heading
renders empty), optionally overwrites `src/components/ProjectCard.astro` with a
mutant, copies `astro.config.mjs`, `package.json`, `tsconfig.json`, symlinks
`node_modules` and `public`, and runs `astro build`. The card renders
`<article class="project" id={en.data.slug}>`, so each fixture's markup is
sliced out of `dist/work/index.html` by its `id` and asserted in isolation.

| fixture slug | `repo:` | `private:` | `links:` | expected markup |
|---|---|---|---|---|
| `fixture-private-no-repo` | absent | `true` | absent | private chip present; no repository `<li>`; no metrics line |
| `fixture-public-repo` | present | absent | one entry | repository `<li>` and service `<li>`, in that order; no private chip |
| `fixture-no-repo-no-private` | absent | absent | absent | no private chip, no `project-links` list at all |
| `fixture-private-with-repo` | present | `true` | absent | private chip *and* repository `<li>` |

The first two rows are criterion B.5 verbatim. The last two exist to give
criterion B.6 something real to fail on: under a card mutated to read
`!en.data.repo` instead of `en.data.private`, `fixture-no-repo-no-private`
gains a chip it must not have and `fixture-private-with-repo` loses one it
must have. `fixture-public-repo` additionally proves criterion 7's rendering
half — a repository link and a service link on the same card — generically,
without pinning a production slug.

The mutation evidence is produced by the test, not described in prose: a
`mutantCard()` helper reads the real `ProjectCard.astro`, asserts the exact
token `{en.data.private && (` occurs exactly once (failing loudly if the source
has drifted), replaces it with `{!en.data.repo && (`, builds a second fixture
tree with that card, and asserts the mutant output violates the two
discriminating expectations. The evidence is therefore committed, re-derived on
every run, and lives in the test file — never in the pull request description,
as `AGENTS.md` requires.

### 7. Journal entry

Add `src/content/journal/2026-09-13-q14-ten-projects-and-service-links.md`
with `service: portfolio`, `issue: https://github.com/mctlhq/portfolio/issues/89`,
`proposal_slug: issue-89-q14-ten-projects-on-work-service-links-t`,
`status: in_progress`, `visibility: public`, `indexing: noindex`, bilingual
`title` and `decided`, a quoted `issue_opened_at`, and `interventions: []`.
A `seoTitle` is supplied so the rendered title stays inside the length budget
`src/lib/seo.ts` enforces via `test/title.test.ts`. The previous entry is
already `status: complete`, so the one-in_progress-at-a-time rule in
`checkJournalCollection` holds with no other edit.

## Alternatives

1. **Keep `pfeifenpatenschaft-backend` as a hidden or draft entry so the
   private-repo tests keep their subject.** Rejected: the owner's decision is
   that the entry does not belong on the site, and a hidden content file that
   exists only to satisfy a test is the same defect issue #83 named — a test
   keyed to one named entry. The fixture gives the capability a subject that no
   editorial decision can remove.

2. **Prove the private chip with source-level greps only (extend the existing
   T3 assertions in `test/work.test.ts:455-459`).** Rejected: those greps
   already exist and would pass unchanged against a card that never renders.
   They cannot distinguish `en.data.private` from `!en.data.repo` in emitted
   markup, which is precisely criterion B.6. `test/journal-build.test.ts`
   already established the isolated-build pattern for exactly this reason.

3. **Render `ProjectCard` through Astro's container API in-process instead of
   spawning a build.** Rejected: it would be a second, unprecedented rendering
   path in a repository that has one (`makeFixtureTree` + spawned `astro`), and
   the component's `render(entry)` call and `astro:content` imports need a real
   content store anyway. Consistency with the existing precedent is worth more
   than the seconds saved.

4. **Renumber by leaving gaps (1, 2, 3, 5, 6, …) to minimise the diff.**
   Rejected: criterion 2 requires `order` to run 1..10 once per language, and
   the order table in the issue is explicit. Contiguity is also what makes the
   "no gap in the list" criterion checkable.

5. **Give `mctl-loyalty` no service link because it has no branded host.**
   Rejected by the issue: `labs-mctl-loyalty.mctl.ai` is public and serves the
   product, so it is linked as it is rather than not at all.

## Platform impact

- **Migrations / data.** None. Content collections are files; no database, no
  schema change. `src/data/metrics.json` keeps its keys for the removed
  repositories by explicit decision, and `repoMetrics`
  (`src/lib/metrics.ts:97-107`) returns `EMPTY_REPO_METRIC` for a key it cannot
  resolve, so an unused key harms nothing.
- **Backward compatibility / URLs.** `/work/` is a single page with no
  per-project routes (`src/pages/work.astro` is the only consumer), so removing
  four projects breaks no URL. The in-page anchors `#mctl-agent`,
  `#mctl-pairdesk`, `#pfeifenpatenschaft-backend` and `#mctl-openclaw`
  disappear; no page in the repository links to them (`scripts/check-links.mjs`
  resolves internal links against emitted files and would report a broken one).
- **Page weight.** `/work/` loses four cards and gains six `<li>` links: a net
  reduction. `dist/index.html` is unaffected by this change and stays under the
  40 KB cap `scripts/check-dist.mjs` enforces.
- **External links.** The six service addresses are off-origin, so
  `scripts/check-links.mjs` counts them as skipped and never opens a socket —
  no CI flake, and no new third-party browser request at page load (the links
  are `<a href>`, not subresources, so ADR-0005 and the CSP are unaffected).
  Risk: an address could go dark later and the site would link to a dead page.
  Mitigation: the link table is asserted in `test/projects.test.ts`, so any
  change to it is a deliberate, reviewed edit; liveness itself is a release
  owner concern, as with `https://docs.mctl.ai` today.
- **Test runtime.** The new fixture file spawns two `astro build` runs (one
  honest, one mutant), the same cost profile `test/journal-build.test.ts`
  already pays. Mitigation if this proves slow: the honest case can drop to one
  build by asserting all four fixtures from a single `dist/work/index.html`,
  which is how it is specified above — two builds total, not one per fixture.
- **Risk: a fixture tree that fails to build for an unrelated reason** (a chip
  with no Russian translation, a `metrics.json` key miss) would read as a
  private-capability regression. Mitigation: fixtures use only chips
  `chipIsKnown` already accepts, and the test asserts the build exited zero
  with its stderr in the failure message, as `journal-build.test.ts` does.
- **Risk: the mutant helper silently stops mutating** if `ProjectCard.astro`'s
  text drifts. Mitigation: the helper asserts the token occurs exactly once
  before replacing, so drift fails the suite instead of quietly passing it.
- **Deployment.** Ordinary release-please cycle; the deploy is dispatched to
  `release-deploy` in mctl-gitops as usual. No DNS, certificate or
  custom-domain action is part of this change; decommissioning
  `preview.dmitriimashkov.com` remains the release owner's separate action
  through the mctl and Cloudflare MCP tools.
