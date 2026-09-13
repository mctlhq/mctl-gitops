# Design: issue-98-q15-conversion-first-home-role-history-c

All copy referenced below is in **requirements.md, Appendix A**, character for
character. Nothing in this file paraphrases a user-facing string.

## Current state

### The home page

`src/pages/index.astro` (61 lines) renders, in this document order:

1. `<h1 class="hero-name"><Lang en={ui.heroName.en} ru={ui.heroName.ru} /></h1>`
2. `<p class="thesis">` and `<p class="subline">`, both through `<Lang>`
3. `<section class="stats">` with four `<Stat>` components whose `value=` props
   are all rooted at `metrics.sources.` (`src/data/metrics.json`), plus a
   `.stat-caption` built from `snapshotDate(metrics.generated_at)`
4. `<span id="ctas-label" class="visually-hidden">` followed by
   `<nav class="ctas" aria-labelledby="ctas-label">` with two `<a class="cta">`
   links: `/work/` (`ui.ctaWork`) and `/colophon/` (`ui.ctaColophon`)
5. three `<Details … heading>` blocks: `detailsRunSummary`,
   `detailsWorkSummary`, and `detailsContactSummary` (the last with `open`),
   the third containing two hard-coded `<p><a>` links (github.com/mctlhq and
   `mailto:hello@dmitriimashkov.com`).

`src/components/Details.astro` renders `<details class="block" open={open}>`
with `<summary>` containing, when `heading` is set,
`<h2 class="block-title"><Lang …/></h2>`. Bilingual list bodies on this page
use the direct pattern `<ul class="l en">` / `<ul class="l ru" lang="ru">`.

### The string dictionary

`src/i18n/ui.ts` exports one frozen `ui` object of `{ en, ru }` pairs; values
are either strings or string arrays (`detailsRunItems`, `cycleNodes`,
`monthAbbrev`, ...). `test/ui.test.ts` walks every entry and asserts: `en` and
`ru` both present, the same kind (string vs array), arrays of equal non-zero
length, and — this is the constraint that matters here — that **every array
item is a non-empty `string`**. The file's own comment on `stackChipRu` records
that a non-`{en, ru}` shape was kept out of `ui` for exactly that reason.

### Structured data and the CSP

`src/layouts/Base.astro` takes an optional `jsonLd` prop and, when present,
emits `<script type="application/ld+json" set:html={JSON.stringify(jsonLd)
.replace(/</g, '\\u003c')} />`. Only the journal and ADR routes pass it, via
`breadcrumbJsonLd(site, crumbs)` from `src/lib/seo.ts` (a deliberately
zero-import module so `node --test` can exercise it). `INLINE_SCRIPT_RE` in
`src/lib/csp.ts` already excludes `type="application/ld+json"` from the
inline-script hash, and both `scripts/csp-hash.mjs` (generator) and
`scripts/check-headers.mjs` (runtime checker) import that one regex.

### The mechanical gates this page already sits behind

- `scripts/check-no-metrics.mjs` (runs first in `npm test`) fails on any
  two-or-more-digit literal in `src/pages`, `src/components`, `src/layouts`
  outside its RULES/ALLOW classifiers. `src/i18n` and `src/lib` are not
  scanned.
- `test/home.test.ts` asserts against the **source** of `index.astro`: the
  metrics import; exactly four `<Stat` tags with `metrics.sources.`-rooted
  values; that the template, with `<h1>`..`<h6>` tag names stripped, contains
  no digit; that no `id="work"` / `id="approach"` remains; that there are
  **exactly three `<Details` tags, each with `heading`, exactly one with
  `open`, bound to `ui.detailsContactSummary`**; that both CTAs use
  trailing-slash paths (`href="/work/"` and **`href="/colophon/"`**); and that
  the template holds no literal name outside the `description=` attribute.
