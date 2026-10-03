# Q6': share image, asset hashing, cache lifetime and the DevLoop diagram

## Context

Issue #50 produced a complete, review-verified implementation of Q6 — a
build-time OpenGraph PNG, content-hashed vendored assets with a year-long
`immutable` cache lifetime, a trimmed and preloaded font set with a
metric-matched fallback, a re-laid-out DevLoop diagram — and then could not
land it. Five implementer rounds ended with no commit because the shepherd
kept handing the implementer the whole bot-findings bundle, including
findings earlier commits had already fixed, so each round spent its budget
re-verifying settled work. The merge could not be forced: the `main
protection` ruleset has no administrator bypass, and dismissing the open
`CHANGES_REQUESTED` would have disabled the very gate that wave opened by
fixing. PR #64 is closed unmerged and its branch
`feat/agents-issue-50-q6-share-image-font-shift-cache-lifetime`, head
`2a37d4b`, is deliberately retained on the remote as the reference
implementation.

This cycle is a re-cut. Almost all of the work is reproduction of that
verified tree onto a fresh branch off `main`; the new engineering is three
narrow deltas. Two are named in the issue: the CI assertion that the
committed vendored tree matches what `npm run vendor` regenerates, and a
committed rationale for keeping all four font preloads rather than reducing
them to latin-only. The third is implied by acceptance criterion 7 and is
absent from `2a37d4b`: the coverage fix inside
`scripts/vendor-assets.mjs`'s `verifyExistingTree()` was proven by a manual
mutation during review, never by a committed test. The CI assertion is the
highest-value item: `src/data/assets.json` now carries content hashes that
`src/layouts/Base.astro` emits verbatim, so a drifted commit means a 404 on
every stylesheet, and it would surface only on the offline, network-less
build path this cycle exists to protect.

## User stories

- AS a reader sharing a link on Telegram, Slack, LinkedIn or X I WANT the
  preview card to carry an image SO THAT the link is not a bare text row —
  no social platform rasterises SVG.
- AS a returning Russian reader I WANT the Cyrillic Onest faces preloaded
  alongside the Latin ones SO THAT the first frame my browser paints — which
  is Russian, because the inline `<head>` script applies `localStorage.lang`
  before the body paints — does not swap fonts under me.
- AS a repeat visitor I WANT every vendored stylesheet and font served with
  a year-long `immutable` cache lifetime SO THAT a second visit re-downloads
  nothing, without ever being stranded on stale bytes after a content
  change.
- AS an operator building the image from a fresh, network-less clone I WANT
  `npm run build` to succeed offline SO THAT a registry or CDN outage cannot
  break a deploy.
- AS a reviewer of a future cycle I WANT CI to fail when the committed
  vendored tree has drifted from what `vendor` regenerates SO THAT a hash
  mismatch is caught in the pull request rather than as a total stylesheet
  404 in production.
- AS a reader of the approach page I WANT the DevLoop diagram to fit its
  labels and explain its dashed outlines SO THAT the Russian labels are not
  clipped and the control points are legible without opening a disclosure.

## Acceptance criteria (EARS)

### Share image

- WHEN `npm run build` runs THE SYSTEM SHALL execute `astro build` and then
  `node scripts/render-og.mjs`, which SHALL rasterise `public/og.svg` to
  `dist/og.png` at exactly 1200x630 using `@resvg/resvg-wasm` and the two
  committed TTF buffers under `scripts/fonts/`.
- WHILE `scripts/render-og.mjs` runs THE SYSTEM SHALL make no network
  request of any kind, and SHALL load no system font
  (`loadSystemFonts: false`).
- IF `rendered.width` or `rendered.height` differs from 1200x630 THEN
  `scripts/render-og.mjs` SHALL print a diagnostic naming both the actual
  and the expected dimensions and SHALL set a non-zero exit code.
- IF either file under `scripts/fonts/` cannot be read THEN
  `scripts/render-og.mjs` SHALL print a diagnostic telling the reader to run
  `npm run vendor` and SHALL set a non-zero exit code.
