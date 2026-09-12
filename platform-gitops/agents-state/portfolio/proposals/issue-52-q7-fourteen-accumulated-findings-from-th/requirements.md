# Q7: fourteen accumulated findings from the polish wave

## Context

Six cycles of the polish wave (#45, #55, #47, #48, #49, #65/#66) left fourteen
real but individually small defects behind. Eleven of them are the same
mistake in different files: a guard that reports success without having
checked anything — `staleHashProblems()` iterating zero inline-script bodies,
`test/fonts.test.ts` matching a weight against any family, `collectHrefs()`
seeing only double-quoted `href`s, `check-headers.mjs` never probing
`/styles/`, and checks that throw out of a run instead of adding to the
`problems` accumulator so the report is truncated at the first failure. The
wave opened with exactly this shape: portfolio#45 shipped a CSP that disabled
the site's only script while four separate guards stayed green, and ADR-0006
(`src/content/adr/0006-browser-verified-security-headers.md`) responded by
requiring that "every such guard must be proven by mutation in both
directions". This cycle applies that rule retroactively to the guards this
repository already ships.

The remaining three findings are evidence and documentation: thirteen contrast
ratios that `scripts/check-contrast.mjs` computes and discards while
`docs/accessibility-checklist.md` quotes specific figures (4.81:1, 5.62:1,
3.64:1) for a reader to trust; a duplicated `leadTimeHours()` call per row in
`src/components/CycleTable.astro`; and three committed documents that no
longer match the code after the share-image, footer and cache-lifetime
changes. The cycle changes guards, tests and documentation only — no feature,
no content, no user-facing copy.

## User stories

- AS a reviewer of a portfolio pull request I WANT every mechanical guard to
  fail when its subject is absent or unparseable SO THAT a green CI run is
  evidence that something was checked rather than evidence that nothing was.
- AS a maintainer I WANT each check to accumulate problems instead of throwing
  SO THAT one missing asset produces a complete report rather than a report
  truncated at its first failure.
- AS a reader of `docs/accessibility-checklist.md` I WANT the contrast figures
  it quotes to appear in the CI log SO THAT the documented numbers are
  traceable to a run rather than to prose.
- AS a browser that has cached a font licence under `Cache-Control: immutable`
  I WANT that response never to carry a year-long immutable lifetime on an
  unhashed URL SO THAT a corrected licence text can actually reach readers.
- AS a future implementer I WANT the CI vendored-tree guard to name only paths
  that exist SO THAT a third of the guard is not silently covering nothing.

## Acceptance criteria (EARS)

### Class A — guards that pass because their subject is absent

- A1. WHEN `staleHashProblems(csp, html, label)` in `src/lib/csp.ts` is called
  with HTML from which `extractInlineScripts()` returns zero bodies THE SYSTEM
  SHALL push a problem naming `label` and stating that no inline `<script>`
  body was found to hash, instead of returning `[]`.
- A1a. WHEN `test/csp.test.ts` runs THE SYSTEM SHALL assert that HTML
  containing no `<script>` element at all, and HTML containing only
  `<script src="…"></script>`, each produce at least one problem whose message
  text matches the new "no inline script" wording.
- A2. WHILE `test/fonts.test.ts` checks reachable font weights THE SYSTEM SHALL
  resolve the `font-family` in effect for each rule that declares a numeric
  `font-weight` and require the generated `public/assets/fonts/fonts.<hash>.css`
  to declare an `@font-face` for that `(family, weight)` pair, not for that
  weight under any family.
- A2a. WHEN a stylesheet reaches JetBrains Mono at weight 600 or 700 (the
  weights pruned in #65, absent from `FAMILIES` in `scripts/vendor-assets.mjs`)
  THE SYSTEM SHALL report that pair as missing, and `test/fonts.test.ts` SHALL
  carry a mutation case over a synthetic stylesheet proving it, asserting on
  the failure message.
- A2b. WHILE a rule declares a `font-weight` but no `font-family` THE SYSTEM
  SHALL fall back to the existing family-blind assertion for that weight, so
  no assertion that holds today is weakened.
- A3. WHEN `npm test` runs THE SYSTEM SHALL verify, for every content-hashed
  file committed under `public/assets/` and every file named by
  `src/data/assets.json`, that the 8-hex segment in its filename equals the
  first 8 hex characters of SHA-256 over the file's own bytes — including the
  24 `.woff2` files that only `fonts.css` references and `fonts.<hash>.css`
  itself, not only the 9 hrefs `src/data/assets.json` names (the check added in
  #66 in `test/cache.test.ts`, which this criterion confirms and extends).
- A3a. WHEN `verifyExistingTree()` in `scripts/vendor-assets.mjs` validates a
  committed tree on the offline path THE SYSTEM SHALL reject a tree in which
  any hashed file's bytes do not hash to the 8-hex segment in its own name,
  rather than accepting it on non-emptiness alone.
- A3b. WHEN `checkHashedSubresources()` in `scripts/check-dist.mjs` examines a
  `/assets/` or `/styles/` reference on a built page THE SYSTEM SHALL verify
  that the referenced file exists under `dist/` and that its bytes hash to the
  8-hex segment in the referenced URL, not only that the URL is hash-shaped.
- A3c. WHEN `scripts/check-headers.mjs` probes a hashed `/assets/` path against
  the running container THE SYSTEM SHALL GET the response body and add a
  problem if its SHA-256 prefix differs from the hash in the served URL.

### Class B — guards that fail open

- B1. WHILE `scripts/check-contrast.mjs` and `scripts/check-links.mjs` each
  carry an `isEntryPoint()` function THE SYSTEM SHALL keep the hybrid form
  (`import.meta.main` when defined, a `realpathSync()` comparison of
  `process.argv[1]` against `fileURLToPath(import.meta.url)` below it), and a
  committed test SHALL fail if either file drifts to a bare `process.argv[1]`
  string comparison or to `import.meta.main` with no fallback.
- B1a. WHEN that test runs THE SYSTEM SHALL also assert, over synthetic source
  strings, that a bare-`process.argv[1]` form and a bare-`import.meta.main`
  form are each reported — proving the matcher discriminates.
- B2. WHEN `collectHrefs()` in `scripts/check-links.mjs` encounters an `<a>`
  element whose `href` is single-quoted or unquoted THE SYSTEM SHALL either
  extract that href for classification or count the element as an href that
  failed to parse.
- B2a. IF the count of `<a>` elements whose `href` failed to parse is non-zero
  THEN THE SYSTEM SHALL add a problem naming the count and the offending
  element text, and exit non-zero — so no `<a>` is ever both uncounted in
  `checked` and unrecorded in `skipped`, which is the guarantee
  `docs/link-check.md` sells the script on.
- B3. WHEN `discoverHashedAssetPath()` finds no hashed `/assets/` href in the
  home-page markup THE SYSTEM SHALL add a problem to the run's accumulator and
  continue with the remaining checks, instead of throwing out of `main()`.
- B3a. WHILE any other helper invoked by a check script can throw on missing or
  malformed input — specifically `siteOrigin()` in `scripts/check-dist.mjs`,
  `discoverAstroAsset()` in `scripts/check-headers.mjs` — THE SYSTEM SHALL
  convert that throw into an accumulated problem so the remaining checks still
  execute and the printed report is complete.
- B4. WHEN `scripts/check-headers.mjs` runs THE SYSTEM SHALL probe a path under
  `/styles/` (discovered from the home-page markup, falling back to a path
  guaranteed to 404 under `/styles/`, mirroring the existing `/_astro/`
  fallback) and assert the full eight-header set on that response.
- B4a. WHEN any single probe inside `scripts/check-headers.mjs` fails THE
  SYSTEM SHALL report every other probe's result too, and exit non-zero once,
  after printing all accumulated problems.

### Class C — evidence that is computed and discarded

- C1. WHEN `scripts/check-contrast.mjs` completes a run THE SYSTEM SHALL print
  one report line per content-link ratio it measured — twelve state x
  background x theme combinations plus the print pair, thirteen in total — in
  the existing shape `check-contrast: [<theme>] <fg> over <bg> = N:1 (min M:1,
  <kind>)`, on a passing run as well as a failing one.
- C1a. WHILE the exported `contentLinkProblems({ siteCssText, tokens })`
  signature is consumed by `test/check-contrast.test.ts` THE SYSTEM SHALL keep
  it returning an array of problem strings, exposing the report lines through a
  separate export computed from the same single code path.
- C2. WHEN `src/components/CycleTable.astro` renders a row THE SYSTEM SHALL
  call `leadTimeHours(entry.data)` exactly once per row and reuse the local
  value for both the `null` test and the `formatLeadTime()` call.

### Class D — assertions that test the wrong object

- D1. WHEN `test/home.test.ts` resolves `.hero-name`'s `font-family` var chain
  THE SYSTEM SHALL resolve each custom property against
  `src/styles/site.css` first and fall back to the hashed
  `public/assets/mctl/mctl.<hash>.css` only for properties site.css does not
  declare, so `--font-display` resolves to the declaration the page applies.
- D1a. WHEN `test/home.test.ts` runs THE SYSTEM SHALL assert that the
  `--font-display` value actually used came from `site.css`, so a future
  deletion of site.css's `:root { --font-display: … }` changes the test result
  rather than silently falling back.
- D2. WHEN `test/work.test.ts` guards the seven `CHIP_LITERALS` against
  `src/pages/work.astro` and `src/components/ProjectCard.astro` THE SYSTEM
  SHALL use the unanchored form — a plain escaped-literal regex over the raw
  file text (`assert.doesNotMatch(work, new RegExp(escaped))`) — in place of
  `hasAnchoredLiteral()` and its `stripComments()` preprocessing.
- D2a. WHILE the anchored matcher's control and mutation cases exist THE SYSTEM
  SHALL retarget them at the unanchored matcher rather than delete them, with
  the two cases whose expected result genuinely inverts (a literal occurring
  only inside a comment is now reported) rewritten to assert the new, broader
  behaviour and named as such in the commit message per acceptance criterion 3.
- D2b. WHEN the retargeted cases run THE SYSTEM SHALL prove both previously
  blind positions are now caught: a chip literal following a regex terminator's
  `//` (which `stripComments()` truncated) and a chip literal in a frontmatter
  shape outside both former alternatives.

### Class E — documentation that contradicts the code

- E1. WHEN `docs/hardening-notes.md`'s section "Open Graph image: SVG, not
  raster" is read THE SYSTEM SHALL describe the shipped state: `src/layouts/
  Base.astro` sets `og:image`/`twitter:image` to `/og.png`, rendered from
  `public/og.svg` at build time by `scripts/render-og.mjs` via
  `@resvg/resvg-wasm`, and the no-raster rule SHALL be attributed to the issue
  that set it rather than to ADR-0005, which speaks only to third-party
  origins.
- E1a. WHEN `docs/accessibility-checklist.md` line 20 ("SVG text
  alternatives") is read THE SYSTEM SHALL state that `public/og.svg` is the
  source the build rasterises to `/og.png`, and that `/og.png` is what the
  `og:image`/`twitter:image` meta tags name.
- E1b. WHEN the "Link purpose" row of `docs/accessibility-checklist.md` is read
  THE SYSTEM SHALL reflect `src/components/Footer.astro` as it stands: the
  GitHub anchor points at `https://github.com/mctlhq/portfolio` (the
  repository, not the organisation) and the release anchor's entire accessible
  text is a bare version number from `package.json`, with the "Release" label
  sitting outside the anchor.
- E1c. WHEN `scripts/vendor-assets.mjs`'s `ValidationError` message for a
  missing `.woff` entry is read THE SYSTEM SHALL not instruct the reader to
  commit `docs/og-image.md`, a file that does not exist and was never needed
  because `@resvg/resvg-wasm` installed cleanly.
- E2. WHEN `.hero-name`'s `font-size: min(var(--mctl-typography-font-size-hero),
  calc(var(--content-max) / 9.6))` in `src/styles/site.css` is read THE SYSTEM
  SHALL carry a comment deriving the divisor (`--content-max` is `768px`, so
  the cap is `80px`), or express it through a named custom property declared
  with that comment, matching how every other magic number in that file is
  documented.

### Class F — cache and serving

- F1. WHILE `location /assets/` in `nginx.conf` serves everything beneath it
  with `expires 1y` and `Cache-Control: public, immutable` THE SYSTEM SHALL
  ensure the three unhashed `public/assets/fonts/LICENSES/*.txt` files are not
  served under that lifetime — by giving `/assets/fonts/LICENSES/` its own
  longer-prefix `location` block that sets no year-long immutable lifetime and
  includes `/etc/nginx/security-headers.conf` exactly once.
- F1a. WHEN `test/nginx.test.ts` and `test/cache.test.ts` run THE SYSTEM SHALL
  assert the new block's existence, its single security-headers include, and
  the absence of `immutable`/`max-age=31536000` from it.
- F1b. WHEN `scripts/check-headers.mjs` runs THE SYSTEM SHALL probe
  `/assets/fonts/LICENSES/onest.txt` and add a problem if its `Cache-Control`
  contains `immutable` or `max-age=31536000`, or if any of the eight security
  headers is missing.
- F2. WHEN `.github/workflows/build.yml` runs its "Vendored tree matches the
  commit" step THE SYSTEM SHALL name only pathspecs that exist in the tracked
  tree: `public/styles` SHALL be dropped from `git diff --exit-code`, because
  `/public/styles/` is listed in `.gitignore` as generated output and is
  therefore never tracked, with a comment recording that `src/data/assets.json`
  is what pins the generated `site.<hash>.css`.

### Cycle-level criteria

- WHEN the cycle's pull request is opened THE SYSTEM SHALL have addressed every
  one of the fourteen items above: each is fixed, or, if a reviewer judges it
  wrong, recorded as closed-with-reasoning in the cycle's journal entry and the
  commit message — never silently skipped.
- WHILE any Class A or Class B fix is made THE SYSTEM SHALL carry a committed
  test that fails before the fix and passes after it, asserting on the failure
  message text rather than only on exit status or array length.
- IF an existing assertion genuinely must change THEN THE SYSTEM SHALL name it
  and the reason in the commit message; no assertion SHALL be weakened or
  deleted merely to make a fix easier.
- WHEN the cycle is complete THE SYSTEM SHALL have `npm test`, `npm run build`
  and `node scripts/check-dist.mjs` green, no `.js` file under `dist/`, and an
  equal count of `class="l en"` and `class="l ru"` on every built page.
- WHEN the cycle is complete THE SYSTEM SHALL leave `docs/hardening-notes.md`,
  `docs/accessibility-checklist.md` and `scripts/vendor-assets.mjs`'s
  `docs/og-image.md` reference consistent with the code as it then stands.

## Out of scope

- Anything requiring a browser: Lighthouse runs, HAR captures, screen-reader
  passes. Those remain reviewer steps, per `AGENTS.md`'s "Issue contract".
- Any new feature or content change. This cycle changes guards, tests and
  documentation only; no user-facing copy is added or altered, so no EN/RU
  pair is introduced.
- Reinstating a network-fetching link checker — settled in #46/#54 and recorded
  in `docs/link-check.md`.
- The journal backfill for #45, #55, #47, #48 and #49; that is the closing
  cycle after this one. (This cycle still writes its own journal entry, as
  every cycle does.)
- Adding `Cross-Origin-Embedder-Policy` or otherwise changing the eight-header
  set; only coverage of existing headers changes.
- Re-pinning any `@fontsource` or `@mctlhq/css` digest, or re-vendoring assets.
  No file under `public/assets/` changes bytes in this cycle.

## Open questions

- **B3 names the wrong file.** `discoverHashedAssetPath()` lives at
  `scripts/check-headers.mjs:69`, not in `scripts/check-dist.mjs`. Taken
  literally B3 and B4 are one file and one defect. Proceeding with the defect
  as described: fix `discoverHashedAssetPath()` where it actually is, and
  additionally convert the one throw of the same shape that does exist in
  `scripts/check-dist.mjs` (`siteOrigin()`, reached from `checkSitemap()`), so
  neither reading of B3 is left unaddressed.
- **F1 offers two branches.** This proposal takes "exclude `LICENSES/` from the
  immutable block" rather than "hash them like every other vendored file": a
  licence has to stay reachable at a stable, human-typable path to serve its
  purpose, nothing on the site links to it, and hashing it would make
  `pruneDir()`/`pruneManaged()` responsible for a directory their comments
  currently, deliberately, exclude. If a reviewer prefers hashing, the change
  is confined to `vendorFonts()` and the manifest.
- **D2 inverts two existing control assertions.** `hasAnchoredLiteral()`'s
  comment-only control cases assert that a literal inside a comment is *not*
  reported; the unanchored form reports it. They are rewritten rather than
  deleted and named in the commit message, which acceptance criterion 3
  permits. If a reviewer reads criterion 3 as forbidding even that, the
  fallback is to keep both matchers and assert on both — noted, not taken,
  because the issue asks for replacement.
- **A2's family resolution is deliberately partial.** Full per-selector
  cascade resolution is out of reach for a source-level test (the existing
  comment in `test/fonts.test.ts` says so). The check resolves the family
  declared in the same rule block and falls back to today's family-blind
  assertion where none is declared, so coverage strictly increases and nothing
  regresses.
- **A3c GETs one asset body in CI.** That is a second request against the local
  container only; it opens no external socket and does not touch the
  no-network posture of `scripts/check-links.mjs`.
