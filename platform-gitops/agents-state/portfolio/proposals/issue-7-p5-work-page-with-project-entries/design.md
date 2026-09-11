# Design: issue-7-p5-work-page-with-project-entries

## Current state

### Routing and layout

`astro.config.mjs` sets `output: 'static'`, `trailingSlash: 'always'` and
`build.inlineStylesheets: 'never'`. Pages live in `src/pages/`: `index.astro`,
`404.astro` and the development-only `dev/[check].astro` whose
`getStaticPaths` returns `[]` outside `astro dev`, so it never reaches `dist/`.
There is no `src/pages/work.astro`, yet `src/pages/index.astro` renders
`<a class="cta" href="/work/">` and `test/home.test.ts` asserts that link
exists. `/work/` is therefore a known 404 today.

`src/layouts/Base.astro` owns the document: it hardcodes
`<html lang="en" data-lang="en" data-theme="dark">`, carries the single inline
preference script (`is:inline`, under the 400-byte budget that
`scripts/csp-hash.mjs` enforces), links the five stylesheets from `public/`, and
renders `<Nav />`, a `<slot />` and `<Footer />`. Its only prop is `title`.

### Bilingual mechanism

`src/i18n/Lang.astro` emits exactly
`<span class="l en">{en}</span><span class="l ru" lang="ru">{ru}</span>`.
`src/styles/site.css` hides the inactive half with
`:root[data-lang='en'] .l.ru { display: none }` and its mirror. Every
user-facing string lives in `src/i18n/ui.ts` as an `{ en, ru }` pair (or a pair
of equal-length arrays); `test/ui.test.ts` walks `Object.entries(ui)` and
asserts each entry has a non-empty `en` and `ru` **of the same kind**, so any
new entry must be a string pair or an array pair — a lookup object keyed by
something other than `en`/`ru` would fail that test.

`scripts/check-dist.mjs` walks every `dist/**/*.html` and fails the build if the
counts of the literal substrings `class="l en"` and `class="l ru"` differ in any
file. It also fails on any `.js` file under `dist/` and caps `dist/index.html`
at 40 KB. It needs no change for this issue: the parity and no-`.js` checks
already cover a new page automatically, and the size cap is `index.html`-only.

### Content collections

`src/content.config.ts` already defines the `projects` collection. Frontmatter
is a `z.strictObject` with `slug` (`/^[a-z0-9-]+$/`), `lang` (`'en' | 'ru'`),
`name`, `group` (`z.enum(['platform', 'product'])`), `order` (non-negative
integer), `repo` (a `https://github.com/...` regex), `stack` (non-empty array of
non-empty strings), `summary` (non-empty, refined to reject `\n`) and an
optional `links` array of `{ label, url }`. `projectsLoader()` wraps the glob
loader for `*.{en,ru}.md` with `generateId: idFromFile`, so entry ids are
`mctl-api.en` and `mctl-api.ru`, and runs `checkProjectParity` over the whole
store after sync: every slug needs exactly one `en` and one `ru` entry, and the
two must agree on `group`, `order`, `repo`, `stack` (compared by
`JSON.stringify`) and each `links[].url`. `name`, `summary`, `links[].label` and
the body may differ.

Two content files exist: `src/content/projects/mctl-api.en.md` and
`mctl-api.ru.md`, with `order: 1`, `group: platform`, a six-element `stack`, and
a `links` entry for `https://docs.mctl.ai`. Nothing renders them. No page in
the repository calls `render()` on a collection entry yet — `/work/` is the
first.

### Metrics

`src/data/metrics.json` currently holds `generated_at: null` and two sources
(`github` with `repos`/`commits`/`releases`, `mctl` with
`services`/`devloop_proposals`), every value `null`, `method: "placeholder"`.
`src/lib/metrics.ts` is deliberately import-free so `node --test` can load it
without a build step; it exports `EM_DASH`, `formatStat` (branching on
`value === null`, never on falsiness, so a real `0` renders as `0`),
`snapshotDate` and `metricProblems`. `metricProblems` validates only the keys it
knows about and ignores unknown keys, so adding `sources.github.per_repo` later
does not break it. `src/components/Stat.astro` wraps `formatStat` with a
`<Lang>` label and a `data-stat` hook; `src/pages/index.astro` passes only
`metrics.sources.*` expressions, which `test/home.test.ts` asserts by regex.

