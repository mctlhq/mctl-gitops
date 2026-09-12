# Design: issue-50-q6-share-image-font-shift-cache-lifetime

## Current state

### Share image

`src/layouts/Base.astro` computes one image URL for every page:

```
const ogImageUrl = new URL('/og.svg', Astro.site);
```

and emits it twice, as `og:image` (line 41) and `twitter:image` (line 46),
alongside `twitter:card = summary_large_image`. `public/og.svg` is a
708-byte, 1200x630 SVG: a `<rect>` background plus three `<text>` elements
in `font-family="Arial, Helvetica, sans-serif"` with literal hex fills.
`public/favicon.svg` is a separate 267-byte file wired through
`<link rel="icon" type="image/svg+xml" href="/favicon.svg">`. Nothing in
`scripts/` or `astro.config.mjs` produces a raster image, and the build
stage in `Dockerfile` is `node:24-alpine` pinned by digest, with no font
packages and no image libraries installed.

### Fonts

`scripts/vendor-assets.mjs` downloads three `@fontsource` tarballs at
pinned versions (`onest@5.3.1`, `instrument-serif@5.3.0`,
`jetbrains-mono@5.3.0`), verifies each tarball against a committed SHA-256,
walks the tar by hand with `iterateTar()`, writes every requested
`{subset}-{weight}-{style}` woff2 into `public/assets/fonts/`, and
generates `public/assets/fonts/fonts.css` from a `faceRules` array — one
`@font-face` block per file, each with `font-display: swap` and the
upstream `unicode-range`. The current `FAMILIES` table asks for Onest
300/400/500/600/700, JetBrains Mono 400/500/600/700 and Instrument Serif
400 normal+italic, which is 40 faces and 13054 bytes of CSS. The same
script copies `src/styles/site.css` to `public/styles/site.css` (gitignored
via `/public/styles/site.css`) so Astro never inlines it — `astro.config.mjs`
sets `inlineStylesheets: 'never'` because the CSP carries `style-src 'self'`
with no `'unsafe-inline'`.

`Base.astro` links five stylesheets in fixed order: `mctl.css`,
`global.css`, `prose.css`, `fonts.css`, `site.css`. There is no
`<link rel="preload">` anywhere in the tree. `public/assets/mctl/global.css`
sets `body { font-family: var(--font-display) }`, and `mctl.css` resolves
`--font-display` to `'Onest', system-ui, -apple-system, sans-serif` — so
Onest is the body face, not just a display face, and the swap from the
system fallback moves every line on the page. `--font-editorial` resolves
to `'Instrument Serif', Georgia, serif` and is bound by `prose.css` to
`.mctl-lede` and `.mctl-prose em`; `src/pages/colophon/adr/[...slug].astro`
renders inside `<div class="mctl-prose">`, so Instrument Serif is reachable
on real pages and cannot simply be dropped.

### Cache lifetime

`nginx.conf` has four `location` blocks. Only `/_astro/` carries a cache
directive (`expires 1y; add_header Cache-Control "public, immutable"`), and
`scripts/check-headers.mjs` documents that the build currently emits
nothing under `dist/_astro/`, so that block is dormant. Everything else —
`/assets/**`, `/styles/site.css`, the HTML — is served with no origin
`Cache-Control`, which is why the edge applies its four-hour default to the
CSS and woff2 while leaving HTML `DYNAMIC`. `test/nginx.test.ts` asserts
`include /etc/nginx/security-headers.conf;` appears exactly five times (the
server block plus four locations) and enumerates those four blocks by name,
so any new location must be reflected there.

### DevLoop diagram