- WHEN `src/layouts/Base.astro` renders THE SYSTEM SHALL derive
  `ogImageUrl` from `new URL('/og.png', Astro.site)` and SHALL emit that same
  value as both `og:image` and `twitter:image`.
- WHEN `scripts/check-dist.mjs` runs THE SYSTEM SHALL fail IF any built page
  is missing either meta tag, IF the two values differ, IF the value is not a
  valid absolute URL, or IF its pathname does not resolve to a file under
  `dist/`.
- IF `dist/og.png` exists THEN `scripts/check-dist.mjs` SHALL read its IHDR
  chunk and SHALL fail unless the dimensions are exactly 1200x630.
- WHILE `@resvg/resvg-wasm` is the declared renderer THE SYSTEM SHALL keep
  it a pure-WebAssembly devDependency, so `npm ci` pulls no platform-gated
  binary and performs no postinstall network fetch (ADR-0005 holds).

### Content-hashed assets and the offline build

- WHILE `scripts/vendor-assets.mjs` writes any file under `public/assets/`
  or `public/styles/` THE SYSTEM SHALL write it only through `emit()`, which
  SHALL name it `<baseName>.<hash8><ext>` where `hash8` is the first 8 hex
  characters of that file's own SHA-256.
- WHEN `npm run vendor` completes its network step THE SYSTEM SHALL write
  `src/data/assets.json` with a `styles` array of exactly five hrefs ordered
  mctl, global, prose, fonts, site, and a `preload` object with exactly the
  keys `onestLatin400`, `onestLatin700`, `onestCyrillic400`,
  `onestCyrillic700`.
- WHEN `npm run vendor` completes its network step THE SYSTEM SHALL prune
  `public/assets/mctl/`, `public/assets/fonts/` and `public/styles/` of every
  file this run did not write, leaving no orphaned hashed file;
  `public/assets/fonts/LICENSES/` SHALL never be pruned.
- WHEN `src/layouts/Base.astro` renders a stylesheet link or a font preload
  link THE SYSTEM SHALL read its `href` from `src/data/assets.json` and SHALL
  never emit a literal asset path.
- WHEN `scripts/check-dist.mjs` runs THE SYSTEM SHALL fail IF any
  `<link|script|img|source>` on a built page references a `/assets/` or
  `/styles/` URL without an 8-hex content hash immediately before its
  extension.
- IF the network step of `npm run vendor` fails THEN THE SYSTEM SHALL fall
  back to `verifyExistingTree()`, which SHALL accept the committed tree only
  when: `src/data/assets.json` parses with five `styles` and a `preload`
  object; every href either names resolves to a non-empty file;
  `styles[0]`'s first line contains `MCTL_VERSION`; every `url(...)` in
  `styles[3]` resolves to a non-empty file; the `url(...)` **count** equals
  the count the `FAMILIES` table independently implies; each family's licence
  file is non-empty; and both `scripts/fonts/onest-latin-{400,700}-normal.ttf`
  are non-empty.
- IF the committed `fonts.css` is missing an `@font-face` entry that
  `FAMILIES` implies THEN `verifyExistingTree()` SHALL reject the tree, and
  `npm run vendor` with its network step failing SHALL exit non-zero.
- IF `npm run vendor`'s network step raises a `ValidationError` THEN THE
  SYSTEM SHALL exit non-zero without consulting the existing tree.
- WHEN `npm run build` runs in a fresh clone with no network available THE
  SYSTEM SHALL succeed, using the committed `public/assets/`,
  `src/data/assets.json` and `scripts/fonts/` TTFs.

### Cache lifetime

- WHILE `nginx.conf` is in force THE SYSTEM SHALL carry a `location /assets/`
  and a `location /styles/` block, each with `expires 1y;`, each with
  `add_header Cache-Control "public, immutable" always;`, each with
  `try_files $uri =404;`, and each with
  `include /etc/nginx/security-headers.conf;` **exactly once**.
- WHILE `nginx.conf` is in force THE SYSTEM SHALL keep `location /` free of
  both `expires` and `add_header Cache-Control`, so the HTML cache policy is
  unchanged.