### Styling

`src/styles/site.css` is the source of truth (`npm run vendor` copies it to
`public/styles/site.css`). Relevant existing rules:

- `.block` — `border-top`, `padding-block`; `.block > summary` gets
  `cursor: pointer`, `min-block-size: 44px`, `display: list-item`; `.block ul`,
  `.block li`, `.block p` get spacing. These are the home page's `<details>`
  blocks.
- `:focus-visible { outline: var(--focus-ring-width) solid var(--focus-ring) }`
  — a global focus ring, so a native `<summary>` is already visibly focusable.
- The `@media print` block forces `.block > *:not(summary)` visible with
  `display: block !important`, then re-hides the inactive language with the
  higher-specificity `:root[data-lang='en'] .block > .l.ru` override. That
  override only matches **direct** children of `.block`.
- `--font-editorial`, `--font-display` and `--font-mono` come from the vendored
  `@mctlhq/css` 0.5.0 (`public/assets/mctl/mctl.css`). `.hero-name` uses
  `--font-editorial` (Instrument Serif); `AGENTS.md` and issue #4 record that
  Instrument Serif ships no Cyrillic subset, so it must not carry translated
  text. `public/assets/mctl/prose.css` scopes its editorial typography under
  `.mctl-prose`, so it does not leak into unopted markup.

### Gates

`package.json` runs `prebuild: npm run vendor && npm test` and
`test: node --test test/journal.test.ts test/adr.test.ts test/metrics.test.ts test/home.test.ts test/ui.test.ts`
— a new test file is invisible to CI unless it is added to that list.
`.github/workflows/build.yml` runs `npm ci` then `npm test`, then a Docker
build. `AGENTS.md` explicitly declares `build.yml` **not** reserved, so touching
it is allowed; this change does not need to.

## Proposed solution

Five files change and four are added. Nothing outside `src/` and
`package.json`'s `test` script is touched.

### 1. `src/lib/projects.ts` (new) — pairing, ordering, chip lookup

An import-free-except-`ui` helper module, in the style of `src/lib/metrics.ts`
and `src/lib/adr.ts`, so `node --test` can exercise it without Astro.
`src/i18n/ui.ts` is itself import-free, so importing it keeps the module
loadable by plain Node (`test/ui.test.ts` already imports it that way).

```ts
export interface ProjectFrontmatter {
  slug: string; lang: 'en' | 'ru'; name: string;
  group: 'platform' | 'product'; order: number; repo: string;
  stack: readonly string[]; summary: string;
  links?: readonly { label: string; url: string }[];
}

export interface ProjectPair<T> {
  slug: string; name: string; group: 'platform' | 'product';
  order: number; repo: string; stack: readonly string[];
  en: T; ru: T;
}

export function pairByLang<T extends { id: string; data: ProjectFrontmatter }>(
  entries: readonly T[],
): ProjectPair<T>[];

export function inGroup<T>(
  pairs: readonly ProjectPair<T>[], group: 'platform' | 'product',
): ProjectPair<T>[];

export function repoLinkText(repo: string): string;   // strips 'https://'
export function chipLabel(chip: string): { en: string; ru: string };
```

- `pairByLang` groups by `data.slug`, throws a message naming every offending
  slug when a language is missing or duplicated, and hoists the
  loader-guaranteed-identical fields (`group`, `order`, `repo`, `stack`, `name`)
  off the English entry. The duplicate check is deliberate belt-and-braces: it
  makes the pairing total in the type system, so `ProjectPair.en` and `.ru` are
  never `undefined` at the call site.
- `inGroup` filters and returns a **new** array sorted by `order` ascending with
  `slug` as a deterministic tiebreak; it must not sort the input array in place,
  because the caller reuses it for the second group.
- `chipLabel` is the only place chip translation lives. It reads a `Map` built
  from the plain-word chip entries in `ui` (`chipDesignTokens`,
  `chipUpstreamFork`) and returns `{ en: chip, ru: <mapped> ?? chip }`. The
  fallback is what keeps `Go`, `chi`, `Telegram Mini App` and the rest
  untranslated with no per-chip bookkeeping.
