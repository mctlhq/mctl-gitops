# Design: issue-7-p5-work-page-with-project-entries

## Current state

### Routes

`src/pages/` holds three routes: `index.astro` (the home page built in #6),
`404.astro`, and `dev/[check].astro`, whose `getStaticPaths` returns `[]` unless
`import.meta.env.DEV`, so it never reaches `dist/`. There is no `work.astro`.
`astro.config.mjs` sets `output: 'static'`, `trailingSlash: 'always'`,
`site: 'https://dmitriimashkov.com'` and `build.inlineStylesheets: 'never'` —
the last because the CSP in `nginx.conf` carries `style-src 'self'` with no
`unsafe-inline`, so a stylesheet must become a linked file rather than a
`<style>` element.

`src/pages/index.astro` already links `/work/` (`<a class="cta" href="/work/">`),
and `test/home.test.ts` asserts that link exists. `src/components/Nav.astro`
still links `/#work` and `/#approach`; #6 deleted both anchors from the home
page, and `test/home.test.ts` asserts `id="work"` is gone.

### The projects collection

`src/content.config.ts` already defines the collection this proposal renders:

- `projectsSchema` is a `z.strictObject` with `slug` (`^[a-z0-9-]+$`), `lang`
  (`'en' | 'ru'`), `name`, `group` (`'platform' | 'product'`), `order`
  (non-negative int), `repo` (a `https://github.com/...` regex), `stack`
  (non-empty string array), `summary` (non-empty, refined to be one line) and
  optional `links` (`{ label, url }`, `url` an https regex).
- `projectsLoader()` wraps the `glob` loader over `*.{en,ru}.md` in
  `src/content/projects`, with `generateId` stripping `.md`, then runs
  `checkProjectParity` over the whole store. That check requires exactly one
  `en` and one `ru` file per slug and byte-identical `group`, `order`, `repo`,
  `stack` (compared with `JSON.stringify`) and `links[].url`; `name`, `summary`,
  `links[].label` and the body are allowed to differ per language. It runs on
  `astro sync`, `astro check`, `astro dev` and `astro build` alike.

Only `mctl-api` exists today, as `mctl-api.en.md` / `mctl-api.ru.md`, with
`order: 1`, `group: platform`, a `Docs` link to `https://docs.mctl.ai`, a stack
of `["Go","chi","PostgreSQL","Temporal","Argo Workflows","Vault"]` and a
one-paragraph body. Nothing renders the bodies yet, so the repository has no
precedent for markdown rendering.

### Bilingualism and components

`src/i18n/Lang.astro` is the whole mechanism: it emits
`<span class="l en">{en}</span><span class="l ru" lang="ru">{ru}</span>`.
`src/styles/site.css` hides the other language with
`:root[data-lang='en'] .l.ru { display: none }` and its mirror;
`src/layouts/Base.astro` authors `data-lang="en" data-theme="dark"` on `<html>`
and carries the single ~400-byte inline script that restores and sets those
attributes. `src/i18n/ui.ts` is a flat `as const` dictionary of
`{ en, ru }` string (or string-array) entries with `export type UiKey`;
`test/ui.test.ts` iterates `Object.entries(ui)` and asserts each value has a
non-empty `en` and `ru` of the same kind, with equal array lengths.

`src/components/Details.astro` is the existing collapsible: `<details
class="block">` with `<summary><Lang .../></summary>` and a `<slot />`.
`src/styles/site.css` styles `.block > summary` with `cursor: pointer`,
`min-block-size: 44px` and `display: list-item`, and has a `@media print` block
that force-expands `.block > *:not(summary)` while still hiding the non-active
language for direct `.l.en` / `.l.ru` children. `src/components/Stat.astro`
renders `formatStat(value)` inside `<span class="stat-value" data-stat>`.

### Metrics discipline

`src/lib/metrics.ts` is deliberately import-free so `node --test` can load it
without a build step. It exports `EM_DASH`, `formatStat(value)` (branching on
`value === null`, never on falsiness, so a real `0` renders), `snapshotDate`,
the `Metrics` interfaces and `metricProblems` for shape validation.
`src/data/metrics.json` currently has `generated_at: null` and all-null values
under `sources.github` and `sources.mctl`; it has no `per_repo` key. `AGENTS.md`
requires every number on the site to come from this file.

### Gates

`package.json` runs `prebuild` = `npm run vendor && npm test`, where `test` names
its five files explicitly (`test/journal.test.ts`, `adr`, `metrics`, `home`,
`ui`) — a new test file is invisible until it is added to that list.
`.github/workflows/build.yml` runs `npm ci` then `npm test`, then builds the
Docker image without pushing. The `Dockerfile` runs
`npm run build && node scripts/check-dist.mjs && node scripts/csp-hash.mjs`.
`scripts/check-dist.mjs` walks `dist/`, fails on any `.js` file, fails on any
HTML whose `class="l en"` and `class="l ru"` counts differ, and caps
`dist/index.html` at 40 KB (that cap is keyed to `index.html` by path, so it does
not apply to other documents). `scripts/vendor-assets.mjs` copies
`src/styles/site.css` to `public/styles/site.css`, which is what `Base.astro`
links — editing only `src/styles/site.css` and not re-running `npm run vendor`
ships nothing.

## Proposed solution

Five pieces: a grouping helper, a card component, the page, the i18n additions,
and the content files, plus two mechanical checks.

### 1. `src/lib/projects.ts` — grouping, import-free

A zero-import module in the style of `src/lib/metrics.ts` and `src/lib/adr.ts`,
so `node --test` can exercise it directly with no Astro in the loop.

```ts
export const GROUP_ORDER = ['platform', 'product'] as const;
export interface ProjectFacts {     // the subset of frontmatter this module needs
  slug: string; lang: 'en' | 'ru'; group: 'platform' | 'product'; order: number;
}
export interface ProjectPair<T> { slug: string; en: T; ru: T }
export function pairByLang<T extends ProjectFacts>(entries: readonly T[]): ProjectPair<T>[]
export function groupProjects<T extends ProjectFacts>(
  entries: readonly T[],
): { group: 'platform' | 'product'; projects: ProjectPair<T>[] }[]
```

`pairByLang` buckets by `slug` and returns one pair per slug, throwing with a
named slug if a language is missing — the same failure `checkProjectParity`
raises at load time, repeated here so the page cannot render a half-pair if the
collection is ever loaded by another path. `groupProjects` returns the two groups
in `GROUP_ORDER` with each group's pairs sorted by ascending `order`, ties broken
by `slug` for determinism. Generic over `T` so the test can pass plain objects
and the page can pass `CollectionEntry<'projects'>`, with no `astro:content`
import in the module.

### 2. `src/components/ProjectCard.astro`

Props: `{ en: CollectionEntry<'projects'>, ru: CollectionEntry<'projects'> }`.
Everything rendered comes from those two entries plus `src/i18n/ui.ts`; no
project string is a literal in the component.

```astro
---
import { render } from 'astro:content';
import Lang from '../i18n/Lang.astro';
import { ui, chipWords } from '../i18n/ui';
import { formatStat } from '../lib/metrics';
const { en, ru } = Astro.props;
const { Content: BodyEn } = await render(en);
const { Content: BodyRu } = await render(ru);
const chip = (s: string) => chipWords[s] ?? { en: s, ru: s };
---
<details class="project-card">
  <summary>
    <span class="project-name font-mono">{en.data.name}</span>
    <span class="project-summary"><Lang en={en.data.summary} ru={ru.data.summary} /></span>
    <ul class="chips" aria-label={`${ui.projectStackLabel.en} / ${ui.projectStackLabel.ru}`}>
      {en.data.stack.map((s) => <li class="chip font-mono"><Lang en={chip(s).en} ru={chip(s).ru} /></li>)}
    </ul>
  </summary>
  <div class="project-body">
    <div class="l en"><BodyEn /></div>
    <div class="l ru" lang="ru"><BodyRu /></div>
    <ul class="project-links"> ... repo link, then en.data.links zipped with ru.data.links ... </ul>
    <p class="project-metrics">
      <slot name="metrics"><span data-stat>{formatStat(null)}</span></slot>
      <span class="project-metrics-note"><Lang en={ui.projectMetricsPending.en} ru={ui.projectMetricsPending.ru} /></span>
    </p>
  </div>
</details>
```

Five points this shape is chosen for:

- **`render()`, not `entry.render()`.** Astro is pinned at 7.3.2
  (`package-lock.json`); under the content layer the renderer is the standalone
  `render(entry)` from `astro:content`. Markdown is compiled at build time and
  adds no client JavaScript, so ADR-0002 holds.
- **Bodies wrapped, not interleaved.** Each language's compiled body goes inside
  one `.l.en` / `.l.ru` wrapper, so a body of any markdown shape still toggles as
  one unit and still contributes exactly one `class="l en"` and one
  `class="l ru"` to `check-dist`'s count. The four projects with no issue copy
  produce two empty wrappers, which keeps the counts balanced.
- **No link inside `<summary>`.** An `<a>` or `<button>` inside a `<summary>`
  swallows Space and breaks the native toggle; every link lives in
  `.project-body`. No `tabindex` is authored anywhere, so `<summary>` keeps its
  native focusability and its native Enter/Space behaviour — acceptance criterion
  5 is met by using the element rather than by scripting it.
- **Chips come from `stack`.** `checkProjectParity` compares `stack` with
  `JSON.stringify`, so the array must be identical in both files; the English
  chip string is therefore the canonical key, and the Russian surface form is
  looked up in `chipWords` with a pass-through default. That keeps `Go`,
  `PostgreSQL`, `Temporal` untranslated by construction and lets
  `design tokens` / `upstream fork` carry a Russian form. The template iterates
  the array; it hard-codes no chip text, satisfying criterion 4.
- **Metrics behind a named slot.** `<slot name="metrics">` with the
  `formatStat(null)` em dash as fallback means P8b fills the slot from
  `work.astro` without touching this component's props, and nothing in this
  change reads or extends `src/data/metrics.json`. `formatStat(null)` rather
  than a typed `—` keeps the em dash single-sourced from `src/lib/metrics.ts`.

### 3. `src/pages/work.astro`

```astro
---
import Base from '../layouts/Base.astro';
import Lang from '../i18n/Lang.astro';
import ProjectCard from '../components/ProjectCard.astro';
import { getCollection } from 'astro:content';
import { groupProjects } from '../lib/projects';
import { ui } from '../i18n/ui';
const groups = groupProjects(await getCollection('projects'));
const heading = { platform: ui.workGroupPlatform, product: ui.workGroupProducts };
---
<Base title={ui.workTitle.en}>
  <main>
    <h1 class="page-title"><Lang en={ui.workHeading.en} ru={ui.workHeading.ru} /></h1>
    {groups.map(({ group, projects }) => (
      <section class="project-group">
        <h2><Lang en={heading[group].en} ru={heading[group].ru} /></h2>
        {projects.map(({ en, ru }) => <ProjectCard en={en} ru={ru} />)}
      </section>
    ))}
  </main>
</Base>
```

`Base.astro` takes a single `title` string and `AGENTS.md` keeps `<title>`
Latin, so `ui.workTitle.en` is passed, exactly as `index.astro` passes
`ui.homeTitle.en`. The visible `<h1>` is a separate bilingual `ui.workHeading`
pair, because the heading is translated copy while the tab label is a filing
label.

### 4. `src/i18n/ui.ts`

Added to the existing flat `ui` object, so `test/ui.test.ts` keeps passing
unchanged: `workTitle` (Latin both sides, like `homeTitle`), `workHeading`
(`Work` / `Работы`), `workGroupPlatform` (`Platform` / `Платформа`),
`workGroupProducts` (`Products` / `Продукты`), `projectStackLabel`
(`Stack` / `Стек`, used only as an `aria-label`), `projectRepoLabel`
(`Repository` / `Репозиторий`) and `projectMetricsPending`
(`metrics pending` / `метрики будут позже`, wording subject to the issue's copy
discipline — it is new UI chrome, not project prose).

The chip dictionary is a **second export**, not a nested key inside `ui`:

```ts
export const chipWords: Record<string, { en: string; ru: string }> = {
  'design tokens': { en: 'design tokens', ru: 'дизайн-токены' },
  'upstream fork': { en: 'upstream fork', ru: 'форк upstream' },
};
```

A nested map inside `ui` would break `test/ui.test.ts`, which asserts every
top-level `ui` value has `en` and `ru`. A sibling export keeps that invariant and
gets its own loop in the extended test.

### 5. Content: twenty-seven new files, two edited

`src/content/projects/<slug>.en.md` and `<slug>.ru.md` for the thirteen new
slugs, plus edits to the existing `mctl-api` pair. Frontmatter follows the
existing files exactly; `order` is the issue's global number (platform 1-6,
product 7-14), so within-group ordering is contiguous and `mctl-api` keeps
`order: 1`. `repo` is `https://github.com/mctlhq/<slug>` except
`pelican-libertex-social`, which uses the `mashkoffdmitry` owner. `mctl-api`'s
`summary` and `stack` are replaced with the issue's wording and its `Docs` link
is kept; its body is replaced with the issue's three detail bullets.

