# Design: issue-55-q2-content-link-contrast-footer-and-colo

## Current state

### Stylesheet and cascade

`src/styles/site.css` is the only site-authored stylesheet. `npm run vendor`
(`scripts/vendor-assets.mjs`, `SITE_CSS_SRC` at line 63) copies it to
`public/styles/site.css`, which is gitignored (`.gitignore`, last entry) and
served from `public/` so Astro never inlines it —
`astro.config.mjs` sets `build.inlineStylesheets: 'never'` because the CSP
carries `style-src 'self'` with no `'unsafe-inline'`.
`src/layouts/Base.astro` links, in order: `mctl.css`, `global.css`,
`prose.css`, `fonts.css`, then `/styles/site.css`.

`site.css` contains no `a` rule other than these three:

- `.site-nav a { color: var(--surface-fg); text-decoration: none }` and
  `.site-nav a:hover { color: var(--accent) }` (lines 66-75)
- `.site-footer a { color: inherit }` (line ~110)
- `.cta { color: var(--surface-fg) }` and `.cta:hover { color: var(--accent); border-color: var(--accent) }` (lines ~170-183)
- `.project-links a { color: var(--surface-fg) }` (no hover rule)

There is no `main a` rule, so a class-less `<a>` inside `<main>` falls through
to the user-agent stylesheet: `#0000EE` unvisited (2.10:1 on
`--mctl-surface-dark-bg: #0a0b0d`), `#551A8B` visited (1.79:1).

`--accent` and `--accent-highlight` are semantic tokens declared in
`public/assets/mctl/mctl.css` on `:root` (line 341-342, the dark default) and on
`[data-theme='light']` (line 391-392); both selectors are specificity (0,1,0).
They resolve to the raw tokens `--mctl-accent-terracotta-dark-primary: #e25a3c`
/ `-highlight: #ff8a6a` (lines 114-115) and
`--mctl-accent-terracotta-light-primary: #b83d28` / `-highlight: #9a3220`
(lines 118-119). `src/layouts/Base.astro` never writes `data-accent`, so the
`[data-theme][data-accent]` blocks further down mctl.css never match.

The `@media print` block at the end of `site.css` already redefines
`--surface-bg/-fg/-fg-muted/-line` on `:root`. It works because `site.css` is
linked after `mctl.css` and the selectors tie on specificity, so the later
declaration wins — the same mechanism a print `--accent` override will use. The
print block does not currently touch `--accent`, so `--accent` in print stays
the dark `#e25a3c`: 3.64:1 on white.

`Nav` and `Footer` are rendered outside `<main>`, as direct children of `<body>`
around the `<slot />` (`src/layouts/Base.astro`), so a `main a` rule cannot
reach `.site-nav a` or `.site-footer a`. `.cta` (`src/pages/index.astro:34-35`)
and `.project-links a` (`src/components/ProjectCard.astro`) are inside `<main>`
and can be reached.

`public/assets/mctl/prose.css:54` has `.mctl-prose a { color: var(--accent) }`
and line 60 `.mctl-prose a:hover { … }`. Only
`src/pages/colophon/adr/[...slug].astro` uses `.mctl-prose`, on the `<div>`
wrapping `<Content />`, not on `<main>`.

### Class-less content links today

- `src/pages/index.astro:57-58` — Contact block: `github.com/mctlhq` and a
  `mailto:`.
- `src/pages/colophon/index.astro` — the ADR table's title links.
- `src/components/CycleTable.astro` — issue/PR links in the cycle table.
- `src/pages/colophon/journal/[...slug].astro` — the `journal-meta` issue and PR
  links, and "Back to the colophon".
- `src/pages/colophon/adr/[...slug].astro` — the superseded-ADR link and "Back
  to the colophon".
- `src/pages/404.astro:15` — "Back to home".

### Footer