`src/components/CycleDiagram.astro` is props-less and builds two variants
in the frontmatter. `buildWide()` uses `w = 112`, `h = 44`,
`cols = [24, 160, 296, 432, 568]`, `topY = 30`, `botY = 226`, and returns
`viewBox: "0 0 740 300"`. The two vertically aligned column pairs —
node 4 (Implement) above node 5 (Review gate) at `cols[4]`, and node 9
(Monitor) below node 0 (Issue) at `cols[0]` — are connected by
three-segment detours out to `rightMargin = cols[4] + w + 30` and
`leftMargin = cols[0] - 12`, which is what forces the viewBox 60 units
wider than the node grid needs. `GATE = [f,f,f,t,f,t,f,f,f,f]` marks nodes
3 and 5, and `src/styles/site.css` draws them with
`.cycle-node.is-gate rect { stroke: var(--accent); stroke-dasharray: 5 4 }`.
The meaning of that dash lives only in `ui.cycleDesc`, rendered into
`<desc>`. `src/pages/approach.astro` wraps the component in
`<figure class="cycle">` and the `Gates` `<Details>` immediately below it
already carries `open` — `test/approach.test.ts` asserts exactly one
`<Details>` does, and that it is that one.

Three gates constrain any edit here. `scripts/check-dist.mjs` caps the
summed byte length of every `<svg>` on the built approach page at 12288
(`MAX_SVG_BYTES`), caps the narrow viewBox width at 360, and rejects raster
references, literal colours, missing `<title>`/`<desc>`, and `width`/`height`
attributes. `test/approach.test.ts` asserts the component source contains
exactly one `<svg>` open tag, one `role="img"`, one `aria-labelledby`, one
`<title>` and one `<desc>`. And `scripts/check-no-metrics.mjs` fails on any
bare two-or-more-digit number under `src/pages`, `src/components` or
`src/layouts` that no `RULES` classifier recognises and no `ALLOW` entry
lists — the component's geometry is excused by an `ALLOW` entry listing
`[10, 12, 24, 30, 40, 44, 60, 64, 112, 160, 220, 226, 296, 300, 320, 432, 568]`,
and a listed value that no longer appears is itself a failure.

### Hero

`src/styles/site.css` line 181 sets
`.hero-name { font-size: var(--mctl-typography-font-size-hero) }`, which
`mctl.css` defines as `clamp(48px, 8.4vw, 132px)`. The container is
`max-width: var(--content-max)` = 768px with `padding-inline: 16px`, so
roughly 736px of usable width. 8.4vw crosses ~92px at a 1100px viewport,
which is where 15 Latin characters of Onest bold stop fitting — exactly the
reported break point.

## Proposed solution

### 1. Build-time PNG from the same composition, or a documented stop

Add `scripts/render-og.mjs`, invoked from `package.json` as part of the
build (a `postbuild`-style step run before `check-dist.mjs`, or appended to
the `build` script), which writes `dist/og.png` at 1200x630 and nothing
else.

The renderer is `@resvg/resvg-wasm`. It is chosen because it is the only
SVG rasteriser that installs as a pure WebAssembly npm package: no
platform-gated `optionalDependencies`, no postinstall download from a
release host, nothing for `npm ci` to resolve per-architecture, and nothing
added to the runtime nginx image, which only ever receives `dist/`.

resvg needs fonts as buffers and understands sfnt (TTF/OTF), not woff2. The
font is taken from bytes this repo already fetches and pins:
`vendor-assets.mjs` gains a step that extracts the WOFF1
(`files/onest-latin-{400,700}-normal.woff`) entries from the same
`@fontsource/onest@5.3.1` tarball it already downloads and SHA-256-verifies,
converts them to TTF, and writes them to `scripts/fonts/` (build-only, not
under `public/`, so they are never served). WOFF1 is a thin container: a
44-byte header, a table directory of `{tag, offset, compLength, origLength}`
records, and each table either stored raw or deflated — `zlib.inflateSync`
from Node's standard library reverses it, and the sfnt is reassembled by
writing the table directory back with recomputed offsets. No dependency.
WOFF2 cannot be handled this way (Brotli plus a transformed `glyf` table),
which is why the `.woff` entry specifically is what matters.

`Base.astro` then computes `new URL('/og.png', Astro.site)` and uses it for
both `og:image` and `twitter:image`. `public/og.svg` stays as the source of
truth for the composition and `public/favicon.svg` is untouched.