- `repoLinkText` exists so the repository link's visible text is derived from
  the `repo` field rather than typed, and is unit-testable.

### 2. `src/i18n/ui.ts` — seven new entries

`workTitle`, `workGroupPlatform`, `workGroupProducts`, `workRepoLabel`,
`workMetricsLabel`, `chipDesignTokens`, `chipUpstreamFork`, with the exact
strings fixed in `requirements.md`. All are `{ en, ru }` string pairs, so
`test/ui.test.ts` passes unchanged. Below the `ui` object, a second export:

```ts
const CHIP_TRANSLATIONS: ReadonlyMap<string, string> = new Map(
  [ui.chipDesignTokens, ui.chipUpstreamFork].map((e) => [e.en, e.ru]),
);
export function chipRu(chip: string): string | undefined { ... }
```

Building the map *from* the `ui` entries rather than beside them means the chip
translations are still covered by `test/ui.test.ts`'s non-empty/same-kind sweep,
and there is exactly one place a Russian chip string is written.

The page heading reuses `ui.navWork`; the metrics row reuses `ui.statCommits`
and `ui.statReleases`. No existing entry is edited.

### 3. `src/lib/metrics.ts` — a forward-compatible `per_repo` reader

Two additions, no change to any existing export:

```ts
export interface MetricPerRepo {
  commits: number | null;
  releases: number | null;
}

export function perRepo(metrics: unknown, slug: string): MetricPerRepo;
```

`perRepo` walks `sources.github.per_repo[slug]` entirely defensively — any
missing or non-object level, and any value that is not a non-negative integer,
yields `null` for that field. Against today's `src/data/metrics.json`, which has
no `per_repo` key, it returns `{ commits: null, releases: null }`, which
`formatStat` renders as `—`. `src/data/metrics.json` is **not** edited: P8b owns
the snapshot's shape and the generator that fills it. `metricProblems` is left
alone; it ignores unknown keys, so it neither rejects nor validates `per_repo`
today, and P8b extends it when the shape is decided.

This is what makes the metrics slot honest: the page displays a number the
moment the snapshot carries one, and an em dash until then, with no number
typed into a template — the rule in `AGENTS.md`.

### 4. `src/components/ProjectCard.astro` (new)

One native `<details>` per card, no client-side code:

```astro
---
import { render } from 'astro:content';
import Lang from '../i18n/Lang.astro';
import { ui } from '../i18n/ui';
import { chipLabel, repoLinkText, type ProjectPair } from '../lib/projects';
import { formatStat, perRepo } from '../lib/metrics';
import raw from '../data/metrics.json';

interface Props { project: ProjectPair<CollectionEntry<'projects'>> }
const { project } = Astro.props;
const { Content: ContentEn } = await render(project.en);
const { Content: ContentRu } = await render(project.ru);
const counts = perRepo(raw, project.slug);
const enLinks = project.en.data.links ?? [];
const ruLinks = project.ru.data.links ?? [];
---
<details class="block card">
  <summary>
    <h3 class="card-name">{project.name}</h3>
    <span class="card-summary">
      <Lang en={project.en.data.summary} ru={project.ru.data.summary} />
    </span>
    <span class="chips">
      {project.stack.map((chip) => {
        const c = chipLabel(chip);
        return <span class="chip"><Lang en={c.en} ru={c.ru} /></span>;
      })}
    </span>
  </summary>
  <div class="card-body">
    <div class="l en"><ContentEn /></div>
    <div class="l ru" lang="ru"><ContentRu /></div>
    <ul class="card-links">
      <li><a href={project.repo}>{repoLinkText(project.repo)}</a></li>
      {enLinks.map((link, i) => (
        <li><a href={link.url}><Lang en={link.label} ru={ruLinks[i]?.label ?? link.label} /></a></li>
      ))}
    </ul>
    <div class="card-metrics">
      <span class="card-metric">
        <span class="card-metric-value">{formatStat(counts.commits)}</span>
        <span class="card-metric-label"><Lang en={ui.statCommits.en} ru={ui.statCommits.ru} /></span>
      </span>
      <span class="card-metric"> ... releases ... </span>
    </div>
  </div>
</details>
```

Why each part is the way it is:

- **`render()` inside the component, not the page.** Astro component
  frontmatter supports top-level `await`, so each card resolves its own two
  bodies and `work.astro` stays a list of `<ProjectCard>` elements. The
  alternative — resolving all twenty-eight in `work.astro` and threading
  component references through props — spreads the concern across two files for
  no gain.
- **`class="block card"`, not `class="card"`.** This reuses every existing
  `.block` rule, including the whole `@media print` treatment, unchanged. The
  print rule `.block > *:not(summary) { display: block !important }` forces the
  single `.card-body` open, and because `.l.en` / `.l.ru` are its *children*
  rather than direct children of `.block`, the ordinary language-toggle rules
  (no `!important` on either side) still hide the inactive language. No print
  CSS changes, and the comment in `src/styles/site.css` explaining that
  override stays accurate.
- **Chips are `<span>`s, not a `<ul>`.** The HTML content model for `<summary>`
  is phrasing content optionally intermixed with heading content; a `<ul>` is
  neither, so it would make the document invalid. Spans are phrasing content.
  The `<h3>` is allowed as heading content and gives the page a real outline
  (`h1` Work, `h2` group, `h3` project).
- **No chip literal in the template.** The chips come from
  `project.stack.map(...)`, and their Russian side comes from `chipLabel`, whose
  data lives in `ui.ts`. Acceptance criterion 4 is then checkable by grepping
  `ProjectCard.astro` for any chip string, which `test/work.test.ts` does.
- **The project name renders once, unwrapped.** `name` is identical in both
  languages (an identifier), so it is not an `.l` pair; that keeps the parity
  counts balanced without a redundant duplicate span, and matches `AGENTS.md`'s
  "identifiers stay untranslated".
- **Links pair by index.** `checkProjectParity` guarantees `links[].url`
  matches in order across the two files, so index pairing is sound; the `??`
  fallback keeps the render total if a future edit slips past the loader.
- **Nothing carries `open`.** All fourteen cards are closed on load, which keeps
  first paint short and the page scannable.
- **No `tabindex`, `role` or `onclick` anywhere.** A bare `<summary>` is
  focusable and toggles on Enter and Space natively; every attribute one might
  add here would only take that away. `test/work.test.ts` asserts their absence.

### 5. `src/pages/work.astro` (new)

```astro
---
import { getCollection } from 'astro:content';
import Base from '../layouts/Base.astro';
import Lang from '../i18n/Lang.astro';
import ProjectCard from '../components/ProjectCard.astro';
import { ui } from '../i18n/ui';
import { inGroup, pairByLang } from '../lib/projects';

const pairs = pairByLang(await getCollection('projects'));
const groups = [
  { heading: ui.workGroupPlatform, items: inGroup(pairs, 'platform') },
  { heading: ui.workGroupProducts, items: inGroup(pairs, 'product') },
];
---
<Base title={ui.workTitle.en}>
  <main>
    <h1><Lang en={ui.navWork.en} ru={ui.navWork.ru} /></h1>
    {groups.map((g) => (
      <section class="work-group">
        <h2><Lang en={g.heading.en} ru={g.heading.ru} /></h2>
        {g.items.map((project) => <ProjectCard project={project} />)}
      </section>
    ))}
  </main>
</Base>
```

The group list is data, so the two sections cannot drift in markup, and the
order of the array is the order on the page. `Base` already supplies the nav,
footer, stylesheets and the single inline script; `work.astro` adds none of its
own. No introductory lede paragraph is added — the issue supplies no copy for
one and inventing copy is forbidden.

### 6. `src/content/projects/*.{en,ru}.md` — twenty-eight files

Twenty-six new files plus a rewrite of the two existing `mctl-api` files, with
the frontmatter and bodies fixed character for character in `requirements.md`.
`mctl-api` keeps `order: 1`, `group: platform` and its `links` block; its
`stack`, `summary` and body are replaced with the issue's copy. `order` uses the
issue's global numbering 1-14 (Platform 1-6, Products 7-14), which leaves
`mctl-api`'s existing value untouched and makes the intended sequence readable
from any single file.

### 7. `src/styles/site.css` — card styling

New rules only, appended near the existing `.block` section; no existing rule is
edited.