- WHEN `test/nginx.test.ts` runs THE SYSTEM SHALL assert the total
  `security-headers.conf` include count in `nginx.conf` is exactly 7 (server
  level plus six location blocks) and that each of `= /healthz`, `= /readyz`,
  `/_astro/`, `/assets/`, `/styles/`, `/` carries exactly one.
- WHEN `nginx -t` runs during the Docker build THE SYSTEM SHALL pass.
- WHEN `scripts/check-headers.mjs` runs against the running container THE
  SYSTEM SHALL find a hashed `/assets/` href in the home page markup, HEAD
  it, and report a problem unless its `Cache-Control` contains both
  `max-age=31536000` and `immutable`; and SHALL report a problem if `/`'s
  `Cache-Control` contains either.

### CI drift gate (delta 2a)

- WHEN the `test` job of `.github/workflows/build.yml` runs THE SYSTEM SHALL,
  after `npm run build` and before `node scripts/check-links.mjs`, execute a
  step named `Vendored tree matches the commit` whose body is exactly:

  ```yaml
      - name: Vendored tree matches the commit
        run: git diff --exit-code -- public/assets public/styles src/data/assets.json
  ```

- IF the tree `npm run vendor` regenerated differs from the tree in the
  commit THEN that step SHALL fail the job.

### Font preloads (delta 2b)

- WHILE `src/layouts/Base.astro` is rendered THE SYSTEM SHALL emit exactly
  four `<link rel="preload" as="font" type="font/woff2" crossorigin>`
  elements, whose `href` values come from `assets.preload.onestLatin400`,
  `assets.preload.onestLatin700`, `assets.preload.onestCyrillic400` and
  `assets.preload.onestCyrillic700`.
- WHILE those four elements exist THE SYSTEM SHALL carry an Astro comment
  immediately above them recording why the pair is not reduced to latin-only.
  The comment SHALL be exactly:

  ```
    {/* Four preloads, not two. The `is:inline` script below applies
        `localStorage.lang` before the body paints, so a returning Russian
        reader paints Cyrillic on the first frame -- for that reader the
        cyrillic faces are the needed pair and latin is the wasted one.
        Which two are wasted is a property of the reader, not of the build.
        Preloading latin only would move the font swap this cycle exists to
        eliminate onto every Russian reader, half the audience of a
        deliberately bilingual site. Reviewed and rejected on #64; do not
        re-litigate without changing that script. */}
  ```

- WHILE `src/layouts/Base.astro` is rendered THE SYSTEM SHALL keep the four
  preload elements before the `is:inline` preference script, so the font
  fetches start ahead of any script evaluation.

### Fonts, fallback and the tests that guard them

- WHILE `FAMILIES` in `scripts/vendor-assets.mjs` is as committed THE SYSTEM
  SHALL declare Onest at weights 400/500/600/700, JetBrains Mono at 400/500
  and Instrument Serif at 400 normal plus italic, and the generated
  `fonts.css` SHALL contain exactly 28 `@font-face` rules across exactly 28
  vendored `.woff2` files on disk.
- WHILE `src/styles/site.css` is as committed THE SYSTEM SHALL declare an
  `Onest Fallback` `@font-face` sourcing `local('Arial')`,
  `local('Helvetica Neue')`, `local('Liberation Sans')`,
  `local('DejaVu Sans')`, `local('Roboto')` and `local('Noto Sans')`, with
  `size-adjust`, `ascent-override`, `descent-override` and
  `line-gap-override`, and SHALL set
  `--font-display: 'Onest', 'Onest Fallback', system-ui, -apple-system, sans-serif;`.
- WHEN `test/fonts.test.ts` runs THE SYSTEM SHALL assert
  `reachableWeights.size > 0` before comparing reachable weights against
  declared faces, so an empty scan is a failure rather than a vacuous pass;
  and `collectWeightTokens()` SHALL resolve the
  `--mctl-typography-font-weight-*` indirection.