The issue's own escape hatch is wired in as a first-class branch, not a
footnote: if `@fontsource/onest@5.3.1` turns out to carry no `.woff`
entries, or if `@resvg/resvg-wasm` cannot be installed by `npm ci` in
`node:24-alpine` without a platform-gated binary, the implementer stops
item 1, leaves the two meta tags on `/og.svg`, commits `docs/og-image.md`
naming each renderer attempted and the reason it was rejected, and says the
same in the commit message. `docs/` already holds exactly this kind of
English-only engineering note (`docs/hardening-notes.md`,
`docs/link-check.md`) and is not rendered on the site, so no bilingual copy
is required for it. A committed file is used rather than the pull request
body because AGENTS.md records that the implementer cannot edit its PR
template.

The check in `check-dist.mjs` is written so it passes in either branch:
`og:image` and `twitter:image` must be equal and must resolve to a file
present under `dist/`; and *if* `dist/og.png` exists, its IHDR width and
height must be 1200 and 630. Reading IHDR is 8 bytes at a fixed offset, no
dependency.

### 2. Preload, prune, and a metric-matched fallback

Three changes, each attacking a different part of the 0.17 CLS.

**Preload.** `Base.astro` emits four preload links immediately after the
viewport meta and before the first stylesheet link:

```
<link rel="preload" as="font" type="font/woff2" crossorigin href={assets.preload.onestLatin400} />
```

for Onest latin 400, latin 700, cyrillic 400 and cyrillic 700. `crossorigin`
is mandatory even same-origin: font requests are made in anonymous CORS
mode, and a preload without it is a second, uncredited fetch. Cyrillic is
included deliberately: the Russian copy is in the DOM on every page behind
`display: none`, so it is not fetched on first paint, but the language
toggle is instant and a reader who flips it should not watch the page
reflow a second time. Four faces at roughly 12-25 KB each is within the
90 KB the page already spends.

**Prune.** `FAMILIES` in `vendor-assets.mjs` drops Onest weight 300 (no
selector in `site.css`, `global.css`, `prose.css` or any `mctl.css`
composite token resolves to it) and JetBrains Mono weights 600 and 700
(`--mctl-typography-text-marker-weight` is 500 and
`--mctl-typography-text-code-weight` is 400; nothing selects heavier mono).
That removes 12 of 40 faces and their woff2 files. Instrument Serif is kept
in full, exactly as the issue requires: it stays *declared* so
`.mctl-lede` and `.mctl-prose em` resolve, and a declared-but-unselected
`@font-face` is never fetched, which is what makes acceptance criterion 4
true without deleting the family.

**Stop the swap from moving anything.** `site.css` declares a local
fallback face with overridden metrics and inserts it into the stack:

```
@font-face {
  font-family: 'Onest Fallback';
  src: local('Arial'), local('Helvetica Neue'), local('Liberation Sans'), local('DejaVu Sans');
  size-adjust: 96%;
  ascent-override: 96%;
  descent-override: 24%;
  line-gap-override: 0%;
}
:root {
  --font-display: 'Onest', 'Onest Fallback', system-ui, -apple-system, sans-serif;
}
```

Overriding the token in `site.css` rather than editing `mctl.css` is
deliberate: the three vendored files are SHA-256-pinned in
`vendor-assets.mjs` and any edit to them fails the next vendor run. The
percentages are starting values derived from Onest's own vertical metrics
against a generic sans; the reviewer's Lighthouse run is what confirms
them. `font-display: swap` is kept — with a preload and a metric-matched
fallback, swap is the correct value, and `optional` would risk never
showing Onest at all on a slow connection.

A new `test/fonts.test.ts` holds the mechanical half: every numeric
`font-weight` reachable from `site.css` and the three vendored stylesheets
has a matching `@font-face` in the generated `fonts.css`; the preload set
rendered by `Base.astro` is exactly those four faces; each preload href
resolves to a file that exists under `public/assets/fonts/`.

### 3. Content-hashed filenames, then a year of immutable

The issue offers two branches and asks for one to be chosen and justified.
**This proposal versions the filenames**, for all five stylesheets and
every woff2, and gives the year to `/assets/` and `/styles/` alike.