- `scripts/check-dist.mjs` `checkHomePage()` (run from the **Dockerfile**:
  `RUN npm run build && node scripts/check-dist.mjs && node scripts/csp-hash.mjs`)
  asserts on `dist/index.html`: the hero `<h1>` carries `Dmitrii Mashkov` in a
  `class="l en"` span and `Дмитрий Машков` in a `class="l ru"` span; `<title>`
  is exactly `Dmitrii Mashkov` and Latin-only; **exactly one `<details open>`**;
  **exactly three `<summary><h2` openings**. A separate global pass asserts
  equal counts of `class="l en"` and `class="l ru"` on every built page, and
  `checkJsonLd()` runs only for `dist/colophon/journal/**` and
  `dist/colophon/adr/**`.
- `test/a11y.test.ts` requires a `min-block-size` of at least 44px on each of
  ten selectors including `.cta` and `.block > summary`.
- `scripts/check-contrast.mjs` proves a fixed `PAIRS` list of token pairs,
  including `{ fg: 'accent-fg', bg: 'accent', kind: 'text' }` — the pair a
  filled primary button needs. `site.css` pins `:visited` for `.cta` with
  `.cta:visited:not(:hover)` and documents the specificity arithmetic that
  keeps `main a:hover` / `main a:visited:not(:hover)` from winning.
- `scripts/check-links.mjs` walks `dist/`, resolves internal hrefs against real
  files, treats a bare `#fragment` href as "resolves to the current document",
  and lists every `mailto:`/off-origin href in a counted `skipped` map. It
  opens no socket, and `test/links.test.ts` fails if the source ever gains
  `fetch(`, `node:http`, `retry`, `setTimeout`, ... `docs/link-check.md`
  records why external reachability is deliberately not proven.
- `test/project-card-private.test.ts` and `test/journal-build.test.ts`
  establish the pattern for asserting on **rendered** markup inside `npm test`:
  copy `src/`, `astro.config.mjs`, `package.json`, `tsconfig.json` into a
  `mkdtemp` tree, symlink `node_modules` and `public`, and `spawnSync('node',
  [node_modules/astro/bin/astro.mjs, 'build'])` there, then read the built
  HTML. This matters because `npm test` runs as `prebuild`, i.e. **before**
  the real `dist/` exists.

### `/work/` and the loyalty link

`src/content/projects/mctl-loyalty.{en,ru}.md` carry
`links: - label: "Service" / url: https://labs-mctl-loyalty.mctl.ai`;
`test/projects.test.ts` asserts the exact `links:` block per slug from an
`EXPECTED_LINKS` table (line 186 today). The projects loader
(`checkProjectParity` in `src/content.config.ts`) requires the en and ru files
to agree on every `links[].url`, so both files must change together.

### The journal

`src/content/journal/*.md` is validated by `journalSchema` plus
`journalEntryProblems()` in `src/lib/journal.ts`: `issue_opened_at` is
required; `status: in_progress` forbids `release`, `released_at`,
`deployed_at`; `checkJournalCollection` allows at most one `in_progress` entry
across the whole collection (there are zero today — every entry is `complete`).
`test/colophon.test.ts` additionally requires `service`, `issue`,
`proposal_slug`, `visibility`, `status`, `title`, `decided`, `issue_opened_at`
and single-quoted ISO timestamps; `test/title.test.ts` requires the computed
`title.en + " — Dmitrii Mashkov"` to stay under 75 characters and to carry a
`seoTitle` when it exceeds 65.

## Proposed solution

### 1. `src/i18n/ui.ts` — nine new keys, two new value shapes

Add, in Appendix A's wording: `heroEyebrow`, `ctaContact`, `aboutHeading`,
`aboutParagraphs` (three strings per language), `capabilitiesHeading`,
`capabilityItems` (three `{ term, body }` per language), `contactHeading`,
`contactIntro`, `contactItems` (four `{ label, href, text }` per language).
`ctaColophon` and `detailsContactSummary` stay in the dictionary, unused.

