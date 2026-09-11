# Design: issue-8-p6-approach-page-with-the-devloop-cycle

## Current state

**Routing and layout.** `astro.config.mjs` sets `output: 'static'`,
`trailingSlash: 'always'` and `build.inlineStylesheets: 'never'`. Pages are
file-routed from `src/pages/`: `index.astro`, `work.astro`, `404.astro` and a
dev-only `dev/[check].astro` whose `getStaticPaths` returns nothing outside
`astro dev`. There is no `approach.astro`. Every page wraps its content in
`src/layouts/Base.astro`, which authors `<html lang="en" data-lang="en"
data-theme="dark">`, one 400-byte inline `<script>` for persisted language and
theme, and five stylesheet links — three vendored `@mctlhq/css` files, the
generated `fonts.css`, and `/styles/site.css`.

**Navigation.** `src/components/Nav.astro` renders three links: `/`, `/work/`
and `/#approach`. The last is dangling — `test/home.test.ts` asserts
`id="approach"` no longer appears in `src/pages/index.astro`.

**Bilingual mechanism.** `src/i18n/Lang.astro` emits
`<span class="l en">{en}</span><span class="l ru" lang="ru">{ru}</span>`.
`src/styles/site.css` hides one side with `:root[data-lang='en'] .l.ru
{ display: none }` and its mirror. Pages that need a non-`<span>` element
write the pair by hand — `src/pages/index.astro` does exactly that for the two
`<ul class="l en">` / `<ul class="l ru" lang="ru">` lists inside each
`<Details>`. Strings live in `src/i18n/ui.ts` as `{ en, ru }` entries;
`test/ui.test.ts` walks every entry and requires both sides to be present,
non-empty, and the same kind (string vs array of the same length). Where only
one string is possible (an `aria-label`, the page `<title>`),
`src/components/Nav.astro` concatenates: `${ui.navLabel.en} / ${ui.navLabel.ru}`.

**Metrics.** `src/data/metrics.json` is the single numeric source, currently
all `null` with `"method": "placeholder"`. `src/lib/metrics.ts` is a
deliberately import-free module exporting `formatStat` (null renders the em
dash `—`, `0` still renders `0`), `snapshotDate` and `metricProblems`.
`src/components/Stat.astro` renders `<span class="stat-value"
data-stat>{formatStat(value)}</span>` plus a `<Lang>` label.
`src/pages/index.astro` renders four `<Stat>`s inside `<section class="stats">`
with a `.stat-caption` line built from `ui.statCaptionPrefix` and
`snapshotDate(metrics.generated_at)`. `test/home.test.ts` enforces the
provenance mechanically: exactly four `<Stat` tags, every `value=` expression
rooted at `metrics.sources.`, and — after slicing off the frontmatter and
stripping `<h1>`…`<h6>` tag names — no digit anywhere in the template.

**Collapsible blocks.** `src/components/Details.astro` is a thin
`<details class="block">` with a bilingual `<summary>` and a slot.

**Styling.** There is no `<style>` element anywhere under `src/` — every rule
lives in `src/styles/site.css`, which `scripts/vendor-assets.mjs` copies to
`public/styles/site.css` on every `npm run vendor` (itself part of `prebuild`).
`nginx.conf` sends `style-src 'self'` with no `'unsafe-inline'`, which is why
`astro.config.mjs` forbids inlined stylesheets. Design tokens come from
`public/assets/mctl/mctl.css` (`@mctlhq/css` 0.5.0): `--surface-bg`,
`--surface-fg` (`#0a0b0d`/`#e6e7e9` dark, `#f1ede4`/`#15181d` light),
`--surface-line`, `--surface-elevated` and `--accent` (terracotta `#e25a3c`
dark, `#b83d28` light), re-bound under `[data-theme='light']`.

**Build gates.** `package.json` runs `prebuild: npm run vendor && npm test`,
so `npm test` (plain `node --test` over seven source-level test files) always
runs *before* `astro build` and cannot see `dist/`. The post-build gate is
`scripts/check-dist.mjs`, invoked from the `Dockerfile`
(`npm run build && node scripts/check-dist.mjs && node scripts/csp-hash.mjs`).
Its header says it exists precisely because `prebuild` is too early to inspect
`dist/`. It walks `dist/`, fails on any `.js` file, fails on any HTML file
whose `class="l en"` and `class="l ru"` counts differ, and fails if
`dist/index.html` reaches 40 KB. `.github/workflows/build.yml` runs `npm test`
in one job and a full Docker build (hence `check-dist`) in another.

