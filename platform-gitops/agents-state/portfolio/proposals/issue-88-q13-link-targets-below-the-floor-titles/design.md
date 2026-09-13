# Design: issue-88-q13-link-targets-below-the-floor-titles

## Current state

### Hit areas

`src/styles/site.css` carries one grouped tap-target rule (around line 497):

```css
/* Tap targets: every interactive element on the page is at least 44px tall
 * at any viewport width, per the 360px acceptance criterion. */
.site-nav a,
.toggle-group button,
.site-footer a {
  display: inline-flex;
  align-items: center;
  min-block-size: 44px;
}
```

plus three individual rules that each set `min-block-size: 44px` with
`display: inline-flex; align-items: center`: `.skip-link:focus` (line ~137),
`.cta` (line ~279) and `.block > summary` (line ~300, `display: list-item`).

`test/a11y.test.ts:22` hard-codes the matching list:

```ts
const TARGET_SELECTORS = ['.site-nav a', '.toggle-group button', '.site-footer a', '.cta', '.block > summary', '.skip-link:focus'];
```

and for each runs a rule-block scan: split `site.css` (comments stripped) into
`selectorList { declarations }` pairs, keep blocks whose comma-split,
whitespace-normalised selector list `includes(selector)` exactly, and assert at
least one such block declares `min-block-size: <n>px` with every such `n >= 24`.

The four unguarded classes exist and carry no size rule:

- `.project-links a` -- `src/components/ProjectCard.astro:47-58`, the repository
  and Docs links on `/work/`. `site.css` sets only `color` on it (line ~376) and
  a `:hover` / `:visited:not(:hover)` colour pin (line ~404).
- `.breadcrumb a` -- `src/components/Breadcrumb.astro`, inside a
  `display: flex; flex-wrap: wrap` `<ol>` (line ~160). No `a` rule at all.
- `.journal-meta a` -- `src/pages/colophon/journal/[...slug].astro:65-96`, the
  issue and pull-request links in the `<dl class="journal-meta">` grid
  (line ~625). No `a` rule at all.
- `.table-scroll a` -- `src/components/CycleTable.astro:23` and
  `src/pages/colophon/index.astro:71`, the cycle-title, issue and PR links in
  the cycles table and the ADR index. `.table-scroll` itself is
  `position: relative; overflow-x: auto` with a `:focus-visible` outline and a
  `@media (max-width: 599px)` `::after` gradient hint. No `a` rule.

All four sit inside `<main>`, so they inherit `main a { color: var(--accent) }`
(line ~390).

### Titles

`src/pages/colophon/journal/[...slug].astro` renders

```astro
<Base title={`${data.title.en} — Dmitrii Mashkov`} description={description}>
```

and `src/pages/colophon/adr/[...slug].astro`

```astro
<Base
  title={`ADR-${padAdrId(entry.data.id)}: ${entry.data.title.en} — Dmitrii Mashkov`}
  description={description}
>
```

`src/layouts/Base.astro` takes `{ title, description, noindex? }` and uses
`title` for `<title>`, `og:title` and `twitter:title`. `src/lib/seo.ts` is a
deliberately zero-import module (its own header comment says so, so that plain
`node --test` can import it) exporting only `clampDescription`.
`test/seo.test.ts` covers `clampDescription` and nothing else.

Measured over the committed tree, 18 of 24 journal pages and 5 of 6 ADR pages
render a title above 65 characters; the longest is 127
(`2026-09-12-symlink-safe-check-no-metrics-entry-guard.md`).

### Indexing

`src/content.config.ts` defines `journal` with a `journalSchema` strict object
plus a `superRefine` mapping `journalEntryProblems`, loaded through
`journalLoader()`, which wraps the base glob loader and runs
`checkJournalCollection` (at most one `in_progress`). `adr` is a plain
`z.strictObject`. Neither has any indexing or SEO field. Both collections are
filtered to public entries by `publicEntries` from `src/lib/content.ts`.

`astro.config.mjs` configures `@astrojs/sitemap` with a path-prefix filter:

```js
filter: (page) => {
  const path = new URL(page).pathname;
  return !path.startsWith('/404') && !path.startsWith('/dev/');
},
```