`src/components/Footer.astro` renders three items: an anchor to
`https://github.com/mctlhq` labelled `ui.footerGithubLabel`, an anchor to
`/colophon/`, and a `<span>` holding `<Lang …/>` then a literal `:` then
`<span data-release>{pkg.version}</span>`. `pkg` is
`import pkg from '../../package.json'` — `0.1.11` today, bumped by
release-please. `scripts/check-dist.mjs` asserts the built markup matches
`/data-release>([^<]*)</` against `package.json`'s version on **every** page.
`site.css` gives `.site-footer a { color: inherit }` plus a tap-target rule
setting `display: inline-flex; min-block-size: 44px` on `.site-footer a`.

### Colophon chain list

`src/pages/colophon/index.astro` renders `ui.colophonChainItems.en` and `.ru`
as `<ul class="l en">` / `<ul class="l ru" lang="ru">` with
`{items.map((item) => <li>{item}</li>)}` — plain escaped text.
`test/ui.test.ts` asserts every `ui` entry is a string or an array of non-empty
strings and that the `en` and `ru` arrays are the same length, so markup cannot
be smuggled into the dictionary.

### Scripts and CI

`scripts/check-contrast.mjs` parses the raw `--mctl-*` hex tokens out of
`public/assets/mctl/mctl.css`, maps semantic names per theme
(`SEMANTIC_TOKENS`), walks a fixed `PAIRS` list, computes WCAG relative
luminance, and exits non-zero on any pair below its threshold. It never reads
`site.css`, and its entry point is a bare top-level `await main()` with no
guard. It runs from `npm test`.

`scripts/check-dist.mjs` walks `dist/` post-build and enforces no `.js`,
`.l.en`/`.l.ru` parity, the 40 KB `index.html` cap, the approach-page SVG
criteria, the colophon criteria, `data-release` parity and sitemap closure. It
runs from the `Dockerfile` (`RUN npm run build && node scripts/check-dist.mjs`),
not from `npm test` — `prebuild` is `npm run vendor && npm test`, so `dist/`
does not exist when `npm test` runs. It reads `site` out of `astro.config.mjs`
via a `siteOrigin()` helper.

`.github/workflows/build.yml` has a `test` job (`npm ci`, `npm test`) and a
`build` job that builds the Docker image and runs
`scripts/check-headers.mjs` against the running container. Nothing in CI walks
`dist/` for links. `AGENTS.md` explicitly permits the implementer to edit
`build.yml` as long as the change only makes the pre-merge gate stricter.

`package.json`'s `test` script names every test file explicitly; a new test file
that is not added to that list never runs.

## Proposed solution

Four independent changes plus their gates. Nothing in the four touches the
others' files except `package.json` (test list) and `build.yml`.

### 1. Content link colour — `src/styles/site.css`

Add one content-link block and two pins, placed after the `.project-links`
rules so all of them are in one reviewable region:

```css
/* Content links: any <a> inside <main> that carries no component class of its
 * own. The UA default (#0000EE / visited #551A8B) is 2.10:1 / 1.79:1 on the
 * dark surface; --accent measures 5.40:1 and 5.19:1 dark, 4.81:1 and 5.11:1
 * light. :visited is pinned to the same colour so #551A8B never renders. */
main a {
  color: var(--accent);
}
main a:visited:not(:hover) {
  color: var(--accent);
}
main a:hover {
  color: var(--accent-highlight);
}

/* Pins. main a:hover (0,1,2) outranks .cta (0,1,0) only on the element count,
 * and main a:visited:not(:hover) (0,2,2) outranks both .cta:visited (0,2,0)
 * and .project-links a:visited (0,2,1). :visited:not(:hover) keeps each pin
 * above the content rules AND out of the way of its own :hover rule, so the
 * result does not depend on source order. */
.cta:visited:not(:hover) {
  color: var(--surface-fg);
}
.project-links a:hover,
.project-links a:visited:not(:hover) {
  color: var(--surface-fg);
}
```

and one line inside the existing `@media print` `:root` block:

```css
  /* --accent resolves to the dark-theme #e25a3c here, 3.64:1 on the forced
   * white background. The light-theme value measures 5.62:1. */
  --accent: #b83d28;
```

Specificity ledger, which is the whole argument:

| selector | a,b,c | beats |
| --- | --- | --- |
| `main a` | 0,0,2 | UA default only |
| `main a:hover` | 0,1,2 | `.project-links a` (0,1,1), `.cta` (0,1,0) |
| `main a:visited:not(:hover)` | 0,2,2 | `.cta:visited` (0,2,0), `.project-links a:visited` (0,2,1) |
| `.cta:hover` (existing) | 0,2,0 | `main a:hover` (0,1,2) |
| `.cta:visited:not(:hover)` (new) | 0,3,0 | `main a:visited:not(:hover)` (0,2,2) |
| `.project-links a:hover` (new) | 0,2,1 | `main a:hover` (0,1,2) |
| `.project-links a:visited:not(:hover)` (new) | 0,3,1 | `main a:visited:not(:hover)` (0,2,2) |

`:not(:hover)` contributes the specificity of its argument, which is why the
pins land at (0,3,0) and (0,3,1) and why they cannot be cancelled by moving a
rule. No pin is added for `.site-nav a` or `.site-footer a`: both render outside
`<main>` (`src/layouts/Base.astro`), so `main a` never matches them. That fact
is asserted by a test instead of by dead CSS. No pin is added for
`.mctl-prose a` either: its hover rule (`prose.css:60`, specificity 0,2,1)
already outranks `main a:hover`.

### 2. Cascade gate — `test/link-cascade.test.ts` (new)

The issue is explicit that "a test must exercise the interaction between the
pins and the hover rules, not merely assert that each rule exists". The test
therefore implements a miniature cascade resolver over the real file:

1. Strip comments from `src/styles/site.css`, strip the `@media print` block,
   and parse the remaining top-level rules into `{ selectors[], declarations,
   sourceIndex }`.
2. For each selector compute `(a, b, c)` with `:not(x)` counted as `x`.
3. Model three elements —
   `{ inMain: true, classes: [] }`, `{ inMain: true, classes: ['cta'] }`,
   `{ inMain: true, ancestorClasses: ['project-links'] }` — and match the small,
   closed set of selector shapes that `site.css` actually uses
   (`main a`, `.cta`, `.project-links a`, each optionally suffixed with
   `:hover`, `:visited`, `:visited:not(:hover)`).
4. For each of the four states (`normal`, `visited`, `hover`,
   `visited+hover`) pick the winning `color` by specificity then source order,
   and assert the twelve expected values:

| element | normal | visited | hover | visited+hover |
| --- | --- | --- | --- | --- |
| class-less `<a>` in `<main>` | `var(--accent)` | `var(--accent)` | `var(--accent-highlight)` | `var(--accent-highlight)` |
| `.cta` | `var(--surface-fg)` | `var(--surface-fg)` | `var(--accent)` | `var(--accent)` |
| `.project-links a` | `var(--surface-fg)` | `var(--surface-fg)` | `var(--surface-fg)` | `var(--surface-fg)` |

Because the resolver ranks by specificity and *then* source order, replacing a
pin with a bare `:visited` makes the visited+hover cell flip and the test goes
red — which is the regression the closed PR's reviewer was pointing at.

A second test in the same file asserts, against `src/layouts/Base.astro`, that
`<Nav />` and `<Footer />` appear outside the element that receives the page
`<slot />`, i.e. that no page's nav or footer can be inside `<main>`.

### 3. Contrast gate — `scripts/check-contrast.mjs`

Refactor the file into (a) pure functions and (b) a thin `main()`:

- Keep `parseTokens`, `relativeLuminance`, `contrastRatio`, `SEMANTIC_TOKENS`,
  `PAIRS`, `EXEMPTIONS` as they are.
