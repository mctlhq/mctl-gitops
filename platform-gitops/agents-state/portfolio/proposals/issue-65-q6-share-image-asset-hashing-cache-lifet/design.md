# Design: issue-65-q6-share-image-asset-hashing-cache-lifet

## Current state

`main` is at merge commit `3692358`. The relevant machinery today:

**Asset vendoring.** `scripts/vendor-assets.mjs` downloads `@mctlhq/css`
0.5.0 (`mctl.css`, `global.css`, `prose.css`) from `https://ui.mctl.ai/0.5.0/`
and three SHA-256-pinned `@fontsource/*` tarballs, writes each font as
`public/assets/fonts/<slug>-<subset>-<weight>-<style>.woff2` with a literal
`writeFile`, generates `public/assets/fonts/fonts.css` with
`src: url('/assets/fonts/<file>') format('woff2')`, and `copyFile`s
`src/styles/site.css` to `public/styles/site.css`. Every name is static. Its
`FAMILIES` table currently declares Onest at 300/400/500/600/700 and
JetBrains Mono at 400/500/600/700 — 40 faces, of which `fonts.css` is 136
lines. `verifyExistingTree()` is the offline fallback taken when the network
step throws a non-`ValidationError`; it reconstructs every expected filename
from `FAMILIES` and checks each is non-empty.

**Layout.** `src/layouts/Base.astro` hardcodes five `<link rel="stylesheet">`
elements (`/assets/mctl/mctl.css`, `global.css`, `prose.css`,
`/assets/fonts/fonts.css`, `/styles/site.css`), has no font preloads at all,
and sets `ogImageUrl = new URL('/og.svg', Astro.site)` for both `og:image`
and `twitter:image`. Its `is:inline` `<head>` script applies
`localStorage.lang` and `localStorage.theme` to `documentElement.dataset`
before the body paints — this is the fact step 2b of the issue turns on.

**Serving.** `nginx.conf` has four location blocks (`= /healthz`,
`= /readyz`, `/_astro/`, `/`). Only `/_astro/` gets `expires 1y` plus
`add_header Cache-Control "public, immutable" always`. Every block, plus
server level, carries `include /etc/nginx/security-headers.conf;` exactly
once — five includes total, asserted by `test/nginx.test.ts`. The reason is
recorded at the top of `security-headers.conf`: a location-level `add_header`
discards the entire inherited set, so a location that adds a header and
omits the include silently loses all eight security headers.
`/assets/` and `/styles/` have no block at all today, so they fall through to
`location /` and are served with the HTML cache policy.

**Build pipeline.** `package.json`: `prebuild` is `npm run vendor && npm test`,
`build` is `astro build`. So `npm run build` regenerates the vendored tree
with network *before* any test runs — every assertion in the suite runs
against a freshly regenerated tree, never the one in git. `astro.config.mjs`
sets `inlineStylesheets: 'never'` because the CSP has no `unsafe-inline`.
`scripts/check-dist.mjs` is invoked not by `npm test` but by the `Dockerfile`:
`RUN npm run build && node scripts/check-dist.mjs && node scripts/csp-hash.mjs`.
`.github/workflows/build.yml` has a `test` job (`npm ci`, `npm run build`,
`node scripts/check-links.mjs`) and a `build` job that builds the image, runs
the container and executes `scripts/check-headers.mjs` against it.

**The reference implementation.** Branch
`feat/agents-issue-50-q6-share-image-font-shift-cache-lifetime`, head
`2a37d4b`, is on the remote and fetchable. `git diff main..2a37d4b` is 69
files, +1200/-219, and is review-verified. It is the authoritative
description of most of this cycle.

## Proposed solution

### Shape of the work

Cut a fresh branch from `main` and reproduce `2a37d4b`'s tree, then apply
three deltas. Reproduction is best done by taking the tree wholesale —
`git checkout 2a37d4b -- .` from a branch based on `main`, or an equivalent
per-path checkout — rather than by re-deriving each file from the issue's
prose summary. `git diff main..2a37d4b` is authoritative; the issue's bullet
list is orientation. Do **not** reuse, re-push or force-push the old branch:
it is the reference and must stay intact on the remote, and a fresh branch is
also what keeps this cycle out of the shepherd's stale-findings bundle
(`mctl-agents#359`) that killed #50.

### What the reproduced tree does

