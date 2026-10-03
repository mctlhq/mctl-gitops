# Tasks: issue-50-q6-share-image-font-shift-cache-lifetime

Order matters: task 1 changes how every asset href is produced, and tasks
2, 3 and 4 consume it. Tasks 7 to 11 (diagram, hero) are independent of
tasks 1 to 6 and can be done in either order.

## Asset hashing and the manifest

- [ ] 1. In `scripts/vendor-assets.mjs`, add an `emit(dir, baseName, ext, bytes)`
  helper that computes `createHash('sha256').update(bytes).digest('hex').slice(0, 8)`,
  writes `<baseName>.<hash><ext>` into `dir`, and returns the public href.
  Route every asset the script currently writes through it: the three
  `public/assets/mctl/*.css` files, every woff2 under
  `public/assets/fonts/`, the generated `fonts.css`, and the
  `src/styles/site.css` copy written to `public/styles/`. The `src: url(...)`
  entries inside the generated `fonts.css` must reference the hashed woff2
  hrefs. — DoD: `npm run vendor` writes only hashed filenames under
  `public/assets/` and `public/styles/`; no unhashed `.css` or `.woff2`
  remains there.

- [ ] 2. (depends on 1) Have `vendor-assets.mjs` write `src/data/assets.json`
  with a `styles` array (the five stylesheet hrefs, in the order
  `mctl`, `global`, `prose`, `fonts`, `site`) and a `preload` object keyed
  `onestLatin400`, `onestLatin700`, `onestCyrillic400`, `onestCyrillic700`.
  After writing it, prune every file under `public/assets/mctl/`,
  `public/assets/fonts/` (excluding `LICENSES/`) and `public/styles/` that
  is not named in the manifest. — DoD: running `npm run vendor` twice in a
  row leaves the tree byte-identical and leaves no orphaned hashed file;
  `src/data/assets.json` is committed.

- [ ] 3. (depends on 2) Rewrite `verifyExistingTree()` to validate the
  committed tree against `src/data/assets.json` (every href exists and is
  non-empty, plus the existing licence and `MCTL_VERSION` first-line
  checks) instead of reconstructing filenames from `FAMILIES`. — DoD: with
  the network unreachable, `npm run vendor` still exits 0 against the
  committed tree and exits non-zero if any manifest entry is missing.

- [ ] 4. (depends on 2) Update `.gitignore`: replace
  `/public/styles/site.css` with `/public/styles/`. — DoD: `git status` is
  clean after `npm run vendor` apart from intended changes.

## Fonts

- [ ] 5. (depends on 2) In `src/layouts/Base.astro`, import
  `src/data/assets.json` and render the five `<link rel="stylesheet">`
  elements from `styles`, in the same order they appear today. Add four
  `<link rel="preload" as="font" type="font/woff2" crossorigin>` elements
  built from `preload`, placed after `<meta name="viewport">` and before
  the first stylesheet link. No literal asset path remains in the file. —
  DoD: `npm run build` emits four preload links and five stylesheet links
  per page, every href hashed; `node scripts/check-no-metrics.mjs` passes.

- [ ] 6. In `scripts/vendor-assets.mjs`, change `FAMILIES`: Onest weights
  become `[400, 500, 600, 700]` (drop 300); JetBrains Mono weights become
  `[400, 500]` (drop 600 and 700); Instrument Serif is unchanged. Do not
  change any pinned version or `sha256` value. — DoD: `npm run vendor`
  emits 28 woff2 files, the generated `fonts.css` declares 28 `@font-face`
  rules, and Instrument Serif is still among them.

- [ ] 7. In `src/styles/site.css`, add the `@font-face { font-family: 'Onest Fallback'; ... }`
  block with `src: local('Arial'), local('Helvetica Neue'), local('Liberation Sans'), local('DejaVu Sans')`
  and `size-adjust: 96%; ascent-override: 96%; descent-override: 24%; line-gap-override: 0%;`,
  and add a `:root` rule redefining
  `--font-display: 'Onest', 'Onest Fallback', system-ui, -apple-system, sans-serif;`.
  Do not edit any file under `public/assets/mctl/` — they are SHA-256
  pinned. — DoD: `npm test` passes, including
  `test/a11y.test.ts`'s "no animation or transition in site.css" assertion
  and `scripts/check-contrast.mjs`.