- WHEN `test/vendor-assets.test.ts` runs THE SYSTEM SHALL copy the committed
  vendored tree into a temporary directory, delete exactly one `@font-face`
  block from the copied `fonts.css`, run `scripts/vendor-assets.mjs` from
  that copy with the network step forced to fail, and assert exit code 1;
  and SHALL assert exit code 0 for the same run against an unmutated copy.
- IF `process.env.VENDOR_FORCE_OFFLINE === '1'` THEN
  `scripts/vendor-assets.mjs` SHALL skip its network step and take the
  existing-tree verification branch, so the mutation test above needs no
  network and no registry.

### Diagram and journal

- WHILE `src/components/CycleDiagram.astro`'s `buildWide()` is as committed
  THE SYSTEM SHALL use `w = 130`, `topY = 30`, `botY = 130`, columns
  `13 + i * 146`, a `viewBox` of `0 0 ${cols[4] + w + 13} 200`, and straight
  vertical connectors for Implement to Review gate and Monitor to Issue.
- WHEN the approach page renders THE SYSTEM SHALL show a visible
  `<figcaption class="cycle-legend">` below the diagram carrying a CSS-drawn
  dashed swatch and the `ui.cycleLegend` copy in both languages.
- WHILE `src/i18n/ui.ts` is as committed THE SYSTEM SHALL carry
  `cycleLegend` with exactly this copy:
  - `en`: `Dashed outline: a control point. The cycle does not continue until this step passes.`
  - `ru`: `Пунктирная рамка: контрольная точка. Цикл не продолжается, пока этот шаг не пройден.`
- WHILE `src/content/journal/2026-09-12-share-image-font-preload-cache-lifetime.md`
  exists THE SYSTEM SHALL validate against the journal schema in
  `src/content.config.ts`, SHALL carry `title` and `decided` in both EN and
  RU, SHALL set `issue: https://github.com/mctlhq/portfolio/issues/65`,
  SHALL set `proposal_slug: issue-65-q6-share-image-asset-hashing-cache-lifet`,
  and SHALL carry `issue_opened_at` and `proposal_approved_at` only (no
  `merged_at`, `released_at`, `deployed_at`, `pr` or `release`).
  `issue_opened_at` SHALL be the `createdAt` of issue #65 and
  `proposal_approved_at` SHALL be this proposal's approval timestamp, each a
  quoted ISO 8601 string with a timezone.
- WHILE the journal entry exists THE SYSTEM SHALL carry exactly this
  `title` copy:
  - `en`: `Share image, font preload, cache lifetime and the DevLoop diagram`
  - `ru`: `Изображение для шеринга, предзагрузка шрифтов, время жизни кеша и диаграмма DevLoop`
- WHILE the journal entry exists THE SYSTEM SHALL carry exactly this
  `decided` copy:
  - `en`: `og:image and twitter:image now point at a build-time 1200x630 PNG rendered offline; Base.astro preloads the four Onest latin/cyrillic 400/700 faces from a hashed asset manifest, and a metric-adjusted fallback face in site.css closes the first-paint reflow gap. Every vendored asset under /assets/ and /styles/ carries a content hash and ships Cache-Control: public, max-age=31536000, immutable, while the HTML cache policy stays untouched. The wide DevLoop diagram is re-parameterised with a visible dashed-outline legend, and the hero name is capped so it stays on one line up to 1920px.`
  - `ru`: `og:image и twitter:image теперь указывают на PNG 1200x630, отрендеренный офлайн во время сборки; Base.astro предзагружает четыре начертания Onest (латиница и кириллица, 400 и 700) из хешированного манифеста активов, а подстроенный по метрикам резервный шрифт в site.css устраняет сдвиг макета при первой отрисовке. Каждый встроенный в сборку файл под /assets/ и /styles/ несёт хеш содержимого и отдаётся с Cache-Control: public, max-age=31536000, immutable, при этом политика кеширования HTML не меняется. Широкий вариант диаграммы DevLoop пересчитан заново с видимой подписью к пунктирной рамке, а имя в хиро ограничено так, что остаётся на одной строке вплоть до 1920px.`

### Suite-level