Bodies are a plain markdown bullet list per language — no `.l.en` spans inside
the markdown, because `ProjectCard` already wraps each compiled body in its
language element. (This differs from the ADR bodies, which carry their own spans
because `src/lib/adr.ts` parses and validates them section by section; projects
need no such structure.) The four projects with no issue-supplied bullets get an
empty body.

### 6. Styling

A `/* Work page. */` block appended to `src/styles/site.css`, with
`npm run vendor` re-run so `public/styles/site.css` is regenerated and committed:
`.project-group`, `.project-card` (reusing the `.block` border/padding idiom),
`.project-card > summary` (`cursor: pointer`, `min-block-size: 44px`,
`display: list-item` so the disclosure marker survives), `.chips` as a
`display: flex; flex-wrap: wrap` unstyled list, `.chip` as a bordered inline
token, `.project-links`, `.project-metrics`. Fonts: `var(--font-display)` (Onest)
for the heading, group headings, summaries and bodies; `var(--font-mono)`
(JetBrains Mono) for names and chips. `var(--font-editorial)` appears nowhere in
the new block — that is the mechanical form of the #4 typography constraint, and
it is asserted by a test rather than left to review. The `@media print` rule
already force-expands `.block > *:not(summary)`; the new `.project-card` selector
is added to that rule's selector list so printing carries expanded cards too.

