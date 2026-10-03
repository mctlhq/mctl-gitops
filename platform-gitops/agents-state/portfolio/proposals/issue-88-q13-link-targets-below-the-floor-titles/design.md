# Design: issue-88-q13-link-targets-below-the-floor-titles

## Current state

### Hit areas

`src/styles/site.css` (727 lines) declares `min-block-size: 44px` in exactly
four places:

- `.skip-link:focus` (line 137 block, with `display: inline-flex; align-items: center`)
- `.cta` (line 278, same shape)
- `.block > summary` (line 298, `display: list-item`, no flex)
- a grouped block at line 494 comment "Tap targets: every interactive element
  on the page is at least 44px tall at any viewport width, per the 360px
  acceptance criterion", covering `.site-nav a`, `.toggle-group button`,
  `.site-footer a` with `display: inline-flex; align-items: center;
  min-block-size: 44px`.

`test/a11y.test.ts:22` hard-codes those six selectors in `TARGET_SELECTORS` and
runs one `node:test` case per selector. The matcher walks `([^{}]+)\{([^}]*)\}`
over the comment-stripped stylesheet, splits each selector list on commas,
requires the exact selector string to be present, and asserts that at least one
matching block sets `min-block-size` and that every such declaration is
`>= MIN_TARGET_PX` (24). The matcher is written inline in the test body; there
is no named function and no synthetic-input proof that it discriminates.

The four unguarded link classes exist and carry no size rule:

- `.project-links a` — `site.css:376` sets only `color`, plus pins at 404-405.
  Rendered by `src/components/ProjectCard.astro:47-56` as the repository link
  and each `links[]` entry (the "Docs" links) on `/work/`.
- `.breadcrumb a` — no rule at all. `site.css:160` styles `.breadcrumb ol`
  (`display: flex; flex-wrap: wrap; gap: var(--mctl-space-2)`) and
  `.breadcrumb li + li::before` renders the `/` separator.
  `src/components/Breadcrumb.astro` renders two links and one
  `<span aria-current="page">`.
- `.journal-meta a` — no rule at all. `site.css:625` makes `.journal-meta` a
  two-column grid; `src/pages/colophon/journal/[...slug].astro` puts the issue
  and pull-request links inside its `<dd>` elements.
- `.table-scroll a` — no rule at all. `src/components/CycleTable.astro:23` and
  `src/pages/colophon/index.astro:71` wrap their tables in
  `<div class="table-scroll" role="region" tabindex="0">`; the links inside are
  the journal entry link (CycleTable line 47), the issue and PR links (lines
  54-55) and the ADR link (colophon index line 87). `site.css:516` sets
  `position: relative; overflow-x: auto`, `:focus-visible` gets the outline at
  521, and an `@media (max-width: 599px)` block adds the `::after` edge
  affordance.

`main a` at `site.css:382` colours every content link inside `<main>`; the
pins at 401-405 keep `.cta` and `.project-links a` above it. Any hit-area rule
must be selector-scoped, never attached to `main a`.

### Titles

`src/layouts/Base.astro` takes `{ title, description, noindex = false }` and
renders `<title>{title}</title>`, the description meta, then either
`<meta name="robots" content="noindex">` (when `noindex`) or
`<link rel="canonical" href={canonicalUrl.href}>` — never both. It then emits
`og:type`, `og:site_name`, `og:title`, `og:description`, `og:url`, `og:image`
(`new URL('/og.png', Astro.site)`), `og:locale`, `twitter:card`,
`twitter:title`, `twitter:description`, `twitter:image`. There is no
`og:image:alt`, no `twitter:image:alt` and no JSON-LD slot.

`src/pages/colophon/journal/[...slug].astro` passes
`` title={`${data.title.en} — Dmitrii Mashkov`} `` and
`description={clampDescription(data.decided.en)}`.
`src/pages/colophon/adr/[...slug].astro` passes
`` title={`ADR-${padAdrId(entry.data.id)}: ${entry.data.title.en} — Dmitrii Mashkov`} ``.
Measured over the clone, the rendered journal titles run 27-127 characters and
the ADR titles 61-113.