The reason for rejecting the other branch is that it does not actually
hold. The claim that "the bytes behind one URL never change" is true only
until a re-pin, and `fonts.css` is regenerated by *this very cycle* when
the family table changes — so `/assets/fonts/fonts.css` is demonstrably a
mutable URL. `AGENTS.md` names a re-pin of `@mctlhq/css` as an expected
future event, and ADR-0005's revisit criteria name it explicitly. Putting
`immutable` on `/assets/mctl/mctl.css` would strand every reader who
cached it across that re-pin, with no recovery path — the failure mode the
issue calls unacceptable.

Astro's own hashing was considered and rejected for a reason that lands
inside this issue's out-of-scope list: moving the stylesheets into the
bundler would let Vite concatenate `mctl.css` with site CSS, which the
issue forbids. So the hashing is done where the files are already
produced.

`vendor-assets.mjs` gains a single `emit(dir, name, bytes)` helper: it
computes `sha256(bytes).slice(0, 8)`, writes `name.<hash>.ext`, and records
the public href. Every asset it currently writes goes through it —
`mctl.css`, `global.css`, `prose.css`, each woff2, the generated
`fonts.css` (whose `src: url(...)` entries now point at the hashed woff2
names, which is free because that CSS is generated), and the `site.css`
copy. It then writes `src/data/assets.json`:

```
{
  "styles": ["/assets/mctl/mctl.<h>.css", "...", "/styles/site.<h>.css"],
  "preload": { "onestLatin400": "/assets/fonts/onest-latin-400-normal.<h>.woff2", ... }
}
```

and prunes any file under `public/assets/` or `public/styles/` matching a
managed pattern that is not named in the new manifest, so the committed
tree never accumulates orphans. `verifyExistingTree()` — the offline
fallback path — is rewritten to validate against `src/data/assets.json`
instead of reconstructing filenames from the `FAMILIES` table.

`Base.astro` imports that JSON and renders both its stylesheet links and
its preload links from it. That also keeps `scripts/check-no-metrics.mjs`
quiet: no `400`/`700` literal ever appears in a layout or component file,
because the hrefs come from data.

`nginx.conf` gains two locations, each with the mandatory
`include /etc/nginx/security-headers.conf;`:

```
location /assets/ { expires 1y; add_header Cache-Control "public, immutable" always; include ...; try_files $uri =404; }
location /styles/ { expires 1y; add_header Cache-Control "public, immutable" always; include ...; try_files $uri =404; }
```

`location /` is untouched, so HTML keeps exactly the policy it has today.
`test/nginx.test.ts` is updated: seven includes instead of five, and the
two new blocks added to the enumerated list. `check-headers.mjs` gains one
assertion pair — a `/assets/` path answers with `max-age=31536000` and
`immutable`, and `/` does not — which is the mechanical form of the
issue's `curl -D -` criterion, run against the real container in
`.github/workflows/build.yml`. `check-dist.mjs` gains the inverse guard:
no built page may reference a subresource under `/assets/` or `/styles/`
whose filename lacks an 8-hex content hash, so nothing unversioned can ever
be dropped into an immutable location later.

The one-time cost is a rename-only diff: 28 woff2 files and four
stylesheets get new names.

### 4. The diagram: a tighter grid, wider boxes, a visible legend

`buildWide()` is re-parameterised:

| | today | proposed |
|---|---|---|
| box width | 112 | 130 |
| box height | 44 | 44 |
| columns | `[24, 160, 296, 432, 568]` | `[13, 159, 305, 451, 597]` (`13 + i * 146`) |
| top row y | 30 | 30 |
| bottom row y | 226 | 130 |
| viewBox | `0 0 740 300` | `0 0 740 200` |

The 150px empty band and the extra 60 units of width both come from the
same thing: the Implement→Review-gate and Monitor→Issue connectors detour
into a right margin and a left gutter even though each pair is already
vertically aligned in the same column. Replacing both with a straight
vertical segment — `M${cols[4] + w/2},${topY + h} L${cols[4] + w/2},${botY}`
and the mirror at `cols[0]` — frees 42 units of horizontal margin, which is
what pays for 18 more units of box width inside the same 740-unit viewBox,
and it reads better: right along the top, down at the right end, left along
the bottom, up at the left end.