- WHEN `npm test` runs THE SYSTEM SHALL pass, with `test/fonts.test.ts`,
  `test/cycle-diagram.test.ts`, `test/cache.test.ts` and
  `test/vendor-assets.test.ts` all named in the `test` script in
  `package.json`.
- WHEN `npm run build` runs THE SYSTEM SHALL succeed, `dist/` SHALL contain
  no `.js` file, and every built page SHALL have an equal count of
  `class="l en"` and `class="l ru"` occurrences.
- WHEN `package-lock.json` is regenerated THE SYSTEM SHALL use
  `npm install --package-lock-only`, so no platform's optional binding is
  pruned out.

## Reviewer steps (not acceptance criteria)

These need a browser and cannot be met by a commit, per `AGENTS.md`:

- Lighthouse mobile on `/work/` reporting CLS below 0.1, confirming the
  `size-adjust` / `*-override` percentages on `Onest Fallback`.
- A HAR capture of `/`, `/work/` and `/colophon/` showing no third-party
  host.

## Out of scope

Everything on #52, fourteen items, explicitly including all of:

- The unhashed `LICENSES/*.txt` files now sitting under the new
  `location /assets/` `immutable` block. They stay unhashed.
- The two docs that contradict the code — `docs/hardening-notes.md`'s
  description of `public/og.svg` as the share image, and
  `docs/accessibility-checklist.md`'s note on it. Neither is updated here.
- The `9.6` divisor in `.hero-name`'s
  `min(var(--mctl-typography-font-size-hero), calc(var(--content-max) / 9.6))`.
  It is reproduced from `2a37d4b` unchanged.
- `scripts/check-headers.mjs`'s `discoverHashedAssetPath()` throwing instead
  of accumulating into `problems`. Reproduced as written.
- `test/home.test.ts:132` resolving `--font-display` against the shadowed
  `mctl.css` rather than the `site.css` override. Reproduced as written.
- Every remaining #52 item.

Also out of scope:

- Reviving, re-pushing or force-pushing branch
  `feat/agents-issue-50-q6-share-image-font-shift-cache-lifetime`. It stays
  on the remote, untouched, as the reference.
- Any change to `.github/workflows/claude-review.yml`,
  `.github/workflows/release-please.yml` or `.github/dependabot.yml` —
  reserved by `AGENTS.md`'s bootstrap boundary.
- Any new ADR. ADR-0005 already covers the WASM-only renderer constraint and
  holds unchanged.
- `mctl-agents#359` itself, the platform-side shepherd bundling defect that
  stalled #50. This cycle only avoids it by being a fresh, small-delta branch.

## Open questions

- **Journal `proposal_slug`.** The issue says to update the entry's `issue:`
  and its two timestamps, and is silent on `proposal_slug`, which in
  `2a37d4b` reads `issue-50-q6-share-image-font-shift-cache-lifetime`.
  Leaving it would point the rendered entry at a proposal that is not the one
  this work was built from. Proceeding with
  `issue-65-q6-share-image-asset-hashing-cache-lifet`.
- **Journal filename.** `2026-09-12-share-image-font-preload-cache-lifetime.md`
  already carries today's date, so it is kept verbatim; only the front matter
  changes.
- **`public/styles` in the drift gate is inert.** `.gitignore` in `2a37d4b`
  ignores `/public/styles/`, so `git diff -- public/styles` can never report
  anything. The step is reproduced verbatim as the issue specifies it, and
  real coverage for `site.<hash>.css` comes through `src/data/assets.json`,
  which is tracked and records that hash. Recorded, not changed.
- **Stale comment in `src/styles/site.css`.** Its header still says `npm run
  vendor` copies it to `public/styles/site.css`, without the hash. Not on the
  #52 list and not named by step 2, so it is left exactly as in `2a37d4b`
  rather than silently widening the diff.
- **Fallback metric percentages.** `size-adjust: 96%`, `ascent-override:
  96%`, `descent-override: 24%`, `line-gap-override: 0%` are the values
  `2a37d4b` carries; the issue calls them starting values confirmable only by
  the named Lighthouse reviewer step. Reproduced unchanged.