`src/lib/seo.ts` is a deliberately zero-import module (its own header comment
says so: "no `astro:content`, no `astro/loaders`, no `zod` … so
`test/seo.test.ts` can exercise the real logic"). It exports only
`clampDescription`. `test/seo.test.ts` has six cases, all on
`clampDescription`.

### Indexing and the sitemap

`src/content.config.ts` defines `journal` with a `strictObject` schema plus a
`superRefine` that maps `journalEntryProblems` from `src/lib/journal.ts`, and
wraps the glob loader in `journalLoader()` so `checkJournalCollection` runs over
the whole store after every sync. `adr` uses `adrLoader()` the same way. There
is no indexing field on either.

`astro.config.mjs` configures `@astrojs/sitemap` with a `filter` that excludes
only `/404` and `/dev/`. All 24 journal entries are `visibility: public`, so
all 24 reach the sitemap.

`scripts/check-dist.mjs` is the post-build gate (`npm test` runs in `prebuild`,
before `astro build`, so it cannot see `dist/`). Its `checkSitemap()` reads
`sitemap-index.xml`, follows every child sitemap, and compares the union of
`<loc>` values against an expected set built from `idsByVisibility()` over
`src/content/journal` and `src/content/adr`: `/`, `/work/`, `/approach/`,
`/colophon/`, one `/colophon/journal/<id>/` per public journal entry and one
`/colophon/adr/<id>/` per public ADR entry. Both directions are checked
("sitemap is missing expected URL", "sitemap contains unexpected URL").
**Excluding eighteen journal pages from the sitemap without touching this
function makes `node scripts/check-dist.mjs` fail with eighteen "missing"
problems.**

`checkColophonPages()` in the same script already walks every `dist/**/*.html`,
runs `checkBreadcrumb()` on each journal/ADR page (asserting a
`<nav class="breadcrumb">` with exactly three `<li>`, a link to `/`, a link to
`/colophon/`, and a non-link third item with `aria-current="page"`), checks the
footer release, the main landmark, the absolute-URL subresource rule
(`SUBRESOURCE_RE` matches only `href=`/`src=` inside a `<link|script|img|source>`
**opening tag**, so a JSON-LD body full of absolute URLs is not matched), and
rejects any `<style>` element or `style="…"` attribute.

### CSP and inline scripts

`src/lib/csp.ts` exports
`INLINE_SCRIPT_RE = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g` and
`extractInlineScripts()`. `scripts/csp-hash.mjs` walks every `dist/**/*.html`,
collects the distinct inline bodies, and **fails when there is more than one**
("expected exactly one distinct inline script body, found N") or when the body
exceeds 400 bytes. `scripts/check-headers.mjs:251` calls `staleHashProblems()`
over the live home page, which hashes every extracted body and requires each
hash to appear in `script-src`.

The negative lookahead only excludes `src=`. A
`<script type="application/ld+json">` has no `src=`, so **today's regex would
capture the JSON-LD body**, `csp-hash.mjs` would see two distinct bodies and
exit 1, and the build/gate chain would break. This is precisely what
acceptance criterion D asks to be proven, and it cannot be proven without
changing the regex.

### 404 and i18n

`src/pages/404.astro` renders `<h1>`, a body paragraph and one
`<p><a href="/">…</a></p>`, all through `<Lang en ru />`, inside
`<Base … noindex>`. `src/i18n/ui.ts` holds `notFoundTitle`, `notFoundBody`,
`notFoundHome`. `test/ui.test.ts` asserts every `ui` entry has a non-empty
`en` and `ru` of the same kind. `src/pages/index.astro:58` already uses
`mailto:hello@dmitriimashkov.com`.

## Proposed solution

Five independent slices. Nothing is refactored beyond what a criterion needs.

### 1. `site.css` — four hit-area rules; `test/a11y.test.ts` — ten selectors

Add one new grouped rule block next to the existing "Tap targets" block at
`site.css:494`, in the same shape and with a comment naming this issue:

```css
/* Standalone links (issue #88, Q13): a link that stands on its own -- a
 * repository or docs link on /work/, a breadcrumb step, the issue and PR
 * links in a journal entry's meta list, a link inside one of the colophon
 * tables -- is a tap target in its own right and measured 17-20px. Prose
 * links inside a paragraph (main a) are deliberately not here: turning an
 * inline sentence link into a 24px flex box would break the line box it
 * sits in. No min-width, no fixed height, no animation, no transition. */
.project-links a,
.breadcrumb a,
.journal-meta a,
.table-scroll a {
  display: inline-flex;
  align-items: center;
  min-block-size: 24px;
}
```

24px rather than 44px: these links sit inside a flex `<ol>`, a grid `<dd>` and
table cells whose row height is set by their text, and 44px is the AAA figure
the six chrome-level controls already exceed. WCAG 2.2 AA 2.5.8 is 24px, which
is the floor `test/a11y.test.ts` already enforces (`MIN_TARGET_PX = 24`). The
grouped form means the existing matcher, which splits the selector list on
commas, finds all four without any change to its shape.

`inline-flex` on a table-cell or grid-cell link does not change the cell's
width, so the cycles table's column layout and `.table-scroll`'s
`overflow-x: auto` behaviour are untouched; `.breadcrumb ol`'s own
`display: flex` is untouched because the new rule targets the `<a>`, not the
list.

In `test/a11y.test.ts`:

1. Extend `TARGET_SELECTORS` to the ten selectors.
2. Lift the inline matcher out of the loop body into a named
   `minBlockSizeProblems(css: string, selector: string, floor: number): string[]`
   that returns problem strings instead of asserting, mirroring
   `entryPointProblems()` in `test/entry-point.test.ts`. Each per-selector test
   becomes `assert.deepEqual(minBlockSizeProblems(siteCss, selector, MIN_TARGET_PX), [])`.
3. Add two mutation cases recorded in the test file, over synthetic stylesheets
   defined as string literals in the test: one where the selector's block
   declares `min-block-size: 20px` (must report a problem naming `20` and the
   selector), one where the selector's block declares no `min-block-size` at
   all (must report the "no min-block-size rule found" problem). This is the
   evidence acceptance criterion A.1 asks for, in the file, runnable by
   `npm test`.

### 2. Titles

`src/lib/seo.ts` gains three exports, staying zero-import:

```ts
export function titleProblems(
  title: string,
  { warn = 65, fail = 75 }: { warn?: number; fail?: number } = {},
): string[]
```

Returns `[]` when `[...title].length <= warn`; one `warning: …` string naming
the measured length and `warn` when it is above `warn` but at or below `fail`;
one `failure: …` string naming the measured length and `fail` when it is above
`fail`. Length is counted in code points (`[...title].length`), not UTF-16
units, so an em dash counts once.

```ts
export function journalPageTitle(data: { title: { en: string }; seoTitle?: string }): string
export function adrPageTitle(data: { id: number; title: { en: string }; seoTitle?: string }): string
```

These hold the two templates — `` `${title.en} — Dmitrii Mashkov` `` and
`` `ADR-${padAdrId(id)}: ${title.en} — Dmitrii Mashkov` `` — and the
`seoTitle ?? template` precedence. `padAdrId` currently lives in
`src/lib/adr.ts`; `adrPageTitle` takes the already-padded id string is one
option, but simpler and drift-free is to re-derive the pad inline in
`src/lib/seo.ts` with `String(id).padStart(4, '0')` and have `test/adr.test.ts`'s
existing `padAdrId` coverage stand — the implementer should instead import
`padAdrId` from `src/lib/adr.ts` **only if** that module is itself zero-import;
it is (`src/lib/adr.ts` is imported by `src/content.config.ts` and by plain
`node --test`), so `adrPageTitle` imports `padAdrId` and no format is retyped.

Both routes then call the helper instead of building the string inline:
`<Base title={journalPageTitle(data)} …>` and
`<Base title={adrPageTitle(entry.data)} …>`. The `<h1>` and the
`<Breadcrumb currentEn … currentRu …>` props are untouched.

`src/content.config.ts` adds `seoTitle: z.string().min(1).optional()` to
`journalSchema` and to the `adr` schema. Both are `strictObject`, so the field
must be declared before any entry may carry it.

The 24 values from `requirements.md` go into the named files as a single
`seoTitle:` frontmatter line each.

A new `test/title.test.ts`:

- unit-tests `titleProblems` at lengths 65 (no problem), 66 (one warning whose
  message names 66 and 65), 75 (no failure), 76 (a failure whose message names
  76 and 75);
- reads `src/content/journal/*.md` and `src/content/adr/*.md`, extracts
  `title.en`, `seoTitle` and (for ADRs) `id` with focused anchored regexes in
  the style `scripts/check-dist.mjs` already uses for `VISIBILITY_RE`, feeds
  them through `journalPageTitle` / `adrPageTitle` — the same functions the
  routes call, so the computed title is the rendered title by construction —
  and asserts `titleProblems(t).every(p => !p.startsWith('failure'))` for every
  entry, i.e. nothing over 75;
- asserts that any entry whose computed title exceeds 65 carries a `seoTitle`.

`test/title.test.ts` is appended to the enumerated `test` script in
`package.json`.

In addition, `scripts/check-dist.mjs` gets a two-line extension inside the
existing per-file loop of `checkColophonPages()`: for a journal or ADR page,
read `<title>([^<]*)</title>` out of the built HTML and report a problem if its
code-point length exceeds 75. This closes the gap between "the template renders
this" and "the browser receives this" without a second source of truth.

### 3. Indexing

New zero-import module `src/lib/indexing.ts` — the single source of truth for
"which journal entries leave the index":

```ts
export const INDEXING_RE = /^indexing:\s*(index|noindex)\s*$/m;
export function indexingFromFrontmatter(text: string): 'index' | 'noindex' | null;
export function noindexJournalIds(dir: string): string[];   // sync fs read, sorted
export function noindexJournalPaths(dir: string): string[]; // `/colophon/journal/<id>/`
```

It is importable three ways, all of which already exist in this repo:
`astro.config.mjs` loads through Vite (TypeScript fine), `scripts/*.mjs` import
`../src/lib/csp.ts` under plain Node 24 today, and `node --test` runs `.ts`
directly.

`src/content.config.ts` adds
`indexing: z.enum(['index', 'noindex']).default('index')` to `journalSchema`
only. The `adr` schema is untouched.

`astro.config.mjs`:

```js
import { noindexJournalPaths } from './src/lib/indexing.ts';
const NOINDEX_PATHS = new Set(noindexJournalPaths('./src/content/journal'));
// …
filter: (page) => {
  const path = new URL(page).pathname;
  if (path.startsWith('/404') || path.startsWith('/dev/')) return false;
  return !NOINDEX_PATHS.has(path);
},
```

The set is computed from the collection's own files at config-load time, so a
new `noindex` entry is excluded the day it is written — no path list to edit.

`src/layouts/Base.astro` gains an optional `robots?: string` prop. The existing
`noindex` boolean keeps its exact current meaning and is left alone for
`/404.astro`:

```astro
{noindex ? (
  <meta name="robots" content="noindex" />
) : (
  <>
    <link rel="canonical" href={canonicalUrl.href} />
    {robots && <meta name="robots" content={robots} />}
  </>
)}
```

An `index` journal page passes nothing and renders exactly what it renders
today. A `noindex` journal page passes `robots="noindex,follow"` and gets both
the robots meta and its canonical.

The journal route computes `const robots = data.indexing === 'noindex' ? 'noindex,follow' : undefined;`
and forwards it. The ADR route forwards nothing.

`scripts/check-dist.mjs`:

- `checkSitemap()` builds its expected journal URLs from
  `idsByVisibility(JOURNAL_DIR).publicIds` **minus** the ids
  `src/lib/indexing.ts` reports as `noindex`, so both directions of the
  existing comparison still hold and a leaked `noindex` page still fails as
  "sitemap contains unexpected URL".
- `checkColophonPages()` gains, for each built journal page, a check that the
  page's robots meta matches its entry's `indexing`: `noindex` ⇒ exactly
  `<meta name="robots" content="noindex,follow">` **and** a
  `<link rel="canonical">`; `index` ⇒ no robots meta at all.

New `test/indexing.test.ts` asserts the structural invariants over the
collection (see `requirements.md` section C): every entry declares an explicit
value, every value is in the enum, the two sets partition the 24 files with no
overlap and no remainder, the `index` set is non-empty, and
`noindexJournalPaths()` returns exactly one `/colophon/journal/<id>/` path per
`noindex` entry. Added to `package.json`.

### 4. Share image alt and JSON-LD

`src/layouts/Base.astro`:

```astro
const OG_IMAGE_ALT = 'Dmitrii Mashkov — platform engineering with AI on proven open source, dmitriimashkov.com';
```

declared as a module-scope const in the frontmatter (one literal, two metas),
emitted as `<meta property="og:image:alt" content={OG_IMAGE_ALT} />` right
after `og:image` and `<meta name="twitter:image:alt" content={OG_IMAGE_ALT} />`
right after `twitter:image`. English on every page, because `public/og.svg`
renders `Dmitrii Mashkov`, `Platform engineering with AI on proven open source`
and `dmitriimashkov.com` in Latin regardless of the reader's toggle.

`jsonLd?: unknown` prop, rendered at the end of `<head>`:

```astro
{jsonLd && (
  <script
    type="application/ld+json"
    set:html={JSON.stringify(jsonLd).replace(/</g, '\\u003c')}
  />
)}
```

`set:html` because Astro would otherwise HTML-escape the quotes; the `<`
escape is the standard guard against a `</script>` sequence appearing inside a
string value. `check-dist.mjs`'s `<style>`/`style="…"` rejections and its
`SUBRESOURCE_RE` are unaffected (no `href`/`src` in the opening tag).

`src/lib/seo.ts` gains:

```ts
export function breadcrumbJsonLd(
  site: string,
  items: { name: string; path: string }[],
): object
```

returning `{'@context':'https://schema.org','@type':'BreadcrumbList','itemListElement':[…]}`
with `position` 1..n, `name`, and `item` as the absolute URL. Both routes build
the same three-element array from the same two `ui` strings and the same
current-page string they already pass to `<Breadcrumb>`:

```astro
const crumbs = [
  { name: ui.navHome.en, path: '/' },
  { name: ui.navColophon.en, path: '/colophon/' },
  { name: currentEn, path: Astro.url.pathname },
];
```

where `currentEn` is the very variable handed to `<Breadcrumb currentEn={currentEn} …>`
— one expression, two consumers, so the JSON-LD and the visible breadcrumb
cannot drift. Names are the English half, consistent with `<title>` being Latin
(`AGENTS.md`, "a browser tab is a filing label").

`src/lib/csp.ts` — the minimum change that makes acceptance criterion D.15
provable. `INLINE_SCRIPT_RE`'s negative lookahead grows one alternative so a
non-executable script type is skipped:

```ts
export const INLINE_SCRIPT_RE =
  /<script(?![^>]*\bsrc=)(?![^>]*\btype="application\/ld\+json")[^>]*>([\s\S]*?)<\/script>/g;
```

This is the one change that keeps `scripts/csp-hash.mjs` emitting exactly one
hash and keeps `scripts/check-headers.mjs`'s `staleHashProblems()` from
demanding a CSP hash for a data block. `test/csp.test.ts` gains three cases:
`extractInlineScripts` ignores a `<script type="application/ld+json">` body,
still captures the executable inline script when both are present, and
`staleHashProblems` returns `[]` for a fixture carrying both. `test/csp.test.ts`
is already enumerated in `package.json`.

`scripts/check-dist.mjs` gains `checkJsonLd(html, rel, breadcrumbNames)`, called
from the existing journal/ADR branch of `checkColophonPages()` next to
`checkBreadcrumb()`: exactly one `application/ld+json` block per page, it
`JSON.parse`s, `@type === 'BreadcrumbList'`, three `itemListElement` entries
with `position` 1,2,3, and the three `name` values equal to the three names read
out of that page's rendered `<nav class="breadcrumb">` English spans. That last
equality is the anti-drift proof acceptance criterion D asks for, measured on
built bytes.

Nothing here needs a CSP, nginx or header change, which is the point: the
`script-src` directive is untouched and `scripts/csp-hash.mjs`'s output is
compared, unchanged, by the existing `check-headers.mjs` run in
`.github/workflows/build.yml`.

### 5. The 404 page

`src/i18n/ui.ts` gains two keys next to `notFoundHome`:

```ts
notFoundWork: { en: 'See the work', ru: 'Посмотреть работы' },
notFoundContact: { en: 'Get in touch', ru: 'Написать' },
```

`src/pages/404.astro` gains two paragraphs below the existing home link:

```astro
<p><a href="/work/"><Lang en={ui.notFoundWork.en} ru={ui.notFoundWork.ru} /></a></p>
<p><a href="mailto:hello@dmitriimashkov.com"><Lang en={ui.notFoundContact.en} ru={ui.notFoundContact.ru} /></a></p>
```

Two more `<Lang>` pairs keep `class="l en"`/`class="l ru"` parity, which
`check-dist.mjs` counts. `noindex` and the bilingual shape are untouched.
`scripts/check-links.mjs` reports the `mailto:` href as skipped by count and by
name, as it already does for `src/pages/index.astro`'s contact link.

`test/ui.test.ts` gains an exact-value assertion for the two new keys, in the
shape of its existing "carry their exact EN/RU values character for character"
test. `scripts/check-dist.mjs` gains a `/404.html` check for both hrefs and both
EN strings, and for the surviving `<meta name="robots" content="noindex">`.

## Alternatives

**A. Put the hit-area rule on `main a` instead of four selectors.** One rule,
zero selector list to maintain. Dropped: `site.css:382`'s comment describes
`main a` as "any `<a>` inside `<main>` that carries no component class of its
own", which is exactly the prose link the issue says must stay untouched.
Giving every sentence link `display: inline-flex; min-block-size: 24px` turns
it into a flex box inside a line of text, changing the line box and the
underline. That is a layout change on every content page, which section
"Not in scope" forbids.

**B. Make `seoTitle` bilingual (`{ en, ru }`) like `title`.** Rejected by
`AGENTS.md`, which fixes `<title>` as a single Latin string and gives
`ui.homeTitle` the same `{ en: 'Dmitrii Mashkov', ru: 'Dmitrii Mashkov' }`
shape for that reason: a tab is a filing label, and the site's one-URL model
means one page cannot serve two titles anyway. A bilingual `seoTitle` would
also need a language decision at render time that the CSS-driven toggle cannot
make in `<head>`.

**C. Auto-truncate long titles with `clampDescription` instead of adding
`seoTitle`.** One line of code and no content edits. Dropped: a machine cut of
"Q10: a symlink-safe entry guard for check-no-metrics.mjs, and an entry-point
test that cannot forget a script" produces a search result that reads as
broken, and the issue is explicit that "an editorial H1 and a search-result
title are different jobs". The 24 values are an owner decision already made in
the issue; the implementer transcribes them.

**D. Hand-write the eighteen excluded paths in `astro.config.mjs`'s filter.**
Simplest possible diff. Dropped by the issue and by precedent:
`test/entry-point.test.ts`'s header records two separate cycles (#69, #75)
where a hand-typed list silently lost coverage. Deriving from the collection's
files is one small module and removes the class.

**E. Reuse `Base.astro`'s existing `noindex` boolean for the `noindex` journal
pages.** Dropped: today that branch emits `content="noindex"` (not
`noindex,follow`) and drops the canonical link, and acceptance criterion C
requires `noindex,follow` **with** the canonical. Overloading the boolean would
silently change `/404.html` too. A separate optional `robots` prop leaves the
404 path byte-identical.

**F. Add a CSP hash for the JSON-LD block, or add `'unsafe-inline'` to
`script-src`.** Dropped: both are wrong on the facts. `application/ld+json` is
a data block a browser never executes, so no CSP `script-src` source applies to
it; adding a hash would make `scripts/csp-hash.mjs` emit two tokens (violating
the "exactly one inline script" budget `AGENTS.md` fixes) and would make
`check-headers.mjs` demand a header change for every content edit. Narrowing
`INLINE_SCRIPT_RE` is the correct fix and makes the claim testable.

**G. Assert the built-output criteria (robots meta, sitemap contents, JSON-LD,
404 copy) in `npm test` rather than in `scripts/check-dist.mjs`.** Dropped:
`package.json`'s `prebuild` is `npm run vendor && npm test`, so `npm test` runs
**before** `astro build` and `dist/` does not exist at that point. This is
already documented at the top of `scripts/check-dist.mjs`. Source-level tests
cover the schema, the helpers and the content; built-output claims belong in
the post-build gate.

## Platform impact

**Migrations.** None. `seoTitle` is optional; `indexing` has a schema default
of `index`, so an entry without the field still validates while the content
files all declare it explicitly and `test/indexing.test.ts` enforces that. No
database, no deployment shape change, no gitops values change.

**Backward compatibility.** Every URL that exists today still exists and is
still reachable and still linked from `/colophon/`. The eighteen `noindex`
entries lose their sitemap row and gain a robots meta; they lose nothing else.
`/404.html` gains two links; no other page changes in wording or layout. The
Docker image, `nginx.conf`, `security-headers.conf` and the CSP header are
untouched.

**Resource impact.** `dist/sitemap-0.xml` shrinks by eighteen URLs. Each
journal and ADR page grows by one JSON-LD block of roughly 300-400 bytes and
every page by two meta tags of about 110 bytes each. `dist/index.html` is
capped at 40960 bytes by `scripts/check-dist.mjs`; it gains only the two meta
tags, so the cap is not at risk.

**Risks and mitigations.**

- *`scripts/csp-hash.mjs` fails with "found 2" once JSON-LD ships.* This is the
  highest-likelihood failure in the change and the reason `src/lib/csp.ts` is in
  scope. Mitigated by narrowing `INLINE_SCRIPT_RE` and by the three new
  `test/csp.test.ts` cases, which fail loudly at `npm test` time — before
  `astro build` — if the narrowing is wrong or is later reverted.
- *`scripts/check-dist.mjs` `checkSitemap()` fails with eighteen "missing URL"
  problems.* Mitigated by updating the expected-set derivation in the same
  commit, from the same `src/lib/indexing.ts` the sitemap filter uses, so the
  two cannot disagree.
- *`astro.config.mjs` importing a `.ts` module.* Precedent exists in the other
  direction (`scripts/csp-hash.mjs` imports `../src/lib/csp.ts` under plain
  Node) and Astro loads its config through Vite. If the import nonetheless
  fails, the fallback is to give `src/lib/indexing.ts` a `.mjs` sibling-free
  form — a plain `.mjs` module under `scripts/` imported by config, tests and
  `check-dist.mjs` alike. Either way there is exactly one implementation.
- *A `min-block-size` on a table-cell link changing the cycles table's layout.*
  Mitigated by using `inline-flex` with no `min-width` and no fixed height, and
  by the named reviewer step that measures the table at 360px and 390px.
- *The em dash in `seoTitle` being typed as a hyphen or an en dash.* Mitigated
  by `test/title.test.ts`'s exact-length assertions and by the fact that the
  24 values are inlined here character for character; a reviewer diffing the
  content against this file catches any drift.
- *The `l en` / `l ru` parity count on `/404.html`.* Two new `<Lang>` pairs add
  one `en` and one `ru` each, so `scripts/check-dist.mjs`'s parity check stays
  balanced. A link added without `<Lang>` would break it and fail the gate.