Labels get both remedies the issue allows, because either alone is thin.
Boxes go to 130, and inside the `@media (min-width: 800px)` block in
`site.css` the Russian labels drop one step:

```
:root[data-lang='ru'] .cycle-wide .cycle-node text { font-size: 12px; }
```

With 8 units of padding a side, the budget is 114 units. `Shepherd merge`
is 14 characters at 13px (about 106 units at an 0.58 advance ratio);
`Мерж шефердом` is 13 characters at 12px (about 91). `test/cycle-diagram.test.ts`
encodes that arithmetic against `ui.cycleNodes` so a future label that no
longer fits fails the build rather than the eye.

The legend is markup, not SVG. `approach.astro` adds a `<figcaption
class="cycle-legend">` inside the existing `<figure class="cycle">`,
carrying an `.l en` / `.l ru` pair and a `<span class="cycle-legend-swatch"
aria-hidden="true">` that `site.css` draws with
`border: 2px dashed var(--accent)`. Keeping it out of the SVG preserves
three things at once: `test/approach.test.ts`'s assertion that the
component source has exactly one `<svg>`, the 12288-byte SVG budget in
`check-dist.mjs`, and the `.l en` / `.l ru` parity count. It also means the
legend text is selectable and translatable like any other copy. The copy
carries no digit, so `approach.test.ts`'s "no digit in the template"
assertion still holds.

`ui.ts` gains `cycleLegend: { en, ru }` with the exact strings from
`requirements.md`. The `ALLOW` entry for `CycleDiagram.astro` in
`check-no-metrics.mjs` is regenerated: with the geometry above and `cols`
derived as `13 + i * 146`, the geometry entry becomes
`[10, 13, 30, 40, 44, 60, 64, 130, 146, 200, 220, 320]`, with the existing
separate `[11]` entry for the header comment left as it is. The
implementer regenerates this by running the script rather than trusting the
list, because a stale entry fails the gate as loudly as a missing one.

The narrow variant is not touched.

### 5. Cap the hero

```
.hero-name {
  font-size: min(var(--mctl-typography-font-size-hero), calc(var(--content-max) / 9.6));
}
```

768/9.6 is 80px. `Дмитрий Машков` is 14 Cyrillic characters, which at an
0.60 advance ratio and -0.02em tracking is about 672 units — comfortably
inside the ~736px the container leaves after `padding-inline: 16px`.
Expressing the cap against `--content-max` rather than as a bare pixel
value keeps the constraint and its cause in the same expression: the name
must fit the container, and the container is what the token does not know
about. Below roughly a 950px viewport the 8.4vw term still wins, so nothing
changes on mobile.

## Alternatives

**`sharp` for the PNG.** Rejected on two counts. Its SVG path goes through
librsvg, whose text rendering needs fontconfig and installed fonts —
`node:24-alpine` has neither, so the three `<text>` elements would render
empty and the failure would be silent rather than loud. And AGENTS.md
already names `sharp` as one of the packages whose
`optionalDependencies` an ordinary `npm install` prunes out of the
lockfile, producing a tree that `npm ci` refuses in the Dockerfile. The
same objection applies to `@resvg/resvg-js`, the native sibling of the wasm
package chosen above.

**Render the PNG once and commit `public/og.png`.** Simplest possible
option, zero new dependencies, and it would satisfy a link-preview check
today. Rejected because it is not generated at build time, so it silently
drifts from `og.svg` the first time the composition changes, and because
nothing would catch the drift — the repository's whole posture is that
evidence is mechanical.

**Leave `site.css` and `fonts.css` at four hours and give the year only to
the rest of `/assets/`.** This is the issue's other branch and it is
cheaper. Rejected because `/assets/mctl/*.css` and the woff2 files are
themselves mutable under a stable URL across a re-pin, so the branch buys
its simplicity by putting `immutable` on exactly the files the issue says
must not carry it. Content hashing costs one helper function in a script
that already writes every one of these files.

**Move the stylesheets into Astro so its bundler hashes them.** The issue
names this as an option and it would reuse the dormant `/_astro/`
immutable block with no nginx change at all. Rejected because Vite
concatenates imported stylesheets, and merging `mctl.css` with site CSS is
explicitly out of scope for this issue.

