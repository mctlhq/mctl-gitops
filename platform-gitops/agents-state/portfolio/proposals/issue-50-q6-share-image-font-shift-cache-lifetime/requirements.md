# Q6: share image, font shift, cache lifetime and the DevLoop diagram

## Context

A Lighthouse mobile run and a link-preview check against the production
mirror turned up four independent defects in `mctlhq/portfolio`, plus one
layout regression in the hero. `src/layouts/Base.astro` points `og:image`
and `twitter:image` at `/og.svg`, and no social platform renders SVG in a
link preview, so every shared link ships without a card image.
`public/assets/fonts/fonts.css` declares 40 `@font-face` rules with
`font-display: swap` and no `<link rel="preload">`, so the first frames of
every page paint in a system fallback and then reflow — measured as CLS
0.17 on `/work/`, the only page above the 0.1 "good" threshold. The
vendored CSS and woff2 payload (about 90 KB compressed) is served with no
origin `Cache-Control` at all — `nginx.conf` sets `expires` only for
`/_astro/`, so the edge falls back to a four-hour default on bytes that are
pinned by SHA-256 in `scripts/vendor-assets.mjs` and never change under a
stable URL. And the wide DevLoop diagram in
`src/components/CycleDiagram.astro` is `viewBox="0 0 740 300"` with its two
node rows at y=30 and y=226 — roughly 150px of empty canvas — while the
Russian labels crowd their 112px boxes and the dashed "control point"
outline is explained only inside `<desc>`, which a sighted reader never
sees.

These are cheap, independently checkable fixes to the two things this site
claims to be good at: it is a verifiable artifact of the DevLoop, so a
share of it should render a card, and a page that reflows on first paint
undercuts the claim before a reader has read a word. The cache item also
carries a correctness trap the issue names explicitly: a year plus
`immutable` on a URL whose bytes can change strands readers on a stale
stylesheet with no recovery path, and two of the five stylesheets this site
serves — `site.css` and the generated `fonts.css` — are exactly that kind
of file today.

## User stories

- AS someone sharing a link to the site in Telegram, Slack, LinkedIn or X
  I WANT the preview card to carry an image SO THAT the link reads as a
  real page rather than a bare URL.
- AS a first-time reader on a mobile connection I WANT the page to paint
  once and stay put SO THAT I can start reading without the text jumping
  under my eyes.
- AS a returning reader I WANT the vendored CSS and fonts to come from my
  own cache SO THAT a second visit costs no bytes.
- AS a returning reader after a stylesheet change I WANT to receive the new
  stylesheet SO THAT a long cache lifetime never strands me on stale CSS.
- AS a sighted reader of the approach page I WANT the dashed outline on two
  diagram nodes to be explained where I can see it SO THAT I do not have to
  open a disclosure or read the SVG source to learn what it means.
- AS a Russian-language reader I WANT the diagram labels to sit inside
  their boxes SO THAT the diagram reads as designed rather than as a
  rendering accident.
- AS a reader on a wide desktop viewport I WANT the hero name to render on
  one line SO THAT the first thing on the page is not an accidental line
  break.

## Acceptance criteria (EARS)

### Share image

- WHEN the build stage runs `npm run build` THE SYSTEM SHALL emit a
  1200x630 PNG at `dist/og.png`, rendered at build time from the same
  composition as `public/og.svg`, with no network request of any kind.
- WHEN a page is built THE SYSTEM SHALL set `og:image` and `twitter:image`
  in `src/layouts/Base.astro` to the absolute URL of that PNG, and both
  meta tags SHALL carry the same value.
- WHILE item 1 is implemented THE SYSTEM SHALL keep `public/favicon.svg`
  and `public/og.svg` in the tree, and `<link rel="icon">` SHALL continue
  to point at `/favicon.svg`.