```css
.work-group { margin-block: var(--mctl-space-6); }
.card > summary { display: list-item; }             /* inherited from .block */
.card-name { font-family: var(--font-mono); font-size: var(--mctl-typography-font-size-body); margin: 0; }
.card-summary { display: block; font-family: var(--font-display); color: var(--surface-fg); }
.chips { display: flex; flex-wrap: wrap; gap: var(--mctl-space-2); margin-block-start: var(--mctl-space-2); }
.chip { font-family: var(--font-mono); font-size: var(--mctl-typography-font-size-xs);
        padding: var(--mctl-space-1) var(--mctl-space-2);
        border: 1px solid var(--surface-line); border-radius: var(--mctl-radius-md);
        color: var(--surface-fg-muted); }
.card-links { list-style: none; padding: 0; margin-block: var(--mctl-space-3); }
.card-links a { overflow-wrap: anywhere; display: inline-flex; align-items: center; min-block-size: 44px; }
.card-metrics { display: flex; flex-wrap: wrap; gap: var(--mctl-space-5); }
.card-metric-value { font-variant-numeric: tabular-nums; }
```

`--font-editorial` appears nowhere in these rules. Every translated string on
`/work/` is Onest (`--font-display`, inherited from the body) and every
identifier is JetBrains Mono (`--font-mono`) — the typography constraint carried
from #4. The chip border and muted foreground come from the vendored token set,
so chips theme correctly in both light and dark without new colour values.
`.card-links a` repeats the 44px tap-target pattern the file already applies to
`.site-nav a`, `.toggle-group button` and `.site-footer a`.

After editing `src/styles/site.css`, `npm run vendor` must run to refresh
`public/styles/site.css` — that copy is what `Base.astro` links, and it is
committed.

### 8. `src/components/Nav.astro` — one `href`

`/#work` becomes `/work/`. This is the one file outside the issue's list that
changes: the anchor it points at no longer exists (`test/home.test.ts` asserts
`id="work"` is gone from `index.astro`), and the nav renders on `/work/` itself.
The Approach link is left as it is; its page is a later issue.

### 9. `package.json` — register the new tests

`test/projects.test.ts` and `test/work.test.ts` are appended to the `test`
script. Without this they run nowhere.

## Alternatives

**Data in a TypeScript module instead of content collections.** A single
`src/data/projects.ts` exporting fourteen objects with `en`/`ru` fields would be
one file instead of twenty-eight and would need no `render()` call. Dropped:
`src/content.config.ts` already ships a `projects` collection with a Zod schema
and a bespoke `checkProjectParity` loader, written for exactly this purpose,
and the issue names `src/content/projects/*.en.md` / `*.ru.md` as the files to
add. Bypassing the collection would leave dead validation code in the repo and
lose markdown bodies for the detail bullets.

**One `.md` file per project with `summary_en` / `summary_ru` frontmatter and
two body sections.** Halves the file count. Dropped: the existing schema pins
`lang: z.enum(['en', 'ru'])` and the loader's parity check is built around
one file per language, so this would mean rewriting `src/content.config.ts` — a
change to reviewed, working validation for a cosmetic gain, in a repository
whose `AGENTS.md` runs one DevLoop cycle at a time.

**Always-visible card header plus a nested `<details>` labelled "Details".**
Reading (b) of the issue's card description. Dropped: it puts a second
focusable control on every card, needs a new `Details` / `Подробнее` string the
issue did not supply, and acceptance criterion 5 speaks of *the* `<summary>` of
a card in the singular. Recorded in `requirements.md`'s Open questions.

**Reusing `src/components/Details.astro` for the card.** Its `<summary>` is a
single `<Lang>` pair, so the card would need a new slot for summary content —
a change to a component the home page depends on, to serve a different shape.
Dropped: `ProjectCard.astro` authors its own `<details class="block card">`,
inherits all the `.block` CSS, and leaves `Details.astro` untouched.

**Reusing `src/components/Stat.astro` for the metrics row.** Dropped for the
same reason inverted: `Stat.astro` renders a large `clamp(28px, 8vw, 40px)`
hero figure with a `data-stat` hook sized for the home page's four headline
numbers. Fourteen cards with two such figures each would dominate the page.
The card uses `formatStat` directly with its own small `.card-metric` markup,
so the em-dash-on-null rule is still shared and there is still exactly one
place that decides what a missing number looks like.

