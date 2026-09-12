# Design: issue-49-q5-navigation-state-disclosure-defaults

## Current state

### The shell

`src/layouts/Base.astro` renders the whole document: `<head>` with one inline
`is:inline` script (persisted `data-lang` / `data-theme`, hash-pinned in
`security-headers.conf`), five stylesheet links, the SEO meta block, and a
`<body>` of exactly `<Nav />`, `<slot />`, `<Footer />`. It has no `<main>`.
Each of the seven pages authors its own `<main>` as the single root of the
slot: `src/pages/index.astro:18`, `work.astro:26`, `approach.astro:19`,
`colophon/index.astro:29`, `404.astro:12`,
`colophon/journal/[...slug].astro:55`, `colophon/adr/[...slug].astro:46`. None
of them carries an `id` or a `tabindex`. `scripts/check-dist.mjs`
(`checkMainLandmark`, line 268) already asserts exactly one `<main>` per built
page.

`src/components/Nav.astro` is nineteen lines: a `<header class="site-header">`
containing a `<nav class="site-nav">` with four hard-coded anchors (`/`,
`/work/`, `/approach/`, `/colophon/`), followed by `<LangToggle />` and
`<ThemeToggle />` as bare siblings. Its only frontmatter computation is

```
const navLabel = `${ui.navLabel.en} / ${ui.navLabel.ru}`;
```

which is emitted as `aria-label="Primary navigation / Основная навигация"`. No
anchor carries `aria-current`, and nothing reads `Astro.url`.

### The bilingual mechanism

`src/i18n/Lang.astro` emits `<span class="l en">{en}</span><span class="l ru"
lang="ru">{ru}</span>` and `src/styles/site.css:10-15` hides one half via
`:root[data-lang='en'] .l.ru { display: none }` and its mirror. The same
pattern drives the theme (`.t.dark` / `.t.light`, lines 18-23). `Details.astro`
already relies on a **hidden descendant being excluded from an accessible
name**: it puts `<span class="visually-hidden">, <Lang …/></span>` inside
`<summary>`, and only the active-language half contributes. `.visually-hidden`
(site.css:211) uses `clip-path`, deliberately not `display: none`, "so a
`<summary>` can carry a distinct accessible name".

`scripts/check-dist.mjs:563` counts the exact substrings `class="l en"` and
`class="l ru"` in every built HTML file and fails on inequality. A class
attribute such as `class="toggle-group l en"` does **not** match that substring,
so the toggle-group wrappers are invisible to the parity count today.

### The toggles

`LangToggle.astro` renders two `<div class="toggle-group l en|l ru">`, each with
two buttons; `ThemeToggle.astro` renders two `<div class="toggle-group t
dark|t light">`, each with two buttons. Both compute a slash-joined bilingual
`groupLabel` and put it in `aria-label` on a bare `<div>` — a generic element,
where `aria-label` is not exposed. `site.css:77` gives `.toggle-group` only
`display: inline-flex; gap: var(--mctl-space-2)`; nothing spaces the two groups
apart. At runtime exactly one div per group is visible (the others are
`display: none`, and therefore out of the tab order), which is why the header
has eight focusable controls, not twelve.

### The disclosures

`src/components/Details.astro` already accepts an `open?: boolean` prop
(default `false`) and passes it straight to `<details class="block"
open={open}>`; no caller passes it today. `index.astro:38,47,56` renders
`What I run`, `How I work`, `Contact`; `approach.astro:27,36,47` renders
`Gates`, `Numbers`, `Proven open source`; `work.astro` renders fourteen via
`ProjectCard.astro`. The summary text is a bare `<Lang>` pair with no heading.

### The gates already in place

- `npm test` runs `check-no-metrics`, `check-contrast` and twenty-one
  `node --test` files, all before `astro build` (`prebuild` is
  `npm run vendor && npm test`), so they see source, never `dist/`.
- `test/a11y.test.ts` asserts a `:focus-visible` outline rule, a
  `min-block-size >= 24px` for each selector in a fixed `TARGET_SELECTORS`
  array, and **no `animation` or `transition` property anywhere in
  `src/styles/site.css`**.
- `test/approach.test.ts:48` asserts `approach.astro` contains **no**
  `tabindex` at all, and `:114` asserts `Nav.astro` still contains the literal
  `href="/approach/"`.
- `test/home.test.ts:26` and `test/approach.test.ts:32` strip `<h1>`…`<h6>` tag
  names from the template and then assert the remainder contains **no digit**.