- IF a renderer capable of producing the PNG offline cannot be installed by
  `npm ci` in the `node:24-alpine` build stage without a platform-gated
  binary download or a postinstall network fetch, THEN THE SYSTEM SHALL
  leave `og:image` and `twitter:image` pointing at `/og.svg`, SHALL commit
  `docs/og-image.md` recording which renderers were attempted and why each
  was rejected, and SHALL state the same in the commit message; the
  remaining items of this proposal still land.
- WHEN `scripts/check-dist.mjs` runs THE SYSTEM SHALL fail if `og:image`
  and `twitter:image` on any built page differ from each other, or if
  either points at a path that does not exist under `dist/`.
- IF `dist/og.png` exists THEN `scripts/check-dist.mjs` SHALL read its PNG
  IHDR chunk and fail unless the dimensions are exactly 1200x630.

### Fonts: preload and no layout shift

- WHEN a page is served THE SYSTEM SHALL emit four
  `<link rel="preload" as="font" type="font/woff2" crossorigin>` elements
  in `<head>`, for Onest latin 400, Onest latin 700, Onest cyrillic 400 and
  Onest cyrillic 700, placed before the first `<link rel="stylesheet">`.
- WHILE a preload element is emitted THE SYSTEM SHALL carry the
  `crossorigin` attribute on it, because a font request is made in
  anonymous CORS mode and a preload without it is fetched twice.
- WHEN `scripts/vendor-assets.mjs` generates `fonts.css` THE SYSTEM SHALL
  emit `@font-face` rules only for: Onest weights 400, 500, 600 and 700
  across the latin, latin-ext, cyrillic and cyrillic-ext subsets;
  JetBrains Mono weights 400 and 500 across the same four subsets; and
  Instrument Serif weight 400 in normal and italic across latin and
  latin-ext.
- WHILE `fonts.css` is generated THE SYSTEM SHALL keep an Instrument Serif
  `@font-face` declaration available, because `public/assets/mctl/prose.css`
  binds `.mctl-lede` and `.mctl-prose em` to `var(--font-editorial)` and
  those selectors are reachable on the colophon pages.
- WHEN `src/styles/site.css` is loaded THE SYSTEM SHALL declare a
  metric-adjusted local fallback face named `Onest Fallback` carrying
  `size-adjust`, `ascent-override`, `descent-override` and
  `line-gap-override`, and SHALL redefine `--font-display` so that
  `Onest Fallback` sits between `Onest` and the generic system stack.
- WHEN `npm test` runs THE SYSTEM SHALL fail if any numeric `font-weight`
  reachable from `src/styles/site.css` or the three vendored
  `public/assets/mctl/*.css` files has no matching `@font-face` rule in the
  generated `fonts.css`.
- WHEN `npm test` runs THE SYSTEM SHALL fail if the set of preloaded font
  hrefs rendered by `src/layouts/Base.astro` is not exactly the four faces
  named above, or if any of them does not resolve to a file that exists
  under `public/assets/fonts/`.
- WHILE the site is served THE SYSTEM SHALL make no request to a
  third-party host from any page, as `scripts/check-dist.mjs` already
  enforces for subresources and `url(...)` references.

Reviewer step, not an acceptance criterion (per AGENTS.md, work that needs
a browser is named as a reviewer step): a Lighthouse mobile run on `/work/`
reports CLS below 0.1, and a HAR capture of `/`, `/work/` and
`/colophon/` shows no third-party host and no fetch of a font family the
page does not use.

### Cache lifetime

- WHEN `scripts/vendor-assets.mjs` writes any asset into `public/assets/`
  or `public/styles/` THE SYSTEM SHALL embed the first 8 hex characters of
  that file's SHA-256 in its filename, immediately before the extension.
- WHEN `scripts/vendor-assets.mjs` completes THE SYSTEM SHALL have written
  `src/data/assets.json` mapping each logical asset to its hashed
  public href, and `src/layouts/Base.astro` SHALL build every stylesheet
  and font-preload href from that file rather than from a literal path.
- WHEN `scripts/vendor-assets.mjs` completes THE SYSTEM SHALL have deleted
  every file it previously emitted under `public/assets/` and
  `public/styles/` that is not named in the current `src/data/assets.json`,
  so a content change leaves no orphan behind.