**Conventions.** `AGENTS.md` fixes the rules this design has to obey: static
output, no client bundles (ADR-0002), zero third-party requests, every number
from the snapshot, every string bilingual, `Instrument Serif`
(`--font-editorial`) never used for a translated string, one journal entry per
cycle, and — decisive for how criteria are verified — "work that genuinely
needs a human (a screen reader, a Lighthouse run, a browser capture) is a
reviewer step named as such, never an acceptance criterion", with machine
evidence living "in a committed file or a script that runs in `npm test`".

## Proposed solution

Five files change, one of them new-and-central.

### 1. `src/components/CycleDiagram.astro` (new)

A props-less component that renders **two sibling top-level `<svg>` elements**,
the wide and the narrow layout of the same ten-node loop, plus nothing else.
It imports only `ui` from `../i18n/ui` — never `metrics.json`, never
`Stat.astro` (requirements criterion 11), so the coordinate digits it
necessarily contains can never be confused with a typed metric.

Structure of each variant (`V` is `wide` or `narrow`):

```
<svg class={`cycle-svg cycle-${V}`} viewBox="…" role="img"
     aria-labelledby={`cycle-${V}-title cycle-${V}-desc`}
     xmlns="http://www.w3.org/2000/svg">
  <title id={`cycle-${V}-title`}>{titleBoth}</title>
  <desc id={`cycle-${V}-desc`}>{descBoth}</desc>
  <defs><marker id={`cycle-${V}-arrow`} …><path d="…" fill="currentColor"/></marker></defs>
  <g class="cycle-edges">…<path … marker-end={`url(#cycle-${V}-arrow)`}/>…</g>
  {NODES.map((node, i) => (
    <g class={node.gate ? 'cycle-node is-gate' : 'cycle-node'}>
      <rect x={…} y={…} width={…} height={…} rx="8"/>
      <text class="l en" x={…} y={…}>{ui.cycleNodes.en[i]}</text>
      <text class="l ru" lang="ru" x={…} y={…}>{ui.cycleNodes.ru[i]}</text>
    </g>
  ))}
</svg>
```

Decisions inside that shape:

- **Labels come from `ui.cycleNodes`**, a `{ en: string[10], ru: string[10] }`
  entry, so `test/ui.test.ts`'s array branch already enforces equal lengths and
  non-empty items. Geometry lives in a local `const NODES` array in the
  component (one `{ x, y, gate }` per index, per variant), because coordinates
  are layout, not copy.
- **`<title>`/`<desc>` carry one `EN / RU` string each.** An SVG `<title>` is
  never rendered, so a `display:none` `.l.ru` child inside it would still be
  concatenated into the accessible name by every engine; the slash form is the
  deterministic option and is already the repo's convention for one-string
  slots (`Nav.astro`'s `aria-label`). The strings live in `ui.cycleTitle` and
  `ui.cycleDesc` as normal `{ en, ru }` pairs and are joined in the component's
  frontmatter with `${…en} / ${…ru}`.
- **Ids are variant-suffixed** (`cycle-wide-title`, `cycle-narrow-title`, …)
  so duplicating the diagram does not duplicate an id, and each
  `aria-labelledby` resolves within its own `<svg>`.
- **No nested `<svg>`.** Both roots are siblings. This keeps the post-build
  gate's `<svg …>…</svg>` slicing unambiguous and avoids the marker-reference
  and id-scoping problems nesting brings.
- **Arrowheads are `<marker>` elements** inside each variant's own `<defs>`,
  filled `currentColor`. A marker referenced across `<svg>` roots is not
  reliable, hence one per variant.
- **Gates.** `Approve` (index 3) and `Review gate` (index 5) get
  `class="cycle-node is-gate"`; CSS gives that rect
  `stroke: var(--accent); stroke-width: 2; stroke-dasharray: 5 4;` against the
  plain nodes' `stroke: var(--surface-line-strong); stroke-width: 1;`. Dash
  plus weight means the distinction survives monochrome printing and is not
  colour-only. The meaning is stated in `<desc>` and expanded by the `Gates`
  block directly below the figure.
- **Geometry.** Wide variant `viewBox="0 0 740 300"`: nodes 1–5 left-to-right
  across the top row, 6–10 right-to-left across the bottom row, a connector
  down the right margin from `Implement` to `Review gate`, and a return
  connector up the left margin from `Monitor` to `Issue` — a visually closed
  loop. Narrow variant `viewBox="0 0 320 700"`: one column of ten nodes with a
  return path routed through the left gutter back to `Issue`; 320 satisfies the
  "at most 360" rule of criterion 20 with room for the page's
  `--mctl-space-4` body padding. Node rects are at least 44 units tall and
  label `font-size` is 14 px in the narrow variant, 13 px in the wide one.
  These numbers are a starting layout, not a contract; the implementer may
  adjust them as long as criteria 12–21 still hold.

Estimated weight: twenty node groups (rect plus two `<text>`) at roughly
200 bytes each, plus edges, markers, title and desc, lands near 7 KB for both
variants together — inside the 12 KB cap of criterion 14, which the post-build
gate measures rather than trusts.

### 2. `src/pages/approach.astro` (new)

Mirrors `src/pages/index.astro` in shape:

```
<Base title={ui.approachPageTitle.en}>
  <main>
    <h1><Lang en={ui.navApproach.en} ru={ui.navApproach.ru} /></h1>
    <p class="subline"><Lang en={ui.approachIntro.en} ru={ui.approachIntro.ru} /></p>
    <figure class="cycle"><CycleDiagram /></figure>
    <Details summaryEn={ui.detailsGatesSummary.en} summaryRu={…}>  … two <ul class="l en"/"l ru"> …
    <Details summaryEn={ui.detailsNumbersSummary.en} …>  <div class="stats"> three <Stat/> + caption </div>
    <Details summaryEn={ui.detailsStackSummary.en} …>  … two <ul> …
  </main>
</Base>
```

The three `<Stat>`s take `metrics.sources.mctl.devloop_proposals`,
`metrics.sources.mctl.services` and `metrics.sources.github.releases`; the
caption reuses `ui.statCaptionPrefix` and `snapshotDate`. Because every digit
of the diagram is inside `CycleDiagram.astro`, this page's template stays
digit-free and the home page's digit proxy transfers verbatim (criterion 9).
The `.stats` / `.stat-caption` rules already in `site.css` are reused as-is;
`.stat-caption { grid-column: 1 / -1 }` needs the grid parent, so the wrapper
keeps `class="stats"`.

`<figure>` rather than a bare `<div>`: it is a figure, and it costs nothing. No
`<figcaption>` is added — the accessible name lives on the SVG, and a caption
would be visible copy the issue does not supply.

### 3. `src/i18n/ui.ts` (edit)

New keys: `approachPageTitle` (both sides `Approach — Dmitrii Mashkov`, the
`workPageTitle` convention), `approachIntro`, `cycleNodes` (arrays of ten),
`cycleTitle`, `cycleDesc`, `detailsGatesSummary`, `detailsGatesItems` (arrays
of four), `detailsNumbersSummary`, `statDevloopProposals`
(`DevLoop proposals` / `Предложений DevLoop`), `statReleasesCount`
(`Releases` / `Релизов`), `detailsStackSummary`, `detailsStackItems`.
`ui.statServices` is reused unchanged for the middle stat because its copy is
already character-identical to what the issue asks for; `ui.statReleases` is
left alone because the home page's `Релизы` is not this page's `Релизов`.

`detailsStackItems` must *be* the home list plus four, not a copy of it. Since
an object literal cannot reference itself, two module-level consts are declared
above `export const ui`:

```ts
const RUN_ITEMS_EN = [ …nine… ] as const;
const RUN_ITEMS_RU = [ …nine… ] as const;
const STACK_EXTRA = ['Claude Agent SDK', 'release-please', 'Astro', 'nginx'] as const;
```

with `detailsRunItems: { en: [...RUN_ITEMS_EN], ru: [...RUN_ITEMS_RU] }` and
`detailsStackItems: { en: [...RUN_ITEMS_EN, ...STACK_EXTRA], ru: [...RUN_ITEMS_RU, ...STACK_EXTRA] }`.
One source array, so the two blocks cannot drift; `test/approach.test.ts`
asserts the prefix/suffix relationship anyway, in case a later edit unpicks it.
`ui.test.ts` keeps passing: both sides stay arrays of equal length.

### 4. `src/components/Nav.astro` and `src/styles/site.css` (edits)

`Nav.astro`: `/#approach` becomes `/approach/` (criterion 2, and
`trailingSlash: 'always'`).