## Share image

- [ ] 8. Add `@resvg/resvg-wasm` as a devDependency and regenerate the
  lockfile with `npm install --package-lock-only` (never a plain
  `npm install` — see AGENTS.md). Verify `npm ci` succeeds and pulls no
  platform-gated binary. — DoD: `npm ci --no-audit --no-fund` is green and
  the Docker build stage completes.

- [ ] 9. (depends on 8) In `scripts/vendor-assets.mjs`, extract
  `files/onest-latin-400-normal.woff` and `files/onest-latin-700-normal.woff`
  from the already-downloaded `@fontsource/onest` tarball, convert each
  WOFF1 container to TTF by inflating its tables with `zlib.inflateSync`
  and rewriting the sfnt table directory, and write the results to
  `scripts/fonts/` (build-only, never under `public/`). — DoD: two `.ttf`
  files are produced and `ttf`-magic (`0x00010000` or `true`) is verified;
  if the tarball carries no `.woff` entries, stop here and go to task 12.

- [ ] 10. (depends on 9) Add `scripts/render-og.mjs`: initialise
  `@resvg/resvg-wasm` from its local `.wasm` file, load the two TTF
  buffers, render `public/og.svg` at width 1200, and write `dist/og.png`.
  Wire it into `package.json` so it runs after `astro build` and before
  `scripts/check-dist.mjs` in the Dockerfile's build command. Point
  `og:image` and `twitter:image` in `src/layouts/Base.astro` at
  `new URL('/og.png', Astro.site)`. Leave `<link rel="icon">` on
  `/favicon.svg` and leave `public/og.svg` in the tree. — DoD:
  `npm run build && node scripts/render-og.mjs` produces a 1200x630
  `dist/og.png` with visible text, with no network access.

- [ ] 11. (alternative to 10, taken only if 8 or 9 fails) Leave both meta
  tags on `/og.svg`, commit `docs/og-image.md` naming each renderer
  attempted (`@resvg/resvg-wasm`, `@resvg/resvg-js`, `sharp`) and the exact
  reason each was rejected, and state the same in the commit message. —
  DoD: `docs/og-image.md` exists, is English-only, and names the blocking
  constraint concretely; items 1-7 and 12-16 still land.

## Cache lifetime

- [ ] 12. (depends on 1) In `nginx.conf`, add `location /assets/` and
  `location /styles/`, each with `expires 1y;`,
  `add_header Cache-Control "public, immutable" always;`,
  `include /etc/nginx/security-headers.conf;` and `try_files $uri =404;`.
  Leave `location /` and `location /_astro/` exactly as they are. — DoD:
  `nginx -t` passes in the Docker build.

- [ ] 13. (depends on 12) Update `test/nginx.test.ts`: the include count
  becomes 7, and the enumerated block list gains `/assets/` and `/styles/`.
  Add an assertion that `location /` contains no `expires` and no
  `add_header Cache-Control`. — DoD: `npm test` passes.

- [ ] 14. (depends on 12) In `scripts/check-headers.mjs`, add a target that
  GETs one hashed `/assets/` href discovered from the home page markup and
  asserts its `Cache-Control` contains `max-age=31536000` and `immutable`,
  and assert that the response for `/` contains neither. — DoD: the
  `Run container and check response headers` step in
  `.github/workflows/build.yml` passes.

## Diagram

- [ ] 15. Rewrite `buildWide()` in `src/components/CycleDiagram.astro`:
  `w = 130`, `h = 44`, `cols = [0,1,2,3,4].map((i) => 13 + i * 146)`,
  `topY = 30`, `botY = 130`, `viewBox = "0 0 " + (cols[4] + w + 13) + " 200"`.
  Replace the right-margin detour with a straight vertical from
  `(cols[4] + w/2, topY + h)` to `(cols[4] + w/2, botY)`, and the
  left-gutter return with the mirror at `cols[0]`. Leave `buildNarrow()`,
  `GATE`, the marker `<defs>` and the `<title>`/`<desc>` untouched. — DoD:
  the built wide `<svg>` carries `viewBox="0 0 740 200"`, ten 130-wide
  rects at y=30 and y=130, and `scripts/check-dist.mjs` reports the summed
  SVG bytes under 12288.