`scripts/check-dist.mjs` `checkSitemap()` (line ~758) derives the *expected*
sitemap as the exact closure `['/', '/work/', '/approach/', '/colophon/']` plus
one `/colophon/journal/<id>/` per public journal id and one
`/colophon/adr/<id>/` per public ADR id, using `idsByVisibility()` (line ~526,
a regex scan of the content directories), and reports both directions --
"sitemap is missing expected URL" and "sitemap contains unexpected URL". This
gate will fail the moment the sitemap loses eighteen journal pages, so it is
part of this change whether or not the issue's file list names it.

`Base.astro` treats indexing as one boolean with an either/or emission:

```astro
{noindex ? (
  <meta name="robots" content="noindex" />
) : (
  <link rel="canonical" href={canonicalUrl.href} />
)}
```

so today "noindex" and "has a canonical" are mutually exclusive. Only
`src/pages/404.astro` passes `noindex`.

### Share image and inline scripts

`Base.astro` emits `og:image` and `twitter:image` from
`new URL('/og.png', Astro.site)`, with no `:alt` companion, and emits exactly
one inline `<script is:inline>` (the ~330-byte language/theme bootstrap).
`scripts/check-dist.mjs` `checkOgImageMeta()` (line ~418) asserts `og:image`
and `twitter:image` are present, equal, absolute and resolve to a file under
`dist/`.

`src/lib/csp.ts` is the single source of truth for what an "inline script" is:

```ts
export const INLINE_SCRIPT_RE = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g;
```

`scripts/csp-hash.mjs` collects `extractInlineScripts` over every
`dist/**/*.html`, and **exits non-zero if the number of distinct bodies is not
exactly one**. `scripts/check-headers.mjs:251` calls `staleHashProblems`, which
requires a `script-src` hash for *every* body the same regex finds in the live
response. The negative lookahead only excludes `src=`; a
`<script type="application/ld+json">` element has no `src`, so it matches. This
is the single largest hidden dependency in the issue: the header genuinely
needs no change, but the tooling does.

### 404 and copy

`src/pages/404.astro` renders one `<h1>`, one body paragraph and one
`<p><a href="/">` home link, all through `<Lang>`, with `noindex` on `Base`.
`src/i18n/ui.ts` holds every user-facing string as an `{ en, ru }` pair;
`test/ui.test.ts` asserts that shape for every key. `ctaWork` already exists as
`{ en: 'See the work', ru: 'Смотреть работы' }` -- same English, different
Russian from what this issue specifies, so it must not be reused.
`scripts/check-dist.mjs` counts `class="l en"` against `class="l ru"` per file
and fails on any imbalance. `scripts/check-links.mjs` classifies `mailto:` as
skipped, never broken. Cloudflare Email Obfuscation was disabled for the zone
on 2026-09-11 (recorded as an intervention in
`src/content/journal/2026-09-11-production-cutover.md`), so a `mailto:` href
survives the edge intact.

### Test conventions

Source-level tests read files with `node:fs` and assert on text
(`test/a11y.test.ts`, `test/colophon.test.ts`, `test/journal-status.test.ts`).
Anything needing real built markup goes either into `scripts/check-dist.mjs`
(post-build, invoked separately because `prebuild` runs `npm test` *before*
`astro build`) or into a fixture Astro build spawned from a test
(`test/journal-build.test.ts` copies `src/`, symlinks `node_modules` and
`public/`, and runs `astro sync` or `astro build` in a temp dir).
`test/entry-point.test.ts` is the house pattern for "derive the list, never
hand-type it", and `test/check-dist.test.ts` for "prove a guard discriminates
by running it over a synthetic fixture".

## Proposed solution

Five independent slices. Nothing user-facing changes in wording or layout
beyond the 404 page's two new links.

### 1. Hit areas (`site.css`, `test/a11y.test.ts`)

Add one grouped rule to `src/styles/site.css`, next to the existing tap-target
block and commented in the same voice:

```css
/* Standalone links -- a link that is its own control rather than a word in a
 * sentence: the repository/Docs links on /work/, the breadcrumb, the journal
 * meta list, and the links inside the colophon tables. 24px is the WCAG 2.2
 * target-size minimum; the six 44px controls above are unchanged. `main a`
 * in prose is deliberately untouched. */
.project-links a,
.breadcrumb a,
.journal-meta a,
.table-scroll a {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  min-block-size: 24px;
}
```