- **`scripts/render-og.mjs`** (new, 97 lines) rasterises `public/og.svg`
  (already a 1200x630 `viewBox` with three `<text>` elements) to
  `dist/og.png` via `@resvg/resvg-wasm`, initialised from
  `node_modules/@resvg/resvg-wasm/index_bg.wasm` read off disk. It sets
  `loadSystemFonts: false` and passes the two `scripts/fonts/*.ttf` buffers
  with `defaultFontFamily: 'Onest'` and `sansSerifFamily: 'Onest'`. That last
  pair is the trick that leaves `og.svg` untouched as the single source of
  the composition: the SVG's `font-family="Arial, Helvetica, sans-serif"`
  resolves to nothing for the first two names on `node:24-alpine`, so the
  generic `sans-serif` keyword is what actually matches, and it is redirected
  to the loaded Onest buffers. `package.json`'s `build` becomes
  `astro build && node scripts/render-og.mjs`; because `check-dist.mjs` runs
  from the `Dockerfile` *after* `npm run build`, `dist/og.png` exists by the
  time `checkOgPngDimensions()` looks for it. `Base.astro` switches
  `ogImageUrl` to `/og.png`. `.dockerignore` excludes only `node_modules`,
  `dist`, `.git` and `.astro`, so `COPY . .` already carries
  `scripts/fonts/` into the builder stage — no Dockerfile change is needed.

- **Content hashing through a single seam.** `emit(dir, baseName, ext, bytes,
  managed)` is the only function in `vendor-assets.mjs` that writes under
  `public/`: it computes `sha256HexBuffer(buf).slice(0, 8)`, writes
  `<baseName>.<hash><ext>`, records the filename in the `managed` map, and
  returns the public href. `vendorMctl()`, `vendorFonts()` (both the woff2
  files and the generated `fonts.css`) and `copySiteCss()` all route through
  it. `pruneManaged()` then calls `pruneDir()` once per managed directory
  (`MCTL_DIR`, `FONTS_DIR`, `SITE_CSS_DEST_DIR`), deleting every file this run
  did not write — non-recursive, so `public/assets/fonts/LICENSES/` is never
  touched. The resulting manifest is written to `src/data/assets.json` as
  `{ styles: [mctl, global, prose, fonts, site], preload: {four keys} }`;
  the ordering is load-order-significant and is asserted by
  `test/cache.test.ts`.

- **`Base.astro` reads the manifest.** Five hardcoded `<link>` elements
  collapse to `{assets.styles.map((href: string) => <link rel="stylesheet"
  href={href} />)}`, and the four preloads take their `href` from
  `assets.preload.*`. No literal asset path remains in the layout — which is
  precisely why the drift gate of delta 2a matters.