- [ ] 16. (depends on 15) Regenerate the `ALLOW` entry for
  `src/components/CycleDiagram.astro` in `scripts/check-no-metrics.mjs` by
  running the script and reading its report; the expected set is
  `[10, 13, 30, 40, 44, 60, 64, 130, 146, 200, 220, 320]` plus the existing
  separate `[11]` comment entry. Do not copy the list blindly — a stale
  value is itself a failure. — DoD: `node scripts/check-no-metrics.mjs`
  exits 0.

- [ ] 17. (depends on 15) In `src/styles/site.css`, inside the existing
  `@media (min-width: 800px)` block, add
  `:root[data-lang='ru'] .cycle-wide .cycle-node text { font-size: 12px; }`.
  Add `.cycle-legend` and `.cycle-legend-swatch` rules; the swatch is an
  inline-block drawn with `border: 2px dashed var(--accent)` and no
  animation or transition. — DoD: `npm test` passes, including
  `test/a11y.test.ts`.

- [ ] 18. (depends on 17) Add `cycleLegend` to `src/i18n/ui.ts` with
  exactly:
  - `en: 'Dashed outline: a control point. The cycle does not continue until this step passes.'`
  - `ru: 'Пунктирная рамка: контрольная точка. Цикл не продолжается, пока этот шаг не пройден.'`

  Render it in `src/pages/approach.astro` as a
  `<figcaption class="cycle-legend">` inside the existing
  `<figure class="cycle">`, directly after `<CycleDiagram />`, as an
  `.l en` / `.l ru` pair with a leading
  `<span class="cycle-legend-swatch" aria-hidden="true"></span>`. — DoD:
  `scripts/check-dist.mjs` reports equal `class="l en"` and `class="l ru"`
  counts on `dist/approach/index.html`; `test/approach.test.ts` still sees
  exactly three `<Details>` tags, one `open`, and no digit in the template.

## Hero

- [ ] 19. In `src/styles/site.css`, change `.hero-name` to
  `font-size: min(var(--mctl-typography-font-size-hero), calc(var(--content-max) / 9.6));`.
  Change nothing else about the rule. — DoD:
  `scripts/check-dist.mjs`'s hero assertions still pass and the computed
  size is 80px at and above a ~950px viewport.

## Tests

- [ ] T1. `test/fonts.test.ts` (new): every numeric `font-weight` value
  reachable from `src/styles/site.css` and the three
  `public/assets/mctl/*.css` files has a matching `@font-face` in the
  generated `fonts.css`; the generated `fonts.css` declares exactly the
  three vendored families and no other; Instrument Serif is among them.
- [ ] T2. `test/fonts.test.ts`: `src/layouts/Base.astro` renders exactly
  four `rel="preload"` links, each with `as="font"`, `type="font/woff2"`
  and `crossorigin`; the four hrefs come from `src/data/assets.json`'s
  `preload` object and each resolves to an existing file under
  `public/assets/fonts/`.
- [ ] T3. `test/fonts.test.ts`: `src/styles/site.css` declares an
  `Onest Fallback` `@font-face` carrying `size-adjust`, `ascent-override`,
  `descent-override` and `line-gap-override`, and a `:root` rule that
  places `'Onest Fallback'` after `'Onest'` in `--font-display`.
- [ ] T4. `test/cycle-diagram.test.ts` (new): for each variant and each
  language, `maxLabelLength * 0.58 * labelFontSize <= boxWidth - 16`, with
  the label set read from `ui.cycleNodes` and the font sizes read from
  `src/styles/site.css`. Also asserts the wide `viewBox` is
  `0 0 740 200` and the narrow one is unchanged.