- Add `parseContentLinkColours(siteCssText)` returning
  `{ normal, visited, hover, print }`, each either `{ kind: 'var', name }`
  (e.g. `--accent`) or `{ kind: 'hex', value }` (e.g. `#0000EE`) or `null` when
  the rule is absent. The parser looks for the `main a`, `main a:visited…` and
  `main a:hover` rules outside `@media print`, and for an `--accent`
  declaration inside the `@media print` block.
- Add `contentLinkProblems({ siteCssText, tokens })`, which for each theme
  resolves each state's colour (a `var(--accent)` / `var(--accent-highlight)`
  goes through the same semantic map the existing pairs use; a hex is taken
  literally; a `null` normal rule is itself a problem) and checks it against
  `surface-bg` and `surface-elevated` at 4.5:1, plus the print colour — the
  print override if present, otherwise the dark `--accent`, which is exactly
  what the browser would resolve — against `#fff` at 4.5:1.
- `main()` reads `public/assets/mctl/mctl.css` and `src/styles/site.css`, runs
  both the existing `PAIRS` loop and `contentLinkProblems`, prints the same
  report style, exits non-zero on any problem.
- Guard the entry point:

```js
if (import.meta.main === undefined) {
  console.error('check-contrast: this Node build does not expose import.meta.main (Node >= 24.2 required); refusing to run rather than skipping the check');
  process.exit(1);
}
if (import.meta.main) {
  await main();
}
```

This is fail-closed by construction: an engine that cannot evaluate the guard
exits 1 instead of loading the module and doing nothing. `import.meta.url`
versus `process.argv[1]` is not used — it compares a URL against a path that a
symlinked checkout resolves differently, so it fails open.

Because `contentLinkProblems` is pure and takes the stylesheet text as an
argument, `test/check-contrast.test.ts` can prove the three required mutations
in-process, with no subprocess and no temp files: take the real `site.css` text,
apply a string substitution (`var(--accent)` → `#0000EE` in the `main a` rule;
`var(--accent)` → `#551A8B` in the `:visited` rule; delete the `main a` block),
and assert a non-empty problem list each time — and an empty one for the
unmutated text.

### 4. Footer — `src/components/Footer.astro`

```astro
---
import Lang from '../i18n/Lang.astro';
import { ui } from '../i18n/ui';
import pkg from '../../package.json';

// package.json's version -- bumped by release-please on every release -- is
// the release source behind the data-release hook and the tag URL.
// release-please-config.json sets include-v-in-tag:false and
// include-component-in-tag:false, so the tag path is the bare semver.
const releaseTagUrl = `https://github.com/mctlhq/portfolio/releases/tag/${pkg.version}`;
---

<footer class="site-footer">
  <a href="https://github.com/mctlhq/portfolio">
    <Lang en={ui.footerGithubLabel.en} ru={ui.footerGithubLabel.ru} />
  </a>
  <a href="/colophon/">
    <Lang en={ui.footerColophonLabel.en} ru={ui.footerColophonLabel.ru} />
  </a>
  <span><Lang en={ui.footerReleaseLabel.en} ru={ui.footerReleaseLabel.ru} />{' '}<a href={releaseTagUrl} data-release>{pkg.version}</a></span>
</footer>
```

Three deliberate details. The `{' '}` expression and the single-line `<span>`
make the single space an explicit character rather than collapsed template
indentation, so the test can assert it. `data-release` stays the **last**
attribute on the version element so `check-dist.mjs`'s
`/data-release>([^<]*)</` still matches — moving it before `href` would break a
gate that already passes. And the version element becomes an `<a>`, which the
existing `.site-footer a` rules now also style: `color: inherit` (unchanged
colour) and the 44px tap-target rule (the other two footer links already carry
it, so the row stays visually consistent).

A new `test/footer.test.ts` asserts against the source: the template contains no
`>:` or `}:` colon between the label and the version; the `href` is built from
`pkg.version` and contains no literal semver (`assert.doesNotMatch(source,
/\d+\.\d+\.\d+/)`); the GitHub anchor is `https://github.com/mctlhq/portfolio`
exactly. A complementary assertion in `scripts/check-dist.mjs` checks the
**built** markup on every page: the footer release block matches
`Release</span><span class="l ru" lang="ru">Релиз</span> <a href="https://github.com/mctlhq/portfolio/releases/tag/<version>" data-release><version></a>`
with `<version>` read from `package.json`. Built-markup assertions belong in
`check-dist.mjs` for the same reason the hero-name check does: `npm test` runs
before `astro build`.