- **`nginx.conf`** gains `location /assets/` and `location /styles/`, each a
  copy of the `/_astro/` block's shape: `expires 1y;`, `add_header
  Cache-Control "public, immutable" always;`, `include
  /etc/nginx/security-headers.conf;`, `try_files $uri =404;`. The include is
  load-bearing, not decorative. `test/nginx.test.ts` moves its total include
  count from 5 to 7, extends the per-block list to six locations, asserts all
  three `immutable` blocks keep both their `add_header` and their `try_files`,
  and adds a negative assertion that `location /` carries neither `expires`
  nor `add_header Cache-Control`. `scripts/check-headers.mjs` adds
  `discoverHashedAssetPath()` and a live `HEAD` of one hashed `/assets/` URL,
  since `test/cache.test.ts` only reads `nginx.conf`'s source text and can
  never prove a real response.

- **Font set trimmed.** `FAMILIES` drops Onest 300 and JetBrains Mono
  600/700, taking `fonts.css` from 40 faces to 28 and from 136 lines to 28.
  `scripts/check-no-metrics.mjs`'s `ALLOW` entry for `CycleDiagram.astro` is
  updated to the new geometry literals. `src/styles/site.css` declares the
  `Onest Fallback` face and redefines `--font-display` to
  `'Onest', 'Onest Fallback', system-ui, -apple-system, sans-serif`. The
  `local()` list is six names, not the four the issue's summary mentions:
  Arial and Helvetica Neue cover macOS and Windows, Liberation Sans and
  DejaVu Sans most Linux, and Roboto plus Noto Sans are what make the
  override apply on Android and the remaining Linux desktops at all — without
  them `local()` falls through the whole list and the metric overrides
  silently do nothing there. The reference tree is authoritative; all six
  stay.

- **Two checks stop being vacuous.** `verifyExistingTree()` is rewritten to
  validate against the manifest rather than reconstructing filenames (it
  cannot reconstruct them any more — they are hashed), and crucially
  cross-checks the `url(...)` count in the committed `fonts.css` against
  `FAMILIES.reduce((sum, fam) => sum + fam.weights.length *
  fam.styles.length * fam.subsets.length, 0)`. Without that count, url()
  resolution is only self-consistency: every reference present resolves, so a
  stale `fonts.css` missing entries would pass. It also requires both
  `scripts/fonts/*.ttf` to be non-empty, because an offline tree that reports
  success and then fails at `render-og.mjs` is not a complete tree.
  `test/fonts.test.ts` gains `assert.ok(reachableWeights.size > 0)` and
  `collectWeightTokens()`, which resolves the
  `--mctl-typography-font-weight-*` indirection — `font-weight` is never a
  literal digit anywhere in this codebase, so without token resolution the
  scan matched nothing and the assertion passed regardless of what
  `fonts.css` declared.

- **Committed TTFs.** `woffToTtf()` reverses a WOFF1 container back to a bare
  sfnt (44-byte header, per-table `zlib.inflateSync`, rewritten table
  directory with 4-byte padding), and `extractOnestTtfs()` pulls
  `package/files/onest-latin-{400,700}-normal.woff` out of the already
  SHA-256-verified tarball and writes both to `scripts/fonts/`. Those two
  files are committed and `.gitignore` records why: they cannot be
  regenerated from the committed woff2 tree alone, and without them the
  offline `npm run build` path this cycle protects does not hold. If the
  tarball carries no `.woff` entry for either weight, `main()` raises a
  `ValidationError` naming the documented stop path.

- **Diagram and journal.** `buildWide()` is re-parameterised (`w = 130`,
  `topY = 30`, `botY = 130`, `cols = [0..4].map(i => 13 + i * 146)`,
  `viewBox: 0 0 ${cols[4] + w + 13} 200`), removing the empty band and
  replacing the two margin-routed connectors with straight verticals inside
  the columns the joined nodes already share. `ui.cycleLegend` and a
  `<figcaption class="cycle-legend">` on `approach.astro` add the visible
  legend, styled with a CSS-drawn dashed swatch so the component keeps its
  one-`<svg>`-per-variant shape and stays under the 12288-byte SVG budget.
  `test/cycle-diagram.test.ts` (new) encodes the label-fits-in-box arithmetic
  for both variants and both languages, reading geometry out of the component
  source rather than hardcoding it.

### Delta 2a — the CI drift gate

Insert into `.github/workflows/build.yml`'s `test` job, after
`- run: npm run build` and before `- run: node scripts/check-links.mjs`:

```yaml
      - name: Vendored tree matches the commit
        run: git diff --exit-code -- public/assets public/styles src/data/assets.json
```

Placement is the whole point. `npm run build` runs `prebuild`, which runs
`npm run vendor` with network; by the time this step executes, the working
tree holds a freshly regenerated vendored tree, and `git diff` compares it
against the commit. This is reproduced verbatim from the issue, including
`public/styles` — which `.gitignore`'s `/public/styles/` entry makes inert,
since an ignored path can never appear in `git diff`. That is harmless and
deliberate: `src/data/assets.json` is tracked and records
`site.<hash>.css`'s hash, so a drifted `site.css` is caught through the
manifest rather than through the ignored directory.

`AGENTS.md` explicitly un-reserves `build.yml`: "This file can only make the
pre-merge gate stricter", which is exactly what this step does.

### Delta 2b — the preload rationale

`2a37d4b` adds the four preload elements but carries no comment explaining
them, which is how the latin-only review finding arose. Add the Astro
comment block from `requirements.md` immediately above the four `<link
rel="preload">` elements in `src/layouts/Base.astro`. An Astro `{/* ... */}`
comment is compiled away and emits nothing, so it costs no bytes in `dist/`
and cannot perturb `test/csp.test.ts`, `scripts/csp-hash.mjs` or the inline
script's SHA-256. `test/fonts.test.ts`'s existing preload assertion matches
`/<link\s+rel="preload"[^>]*>/g` against the source, which a preceding
comment does not affect.

### Delta 3 — a committed test for the coverage fix

Acceptance criterion 7 asks that `verifyExistingTree()`'s rejection of an
under-populated `fonts.css` be "proven by a test that mutates the tree".
`2a37d4b` has no such test: the proof was a manual mutation during review.
Two small pieces close it.

First, a named test seam in `vendor-assets.mjs`'s `main()`, as the first
statement inside the existing `try`:

```js
  if (process.env.VENDOR_FORCE_OFFLINE === '1') {
    throw new Error('VENDOR_FORCE_OFFLINE=1 -- skipping the network step (test seam)');
  }