`flex-wrap: wrap` is the one addition beyond the six existing rules' shape and
is there for `.table-scroll a`: a cycle-title link wraps two `<span class="l">`
children, and a nowrap flex container would resist breaking between them if
both were ever visible. It costs nothing and removes the only plausible way
this rule widens the cycles table. No `min-width`, no fixed height, no change
to `.table-scroll`, its `role="region" tabindex="0"` markup, its
`:focus-visible` outline or its `@media (max-width: 599px) .table-scroll::after`
hint.

In `test/a11y.test.ts`, extend `TARGET_SELECTORS` to all ten, and refactor the
per-selector body into a local pure function so the same matcher can be run
over a synthetic stylesheet:

```ts
/** Every min-block-size (in px) declared by a rule block whose comma-split
 * selector list contains `selector` exactly. */
function declaredMinBlockSizes(css: string, selector: string): number[] { ... }

/** Problems for one selector: no rule at all, or any declaration below the
 * floor. Same two assertions as before, expressed as data so the matcher can
 * be proven to discriminate. */
function minBlockSizeProblems(css: string, selector: string, floor: number): string[] { ... }
```

The recorded mutation required by acceptance criterion 1 is a test that runs
`minBlockSizeProblems` over a synthetic string containing
`.breadcrumb a { min-block-size: 16px; }` and asserts it reports a problem
naming 16, plus one over a stylesheet with no rule for the selector at all --
mirroring how `test/entry-point.test.ts` proves `entryPointProblems`
discriminates and `test/check-dist.test.ts` proves its script fails on a bad
fixture. No file outside the test is mutated.

### 2. Title budget (`src/lib/seo.ts`, both routes, `src/content.config.ts`)

`src/lib/seo.ts` gains three exports and keeps its zero-import property:

```ts
export interface TitleProblem { level: 'warn' | 'fail'; message: string }

/** Problems with a rendered <title>: a warning above `warn`, a failure above
 * `fail`. Both messages name the actual length, so a failing test says how
 * far over budget the page is. Empty list at or below `warn`. */
export function titleProblems(title: string, { warn = 65, fail = 75 } = {}): TitleProblem[]

/** The <title> a journal page renders: `seoTitle` when present, otherwise
 * `${titleEn} — Dmitrii Mashkov`. */
export function journalPageTitle(entry: { seoTitle?: string; title: { en: string } }): string

/** The <title> an ADR page renders: `seoTitle` when present, otherwise
 * `ADR-${paddedId}: ${titleEn} — Dmitrii Mashkov`. */
export function adrPageTitle(entry: { seoTitle?: string; id: number; title: { en: string } }, paddedId: string): string
```

`titleProblems` returns `[]` at 65, one `warn` at 66, and a `fail` (plus the
warn, or a single `fail`-level entry -- the criterion only requires "a failure"
at 76) above 75. The `SITE_TITLE_SUFFIX = ' — Dmitrii Mashkov'` constant lives
here too so the em-dash byte sequence exists once.

Both routes stop composing the string inline and call the helper:

```astro
<Base title={journalPageTitle(data)} description={description}>
```

```astro
<Base title={adrPageTitle(entry.data, padAdrId(entry.data.id))} description={description}>
```

`padAdrId` stays in `src/lib/adr.ts` and is passed in, so `seo.ts` keeps no
dependency on the ADR module. `<h1>` and `<Breadcrumb currentEn/currentRu>` are
untouched on both routes.

This hoist is what makes acceptance criterion 2 honest: the test imports the
same two functions the routes call, reads the frontmatter of every
`src/content/journal/*.md` and `src/content/adr/*.md`, and asserts
`titleProblems(...)` reports no `fail` for any of them, and that any page above
65 carries a `seoTitle`. Nothing is hand-typed, and the route cannot drift from
the check without the check breaking.

Schema: `seoTitle: z.string().min(1).optional()` on both `journalSchema` and the
`adr` schema in `src/content.config.ts`. Both are `strictObject`, so an
unlisted key would otherwise be rejected -- this is why the schema change is
mandatory rather than cosmetic.

### 3. Indexing (`content.config.ts`, journal route, `Base.astro`, `astro.config.mjs`, `check-dist.mjs`)

**Schema.** `indexing: z.enum(['index', 'noindex']).default('index')` on
`journalSchema` only. The default keeps a hypothetical future entry valid; the
committed tree carries the key explicitly on every entry so the file-level test
can read it without running Astro.

**Robots emission.** `Base.astro`'s `Props` gains `robots?: string`, and the
either/or block becomes:

```astro
const robotsContent = noindex ? 'noindex' : robots;
...
{robotsContent && <meta name="robots" content={robotsContent} />}
{!noindex && <link rel="canonical" href={canonicalUrl.href} />}
```

This preserves both existing outputs byte for byte -- `/404.html` emits the
robots meta and no canonical; an ordinary page emits the canonical and no
robots meta -- and adds exactly one new combination, which the journal route
uses: `robots="noindex,follow"` *with* the canonical. `noindex` stays the 404's
switch and is not overloaded.

The journal route passes
`robots={data.indexing === 'noindex' ? 'noindex,follow' : undefined}`. The ADR
route passes nothing.

**Sitemap.** `astro.config.mjs` cannot import `astro:content`. A new zero-import
helper `src/lib/indexing.ts` does the derivation once, for three consumers:

```ts
/** Reads `indexing:` out of one journal file's frontmatter; 'index' when the
 * key is absent, matching the schema default. */
export function parseIndexing(source: string): 'index' | 'noindex'

/** Every journal id whose file declares `indexing: noindex`, sorted.
 * Directory-scanning, so a new entry is covered the day it is written. */
export function noindexJournalIds(journalDir: string): string[]

/** The route paths those ids map to: `/colophon/journal/<id>/`. */
export function noindexJournalPaths(journalDir: string): string[]
```

`astro.config.mjs` imports it and closes over the set once at config load:

```js
import { noindexJournalPaths } from './src/lib/indexing.ts';
const noindexPaths = new Set(noindexJournalPaths('./src/content/journal'));
...
filter: (page) => {
  const path = new URL(page).pathname;
  if (path.startsWith('/404') || path.startsWith('/dev/')) return false;
  return !noindexPaths.has(path);
},
```

Astro loads its config through Vite, which strips TypeScript, and
`scripts/check-dist.mjs` already imports `../src/lib/content-hash.ts` from a
`.mjs` file under Node's type stripping, so a `.ts` helper is consistent with
the repository. If the config loader turns out to reject the `.ts` import in
this Astro version, the fallback is to inline the same `readdirSync` +
`parseIndexing` scan directly in `astro.config.mjs` and have the test import
`parseIndexing` from `src/lib/indexing.ts` -- still derived, still no
hand-typed path list. Either way a test asserts `astro.config.mjs` contains no
literal `/colophon/journal/` path.

**check-dist.** `idsByVisibility()` gains a third bucket, populated only for the
journal directory: `indexedIds` (public and `indexing: index`) and
`noindexIds` (public and `indexing: noindex`), read with the same
`parseIndexing` helper so the script and the config cannot disagree.
`checkSitemap()` swaps `journal.publicIds` for `journal.indexedIds` in
`expectedPaths` -- the existing "unexpected URL" branch then already proves no
`noindex` page is present, and the "missing expected URL" branch proves all six
indexed ones are. A new `checkJournalRobots()` walks
`dist/colophon/journal/<id>/index.html` and asserts, per entry: a `noindex` page
has exactly one `<meta name="robots" content="noindex,follow">` **and** a
`<link rel="canonical">`; an `index` page has no robots meta at all.

`/colophon/` itself, the cycle table, the totals, `data-cycle-row` count and the
per-entry page generation are all untouched: `checkColophonPages()` keeps using
`publicIds`.

### 4. Share image alt and BreadcrumbList (`Base.astro`, both routes, `csp.ts`)

**Alt text.** A module-level constant in `Base.astro`:

```ts
const OG_IMAGE_ALT = 'Dmitrii Mashkov — platform engineering with AI on proven open source, dmitriimashkov.com';
```

emitted as `<meta property="og:image:alt" content={OG_IMAGE_ALT} />` directly
after `og:image`, and `<meta name="twitter:image:alt" content={OG_IMAGE_ALT} />`
directly after `twitter:image`. English on every page, deliberately: the image
is English and Latin. `checkOgImageMeta()` in `scripts/check-dist.mjs` gains an
assertion that both alt values are present and equal that exact string.

**JSON-LD.** `Base.astro`'s `Props` gains `jsonLd?: unknown`:

```astro
{jsonLd && (
  <script
    type="application/ld+json"
    set:html={JSON.stringify(jsonLd).replace(/</g, '\\u003c')}
  />
)}
```