- WHEN nginx serves any path under `/assets/` or `/styles/` THE SYSTEM
  SHALL send `Cache-Control: public, max-age=31536000, immutable`.
- WHILE nginx serves HTML THE SYSTEM SHALL leave its cache policy exactly
  as it is today, adding no `expires` and no `Cache-Control` to
  `location /`.
- WHILE any new `location` block exists in `nginx.conf` THE SYSTEM SHALL
  `include /etc/nginx/security-headers.conf;` inside it exactly once, and
  `test/nginx.test.ts` SHALL be updated so its include count and its list
  of location blocks match the new file.
- WHEN `scripts/check-dist.mjs` runs THE SYSTEM SHALL fail if any built
  page references a subresource under `/assets/` or `/styles/` whose
  filename does not carry an 8-hex-character content hash before its
  extension.
- WHEN `scripts/check-headers.mjs` runs against the built image THE SYSTEM
  SHALL additionally assert that a `/assets/` path responds with
  `Cache-Control` containing `max-age=31536000` and `immutable`, and that
  the response for `/` does not.

### DevLoop diagram

- WHEN the wide variant of `src/components/CycleDiagram.astro` is built THE
  SYSTEM SHALL use `viewBox="0 0 740 200"` with the top node row at y=30
  and the bottom node row at y=130.
- WHEN the wide variant is built THE SYSTEM SHALL render node boxes 130
  units wide.
- WHILE the document language is Russian THE SYSTEM SHALL render the wide
  variant's node labels one step smaller than the English labels, so that
  the longest label in either language fits inside its box with padding to
  spare.
- WHEN `npm test` runs THE SYSTEM SHALL fail if, for either language, the
  longest label's estimated advance width — its character count times 0.58
  times the variant's label font-size — exceeds the variant's box width
  less 16 units of padding.
- WHEN the approach page is built THE SYSTEM SHALL render a visible legend
  directly below the diagram, inside the existing `<figure class="cycle">`
  in `src/pages/approach.astro`, as an `.l en` / `.l ru` pair carrying
  exactly this copy:
  - EN: `Dashed outline: a control point. The cycle does not continue until this step passes.`
  - RU: `Пунктирная рамка: контрольная точка. Цикл не продолжается, пока этот шаг не пройден.`
- WHILE the legend is rendered THE SYSTEM SHALL draw its dashed swatch with
  CSS in `src/styles/site.css` on an `aria-hidden="true"` element, not as a
  third inline `<svg>`, so that `test/approach.test.ts` still sees exactly
  one `<svg>` template in the component and the swatch adds nothing to the
  SVG byte budget.
- WHILE both variants are built THE SYSTEM SHALL keep exactly one `<title>`
  and one `<desc>` per `<svg>`, `role="img"`, `aria-labelledby` resolving
  inside the same `<svg>`, `currentColor` and design-token colours only, no
  `width`/`height` attribute, and a combined SVG byte total on the built
  approach page under 12288 bytes.
- WHILE the wide variant changes THE SYSTEM SHALL leave the narrow variant
  geometry unchanged: one column of ten 220-unit nodes and a viewBox width
  of 320.
- WHEN `scripts/check-no-metrics.mjs` runs THE SYSTEM SHALL pass, which
  requires the `ALLOW` entry for `src/components/CycleDiagram.astro` to be
  regenerated so it lists exactly the numeric literals the rewritten
  component contains and no stale value.

### Hero name

- WHILE the viewport is between 768px and 1920px wide THE SYSTEM SHALL
  render `Dmitrii Mashkov` and `Дмитрий Машков` inside
  `<h1 class="hero-name">` on a single line.
- WHEN `src/styles/site.css` sets `.hero-name` font-size THE SYSTEM SHALL
  cap it with `min(...)` against a value derived from `--content-max`,
  rather than letting the viewport-scaled hero token run free against a
  fixed 768px container.