```

A plain `Error` (not a `ValidationError`) lands in the existing
network-failure branch, which warns and calls `verifyExistingTree()`. The
seam only ever *skips* work and routes to the stricter verification path, so
it cannot loosen a production run, and it makes the test network-free.

Second, `test/vendor-assets.test.ts` (new):

1. `fs.cp` the committed `scripts/`, `public/`, `src/data/assets.json` and
   `src/styles/site.css` into a fresh `mkdtemp` directory.
2. Control: `spawnSync('node', [tmp/scripts/vendor-assets.mjs], { env: {
   ...process.env, VENDOR_FORCE_OFFLINE: '1' } })` exits 0. Because
   `vendor-assets.mjs` derives `ROOT` from `import.meta.url`, running the
   *copied* script points every path at the copy — no second seam is needed,
   and the real tree is never written to.
3. Mutant: on a second copy, delete exactly one `@font-face { ... }` block
   from the copied `fonts.css` (located through `src/data/assets.json`'s
   `styles[3]`) and assert the same run exits 1 with
   `vendor: no valid existing tree` on stderr.

Step 2 is the control that makes step 3 meaningful — without it a test could
pass because the harness is broken rather than because the guard works.
`copySiteCss()` runs before the `try`, so it emits `site.<hash>.css` into the
copy with the same hash the manifest already names; the manifest still
resolves. `pruneManaged()` is never reached on the offline path, so nothing
in the copy is deleted.

`package.json`'s `test` script gains `test/vendor-assets.test.ts` alongside
`test/fonts.test.ts`, `test/cycle-diagram.test.ts` and `test/cache.test.ts`.

## Alternatives

**Reopen or force-push the #50 branch instead of cutting a fresh one.**
Dropped. The `main protection` ruleset has no administrator bypass, so the
open `CHANGES_REQUESTED` on PR #64 blocks the merge regardless of new
commits, and dismissing it would disable the gate this wave opened by
fixing. Worse, reusing the branch keeps the accumulated `codex_findings`
bundle attached, which is the platform defect (`mctl-agents#359`) that
exhausted five implementer rounds. A fresh branch starts the review ledger
empty. The old branch is also the only surviving copy of the reference tree,
so overwriting it would destroy the artifact this proposal depends on.