### 7. Mechanical verification

- `scripts/check-dist.mjs` gains one assertion: `dist/work/index.html` exists and
  contains exactly fourteen occurrences of `<details class="project-card"`. It
  already covers criterion 6's no-`.js` half and the `.l.en` / `.l.ru` parity
  half for every document including the new one. Placed here rather than in
  `npm test` because it needs a built `dist/`, which `prebuild` predates — the
  comment block at the top of that script says exactly this.
- `scripts/check-links.mjs` (new) extracts every `href` from `dist/**/*.html`,
  de-duplicates, resolves site-relative hrefs against `dist/` on disk and
  absolute `https://` hrefs with a `HEAD` (falling back to `GET`) request, and
  prints one `status url` line per link plus a non-zero exit if any is not 200.
  Exposed as `npm run check:links` and **not** wired into `prebuild`, `build.yml`
  or the `Dockerfile`: `scripts/vendor-assets.mjs` exists in its current shape
  precisely because the build must survive with no network, and a link checker in
  the build path would make every image build depend on github.com being up. Its
  output is pasted into the pull-request description, which is what criterion 3
  asks for.
- `test/projects.test.ts` covers `src/lib/projects.ts` directly (group order,
  within-group `order` sort, pairing, the missing-language throw).
- `test/work.test.ts` reads `src/pages/work.astro`, `ProjectCard.astro`, the new
  `src/styles/site.css` block and the content directory as text, in the style of
  `test/home.test.ts`: fourteen slugs present as en/ru pairs, counts of 6 and 8
  per group, no `<a ` inside the `<summary>` region of `ProjectCard.astro`, no
  `tabindex`, no `font-editorial` in either component or in the work-page CSS
  block, no digit in the rendered template outside heading tag names (the same
  proxy `test/home.test.ts` uses for "no number is typed in"), and every `repo`
  value matching the expected owner/slug.