### 5. Colophon chain links — `src/lib/chain.ts` (new) + `colophon/index.astro`

`ui.ts` must keep plain strings (`test/ui.test.ts`), so the linkification is a
render-time transform:

```ts
// src/lib/chain.ts
export interface ChainSegment { text: string; href?: string }

// Longest text first so a future prefix relationship cannot mis-split.
export const CHAIN_LINKS = [
  { text: 'github.com/mctlhq/portfolio', href: 'https://github.com/mctlhq/portfolio' },
  { text: 'ghcr.io/mctlhq/portfolio', href: 'https://github.com/mctlhq/portfolio/packages' },
] as const;

export function chainSegments(item: string): ChainSegment[];
```

`chainSegments` scans left to right, at each position taking the earliest match
(ties broken by longest `text`), emitting the skipped prefix as a plain segment
and the match as a linked one. Its invariant —
`chainSegments(item).map((s) => s.text).join('') === item` — is asserted in
`test/chain.test.ts` for every item of `ui.colophonChainItems.en` and `.ru`,
which is precisely "leaving every other character unchanged". The same test
asserts each language yields exactly one `github.com/mctlhq/portfolio` link and
one `ghcr.io/mctlhq/portfolio` link with the stated hrefs.

The page renders:

```astro
<li>{chainSegments(item).map((seg) => (seg.href ? <a href={seg.href}>{seg.text}</a> : seg.text))}</li>
```

Astro escapes `seg.text`, so no `set:html` and no injection surface. The list
items stay inside `<main>`, so the new anchors pick up the `main a` colour from
change 1. `.l.en`/`.l.ru` parity is untouched: no `<Lang>` is added or removed.

### 6. Internal link check — `scripts/check-links.mjs` (new)

Structure mirrors `check-dist.mjs` (regex extraction, no dependency, pure
helpers plus a `main()`), and exports its helpers so the test can drive it:

- `siteOrigin()` — reads `site` from `astro.config.mjs` with the same regex
  `check-dist.mjs` uses, so the config stays the single source of truth.
- `collectHrefs(html)` — every `href="…"` on an `<a …>` and on a
  `<link rel="canonical" …>`, HTML-entity-decoded (`&amp;` at minimum).
- `classifyHref(href, origin)` → `{ kind: 'internal', pathname }` |
  `{ kind: 'skipped', reason: 'mailto' | 'off-origin' | 'other-scheme' }` |
  `{ kind: 'fragment' }`. Absolute `http(s)` URLs are parsed with `new URL` and
  classified by `url.origin === origin`; anything root-relative or relative is
  internal; `mailto:` and any other scheme is skipped.
- `resolveInternal(pathname, distDir)` → `{ ok, candidates[] }`. Query and
  fragment are stripped first. Trailing slash → `<dist><path>index.html`. A
  path with a file extension → `<dist><path>`. Otherwise both
  `<dist><path>/index.html` and `<dist><path>` are tried, and both are named in
  the failure.
- `run({ distDir, origin })` — walks `dist/**/*.html`, derives each page's own
  pathname from its location (so relative and fragment hrefs resolve against
  it), classifies, resolves, and returns
  `{ problems[], checked, pages, skipped: Map<href, count> }`.