- `scripts/check-contrast.mjs` resolves real hex tokens from
  `public/assets/mctl/mctl.css` and checks a fixed `PAIRS` list; `accent` over
  `surface-bg` / `surface-elevated` is already covered.
- `scripts/check-links.mjs:86` classifies a bare `#…` href as
  `{ kind: 'fragment' }` and skips it, with a comment noting no such href
  exists on the site yet.
- `src/styles/site.css` is the source of truth; `npm run vendor` copies it to
  the gitignored `public/styles/site.css`.

## Proposed solution

Seven small, independent edits plus one structural move. Nothing gains a
client-side script; every decision is made at build time.

### 1. Hoist `<main>` into `Base.astro`

`Base.astro`'s `<body>` becomes:

```astro
<body>
  <a class="skip-link" href="#main"><Lang en={ui.skipToContent.en} ru={ui.skipToContent.ru} /></a>
  <Nav />
  <main id="main" tabindex="-1"><slot /></main>
  <Footer />
</body>
```

and each of the seven pages drops its own `<main>` wrapper, keeping its
children. This is the load-bearing choice: it puts `id="main"` and
`tabindex="-1"` on every page from one edit, keeps `checkMainLandmark`'s
"exactly one `<main>`" invariant true, and — critically — keeps
`test/approach.test.ts`'s `assert.doesNotMatch(approach, /tabindex/)` green,
because the `tabindex` now lives in the layout, not in `approach.astro`. The
existing `main { max-width: var(--content-max); margin-inline: auto }` rule
(site.css:45) matches unchanged.

### 2. Skip link

Placed before `<Nav />`, so it is the first focusable node in `<body>`.
Hidden with the same clip technique as `.visually-hidden` and revealed on
`:focus` (not `:focus-visible`, so any focus reveals it), with no `transition`
— `test/a11y.test.ts` forbids one. It reuses `--surface-elevated` /
`--surface-fg` / `--surface-line`, a pair `check-contrast.mjs` already proves,
so no new contrast pair is introduced. `min-block-size: 44px` goes on
`.skip-link:focus`, which is the selector added to `TARGET_SELECTORS`.

### 3. Toggle bar

`Nav.astro` wraps the two toggles:

```astro
<div class="toggle-bar">
  <LangToggle />
  <ThemeToggle />
</div>
```

with `.toggle-bar { display: flex; flex-wrap: wrap; gap: var(--mctl-space-4);
padding-block: var(--mctl-space-4); }`. Because `display: none` children do not
participate in flex layout, the bar has exactly two visible items at any time —
one language group and one theme group — separated by a real gap rather than a
whitespace text node, in either language. `.toggle-bar noscript { flex-basis:
100% }` keeps the two `<noscript>` paragraphs on their own line for a reader
with JavaScript disabled. `.toggle-group` keeps its own `inline-flex` and
`--mctl-space-2` internal gap untouched.

### 4. `aria-current` from `Astro.url.pathname`

`astro.config.mjs` sets `trailingSlash: 'always'`, so pathnames are `/`,
`/work/`, `/approach/`, `/colophon/`, `/colophon/journal/<id>/`,
`/colophon/adr/<id>/`. `Nav.astro` frontmatter gains:

```ts
const here = Astro.url.pathname.endsWith('/') ? Astro.url.pathname : `${Astro.url.pathname}/`;
const current = (href: string) =>
  here === href ? 'page' : href !== '/' && here.startsWith(href) ? 'true' : undefined;
```

and each anchor stays a literal element — `<a href="/approach/"
aria-current={current('/approach/')}>` — rather than being generated from an
array, because `test/approach.test.ts` matches the literal `href="/approach/"`
in `Nav.astro`'s source. Astro omits an attribute whose value is `undefined`,
so the 404 page emits none. `/` is excluded from the prefix branch, otherwise
every page would mark Home.

Styling: `.site-nav a[aria-current] { color: var(--accent); text-decoration:
underline; text-underline-offset: 0.25em; text-decoration-thickness: 2px; }`.
Attribute presence, so `page` and `true` both hit; colour **and** underline, so
colour is never the sole indicator; `--accent` over both surfaces is already
proven at the 4.5:1 text threshold by `check-contrast.mjs`'s content-link
pairs. The selector is scoped to `.site-nav` rather than the issue's bare
`nav a[aria-current]` so it cannot reach into the new breadcrumb `<nav>` or the
home page's `.ctas` `<nav>`.

### 5. Breadcrumb