- Both files are added to the explicit list in `package.json`'s `test` script,
  otherwise `npm test` and `build.yml` never run them.

### 8. Journal

`src/content/journal/2026-09-11-work-page.md` per `AGENTS.md`, `service:
portfolio`, `issue` the #7 URL, `proposal_slug`
`issue-7-p5-work-page-with-project-entries`, `visibility: public`, bilingual
`title` and `decided`, the timestamps known at merge time, and `interventions`
for anything a human had to touch (for example making a repository public).

## Alternatives

**One file per project instead of an `.en.md` / `.ru.md` pair.** A single file
with `summary: { en, ru }` and two body sections would halve the file count. It
was dropped because `projectsSchema`, `checkProjectParity` and the existing
`mctl-api` pair already encode the two-file convention, the loader glob is
`*.{en,ru}.md`, and changing it would be a schema migration plus a rewrite of an
already-reviewed validation path — large blast radius for a cosmetic win, and it
would make this proposal's diff mostly infrastructure instead of content.

**Per-language `stack` arrays in frontmatter.** Would let `.ru.md` carry
`дизайн-токены` directly and drop `chipWords`. Dropped because
`checkProjectParity` compares `stack` with `JSON.stringify` and would have to be
relaxed to "same length" — weakening a real invariant (that the two files agree
on the factual fields) to carry two translated words. The issue also states
outright that chip words that are plain words belong in `src/i18n/ui.ts`.