`site.css` gains one block, narrow-first so that any context without media
query evaluation (print) gets the readable vertical variant:

```css
/* Approach page: the DevLoop cycle diagram. */
.cycle { margin: 0 0 var(--mctl-space-6); }
.cycle-svg { display: block; width: 100%; height: auto; color: var(--surface-fg); }
.cycle-wide { display: none; }
.cycle-node rect { fill: var(--surface-elevated); stroke: var(--surface-line-strong); stroke-width: 1; }
.cycle-node.is-gate rect { stroke: var(--accent); stroke-width: 2; stroke-dasharray: 5 4; }
.cycle-node text { fill: currentColor; font-family: var(--font-display); font-size: 14px; }
.cycle-edges path { fill: none; stroke: currentColor; stroke-width: 1.5; }
@media (min-width: 600px) {
  .cycle-narrow { display: none; }
  .cycle-wide { display: block; }
  .cycle-node text { font-size: 13px; }
}
```

All of it in `src/styles/site.css`, never a component `<style>` — that is both
the repo's existing convention (no `<style>` exists under `src/`) and the only
form guaranteed to satisfy `style-src 'self'` without a hash. `npm run vendor`
copies it to `public/styles/site.css` as part of `prebuild`, so no separate
step is needed, but the copy is committed and must be in the diff.

