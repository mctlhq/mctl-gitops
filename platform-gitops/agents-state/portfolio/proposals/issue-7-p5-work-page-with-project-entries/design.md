# Design: issue-7-p5-work-page-with-project-entries

## Current state

**Routes.** `src/pages/` holds `index.astro`, `404.astro` and
`dev/[check].astro`. The dev route's `getStaticPaths` returns `[]` outside
`astro dev`, so a production build emits only `dist/index.html` and
`dist/404.html`. There is no `/work/` route, yet `src/pages/index.astro:31`
already renders `<a class="cta" href="/work/">` and `test/home.test.ts` asserts
that href exists. `src/components/Nav.astro:13` still links `/#work`, a
fragment no element carries since P4 removed the placeholder sections
(`test/home.test.ts` asserts `id="work"` is gone).

**Content collection.** `src/content.config.ts` already defines a `projects`
collection with a `strictObject` schema: `slug`, `lang` (`en` | `ru`), `name`,
`group` (`platform` | `product`), `order`, `repo` (a **required**
`https://github.com/...` string), `stack` (non-empty string array), `summary`
(one line), and optional `links[] = { label, url }`. `projectsLoader()` wraps
the glob loader for `*.{en,ru}.md` under `src/content/projects` and runs
`checkProjectParity`, which requires exactly one `en` and one `ru` file per
slug and requires the two to agree on `group`, `order`, `repo`, `stack` (by
`JSON.stringify`) and the ordered list of `links[].url`. `name`, `summary`,
`links[].label` and the body are allowed to differ per language. Only
`mctl-api.en.md` / `mctl-api.ru.md` exist today, and their `stack` and
`summary` differ from the copy this issue specifies.

**Bilingual mechanism.** `src/i18n/Lang.astro` emits
`<span class="l en">…</span><span class="l ru" lang="ru">…</span>`;
`src/styles/site.css` hides one side per `:root[data-lang]`. The 400-byte
inline script in `src/layouts/Base.astro` only flips `data-lang` /
`data-theme`, so English renders with JavaScript disabled.
`scripts/check-dist.mjs` walks `dist/` post-build and fails if any file ends in
`.js`, if any HTML file's `class="l en"` count differs from its `class="l ru"`
count, or if `dist/index.html` reaches 40 KB. It is invoked from the
`Dockerfile` build stage, not from `npm test`.

**Strings.** `src/i18n/ui.ts` exports one flat `ui` object of `{ en, ru }`
pairs (values are strings or equal-length string arrays).
`test/ui.test.ts` iterates `Object.entries(ui)` and requires every value to
have `en` and `ru` of the same kind — so a nested lookup map cannot live inside
`ui`.

**Existing card-shaped components.** `src/components/Details.astro` wraps a
native `<details class="block">` with a `<summary>` carrying a `<Lang>` pair and
a `<slot />`. `src/components/Stat.astro` renders `formatStat(value)` from
`src/lib/metrics.ts`, where `formatStat(null)` returns the `EM_DASH` constant.
`src/styles/site.css` already styles `.block > summary` with
`min-block-size: 44px; display: list-item`, a global `:focus-visible` outline,
and a print rule that force-opens collapsed `.block` bodies while keeping the
language pair correct.

**Nobody renders a markdown body yet.** No page calls `render()` on a
collection entry; ADRs and journal entries are validated but not yet displayed.
`public/assets/mctl/prose.css` is already linked from `Base.astro`, so rendered
markdown inherits prose styling without new CSS.

**Typography.** `site.css` uses `var(--font-editorial)` only on `.hero-name`;
everything translated uses `var(--font-display)` (Onest). AGENTS.md records why:
Instrument Serif ships no Cyrillic subset.

## Proposed solution

### 1. Make `repo` optional in the schema

In `src/content.config.ts`, change `repo: githubUrl` to
`repo: githubUrl.optional()`. `checkProjectParity` compares
`en[0].data.repo === ru[0].data.repo`, which already behaves correctly when
both sides are `undefined`, so no change is needed there. This is the one
schema change; it exists solely so `pfeifenpatenschaft-backend` — private, 404
to anonymous visitors — can be listed without a link. The `type ProjectData`
alias is inferred from the schema, so it follows automatically.