**A `<button>` plus CSS-only checkbox hack instead of `<details>`.** Considered
only to get finer control over the marker and animation. Dropped immediately:
ADR-0002 forbids client JavaScript, a checkbox hack puts a focusable control
outside the reading order and needs `aria-expanded` maintained by script to be
honest, and `<details>`/`<summary>` gives focus, Enter and Space for free —
which is exactly what criterion 5 asks for.

**Generating per-project pages at `/work/<slug>/` with the cards as index
entries.** More room per project and better deep-linking. Dropped as out of
scope for P5: the issue specifies one page with expanding cards, fourteen extra
documents would multiply the bilingual parity surface, and nothing in the issue
asks for a per-project URL.

**Wiring `scripts/check-links.mjs` into `prebuild` or `build.yml`.** Dropped
because it makes the build depend on third-party availability; the vendoring
script's explicit offline fallback shows the repository has already decided that
builds must not need the network. An opt-in script whose output lands in the pull
request keeps the evidence without the flakiness.

## Platform impact

**Migrations.** None in the data sense. `src/content.config.ts` is unchanged:
every new file validates against the existing `projectsSchema`. No change to
`src/data/metrics.json`, so `metricProblems` and `test/metrics.test.ts` are
untouched. `package.json` changes only in its `test` and `scripts` entries.

**Backward compatibility.** `mctl-api`'s `summary` and `stack` change wording;
nothing consumes them but the new page and `dev/[check].astro`'s count. The
`Nav.astro` `/#work` to `/work/` change is visible in the header on every page
and is the one edit outside the issue's stated file list (see open question 3).
`src/styles/site.css` gains an appended block and no existing rule changes, so
the home page renders byte-identically apart from that header href.

**Resource impact.** `dist/work/index.html` will be the largest document on the
site: fourteen cards with both languages inline, roughly 45-60 KB of HTML before
compression. `scripts/check-dist.mjs`'s 40 KB cap is keyed to `dist/index.html`
by path and does not apply, and `nginx.conf` already serves gzip/brotli-eligible
static files from the same origin. No new asset, no new font subset, no new
third-party request: criterion 6's same-origin half holds because nothing new is
referenced at all. Build time grows by twenty-eight markdown compilations,
which is noise next to the font vendoring step.

**Risks and mitigations.**

- *A repository URL is private or does not exist, failing criterion 3.* The
  highest-probability failure, since `mctl-loyalty`, `mctl-pairdesk`,
  `seerrsense`, `pfeifenpatenschaft-backend` and
  `pelican-libertex-social` are not referenced anywhere in this repository
  today. Mitigation: `scripts/check-links.mjs` names every non-200 in the pull
  request; the implementer reports rather than silently editing the URL, and the
  human gate decides whether to publish the repository or amend the issue.
- *`class="l en"` / `class="l ru"` counts drift.* Any helper that emits one
  language conditionally breaks `check-dist` at image build time. Mitigated by
  routing every string through `Lang.astro` or a matched pair of wrappers, and by
  the fact that the gate is mechanical and runs in the `Dockerfile`.
- *A compiled markdown body smuggles in an unbalanced element or an external
  URL.* Bodies are authored from issue copy only, contain no HTML and no image,
  and `check-links.mjs` plus the CSP (`default-src 'self'`) would surface a
  stray external reference.
- *`<summary>` loses keyboard behaviour through styling.* Avoided by keeping
  `display: list-item`, authoring no `tabindex`, and placing no interactive
  element inside `<summary>`; asserted by `test/work.test.ts` and verifiable by
  Tab-then-Space on the built page.
- *`src/styles/site.css` edited without re-running `npm run vendor`.* The served
  file is `public/styles/site.css`, a committed copy. Mitigation: `prebuild` runs
  `npm run vendor`, but the copy must also be committed in the same pull request
  or the deployed image lags the source; called out as its own task with its own
  definition of done.
- *New test files silently not run.* `package.json`'s `test` script names files
  explicitly. Mitigation: adding both files to that list is a task with a DoD
  that the test count visibly rises.
- *Page weight grows unbounded as projects are added.* Accepted for now; the
  revisit trigger is `dist/work/index.html` crossing roughly 100 KB, at which
  point per-project routes (the dropped alternative) become the answer. No cap
  is added in this proposal because the issue sets none.