- `main()` prints `check-links: <pages> pages, <checked> internal hrefs
  resolved, <skipped> skipped`, then the skipped hrefs one per line with their
  counts, then each problem, exiting 1 if `problems.length > 0`. The skipped
  block prints on success too — "nothing skipped may be counted as passing"
  means the reader sees the list either way.
- The same fail-closed `import.meta.main` guard as `check-contrast.mjs`.

There is no `fetch`, no `node:http`/`https`/`net` import, no timer, no retry, no
status code anywhere in the file. `test/links.test.ts` proves it two ways: a
static scan of the source for those identifiers, and a dynamic run of
`run({ distDir })` over a temporary fixture tree built with `mkdtemp`, with
`globalThis.fetch` swapped for a counting stub that throws. The fixture carries
`index.html` and `colophon/index.html` and exercises: a working root-relative
href, a working same-origin absolute href with a `#fragment`, a working
same-origin absolute href with no trailing slash, a broken internal href
(asserted to appear in `problems` naming both the href and the expected file), a
`mailto:` and an off-origin `https://github.com/…` (both asserted present in
`skipped` and absent from `checked`).

### 7. CI wiring — `.github/workflows/build.yml`

In the `test` job, replace `- run: npm test` with:

```yaml
      # `prebuild` is `npm run vendor && npm test`, so this is a strict
      # superset of the previous `npm test` step, and it produces the dist/
      # tree the link check needs.
      - run: npm run build

      - run: node scripts/check-links.mjs
```

This only tightens the gate, which is what `AGENTS.md` permits for this file.
`npm run vendor` already runs in CI today inside the Docker build and falls back
to the committed tree if the network step fails, so no new network dependency is
introduced. `scripts/check-dist.mjs` is deliberately **not** added here: it
already runs in the `Dockerfile`, and duplicating it would double a slow check
for no new signal.

### 8. Docs — `docs/link-check.md` (new), `docs/accessibility-checklist.md`

`docs/link-check.md` follows the house style of `docs/hardening-notes.md`: what
the check proves (every `<a>` and canonical href in the built site that points
at this origin resolves to a real file under `dist/`, with
`trailingSlash: 'always'` semantics; same-origin absolutes are resolved by
origin comparison, not byte equality), what it deliberately does not prove (it
says nothing about whether any third-party URL is reachable; nothing about
fragment targets existing; nothing about nginx redirect behaviour; nothing about
link text), how to run it locally (`npm run build && node
scripts/check-links.mjs`), and the rationale for external checking being out of
scope — copied from the issue's reasoning about rate limits, and with **no**
dated table of third-party URL statuses, since a snapshot of someone else's
uptime is not evidence about this repository.

The "Contrast in both themes" row of `docs/accessibility-checklist.md` currently
claims "All fourteen pairs clear their threshold" and names the tightest pair.
After this change the script checks the content-link states too, so that row is
updated to state the new count and the new tightest ratio, otherwise a committed
document asserts coverage that no longer matches the script.

## Alternatives

1. **Apply `.mctl-prose` to `<main>`.** The rule
   `.mctl-prose a { color: var(--accent) }` already exists at
   `public/assets/mctl/prose.css:54`, so this is one class on one element.
   Dropped: the class also styles `h1`–`h4`, `p`, `ul`, `ol`, `em`, `code`,
   `pre`, `blockquote` and the lede, so every page's typography would change —
   a redesign smuggled in as an accessibility fix. The issue rules it out
   explicitly.

2. **Style `a:not([class])` globally instead of scoping to `main`.** Tempting,
   because "content link" really means "link with no component class". Dropped:
   the anchors in `Nav.astro`, `Footer.astro` and `ProjectCard.astro` carry no
   class of their own either — the class is on the parent (`.site-nav`,
   `.site-footer`, `.project-links`) — so the selector would recolour exactly
   the four things the issue says to leave alone, and every pin would have to be
   re-derived against a higher-specificity base.