### 2. `src/components/ProjectCard.astro`

A single component that takes the **pair** of entries for one project, because
every card interleaves English and Russian:

```astro
---
import type { CollectionEntry } from 'astro:content';
import { render } from 'astro:content';
import Lang from '../i18n/Lang.astro';
import { ui, stackChipRu } from '../i18n/ui';
import { formatStat } from '../lib/metrics';

interface Props {
  en: CollectionEntry<'projects'>;
  ru: CollectionEntry<'projects'>;
}

const { en, ru } = Astro.props;
const { Content: BodyEn } = await render(en);
const { Content: BodyRu } = await render(ru);
const repoLabel = en.data.repo?.replace(/^https:\/\//, '').replace(/\/$/, '');
---
```

Markup, in order:

1. `<article class="project">` with an `id={en.data.slug}` so a card can be
   linked directly later.
2. `<h3 class="project-name">{en.data.name}</h3>` — the project name is an
   identifier, identical in both languages, so it is not a `<Lang>` pair and it
   is **not** set in `--font-editorial`.
3. `<p class="project-summary"><Lang en={en.data.summary} ru={ru.data.summary} /></p>`.
4. `<ul class="chips">` built by `en.data.stack.map((chip) => …)`, each item
   `<li class="chip"><Lang en={chip} ru={stackChipRu[chip] ?? chip} /></li>`.
   The chip text comes from frontmatter; the template contains no chip literal,
   which is acceptance criterion 4. `stack` is guaranteed identical in both
   files by `checkProjectParity`, so iterating the English entry is safe, and
   the Russian side is the dictionary lookup with identity fallback.
5. `<details class="block project-details">` whose `<summary>` carries the
   `<Lang>` pair `ui.workDetailsSummary` (`Details` / `Подробнее`) — interface
   chrome, the one label a `<summary>` cannot do without — and whose body
   holds:
   - `<div class="l en"><BodyEn /></div>` and
     `<div class="l ru" lang="ru"><BodyRu /></div>` — the rendered detail
     bullets, one `.l.en` / `.l.ru` pair;
   - a `<ul class="project-links">` containing, when `en.data.repo` is defined,
     `<li><a href={en.data.repo}>{repoLabel}</a></li>`, then one `<li>` per
     index of `en.data.links ?? []` rendering a single `<a href={link.url}>`
     with `<Lang en={enLabel} ru={ruLabel} />`. URLs are identical across the
     pair by the parity check, so one anchor with a bilingual label is correct
     and keeps the `.l.en` / `.l.ru` counts balanced;
   - `<p class="project-metrics"><Lang en={ui.workMetricsLabel.en} ru={ui.workMetricsLabel.ru} /> <span data-stat><slot name="metrics">{formatStat(null)}</slot></span></p>`.
     P8b fills the named slot from `per_repo`; until then the fallback renders
     the em dash from `src/lib/metrics.ts`, so the placeholder is produced by
     the metrics module rather than typed.

Because `<details>` / `<summary>` are native, acceptance criterion 5 (focus,
Enter, Space) is satisfied by the platform: no `tabindex`, no `role`, no
script. `.block > summary` in `site.css` already gives a 44px target and
`display: list-item`, both of which keep the element focusable, and the global
`:focus-visible` rule supplies the ring.

### 3. `src/pages/work.astro`

```astro
const all = await getCollection('projects');
const en = all.filter((e) => e.data.lang === 'en');
const ru = new Map(all.filter((e) => e.data.lang === 'ru').map((e) => [e.data.slug, e]));
const inGroup = (group: 'platform' | 'product') =>
  en.filter((e) => e.data.group === group).sort((a, b) => a.data.order - b.data.order);
```