A new `src/components/Breadcrumb.astro` takes `currentEn` / `currentRu` and
renders a `<nav class="breadcrumb">` with an `<ol>` of three items: `Home`
(link to `/`), `Colophon` (link to `/colophon/`), and the current entry as a
non-link `<span aria-current="page">`. The journal page passes
`entry.data.title.en` / `.ru`; the ADR page passes `ADR-${padAdrId(id)}` for
both languages (an identifier, untranslated). It is rendered as the first child
of the page body, above the `<h1>`. Separators are a CSS
`.breadcrumb li + li::before { content: '/' }` pseudo-element, so no screen
reader announces them and no extra markup carries a language.

### 6. Group roles and single-language names

CSS cannot switch an attribute value, so the name has to come from content the
existing `.l.en` / `.l.ru` mechanism can already toggle. Each toggle becomes:

```astro
<div class="toggle-group l en" role="group" aria-labelledby="lang-toggle-label"> … </div>
<div class="toggle-group l ru" role="group" aria-labelledby="lang-toggle-label"> … </div>
<span id="lang-toggle-label" class="visually-hidden"><Lang en={ui.langToggleLabel.en} ru={ui.langToggleLabel.ru} /></span>
```

and the theme toggle the same with `theme-toggle-label`. `Nav.astro`'s `<nav>`
swaps its bilingual `aria-label` for `aria-labelledby="nav-label"` pointing at
the same kind of span, and `index.astro`'s `.ctas` `<nav>` for
`aria-labelledby="ctas-label"` with the new `ctasLabel` copy. During accessible
name computation the referenced span is traversed and its `display: none` half
is skipped, so exactly one language reaches the name — the same behaviour
`Details.astro` already depends on for its `.visually-hidden` suffix, and it
keeps working when a reader flips the language without a reload. Each id is
rendered once per page (`Nav` and the `.ctas` block are both single-instance),
so ids stay unique. Both `.toggle-group` divs of a pair may safely reference one
id. Each added span is a full `<Lang>` pair, so the `class="l en"` /
`class="l ru"` parity count stays balanced.

### 7. Disclosure defaults and heading titles

`index.astro` passes `open` to the `Contact` block only; `approach.astro`
passes `open` to the `Gates` block only. `Details.astro` gains a boolean
`heading?: boolean` prop (default `false`) that wraps the summary text:

```astro
<summary>
  {heading ? <h2 class="block-title"><Lang en={summaryEn} ru={summaryRu} /></h2>
           : <Lang en={summaryEn} ru={summaryRu} />}{suffix…}
</summary>
```

`index.astro` passes the bare `heading` flag on all three blocks. It is a
**boolean**, not a numeric level, on purpose: `test/home.test.ts` and
`test/approach.test.ts` assert those templates contain no digit once `<h1>`…
`<h6>` tag names are stripped, and `heading={2}` would break that. `work.astro`
and `approach.astro` pass nothing, so `/work/`'s fourteen disclosures and the
approach summaries are untouched — both out of scope. `.block > summary h2
{ display: inline; font: inherit; margin: 0 }` keeps the native `display:
list-item` marker and the existing visual line while the heading semantics are
real.

### 8. Evidence

Three layers, matching how this repo already proves things:

- **Source tests** (`npm test`): extend `test/a11y.test.ts` with the
  `.toggle-bar` declarations, the `.site-nav a[aria-current]`
  colour-plus-underline rule and `.skip-link:focus` in `TARGET_SELECTORS`; add
  `test/nav.test.ts` for the `Astro.url.pathname` derivation, `role="group"`,
  `aria-labelledby` on both toggles and on the two `<nav>` landmarks, and the
  absence of any remaining slash-joined bilingual `aria-label` in
  `src/components/`, `src/layouts/` and `src/pages/index.astro`; extend
  `test/home.test.ts` / `test/approach.test.ts` for the `open` and `heading`
  props.
- **Built-output checks** (`scripts/check-dist.mjs`): a new
  `checkNavigationState(html, rel)` asserting `<main id="main" tabindex="-1">`,
  a `#main` skip link before the first `<nav`, the expected `aria-current`
  count inside `.site-nav`, and no `aria-label` containing both a Latin and a
  Cyrillic letter — with one named exemption for the `.table-scroll` region on
  `/colophon/`, which this cycle does not touch. Plus `<details open>` counted
  as exactly one on `dist/index.html` and `dist/approach/index.html`, and
  `<summary><h2` counted as exactly three on `dist/index.html`.