Note the interaction with the language toggle: `:root[data-lang='ru'] .l.en
{ display: none }` and the variant toggle both use `display`, on different
elements (`<text>` vs `<svg>`), so they compose without a specificity fight.

### 5. Verification: `test/approach.test.ts` (new) and `scripts/check-dist.mjs` (edit)

The split follows the repo's existing and documented division of labour.

*Source-level, in `npm test`* (`test/approach.test.ts`, added to the `test`
script in `package.json`), modelled on `test/home.test.ts` and
`test/work.test.ts`:

- `approach.astro` imports `../data/metrics.json`; exactly three `<Stat` tags;
  every `value=` expression matches `/^metrics\.sources\./`.
- the template region of `approach.astro`, after stripping `<h1>`…`<h6>` tag
  names, contains no digit (criterion 9).
- neither `approach.astro` nor `CycleDiagram.astro` mentions
  `--font-editorial` (criterion 21) or `tabindex`.
- `CycleDiagram.astro` does not match `/data\/metrics\.json/` and contains no
  `<Stat` (criterion 11).
- `Nav.astro` links `/approach/` and no longer matches `/#approach"/`.
- `ui.detailsStackItems.en` starts with `ui.detailsRunItems.en` and ends with
  the four additions, same for `ru`; `cycleNodes` has ten entries per side
  (criterion 7).
- `site.css` contains the `@media (min-width: 600px)` variant toggle and the
  `.cycle-svg { … width: 100% … }` fluid rule (criterion 19, 20).

*Built-page, in `scripts/check-dist.mjs`* — the only place that can see
`dist/`, per the script's own header. A new `checkApproachPage()` reads
`dist/approach/index.html`, slices out every `<svg\b[\s\S]*?<\/svg>` (sound
because the design forbids nesting) and pushes a problem string, in the file's
existing style, when:

- the file does not exist, or contains fewer than two `<svg` (criterion 1, 19);
- the summed byte length of the slices is ≥ 12288 (criterion 14);
- any slice matches `<image\b`, `data:`, `xlink:href`, or
  `\.(png|jpe?g|gif|webp)` (criterion 15);
- any slice matches `#[0-9a-fA-F]{3,8}\b`, `rgb(`, `hsl(` (criterion 16);
- any slice lacks `role="img"`, lacks `aria-labelledby`, or names an id token
  in `aria-labelledby` that is not an `id="…"` of a `<title>`/`<desc>` inside
  that slice; or does not contain exactly one `<title` and one `<desc`
  (criterion 17);
- any slice lacks `viewBox="` or carries a `width="`/`height="` attribute on
  the root `<svg>` (criterion 20);
- the per-slice counts of `class="l en"` and `class="l ru"` differ
  (criterion 6);
- the narrow slice's `viewBox` third number exceeds 360 (criterion 20).

The existing whole-file `l en`/`l ru` parity walk already covers criterion 5
for `dist/approach/index.html` with no change, and the 40 KB cap stays scoped
to `dist/index.html` as today.

### 6. Journal

`src/content/journal/2026-09-11-approach-page.md`, frontmatter only, exactly as
listed in `requirements.md`. The `journal` collection schema in
`src/content.config.ts` is `strictObject`, so unlisted keys fail the build and
`issue_opened_at` must be a *quoted* ISO 8601 string with a timezone.

## Alternatives