**`font-display: optional` instead of preload plus metric overrides.**
`optional` eliminates the swap and therefore the CLS outright. Rejected
because on a slow first visit the reader simply never sees Onest, which
trades a measurable defect for an invisible one; with a preload in flight
before the stylesheet parses, `swap` has nothing left to shift.

**Legend as a third inline `<svg>`, or as `<text>` inside the existing
one.** Rejected: the first breaks `test/approach.test.ts`'s single-`<svg>`
assertion on the component source, and both spend the 12288-byte SVG budget
on text that is cheaper, selectable and more translatable as markup.

## Platform impact

**Migrations.** None at the data layer. The only migration is a filename
migration inside the repository: 28 woff2 files and four stylesheets are
renamed to carry a content hash, `/public/styles/site.css` in `.gitignore`
becomes `/public/styles/`, and `src/data/assets.json` becomes a generated,
committed file. No URL that a reader has bookmarked changes — only
subresource URLs, which are always rediscovered from the HTML.

**Backward compatibility.** The HTML cache policy is unchanged, so a reader
holding a cached page gets the new HTML on the next visit and with it the
new hashed subresource URLs. Readers holding the old four-hour-cached
`/assets/fonts/fonts.css` are unaffected: that URL stops being referenced,
and their cache entry simply expires unused. `/og.svg` stays in place, so
any platform that already scraped and cached the old card keeps resolving
it.

**Resource impact.** Build stage grows by `@resvg/resvg-wasm` (roughly
2 MB of wasm in `node_modules`, builder stage only — the runtime image is
`nginx:1.30-alpine` and receives only `dist/`). `dist/` grows by one PNG,
on the order of 20-40 KB for a flat three-line composition. The font
payload *shrinks* by 12 woff2 files, and `fonts.css` shrinks by roughly
30%. `dist/index.html` grows by four preload links, about 400 bytes against
the 40960-byte cap in `check-dist.mjs` — headroom must be confirmed by the
build, and if the cap is approached the preload set is the thing to trim,
not the cap.

**Risks and mitigations.**

- *`@fontsource/onest@5.3.1` may ship no `.woff`.* Then there is no offline
  sfnt for resvg and item 1 takes its documented stop path. Mitigation: the
  stop path is specified up front, `check-dist.mjs` is written to pass in
  both branches, and items 2-5 are independent of item 1.
- *`npm ci` lockfile hazard.* Adding any dependency risks the
  `optionalDependencies` pruning AGENTS.md documents. Mitigation:
  regenerate with `npm install --package-lock-only`, never a plain
  `npm install`, and confirm the Docker build — which runs `npm ci` — is
  green in CI before merge. `@resvg/resvg-wasm` has no platform-gated
  optional deps, which is a large part of why it was chosen.
- *`immutable` on a wrong file.* Mitigated by the `check-dist.mjs` guard
  that rejects any referenced `/assets/` or `/styles/` subresource without
  an 8-hex hash in its filename, and by `check-headers.mjs` asserting the
  header against the running container.
- *Stale `ALLOW` entry in `check-no-metrics.mjs`.* A listed value that no
  longer matches is itself a failure, so a partial edit of the diagram
  geometry breaks `npm test` loudly. Mitigation: regenerate the entry from
  the script's own output.
- *Fallback metric overrides that are wrong for a given OS.* A bad
  `size-adjust` can make CLS worse rather than better. Mitigation: the
  values are starting points, the Lighthouse run is a named reviewer step,
  and reverting just the `@font-face` fallback block is a two-line change
  independent of the preload and pruning work.
- *The preload set and the pruned weight set can disagree.* Mitigated by
  `test/fonts.test.ts`, which resolves every preload href against the files
  actually on disk and every reachable `font-weight` against the generated
  `fonts.css`.
- *CSP.* Nothing here adds an inline script, an inline style, or an
  external origin: the PNG is same-origin (`img-src 'self' data:` already
  covers it), the preloads are same-origin (`font-src 'self'`), and the
  legend swatch is styled from `site.css`. `scripts/csp-hash.mjs` and the
  Dockerfile substitution are untouched.