**Adding `per_repo` data to `src/data/metrics.json` now.** Dropped: the issue
puts per-project numbers out of scope and assigns the snapshot to P8b. Writing
placeholder objects full of `null`s into the snapshot would be speculative
shape-setting for another cycle, and the defensive reader gives the same
rendered result (`—`) with no commitment.

**Extending `scripts/check-dist.mjs` with a size cap for `dist/work/index.html`
and a card-count assertion.** Dropped: the issue asks for neither, a threshold
invented here could block the page on a number nobody agreed to, and the
existing parity and no-`.js` checks already cover the new page. The pull request
reports the built byte size so a cap can be set with evidence later.

## Platform impact

**Migrations.** None. No database, no API, no schema change. `src/data/metrics.json`
is unchanged, so no snapshot migration. `src/content.config.ts` is unchanged, so
no content re-validation beyond the new files passing the existing schema.

**Backward compatibility.** Purely additive at the routing level: `/work/`
starts returning 200 where it returned the 404 page. `src/pages/index.astro`,
`Base.astro`, `Details.astro`, `Stat.astro` and `Lang.astro` are untouched, so
`test/home.test.ts` and `test/ui.test.ts` keep passing as written. The one
behavioural change outside the new page is `Nav.astro`'s Work link, which moves
from a dangling `/#work` fragment to a real route.

**Resource impact.** `dist/work/index.html` adds one static file. It carries
twenty-eight markdown bodies and fourteen chip sets in both languages, so it
will be substantially larger than the 40 KB `index.html` — expect roughly
60-110 KB uncompressed, well compressed by the `gzip_types text/plain` entry
already in `nginx.conf`. No new font subset, no new stylesheet, no new request:
the page uses only the five already-linked stylesheets from `public/`. Zero
JavaScript bytes added; `dist/` still contains no `.js` and exactly one inline
script body, so the CSP hash in `nginx.conf` does not change. No third-party
origin is introduced, so the HAR stays same-origin.

**Risks and mitigations.**

- *A copy transcription error.* Twenty-eight files of fixed bilingual copy is
  the largest failure surface here. Mitigation: every string is inlined in
  `requirements.md`, and `test/work.test.ts` mechanically checks that each
  `*.ru.md` body and summary contains Cyrillic while each `*.en.md` does not,
  which catches the realistic mistakes (a language pasted into the wrong file,
  a half-translated file) without asserting on prose.
- *A missing or mismatched language file.* Mitigation: already fatal.
  `checkProjectParity` in `src/content.config.ts` throws during `astro sync`,
  `astro check`, `astro dev` and `astro build` alike, and `pairByLang` throws a
  second time with the offending slug named.
- *Bilingual parity drift breaking the build gate.* An `.l.en` without its
  `.l.ru` fails `scripts/check-dist.mjs`. Mitigation: every pair on the page
  comes from `Lang.astro` or from the two explicit body wrappers in
  `ProjectCard.astro`, so parity is structural rather than maintained by hand.
- *Instrument Serif leaking onto Russian text.* Mitigation: no new rule uses
  `--font-editorial`, and `test/work.test.ts` asserts the string
  `--font-editorial` does not appear in any rule added for this page.
- *Forgetting `npm run vendor` after editing `src/styles/site.css`.* The served
  copy is `public/styles/site.css`, so the page would ship unstyled cards.
  Mitigation: `prebuild` runs `npm run vendor` before every build, and the task
  list makes the committed diff of `public/styles/site.css` an explicit
  deliverable.
- *`https://docs.mctl.ai` returning a non-200 and failing acceptance criterion
  3.* Mitigation: the link-check script runs before the pull request is opened;
  if that host fails, the `links` block is removed from both `mctl-api` files
  and the removal is stated in the description.
- *`per_repo` landing in P8b with a different shape.* Mitigation: `perRepo` is
  defensive at every level and returns nulls rather than throwing, so a shape
  mismatch degrades to em dashes — the same thing the page renders today — and
  P8b adapts one function in `src/lib/metrics.ts`.
- *New test files not running in CI.* Mitigation: they are added to
  `package.json`'s `test` script, which both `prebuild` and
  `.github/workflows/build.yml` invoke; the task list gates on seeing them in
  the `npm test` output.