**Re-derive the tree from the issue's prose rather than from `git diff
main..2a37d4b`.** Dropped, and the issue says so outright. The summary is
demonstrably lossy: it names four `local()` families where the code carries
six, and it describes the `nginx` blocks as serving
`Cache-Control: public, max-age=31536000, immutable` where the code composes
that from `expires 1y` plus `add_header Cache-Control "public, immutable"`
(as `/_astro/` already does). Re-deriving would silently discard
review-verified detail.

**Reduce the four preloads to latin-only, as the #64 review asked.**
Dropped, with the reason now committed next to the code. `Base.astro`'s
`is:inline` script applies `localStorage.lang` before the body paints, so a
returning Russian reader paints Cyrillic on the first frame. Which two faces
are wasted is a property of the reader, not of the build, and latin-only
would move the swap this cycle exists to eliminate onto half the audience of
a deliberately bilingual site.

**Prove criterion 7 by exporting a pure helper (`fontsCssUrlCount` /
`expectedFontFileCount`) and mutating a string in memory.** Dropped as the
primary approach: it tests the arithmetic but not the wiring, so a future
refactor that stops calling the helper from `verifyExistingTree()` would keep
the test green. Running the real script against a mutated on-disk copy tests
the behaviour the criterion names. The cost is one three-line env seam, which
is cheaper than the false confidence.

**Make `render-og.mjs` an Astro integration hook instead of a `build` script
step.** Dropped. `astro build` writes `dist/` and an integration's
`astro:build:done` would work, but the current shape keeps the ordering
legible in `package.json` (`astro build && node scripts/render-og.mjs`) and
keeps the renderer runnable on its own for debugging. It also avoids putting
a WASM initialisation inside Astro's plugin lifecycle.

**Use `sharp` or `@resvg/resvg-js` for the PNG.** Dropped, and already
settled by ADR-0005 plus `AGENTS.md`'s lockfile hazard note: both ship
native bindings as `optionalDependencies`, which an ordinary `npm install`
prunes down to the implementer's linux/x64, after which `npm ci` in the
Dockerfile refuses the tree. A librsvg-backed renderer would additionally
need system fontconfig and would render the three `<text>` elements empty on
`node:24-alpine`.

## Platform impact

**Migrations.** None in the data sense. There is a one-way URL migration:
every `/assets/**` and `/styles/**` URL changes, and the old unhashed URLs
stop existing. Nothing links to them except `src/data/assets.json`, and the
old paths were served with the HTML cache policy (no `immutable`), so no
client holds a long-lived cache entry for them. `dist/og.svg` continues to be
published as a `public/` passthrough even though nothing references it any
more.

**Backward compatibility.** `nginx.conf`'s new blocks are additive; the
`/_astro/`, `/healthz`, `/readyz` and `/` blocks are unchanged, so HTML,
health endpoints and Astro's own hashed bundles keep their current behaviour.
The CSP, HSTS and the other six security headers are unchanged in content —
but the two new location blocks are exactly the case
`security-headers.conf`'s header warns about, so the `include` in each is a
correctness requirement, and `test/nginx.test.ts`'s include-count assertion
(5 to 7) is what keeps it from being dropped later.

**Resource impact.** `@resvg/resvg-wasm` adds roughly 1 MB of WASM to
`devDependencies` — builder stage only, never shipped. `scripts/fonts/` adds
about 65 KB of committed TTF. The pruned font set removes 12 woff2 files from
the served tree (Onest 300 x4 subsets, JetBrains Mono 600/700 x4 subsets),
roughly 130 KB, and `fonts.css` drops from 136 lines to 28. Net served bytes
go down; repeat-visit bytes go to near zero for `/assets/` and `/styles/`.
Build time grows by one WASM rasterisation of a three-text-element SVG —
well under a second.

**Risks and mitigations.**

- *A drifted commit 404s every stylesheet.* This is the failure the cycle
  introduces and delta 2a is its mitigation. It is severe precisely because
  it is invisible on the online path: `prebuild` regenerates the tree before
  any test, so tests pass either way; only an offline build serves the
  committed hrefs. The `git diff --exit-code` step is the only thing that
  compares the two.
- *`emit()` bypassed by a future writer.* Mitigated in both directions:
  `pruneManaged()` deletes anything under the managed directories that the
  current run did not write, and `checkHashedSubresources()` in
  `check-dist.mjs` fails the Docker build if any built page references an
  unhashed `/assets/` or `/styles/` URL.
- *The `immutable` block also covers `LICENSES/*.txt`, which are unhashed.*
  Known, on the #52 list, explicitly out of scope. They are not referenced by
  any page and are not pruned.
- *The env seam is a production bypass.* It only short-circuits into the
  stricter offline verification path, never past a check, and it is named
  and commented as a test seam. `npm run vendor` without the variable is
  byte-for-byte the behaviour of `2a37d4b`.
- *`woffToTtf()` carries per-table checksums over unchanged and does not
  recompute `head.checksumAdjustment`.* Documented in the function's own
  comment: resvg's `ttf-parser` does not validate them, and the buffer is
  build-only and never served. If a future renderer does validate, the
  symptom is a loud failure in `render-og.mjs`, not a silent bad PNG —
  `check-dist.mjs` also re-reads the IHDR.
- *`package-lock.json` regeneration.* Adding `@resvg/resvg-wasm` requires
  `npm install --package-lock-only` per `AGENTS.md`; a plain `npm install`
  prunes other platforms' optional bindings and breaks `npm ci` in the
  Dockerfile. The reference lockfile diff is +11 lines and can be reproduced
  from `2a37d4b` directly.
- *Shepherd findings-bundle recurrence.* `mctl-agents#359` is unfixed. The
  mitigation available inside this repository is to keep the branch fresh and
  the delta over the verified tree small — three changes, each independently
  checkable — so a review round has little surface to re-open.