- WHEN `npm test` runs THE SYSTEM SHALL fail if the `.hero-name` rule in
  `src/styles/site.css` sets `font-size` without a `min(` or `clamp(`
  upper bound.

Reviewer step: the hero name renders on one line at 768px, 1100px, 1440px
and 1920px in both languages.

### Gates that must stay green

- WHEN `node scripts/check-dist.mjs` runs after `npm run build` THE SYSTEM
  SHALL exit zero: no file under `dist/` ends in `.js`, every
  `dist/**/*.html` has an equal count of `class="l en"` and `class="l ru"`,
  and `dist/index.html` stays under 40960 bytes.
- WHEN `npm test` and `npm run build` run THE SYSTEM SHALL exit zero.
- WHEN `node scripts/check-links.mjs` runs THE SYSTEM SHALL exit zero.

## Out of scope

- Merging the five stylesheets into one. `public/assets/mctl/mctl.css`,
  `global.css` and `prose.css` are vendored from the design system and must
  not be concatenated with site CSS. This proposal deliberately does not
  move any stylesheet into Astro's bundler, because `astro build` would
  concatenate them. If render-blocking is worth attacking beyond preload,
  it gets its own issue.
- Re-pinning `@mctlhq/css` past 0.5.0 or any `@fontsource` package past its
  current version. Only the emitted filenames change here, never the bytes.
- Everything owned by the other cycles in this wave: the CSP guards, link
  colour, the Colophon tables, the `/work/` page content, navigation and
  disclosure state.
- Changing the HTML cache policy. `location /` in `nginx.conf` is left
  exactly as it is.
- Adding a second inline script, a client bundle, analytics or a cookie.
- Translating the `<title>` element or any identifier, hostname or command.

## Open questions

- **Does `@fontsource/onest@5.3.1` ship `.woff` alongside `.woff2`?** The
  offline PNG renderer needs a TTF/OTF buffer, and the only font bytes this
  repo can reach without a new network dependency are inside the already
  pinned fontsource tarballs. WOFF1 is a zlib-compressed sfnt and converts
  to TTF with `node:zlib` alone; WOFF2 does not. The clone has no network,
  so this could not be verified. Proceed on the assumption it does; if the
  tarball carries only `.woff2`, item 1 takes its documented stop path
  (`docs/og-image.md`, meta tags unchanged) and items 2 to 5 still land.
- **The issue says the `Gates` disclosure is collapsed; it is not.**
  `src/pages/approach.astro` already passes `open` to the Gates `<Details>`,
  and `test/approach.test.ts` asserts exactly one `<Details>` carries `open`
  and that it is the Gates one. The observation is stale, the remedy is
  not — a legend that a reader sees without expanding anything is still the
  right fix, and nothing about the disclosure state changes here.
- **The issue says `fonts.css` declares 44 `@font-face` rules; it declares
  40.** The pruning list in this proposal is stated absolutely (which
  families, weights and subsets survive), not as a delta, so the count does
  not matter.
- **CLS cannot be an acceptance criterion.** AGENTS.md requires that work
  needing a browser be a reviewer step rather than something the
  implementer must satisfy with a commit. The mechanical criteria above
  (preload set, fallback metric overrides, family pruning) are what the
  implementer commits; the Lighthouse number is named as a reviewer step.
  The same applies to the one-line hero name and to pasting the apex URL
  into Telegram.
- **Exact `size-adjust` / `ascent-override` values.** These depend on the
  fallback family the reader's OS actually resolves and cannot be measured
  in a headless clone. `design.md` gives starting values computed from
  Onest's own vertical metrics against a generic sans; the reviewer's
  Lighthouse run is what confirms them.
- **Hashed filenames churn the committed tree once.** 28 woff2 files and
  four stylesheets are renamed in this cycle. This is a rename-only diff.
  If a reviewer prefers a single version-stamped directory segment instead
  of a per-file hash, the mechanism is interchangeable and the nginx rule
  is identical; per-file was chosen so one changed font does not invalidate
  the other 27.