- [ ] T5. `test/cycle-diagram.test.ts`: `ui.cycleLegend` exists with
  non-empty `en` and `ru`, and `src/pages/approach.astro` renders it as one
  `.l en` and one `.l ru` occurrence inside `<figure class="cycle">`.
- [ ] T6. `test/cache.test.ts` (new): `nginx.conf` gives `/assets/` and
  `/styles/` `expires 1y` plus `Cache-Control "public, immutable"`, each
  with exactly one `include /etc/nginx/security-headers.conf;`; and
  `location /` carries neither `expires` nor `add_header Cache-Control`.
- [ ] T7. `test/cache.test.ts`: every href in `src/data/assets.json`
  matches `\.[0-9a-f]{8}\.(css|woff2)$` and points at a file that exists.
- [ ] T8. `test/home.test.ts` (extend): the `.hero-name` rule in
  `src/styles/site.css` sets `font-size` with a `min(` or `clamp(` upper
  bound.
- [ ] T9. `scripts/check-dist.mjs` (extend): `og:image` and
  `twitter:image` are equal on every built page and resolve to a file under
  `dist/`; if `dist/og.png` exists, its IHDR is 1200x630; no built page
  references an `/assets/` or `/styles/` subresource whose filename lacks
  an 8-hex content hash.
- [ ] T10. Register every new test file in the `test` script in
  `package.json`, in the existing `node --test ...` list.
- [ ] T11. Full gate: `npm test`, `npm run build`,
  `node scripts/check-dist.mjs`, `node scripts/check-links.mjs`, the Docker
  build and `scripts/check-headers.mjs` against the running container all
  green.

## Reviewer steps (not acceptance criteria)

- Lighthouse mobile on `/work/` reports CLS below 0.1 (baseline 0.17).
- A HAR capture of `/`, `/work/` and `/colophon/` shows no third-party
  host and no fetch of a font family the page does not use.
- Pasting the apex URL into Telegram shows the card image (only if item 1
  landed rather than taking the stop path).
- `Dmitrii Mashkov` and `Дмитрий Машков` render on one line at 768px,
  1100px, 1440px and 1920px.
- The wide diagram shows no empty band and no label touching its border in
  either language.

## Rollback

Every item is independently revertible, and none of them changes data or a
URL a reader can bookmark.

- **Whole cycle.** `git revert` the merge commit and re-run
  `npm run vendor && npm run build`. The vendor script regenerates the
  unhashed tree from the same pinned versions and digests, so the revert is
  byte-exact.
- **Cache only.** Delete the two new `location` blocks from `nginx.conf`
  and revert `test/nginx.test.ts` and the `check-headers.mjs` addition.
  Readers who cached a hashed `/assets/` URL for a year are unharmed: the
  HTML is never cached long, so the next page load hands them whatever
  hrefs the current build emits. No stale-asset recovery problem exists in
  either direction, which is the point of hashing the filenames.
- **Share image only.** Revert `src/layouts/Base.astro`'s two meta tags to
  `/og.svg`, drop `scripts/render-og.mjs` and the `@resvg/resvg-wasm`
  devDependency, and regenerate the lockfile with
  `npm install --package-lock-only`. `public/og.svg` was never removed.
  Social platforms re-scrape on the next share.
- **Font fallback only.** If `size-adjust` makes CLS worse on some
  platform, delete the `Onest Fallback` `@font-face` block and the `:root`
  `--font-display` override from `src/styles/site.css`. Preload and
  pruning are independent and stay.
- **Diagram only.** Revert `src/components/CycleDiagram.astro`,
  `src/pages/approach.astro`, the `cycleLegend` key in `src/i18n/ui.ts`,
  the `.cycle-legend*` rules in `src/styles/site.css`, and the
  `CycleDiagram.astro` `ALLOW` entry in `scripts/check-no-metrics.mjs`
  together — the `ALLOW` entry must move with the geometry or the gate
  fails on a stale value.
- **Deployment.** If a deployed image misbehaves, roll back with
  `mctl_rollback_service` to the previous image tag; no `kubectl`, no
  hand-edited gitops values.