- **Checklist** (`docs/accessibility-checklist.md`): the heading-hierarchy row
  is rewritten for the new `<h2>` titles, and three rows are added — bypass
  blocks, current-page indication, group naming in the active language — each
  citing the file or script that backs it. A short "Re-walk log" line records
  that the checklist was re-walked for this issue and what changed.

## Alternatives

1. **Give each `.toggle-group` a per-language `aria-label` instead of
   `aria-labelledby`.** Free for `LangToggle`, whose two divs are already split
   by language. But `ThemeToggle`'s two divs are split by *theme*, so a
   per-language label needs the cross product — four divs, eight buttons,
   `t dark l en` through `t light l ru` — and the button text has to drop out
   of `<Lang>` to stay single-language. Twice the interactive markup and a
   second mechanism to maintain. Dropped: `aria-labelledby` into a
   `.visually-hidden` bilingual span is one mechanism for both groups and both
   `<nav>` landmarks, and it is the mechanism `Details.astro` already uses.

2. **Add `id="main" tabindex="-1"` to each page's own `<main>` instead of
   hoisting `<main>` into `Base.astro`.** Same number of files touched, but it
   puts `tabindex` inside `approach.astro`, which
   `test/approach.test.ts:48` forbids outright, so the test would have to be
   loosened — weakening a guard written to keep a `tabindex` override off the
   DevLoop diagram. It also leaves the invariant per-page: a future page could
   forget `id="main"` and silently break the skip link. Dropped.

3. **Mark the current page with a client-side script reading
   `location.pathname`.** Would survive future routing changes without a
   rebuild. Dropped outright: ADR-0002 and `AGENTS.md` allow exactly one inline
   script of at most 400 bytes, hash-pinned in the CSP, and
   `scripts/check-dist.mjs` fails the build on any `.js` under `dist/`.
   `Astro.url.pathname` is known at build time; there is nothing to defer.

4. **Open `Contact` and `Gates` with `<details open>` only above a width
   breakpoint, or open every block.** The issue is explicit that exactly one
   block per page opens and that this is "not licence to expand" the site, and
   CSS cannot set the `open` attribute anyway (`details[open]` is a state, not
   a style). Dropped.

5. **Style the current page with `font-weight: bold` instead of colour plus
   underline.** A weight change shifts the nav's layout and can push the header
   to a different wrap point at 360px, which acceptance criterion 1 cares
   about. Colour plus underline changes no metrics and satisfies "colour alone
   is not sufficient". Dropped.

## Platform impact

- **Migrations**: none. Static site, no database, no persisted state; the
  reader's `localStorage` keys (`lang`, `theme`) and the inline head script are
  untouched.
- **Backward compatibility**: no URL changes, no removed page, no changed
  `<title>`, `<meta name="description">`, canonical or sitemap entry.
  `scripts/check-dist.mjs`'s sitemap closure check is unaffected. The skip
  link's `#main` href is the first `#…` href on the site;
  `scripts/check-links.mjs` already classifies bare fragments as `fragment`
  and skips them, so the link check keeps passing — but the stale comment at
  `check-links.mjs:72` ("no `href="#..."` exists on the site") should be
  corrected in the same commit.
- **Resource impact**: zero new requests, zero new bytes under
  `public/assets/`. `dist/index.html` grows by roughly a few hundred bytes
  (skip link, four `.visually-hidden` label spans, three `<h2>` wrappers)
  against a 40960-byte cap that the page is comfortably under today; the
  existing check in `check-dist.mjs` is the guard.
- **Risks and mitigations**:
  - *`.l.en`/`.l.ru` parity drift* — every new string goes through `<Lang>`, so
    each addition is a balanced pair; `check-dist.mjs` fails the build if not.
  - *A `<h2>` inside `<summary>` breaking the disclosure marker or spacing* —
    mitigated by `display: inline; font: inherit; margin: 0`, and confirmed
    visually as a reviewer step.
  - *Accessible-name computation skipping the hidden half differently across
    engines* — the site already depends on this behaviour in `Details.astro`;
    the screen-reader sweep in the checklist stays a reviewer step.
  - *The header wrapping badly at 360px in Russian* — the only genuinely
    visual criterion. The CSS rule is the mechanical gate; the 360px check in
    both languages, with the toggles actually operable, is a named reviewer
    step per `AGENTS.md`.
  - *Forgetting `npm run vendor`* — `public/styles/site.css` is gitignored and
    regenerated by `prebuild`, so a stale copy cannot be committed.
- **Deployment**: ordinary release-please tag plus the existing
  `release-deploy` dispatch; no mctl operation beyond the normal deploy, and
  no gitops values edited by hand.