The `<` escape is the standard defence against a `</script>` sequence inside a
JSON string value; no current value contains one, and the escape keeps that
true for whatever a later cycle passes.

A new zero-import `src/lib/jsonld.ts` builds the entity:

```ts
export interface BreadcrumbItem { name: string; path: string }

/** A schema.org BreadcrumbList over `items`, positions 1..n, each `item`
 * resolved against `site`. Pure, so test/seo (or a dedicated test) can assert
 * its exact shape without a build. */
export function breadcrumbList(items: readonly BreadcrumbItem[], site: string | URL): object
```

Both routes build the three items once and pass the *same* values to both the
visible breadcrumb and the JSON-LD, which is what makes "the two cannot drift"
structural rather than aspirational:

```astro
const crumbs = [
  { name: ui.navHome.en, path: '/' },
  { name: ui.navColophon.en, path: '/colophon/' },
  { name: data.title.en, path: Astro.url.pathname },   // ADR: `ADR-${padAdrId(id)}`
];
---
<Base ... jsonLd={breadcrumbList(crumbs, Astro.site)}>
  <Breadcrumb currentEn={crumbs[2].name} currentRu={data.title.ru} />
```

The names are the English side of each pair: `<title>` is already Latin-only by
`AGENTS.md`, JSON-LD holds one string per item, and the site is one URL per
page with no `hreflang` (explicitly out of scope). `crumbs[2].name` on the ADR
route is `ADR-${padAdrId(entry.data.id)}`, exactly what the visible breadcrumb
renders today for both languages. No `Person`, `WebSite` or `Article`.

**CSP.** `src/lib/csp.ts` narrows what counts as an inline script. The regex
keeps its name and its `src=` exclusion and gains a data-block exclusion, with
the classification expressed as a small pure predicate so it is testable:

```ts
/** True for a `type` attribute value that makes the element a data block
 * rather than script: anything that is not absent, empty, `module`, or a
 * JavaScript MIME type. Per HTML, CSP script-src does not govern a data
 * block, so `application/ld+json` carries no hash. */
export function isDataBlockType(type: string | null): boolean
```

`extractInlineScripts` parses each match's attributes, skips data blocks, and
returns only real script bodies. `scripts/csp-hash.mjs` and
`scripts/check-headers.mjs` both consume it unchanged and therefore both keep
seeing exactly one body. `test/csp.test.ts` gains cases: a `ld+json` element is
ignored; `type="module"`, `type="text/javascript"`, `type=""` and no `type` are
all still captured; a document containing both the bootstrap script and a
`ld+json` block yields exactly one body. `scripts/check-dist.mjs` asserts that
every built journal and ADR page carries exactly one
`<script type="application/ld+json">`, that it parses as JSON with
`"@type": "BreadcrumbList"` and three items, and that its three `name` values
equal the three English names parsed out of that page's own
`<nav class="breadcrumb">` -- the drift check, run against real markup.
Acceptance criterion 8's "one hash for the build" is proven by
`node scripts/csp-hash.mjs` continuing to exit 0 with one token, which the
existing `.github/workflows/build.yml` path and the manual gate already run;
`test/csp.test.ts` additionally asserts `scriptSrcTokens` over the committed
`security-headers.conf` still yields exactly one hash-shaped token.

### 5. 404 (`src/i18n/ui.ts`, `src/pages/404.astro`)

Two new keys, placed beside `notFoundHome`:

```ts
notFoundWork: { en: 'See the work', ru: 'Посмотреть работы' },
notFoundContact: { en: 'Get in touch', ru: 'Написать' },
```

and two paragraphs after the existing home link:

```astro
<p><a href="/"><Lang en={ui.notFoundHome.en} ru={ui.notFoundHome.ru} /></a></p>
<p><a href="/work/"><Lang en={ui.notFoundWork.en} ru={ui.notFoundWork.ru} /></a></p>
<p><a href="mailto:hello@dmitriimashkov.com"><Lang en={ui.notFoundContact.en} ru={ui.notFoundContact.ru} /></a></p>
```

`noindex` stays. Each link adds one `class="l en"` and one `class="l ru"`, so
`check-dist`'s parity count stays balanced. `ctaWork` is untouched and not
reused. `scripts/check-links.mjs` resolves `/work/` under `dist/` and reports
the `mailto:` as skipped-and-listed.

### Content edits