**One SVG with a single fluid layout instead of two variants.** A wide loop
scaled to 360 px renders its labels at roughly 6 px; a vertical-only layout
readable at 360 px becomes a 1300 px-tall ribbon on a 768 px-wide desktop
`main`. Both fail the spirit of the issue. A single `viewBox` cannot be two
aspect ratios, and `preserveAspectRatio` slicing would crop nodes. Dropped: the
duplication costs about 3 KB of markup and buys a diagram that is right at both
ends, and the issue explicitly sanctions two CSS-toggled variants.

**Ship the diagram as `public/cycle.svg` and reference it with `<img>`.** An
external SVG in an `<img>` cannot inherit `currentColor` or read the page's
`--accent`, so it would need its own colour logic and would not follow the
theme toggle at all; it would also be a second HTTP request and could not
participate in the `.l.en`/`.l.ru` toggle, which is driven by an attribute on
the host document's `:root`. Dropped outright.

**Put the diagram CSS in a `<style>` block inside `CycleDiagram.astro`.**
Astro would hoist and bundle it into `_astro/*.css` (because
`inlineStylesheets: 'never'`), which would in fact satisfy the CSP — but it
would be the only `<style>` in the repo, it would split the site's styling
across two sources of truth, and it depends on a compiler behaviour
(`<style>` nested inside SVG markup being hoisted) that nothing here verifies.
Dropped for `src/styles/site.css`, the documented source of truth.

**Assert the accessibility and weight criteria in `npm test` by parsing the
`.astro` source.** `prebuild` runs `npm test` before `astro build`, so a source
test can only ever inspect the template text, not the emitted HTML — and the
issue asks for "a test over the built page". `scripts/check-dist.mjs` already
exists for exactly this reason and already runs in the Docker build that
`.github/workflows/build.yml` gates the PR on. Dropped in favour of extending
it; the cheap, purely-lexical checks stay in `npm test` where they fail faster.

**Add Playwright (or `linkedom`/`jsdom`) to measure the 360 px render and the
contrast ratios.** That is a new dependency, a browser download in CI, and a
class of flake this repo has deliberately avoided; `AGENTS.md` also settles the
question — a browser capture is a reviewer step, never an acceptance criterion.
Dropped: the mechanical proxies (fluid sizing, `viewBox` width ≤ 360, tokens
only, no colour literals) are what the implementer can commit, and R1/R2 record
what the human does.

## Platform impact

- **Migrations:** none. No schema, no database, no gitops values change. One
  new content file in an existing collection.
- **Backward compatibility:** additive except for the `Nav.astro` href, which
  changes a dangling in-page anchor into a real route. Any existing link to
  `/#approach` still lands on the home page. `trailingSlash: 'always'` means
  the route must be written `/approach/`; nginx's
  `try_files $uri $uri/index.html $uri.html =404` serves
  `dist/approach/index.html` for both `/approach` and `/approach/`.
- **Resource impact:** one more static HTML page (a few KB gzipped) and one
  more CSS block in an already-cached stylesheet. No new request, no new
  dependency, no image. The container image grows by kilobytes.
- **CSP:** unchanged. No new inline script, so `scripts/csp-hash.mjs` emits the
  same hash set; no inline style, so `style-src 'self'` holds.
- **Risk — the two variants drift.** Two copies of the same ten labels is the
  standing cost of this design. Mitigation: both variants iterate the same
  `ui.cycleNodes` arrays and the same local geometry table, so the labels have
  one source; only coordinates are per-variant.
- **Risk — the 12 KB cap is breached by a later edit.** Mitigation:
  criterion 14 is enforced by `check-dist.mjs` on every Docker build, which the
  PR gate runs; the failure names the measured byte count.
- **Risk — `aria-labelledby` points at both variants, or the hidden variant is
  announced.** Mitigation: variant-suffixed ids, each `aria-labelledby`
  resolved inside its own slice by the post-build check, and `display: none` on
  the inactive variant, which removes it from the accessibility tree.
- **Risk — the regex-based `<svg>` slicing in `check-dist.mjs` mis-parses.**
  Mitigation: the design forbids nested `<svg>` and the check fails loudly if
  fewer than two roots are found, so a structural surprise surfaces as a build
  failure rather than a silent pass.
- **Risk — `compressHTML` (Astro's default) reflows the SVG whitespace and
  changes the measured byte count.** Mitigation: the cap is measured on the
  built file, which is the number that matters; the 12 KB budget has roughly
  5 KB of headroom against the estimate.
- **Risk — a reviewer reads the 12 KB cap as per-`<svg>`.** Recorded as an open
  question; this proposal enforces the stricter sum.