3. **Pin `:visited` without `:not(:hover)` and fix the order.** Dropped, and
   this is the failure the superseded cycle documented: `.cta:hover` and
   `.cta:visited` are both (0,2,0), so a `:visited` pin written after `:hover`
   silently cancels the hover colour on both home-page CTAs — which point at
   `/work/` and `/colophon/` and are therefore visited for any returning
   reader — and `.project-links a:visited` (0,2,1) loses to `main a:hover`
   (0,1,2) at *any* order, which reordering cannot fix.

4. **Put the link check in the `Dockerfile` next to `check-dist.mjs`.** It would
   run on the same `dist/` with no extra build. Dropped: the issue asks for
   `build.yml`, a failure inside a Docker layer gives worse logs and interacts
   with the buildx GHA cache, and the `test` job already has Node 24 and a
   checkout, so the marginal cost is one `npm run build`.

5. **Use an HTML parser (`linkedom`, `cheerio`) or an off-the-shelf link
   checker (`lychee`, `linkinator`).** Dropped: the repo ships two runtime
   dependencies and does all built-output analysis with regexes in
   `scripts/*.mjs`; every off-the-shelf checker is built around fetching, which
   is the requirement being removed. Adding a dev dependency to *not* use its
   main feature is the wrong trade.

6. **Store the colophon links as HTML in `src/i18n/ui.ts` and render with
   `set:html`.** Fewer moving parts at the page. Dropped: `test/ui.test.ts`
   asserts every dictionary entry is a plain string or array of plain strings,
   and putting markup in the one file that holds all user-facing copy turns
   every future copy edit into an HTML edit, with `set:html` as a standing
   injection-shaped pattern.

## Platform impact

- **Migrations / data.** None. No schema, no content collection, no metrics
  file is touched.
- **Backward compatibility.** Purely additive at the CSS level: three new rules
  plus two pins plus one custom-property override inside an existing
  `@media print` block. The footer and colophon changes alter markup a reader
  sees but no route, no URL and no `data-*` hook that another gate depends on;
  `data-release` keeps its position and value.
- **Build and CI.** The `test` job gains an `astro build` (seconds on this site)
  and one script run. The Docker build is unchanged. `dist/` remains free of
  `.js` — `check-links.mjs` is a build-time Node script, never shipped.
- **Runtime and resource impact.** Zero. No new asset, no new request, no
  client-side script; `site.css` grows by roughly 20 lines.
- **Risk: `import.meta.main` on an older Node.** The builder image is
  `node:24-alpine` pinned by digest and CI pins `node-version: 24`;
  `import.meta.main` needs >= 24.2. Mitigation: the guard is fail-closed — an
  engine without it exits 1 with a named diagnostic, so the failure mode is a
  loud red build, never a green one that checked nothing. If it does fire, the
  fix is re-pinning the base image, which is out of scope here. Side effect: a
  contributor on Node 22 sees `npm test` refuse rather than silently skip.
- **Risk: the cascade test becomes a second CSS parser.** Mitigation: it parses
  only the closed set of selector shapes `site.css` actually contains and fails
  loudly (`assert.ok(found, …)`) if a selector it does not understand carries a
  `color` declaration for one of the three modelled elements, so an unparsed
  rule cannot be silently ignored.
- **Risk: `main a` reaching a link the issue wants left alone.** Mitigation: the
  specificity ledger above is encoded as the twelve-cell cascade table, and the
  structural test on `Base.astro` fails if nav or footer ever move inside
  `<main>`.
- **Risk: the footer built-markup assertion is brittle.** It hard-codes the
  `<Lang>` output shape. Mitigation: `src/i18n/Lang.astro` is a four-line
  component already asserted character for character by `test/a11y.test.ts`, so
  the two assertions fail together and point at the same file.
- **Security.** No new inline style or script, so the CSP hash set
  (`scripts/csp-hash.mjs`) and `security-headers.conf` are untouched. All new
  anchors render escaped text; no `set:html` is introduced. Zero third-party
  browser requests is preserved — the new links are user-initiated navigations,
  not subresources.