`capabilityItems` and `contactItems` are the first arrays of objects in `ui`,
so `test/ui.test.ts`'s parity walk is generalised: for an array pair, keep the
same-kind and same-length assertions; then, per index, if both items are
strings apply the current non-empty check, and if both are objects require
identical key sets and non-empty string values for every key; a string/object
mismatch at the same index is a failure. This keeps one dictionary and one
parity gate rather than exiling two keys to a side export.

### 2. `src/pages/index.astro` — the new page structure

Document order becomes:

```
<span class="eyebrow"><Lang en={ui.heroEyebrow.en} ru={ui.heroEyebrow.ru} /></span>
<h1 class="hero-name">…heroName…</h1>
<p class="thesis">…</p>
<p class="subline">…</p>
<span id="ctas-label" class="visually-hidden">…</span>
<nav class="ctas" aria-labelledby="ctas-label">
  <a class="cta cta-primary" href="#contact">…ctaContact…</a>
  <a class="cta" href="/work/">…ctaWork…</a>
</nav>
<section id="about">      <h2>…aboutHeading…</h2>        three <p>…</p>
<section id="capabilities"><h2>…capabilitiesHeading…</h2> three (<h3>,<p>) pairs
<section class="stats">   (unchanged)
<Details detailsRunSummary heading>  (unchanged)
<Details detailsWorkSummary heading> (unchanged)
<section id="contact">    <h2>…contactHeading…</h2> <p>…contactIntro…</p> <ul>…four links…</ul>
```

The eyebrow is a block-level `<span class="eyebrow">` (not a `<p>`) so it reads
as a label attached to the heading rather than a separate paragraph; it is
still a plain `.l.en`/`.l.ru` pair through `<Lang>`.

**Bilingual rendering pattern.** Every new string goes through the existing
`<Lang en ru />` component, which emits
`<span class="l en">EN</span><span class="l ru" lang="ru">RU</span>`. This is
preferred over duplicating whole blocks per language because (a) it keeps one
heading outline — three `<h3>` terms, not six — and (b) it keeps
`class="l en"` and `class="l ru"` counts equal by construction, which is what
`scripts/check-dist.mjs`'s global bilingual-parity pass measures. The three
identity paragraphs are rendered by mapping `ui.aboutParagraphs.en` with its
index and pairing each with `ui.aboutParagraphs.ru[index]`; `capabilityItems`
and `contactItems` are mapped the same way. The `href` of a contact item is
taken from the `en` entry (the issue fixes `href`/`text` as identical across
languages), and its visible `text` likewise; only `label` is a `<Lang>` pair,
rendered before the link as the item's label.

**Digit gate.** `test/home.test.ts`'s "stripped template has no digit" rule
still holds: the new markup contains `<h2>`/`<h3>` (stripped by that test's
`/<\/?h[1-6]\b/g`), `id` values with no digits, and a map callback whose index
parameter is a name, not a literal. All digit-bearing copy (`2021`, `2024`,
`2026`, `OAuth 2.1`) lives in `src/i18n/ui.ts`, which neither that test nor
`scripts/check-no-metrics.mjs` scans.

**Name-literal gate.** `Dmitrii Mashkov` must not appear in the `index.astro`
template outside the `description=` attribute, which is why the JSON-LD is
built in `Base.astro` from `src/lib/seo.ts` and never passed from this page.

### 3. `src/layouts/Base.astro` + `src/lib/seo.ts` — `Person` and `WebSite`

`src/lib/seo.ts` (zero-import, already unit-tested by `test/seo.test.ts`) gains
`homeJsonLd()`, returning one object:

```
{
  '@context': 'https://schema.org',
  '@graph': [
    { '@type': 'Person',  name, url, jobTitle, email, sameAs: [linkedin, github, telegram] },
    { '@type': 'WebSite', name, url, inLanguage: 'en' },
  ],
}
```