Every `seoTitle` from the table in `requirements.md` is added as a top-level
scalar key in its entry's frontmatter, and every journal entry gains a
top-level `indexing:` key. Both are flat scalars, which matters for
`scripts/close-journal.mjs`: its `parseFrontmatter` reads top-level
`key: value` pairs into `data`, and `applyClosure` only ever *writes* the five
lifecycle fields (`pr`, `release`, `merged_at`, `released_at`, `deployed_at`),
preserving everything else verbatim. Adding two more flat keys is inside that
contract, and `scripts/close-journal.mjs` is not edited (out of scope).

This cycle's own entry, `src/content/journal/2026-09-13-<slug>.md`, carries
`status: in_progress`, `indexing: noindex`, no `seoTitle`, and a `title.en` at
or below 47 characters. No entry currently holds `in_progress`, so
`checkJournalCollection`'s one-cycle rule is satisfied.

### Where each acceptance criterion is proven

| criterion | proven by |
|---|---|
| 1 hit areas + mutation | `test/a11y.test.ts` (ten selectors, `minBlockSizeProblems` over real and synthetic CSS) |
| 2 `titleProblems` + no page over 75 | `test/seo.test.ts` (unit) and a new `test/title-budget.test.ts` (frontmatter scan through `journalPageTitle`/`adrPageTitle`) |
| 3 all 24 `seoTitle` verbatim | `test/title-budget.test.ts` (exact-string table; also asserts no unlisted entry carries one) |
| 4 indexing split from the collection | `test/indexing.test.ts` (`index` set equals the six named ids, all others `noindex`, every entry declares the key) |
| 5 robots meta + canonical on built pages | `scripts/check-dist.mjs` `checkJournalRobots()` |
| 6 sitemap contents derived | `scripts/check-dist.mjs` `checkSitemap()` |
| 7 `og:image:alt` / `twitter:image:alt` | `scripts/check-dist.mjs` `checkOgImageMeta()` |
| 8 one BreadcrumbList, names match, one script hash | `scripts/check-dist.mjs` + `scripts/csp-hash.mjs` + `test/csp.test.ts` |
| 9 404 copy and noindex | `scripts/check-dist.mjs` (or `test/ui.test.ts` for the exact strings plus a source assertion on `404.astro`) |
| 10 suite green | `npm run vendor && npm test`, `npm run build`, `check-dist`, `check-links` |
| 11 journal entry | the committed entry with `status: in_progress` |

Three test files may be new: `test/title-budget.test.ts`, `test/indexing.test.ts`
and `test/jsonld.test.ts` (if `breadcrumbList` is not folded into
`test/seo.test.ts`). Every one added must be appended to the enumerated
`node --test` list in `package.json`'s `test` script.

## Alternatives

**A single `noindex: boolean` on the journal schema instead of an
`indexing` enum.** Shorter to write and it would have reused `Base.astro`'s
existing prop name. Dropped: the issue specifies the enum, and a boolean makes
the third state ("indexed, and we said so on purpose") unrepresentable, so a
future `noarchive` or `max-snippet` value would be a schema migration rather
than an enum member. It would also have collided with `Base.astro`'s existing
`noindex`, which means "robots noindex *and no canonical*" -- exactly the
behaviour criterion 9 forbids for a journal page.

**Hand-typing the eighteen excluded paths in `astro.config.mjs`'s filter.**
The smallest possible diff and no new module. Dropped by the issue's own
reasoning: `test/entry-point.test.ts` exists because a hand-typed list of
scripts was wrong twice, and a hand-typed list of eighteen slugs is the same
defect class -- an entry added or reclassified in a later cycle would silently
stay in or out of the index.

**Reading the indexing split from the sitemap output rather than from the
collection.** Would have avoided touching `astro.config.mjs` at all: build
everything, then post-process `dist/sitemap-0.xml`. Dropped: the sitemap is
generated by `@astrojs/sitemap` before any post-build step runs, and rewriting
XML after the fact means `dist/` is briefly wrong and the integration's own
`sitemap-index.xml` checksum-free contract has to be re-derived. Filtering at
the source is one function and one truth.

**Leaving `src/lib/csp.ts` alone and instead giving the JSON-LD block its own
hash in `security-headers.conf`.** It would "work" in the sense that
`csp-hash.mjs` emits two tokens and the header lists both. Dropped for three
reasons: it is factually wrong (a data block is not script and needs no hash);
it breaks `csp-hash.mjs`'s "exactly one distinct inline body" rule, which
`AGENTS.md` fixes as the site's inline-script budget, so every future JSON-LD
consumer would erode that budget; and it makes the header depend on page
content, meaning any breadcrumb rename would require a header change and a
redeploy of `nginx.conf`. Editing the header is also explicitly out of scope.