The page renders two `<section>` elements — Platform then Products — each with
an `<h2>` carrying `ui.workGroupPlatform` / `ui.workGroupProducts` as a `<Lang>`
pair, and each mapping its group's ordered entries to
`<ProjectCard en={entry} ru={ru.get(entry.data.slug)!} />`. Sorting on
`data.order` rather than on the loader's return order makes criterion 1's
ordering a property of the content, not of file-system iteration. Global
ordering 1..14 is kept (so `mctl-api`'s existing `order: 1` is untouched) and
the group filter makes the two sequences 1..6 and 7..14.

The page uses `<Base title={ui.workPageTitle.en}>` and an `<h1>` with the
existing `ui.navWork` pair.

### 4. `src/i18n/ui.ts`

Add to the `ui` object: `workGroupPlatform`, `workGroupProducts`,
`workDetailsSummary`, `workMetricsLabel`, `workPageTitle` — all `{ en, ru }`
string pairs, so `test/ui.test.ts` continues to pass unchanged. Add
`stackChipRu` as a **separate named export** outside `ui`, because
`test/ui.test.ts` asserts every `ui` value is an `{ en, ru }` pair and a
`Record<string, string>` would fail that assertion. `stackChipRu` carries the
only two plain-word chips in the fourteen stacks: `design tokens` and
`upstream fork`.

### 5. Content files

Twenty-eight files `src/content/projects/<slug>.{en,ru}.md`, with the exact
frontmatter and bodies transcribed in `requirements.md`. The two existing
`mctl-api` files are rewritten to this issue's `stack`, `summary` and body; the
`links` entry for `https://docs.mctl.ai` stays. `pfeifenpatenschaft-backend`
omits `repo`; `pelican-libertex-social` uses the `mashkoffdmitry` URL. Each
body is a markdown bullet list, one `- ` line per detail clause, which
`render()` turns into a `<ul>` styled by the already-linked `prose.css`.

### 6. `src/styles/site.css`

Add a `/* Work page. */` block: `.project` spacing and separator borders,
`.project-name` in `var(--font-display)` (or `var(--font-mono)`, since it is an
identifier) — never `var(--font-editorial)`; `.project-summary` in
`var(--font-display)`; `.chips` as a `display: flex; flex-wrap: wrap` list with
`list-style: none`; `.chip` as a small bordered pill using existing
`--mctl-space-*` / `--mctl-radius-*` / `--surface-*` tokens; `.project-links`
and `.project-metrics` muted. `.project-details` reuses the existing `.block`
class so the 44px summary target, the list marker and the print rules apply
unchanged. Note that the print override
`:root[data-lang='en'] .block > .l.ru` matches only **direct** children of
`.block`; the card's two body wrappers are direct children of the `<details>`,
so the existing rule keeps working — the implementer must not nest them inside
an extra wrapper `div`.

Because `site.css` is copied to `public/styles/site.css` by
`npm run vendor` (which `prebuild` runs), no extra wiring is needed; the
implementer must run `npm run vendor` (or `npm run build`) so the public copy
is regenerated and committed.

### 7. `src/components/Nav.astro`

Change `href="/#work"` to `href="/work/"`. `/#approach` stays until P6.

### 8. Link checking (criterion 3)

The check is a throwaway script pasted into the pull request description
together with its output, not a committed test: `npm test` runs in CI with
`permissions: contents: read` and must not depend on reachability of
github.com. The script extracts every `href` from `dist/work/index.html`,
resolves site-relative ones against the deployed origin, and requests each one,
printing `url -> status`. A repository-resident, offline test
(`test/projects.test.ts`) covers the parts that can be checked without the
network: that 28 content files exist, that exactly 14 slugs appear, that
`pfeifenpatenschaft-backend` has no `repo:` line, and that every other `repo:`
value matches `https://github.com/(mctlhq|mashkoffdmitry)/<slug>`.

## Alternatives

**A. One `ProjectCard` per language, rendered twice inside `.l.en` / `.l.ru`
wrappers.** Simpler component props (one entry), but it duplicates the chips,
the links and the metrics placeholder in the HTML, doubling the shared markup
of fourteen cards for no benefit, and it makes the language classes wrap
structure rather than text — which is exactly what the print override in
`site.css` had to be patched for on the home page. Dropped.

**B. Put the detail bullets in `src/i18n/ui.ts` as arrays, like
`detailsRunItems`, and keep the markdown bodies empty.** It would reuse the
existing pattern and need no `render()` call. Dropped: the issue names
`src/content/projects/*.md` as the place the project copy lives, the collection
already exists for exactly this, and `ui.ts` is for interface chrome — putting
fourteen projects' prose there would make the file the de-facto content store
and leave the collection an empty formality.

**C. Translate chips by giving `.ru.md` a different `stack` array.** The most
obvious way to get Russian chips. Dropped: `checkProjectParity` in
`src/content.config.ts` compares `stack` across the pair by `JSON.stringify`
and would fail the build, and weakening that check to allow per-language stacks
would remove the guarantee that both cards describe the same project. A
dictionary in `src/i18n/ui.ts` keyed by the frontmatter chip keeps frontmatter
as the single source of the chip set and keeps the template free of chip
literals.

**D. Give `pfeifenpatenschaft-backend` its GitHub URL anyway and let the link
404.** Dropped outright: it breaks acceptance criterion 3 by construction, and
a portfolio that links to a page the reader cannot open is worse than one that
does not link at all.

## Platform impact

- **Migrations.** None. No database, no API, no gitops values. The only schema
  change is `repo` becoming optional in the Astro content schema, which is a
  widening: every existing entry still validates.
- **Backward compatibility.** `dist/index.html` is unchanged except that
  `Nav.astro`'s first link now points at `/work/`; the CTA on the home page
  already pointed there. The 40 KB cap in `scripts/check-dist.mjs` applies only
  to `dist/index.html`, so the new page is not size-gated; the `.l en` / `.l ru`
  parity and the no-`.js` rule apply to it automatically because the script
  walks all of `dist/`.
- **Resource impact.** One extra static HTML page (estimated 25-40 KB before
  gzip for fourteen cards) plus a few hundred bytes of CSS. No new
  dependency, no new network request, no change to the CSP or to
  `scripts/csp-hash.mjs` — the page ships no script of its own.
- **Risk: `render()` API shape.** No page in this repo has rendered a
  collection body before. On the content layer the call is
  `const { Content } = await render(entry)` imported from `astro:content`.
  Mitigation: `npm run check` (`astro sync && astro check`) fails loudly if the
  import or the call shape is wrong; the implementer runs it before pushing.
- **Risk: bilingual parity drift.** Fourteen cards multiply the chance of an
  unmatched `.l.en` / `.l.ru`. Mitigation: `scripts/check-dist.mjs` already
  fails the Docker build on an imbalance in any HTML file; the implementer runs
  `npm run build && node scripts/check-dist.mjs` locally.
- **Risk: copy corruption.** The Russian strings contain `ё`, em dashes and
  typographic apostrophes (`runbook'и`, `backend'ом`). A shell-quoting or
  editor-normalisation slip would silently alter published copy. Mitigation:
  the implementer writes files directly (no `sed`/`echo` pipelines) and diffs
  each summary against `requirements.md` before committing.
- **Risk: numbers in prose.** AGENTS.md forbids typing metric values into
  templates and content. The issue's copy contains `60 seconds`, `0.5.0`,
  `15-minute`, `SOC 2`, `OAuth 2.0`, `Vue 3`. These are descriptive constants
  and version identifiers, not site metrics, and `0.5.0` matches the
  `MCTL_VERSION` constant pinned in `scripts/vendor-assets.mjs`. The "no digit"
  assertion in `test/home.test.ts` is scoped to `src/pages/index.astro` and must
  **not** be extended to `work.astro`.
- **Risk: private repository exposure.** `pfeifenpatenschaft-backend` is
  listed by name, summary and stack only. No URL, no hostname, nothing that
  identifies a client. Consistent with the AGENTS.md rule about third parties in
  public content.
- **Rollback.** Deleting the new page, component, content files and CSS block
  returns the site to its current state; see `tasks.md`.