with exactly the literals in Appendix A.11 and no other field — no `worksFor`,
`address`, `alumniOf`, `telephone`, or `SearchAction`. One block, one
`@graph`, so `dist/index.html` holds exactly one `application/ld+json` element.

`Base.astro` computes `const isHome = Astro.url.pathname === '/'` (the site
runs `trailingSlash: 'always'`, so the home route's pathname is exactly `/`)
and passes `jsonLd ?? (isHome ? homeJsonLd() : undefined)` into the **existing**
emission block. Nothing about that block's markup, escaping or position
changes, so:

- the journal/ADR `BreadcrumbList` path is untouched (the explicit `jsonLd`
  prop still wins), and
- the CSP inline-script hash is untouched, because `INLINE_SCRIPT_RE` excludes
  `type="application/ld+json"` and the executable inline script's bytes do not
  move.

Keeping the string literals in `src/lib/seo.ts` rather than inline in
`Base.astro` also keeps `scripts/check-no-metrics.mjs`'s scan of `src/layouts`
looking at code with no literals in it.

### 4. `src/styles/site.css`

New rules, all reusing existing tokens (no new colour pair, so
`scripts/check-contrast.mjs`'s `PAIRS` list needs no entry):

- `.eyebrow` — `display: block`, `font-family: var(--font-display)`,
  `font-size: var(--mctl-typography-font-size-sm)`, `color:
  var(--surface-fg-muted)`, letter-spacing and a small block-end margin. The
  `surface-fg-muted` on `surface-bg` pair is already proven.
- `.cta-primary` — `background-color: var(--accent)`, `border-color:
  var(--accent)`, `color: var(--accent-fg)`. The `accent-fg` on `accent` pair
  is already in `PAIRS` as `kind: 'text'`. Because `main a:hover` (0,1,2) and
  `main a:visited:not(:hover)` (0,2,2) outrank a bare `.cta-primary` (0,1,0),
  add the same kind of pins `site.css` already documents for `.cta`:
  `.cta-primary:hover` and `.cta-primary:visited:not(:hover)` both keeping
  `color: var(--accent-fg)` on the accent background, with the hover state
  distinguished by `text-decoration: underline` (a non-colour affordance, and
  no new token pair to prove). Place these after the existing
  `.cta:visited:not(:hover)` pin so the equal-specificity tie resolves in their
  favour.
- `#about` / `#capabilities` / `#contact` section spacing consistent with
  `.block` (a top border and block padding), plus `.capability-list` (`h3`
  size/weight from the display tokens, `p` with body line-height) and
  `.contact-list` (unbulleted list, `gap`, and `min-block-size: 44px` with
  `display: inline-flex; align-items: center` on `.contact-list a` so a contact
  link meets the same 44px hit-area floor `.cta` and `.project-links a` do).
- No `animation` and no `transition` anywhere (`test/a11y.test.ts` forbids both
  in this stylesheet).

`.contact-list a` is added to `TARGET_SELECTORS` in `test/a11y.test.ts` so the
new hit area is enforced rather than merely written.

### 5. `scripts/check-dist.mjs` — the gate the issue's file list omits

`checkHomePage()` currently hard-codes "exactly one `<details open>`" and
"exactly three `<summary><h2`". After this cycle the home page has **zero**
open disclosures and **two** heading summaries, so these two expectations must
be updated or the Dockerfile build fails on a correct implementation. The same
function additionally gains the home-page JSON-LD assertion (exactly one
`application/ld+json` block; `JSON.parse` it; a `Person` node with the five
fields and the three ordered `sameAs` entries; a `WebSite` node with its three
fields), mirroring the existing `checkJsonLd()` for breadcrumbs. This is the
built-bytes half of acceptance criterion 5; the `npm test` half is in
`test/home.test.ts` (below).

`docs/accessibility-checklist.md`'s heading-hierarchy row states the built home
page carries exactly three `<summary><h2` — it is updated to describe the new
outline (one `h1`; `h2` for About, Capabilities, the two disclosure summaries
and Contact; `h3` for the three capability terms).

### 6. Tests

- `test/ui.test.ts` — generalised array-parity walk (section 1) and a new
  exact-value test for all nine keys, including every array element and object
  field, character for character from Appendix A.
- `test/home.test.ts` — source-level updates: two `<Details` tags, each with
  `heading`, none with `open`; `.ctas` contains exactly two `<a>`, the first
  `href="#contact"` with `class="cta cta-primary"`, the second `href="/work/"`
  with `class="cta"`; `ui.ctaColophon` and `ui.detailsContactSummary` no longer
  referenced in the file. Plus a **build-backed** group following
  `test/project-card-private.test.ts`: one `astro build` over a copied tree
  (memoised so the build runs once for the whole file), then assertions over
  `dist/index.html` and `dist/work/index.html` — the eyebrow, each of the three
  identity paragraphs, each of the three capability terms and bodies, the
  contact intro and the four contact links all present in both `class="l en"`
  and `class="l ru"` variants; no `<details>` element containing any of those
  texts; exactly one `application/ld+json` block that `JSON.parse`s to the
  Appendix A.11 graph; `https://rewards.mctl.ai` present and
  `labs-mctl-loyalty.mctl.ai` absent from every built page. Comparisons decode
  HTML entities first (the same `decodeHtmlEntities` shape `check-dist.mjs`
  uses), because Astro escapes the apostrophe in "the team's".
- `test/seo.test.ts` — unit tests for `homeJsonLd()`: the `@graph` has two
  nodes; the `Person` node's key set is exactly
  `['@type','name','url','jobTitle','email','sameAs']`; `sameAs` deep-equals
  the three URLs in order; the `WebSite` node's key set is exactly
  `['@type','name','url','inLanguage']` and carries no `potentialAction`;
  `breadcrumbJsonLd` is unchanged.
- `test/links.test.ts` — a fixture-tree case asserting that the three new
  off-origin hrefs classify as `{ kind: 'skipped', reason: 'off-origin' }` and
  appear in `run()`'s counted `skipped` map, so the checker reports them rather
  than passing silently (open question 2).
- `test/projects.test.ts` — the one-row URL change (Appendix A.10).
- `test/a11y.test.ts` — `.contact-list a` added to `TARGET_SELECTORS`.
- `test/check-dist.test.ts` — a fixture case for the new home-page JSON-LD
  branch, in the existing spawn-the-real-script-against-a-fixture-tree style.
- Untouched and expected to keep passing: `test/nav.test.ts`,
  `test/footer.test.ts`, `test/csp.test.ts`, `test/title.test.ts`,
  `test/work.test.ts`, `test/colophon.test.ts`, `test/indexing.test.ts`.

No new file is added to the `npm test` list in `package.json`; every new
assertion lands in a file that list already names.

### 7. Journal entry

`src/content/journal/2026-09-13-q15-conversion-first-home.md`, `status:
in_progress`, `visibility: public`, `indexing: noindex`, `service: portfolio`,
`issue: https://github.com/mctlhq/portfolio/issues/98`, `proposal_slug:
issue-98-q15-conversion-first-home-role-history-c`, bilingual `title` and
`decided`, `seoTitle` short enough for the 65-character budget,
`interventions: []`, single-quoted `issue_opened_at`, and none of `pr`,
`merged_at`, `release`, `released_at`, `deployed_at`. It is the only
`in_progress` entry in the collection.

## Alternatives

1. **Keep `capabilityItems` / `contactItems` out of `ui` in a side export**
   (the `stackChipRu` precedent), leaving `test/ui.test.ts` untouched.
   Dropped: acceptance criterion 1 requires every named key to live in
   `src/i18n/ui.ts` with `en` and `ru`, and a second dictionary would put
   user-facing copy outside the file the parity gate walks — the opposite of
   what that gate exists for. Generalising the walk costs ten lines and keeps
   one source of truth.
2. **Duplicate each new block per language** (`<div class="l en">…</div>` /
   `<div class="l ru" lang="ru">…</div>`), as the two disclosure lists do.
   Dropped: it doubles the heading outline (six `<h3>` terms and two of each
   `<h2>`, half of them hidden by CSS only, which a screen reader in a
   non-toggled state would still announce), and it duplicates the contact
   `href`s, which the issue fixes as language-independent. The `<Lang>` span
   pattern already used by the hero, the thesis and every `<Stat>` label keeps
   one outline and one set of links.
3. **Emit the `Person`/`WebSite` graph from `index.astro` via the existing
   `jsonLd` prop.** Dropped: the issue puts it in `Base.astro` "on the home
   route only", and `test/home.test.ts` forbids the literal `Dmitrii Mashkov`
   anywhere in the `index.astro` template outside the `description=`
   attribute — a graph built there would trip that assertion or force an
   awkward exemption.
4. **Two separate `application/ld+json` blocks, one per node.** Dropped:
   acceptance criterion 5 requires exactly one block on `dist/index.html`, and
   a single `@graph` is the schema.org-idiomatic way to carry two nodes.
5. **Make `scripts/check-links.mjs` actually fetch the three external URLs.**
   Dropped: `test/links.test.ts` fails the build if the script gains any
   network identifier, `docs/link-check.md` records the superseded issue (#46 /
   PR #54) that died on exactly this, and the "report rather than pass
   silently" requirement is already met by the counted, listed `skipped` set.

## Platform impact

- **Migrations:** none. No schema change, no content-collection change beyond
  one URL value, no data file touched, no new dependency, no new binary asset.
- **Backward compatibility:** `ui.ctaColophon` and `ui.detailsContactSummary`
  remain exported, so nothing else that imports `ui` breaks. `Details.astro`,
  `Lang.astro`, `Nav.astro` and `Footer.astro` are unchanged. The colophon
  stays linked from the nav and the footer.
- **Resource impact:** the page grows by roughly 3-4 KB of gzipped HTML (the
  new copy, doubled for the two languages) and one small JSON-LD block. No new
  request, no client-side script, no font. `npm test` gains one `astro build`
  in `test/home.test.ts` (about the same cost as the four builds
  `test/project-card-private.test.ts` already runs), memoised so the file
  builds once.
- **Risk: the Dockerfile gate.** `scripts/check-dist.mjs` is not in the issue's
  file list but hard-codes "one `<details open>`" and "three `<summary><h2`" on
  the home page, and it runs inside `docker build`. A correct implementation
  that skips it produces a green `npm test` and a red image build. Mitigation:
  section 5 makes the update an explicit task with its own DoD, and
  `test/check-dist.test.ts` covers the new branch.
- **Risk: bilingual parity.** `scripts/check-dist.mjs` fails any built page
  whose `class="l en"` and `class="l ru"` counts differ. Mitigation: the
  `<Lang>` pattern emits both spans from one call site, so a forgotten Russian
  variant is a build failure, not a silent regression.
- **Risk: CSP hash drift.** Any change to the `<head>` inline script would
  invalidate the hash the image bakes into the CSP. Mitigation: this cycle does
  not touch that script, and the JSON-LD block is excluded from
  `INLINE_SCRIPT_RE` by the regex both the generator and the runtime checker
  import.
- **Risk: the in-progress journal invariant.** `checkJournalCollection` throws
  if two entries are `in_progress`. The collection currently has zero, so this
  cycle's entry is the only one; if a concurrent cycle has since opened one,
  the build fails loudly rather than silently.
- **Risk: `rewards.mctl.ai` reachability.** The link check proves nothing about
  external hosts by design; the host is declared in `mctlhq/mctl-gitops` at
  `platform-gitops/services/labs/mctl-loyalty/values.yaml` and is confirmed by
  reviewer step 3 after deployment.