**Putting the title-length assertion in `scripts/check-dist.mjs` by parsing
`<title>` out of built HTML instead of computing it from the collection.** It
would be the most literal reading of "the title the route actually renders".
Dropped: criterion 2 asks for a *test*, `npm test` runs before `astro build`,
and the hoisted `journalPageTitle`/`adrPageTitle` helpers give the same
guarantee -- the route and the test call one function -- while running in
milliseconds. `check-dist` still sees the built `<title>` indirectly, via
`og:title`, which it already reads.

## Platform impact

**Migrations.** None. Two new optional/defaulted frontmatter fields on content
files in the same repository; no database, no API, no deployed configuration.

**Backward compatibility.**

- `Base.astro`'s existing `title`, `description` and `noindex` props keep their
  exact behaviour; `robots` and `jsonLd` are additive and optional. Every page
  that passes neither renders byte-identically to today apart from the two new
  `:alt` meta tags.
- `src/lib/csp.ts`'s narrowing changes behaviour only for `<script>` elements
  with a non-JavaScript `type`, of which there are currently zero in `dist/`.
  `scripts/csp-hash.mjs` output is therefore unchanged today and stays
  unchanged after the JSON-LD lands -- which is the point.
- `scripts/close-journal.mjs` is untouched and its five-field contract is
  respected; `test/journal-closure.test.ts` must still pass over entries that
  now carry two extra flat keys.
- The sitemap loses eighteen URLs. That is the intended change, and
  `public/robots.txt` (`Disallow:` for all agents, `Sitemap:` pointing at
  `sitemap-index.xml`) needs no edit: `noindex,follow` on the page is what
  removes it from the index, and the pages stay crawlable so their outbound
  links keep counting.

**Resource impact.** Negligible. Four CSS declarations, one extra `<script>`
element of roughly 250-350 bytes on 30 pages, and two extra `<meta>` tags on
every page. `dist/index.html` gains only the two meta tags and stays far under
`check-dist`'s 40 KB cap. No new dependency; every new module is zero-import
and plain TypeScript.

**Risks and mitigations.**

| risk | mitigation |
|---|---|
| `display: inline-flex` on `.table-scroll a` makes a long cycle title unwrappable and widens the cycles table | `flex-wrap: wrap` in the same rule; no `min-width`; reviewer measures the table at 360px and 390px, EN and RU |
| `astro.config.mjs` cannot import a `.ts` helper in this Astro version | Fallback documented above: inline the same `readdirSync`/`parseIndexing` scan in the config, keep the helper as the shared parser, keep the "no literal `/colophon/journal/` path in the config" test |
| `csp-hash.mjs` fails the build on the JSON-LD block | Exactly what slice 4's `isDataBlockType` narrowing prevents; `test/csp.test.ts` proves the predicate discriminates in both directions before any build runs |
| `check-dist.mjs` `checkSitemap()` fails with eighteen "missing expected URL" problems | `idsByVisibility()` gains `indexedIds`/`noindexIds` from the same `parseIndexing`; the pre-existing bidirectional check then proves criterion 6 with no new logic |
| A `noindex` entry is read as "deleted" or "hidden" | The entry keeps its page, its colophon row, its totals contribution and `follow`; `checkColophonPages()` still counts every public entry, so a regression here fails the build |
| The 404 `mailto:` is rewritten by the edge into `/cdn-cgi/l/email-protection` | Cloudflare Email Obfuscation was disabled zone-wide on 2026-09-11 (recorded intervention in `2026-09-11-production-cutover.md`); the home page's identical `mailto:` has served correctly since |
| Sixty-odd content files edited by hand, one typo away from a wrong `seoTitle` | The exact-string table in `test/title-budget.test.ts` is the gate: a mistyped value fails by name, and `astro sync` rejects an unknown key because both schemas are `strictObject` |
| The new journal entry accidentally needs a `seoTitle` | Its `title.en` is capped at 47 characters; `test/title-budget.test.ts`'s "no unlisted entry carries `seoTitle`" and "no page over 75" assertions catch either mistake |
