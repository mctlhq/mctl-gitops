# Design: issue-52-q7-fourteen-accumulated-findings-from-th

## Current state

### The guard layer

`portfolio` gates itself with five node scripts and 25 `node --test` files
(`package.json`'s `test` script names them all explicitly):

- `scripts/check-contrast.mjs` — WCAG ratios over the vendored tokens. Its
  `main()` builds a `report` array of `check-contrast: [<theme>] <fg> (<hex>)
  over <bg> (<hex>) = N:1 (min M:1, <kind>)` lines for the seven `PAIRS` x two
  themes and prints them (lines 326-354). `contentLinkProblems({ siteCssText,
  tokens })` (line 260) computes thirteen further ratios — three link states x
  two backgrounds x two themes, plus print — and returns only the failures;
  the passing ratios are discarded, and `main()` prints a bare count line
  instead (line 358). `docs/accessibility-checklist.md`'s "Contrast in both
  themes" row quotes 4.81:1, 5.62:1 and 3.64:1 from exactly those discarded
  numbers.
- `scripts/check-links.mjs` — walks `dist/`, extracts hrefs, resolves them.
  `HREF_ATTR_RE = /\shref="([^"]*)"/i` (line 50) matches only a double-quoted
  attribute; `collectHrefs()` (line 54) pushes only on a match, so an `<a>`
  with a single-quoted or unquoted href silently produces nothing — neither
  `checked` nor `skipped`. `docs/link-check.md` sells the script on "the
  `href` of every `<a>` element" and on "nothing skipped is ever mistaken for
  something that passed".
- `scripts/check-dist.mjs` — the post-build gate. Every check returns a
  `problems` array that `main()` concatenates (lines 799-891), with one
  exception: `siteOrigin()` (line 714) throws when `astro.config.mjs` has no
  `site`, aborting `checkSitemap()` and therefore `main()` before the report
  prints. `checkHashedSubresources()` (line 486) tests only
  `HASHED_SUFFIX_RE = /\.[0-9a-f]{8}\.[a-zA-Z0-9]+$/` against the URL string —
  shape, never bytes.
- `scripts/check-headers.mjs` — the runtime gate, run from
  `.github/workflows/build.yml` against a container. `discoverHashedAssetPath()`
  (line 69 — the symbol B3 attributes to `check-dist.mjs`) throws when the home
  page carries no hashed `/assets/` href, aborting `main()` past the
  `problems` accumulator; `discoverAstroAsset()` (line 47) can throw the same
  way on a failed `fetch`. `targets` covers `/`, `/healthz`, an `/_astro/`
  path and a 404 path; `/styles/` — which got its own `location` block in
  nginx.conf during #65 — is never probed, so its eight headers are unverified
  at runtime.
- `scripts/vendor-assets.mjs` — the vendoring script. `emit()` (line 57) is the
  single place that computes `sha256HexBuffer(buf).slice(0, 8)` and writes
  `<base>.<hash8><ext>`; that identity is what makes nginx's year-long
  `immutable` safe. `verifyExistingTree()` (line 596) is the offline path: it
  checks non-emptiness, `MCTL_VERSION` on styles[0], a `url()` count against
  `FAMILIES`, licence presence and the two build-only TTFs — never a hash.

`src/lib/csp.ts` is the established pattern for shared guard logic: a
zero-import module (only `node:crypto`) importable by both `.mjs` scripts and
`node --test`, so "the same regex" and "the same quoting function" are enforced
by identity rather than by two hand-kept copies. `staleHashProblems()` (line
106) loops over `extractInlineScripts(html)`; with zero bodies the loop body
never runs and it returns `[]`, so `check-headers` prints `OK -- all responses
carried the expected headers` without having compared a hash. Only
`scripts/csp-hash.mjs` failing the build on zero inline bodies makes that
unreachable today.

### The tests

- `test/csp.test.ts` is the model this cycle follows: every failing case
  asserts on the message text (`assert.match`), and the header comment says
  why.
- `test/cache.test.ts` already carries the #66 content-addressing test —
  "every hashed href in src/data/assets.json actually hashes to its own file
  bytes" — over the 5 `styles` and 4 `preload` hrefs. The 24 `.woff2` files
  that only `fonts.<hash>.css` references, and `fonts.<hash>.css` itself, are
  outside it.
- `test/fonts.test.ts`'s reachable-weight test collects weights from
  `site.css` + the three vendored stylesheets and asserts each has *some*
  `@font-face` at that weight. Its own comment concedes "the mechanical proxy
  this repository can check without per-selector font-family resolution", so
  JetBrains Mono 600/700 could vanish and Onest 600/700 would keep the
  assertion green.
- `test/home.test.ts` reads `mctlCss` via `resolveMctlCssPath()` (line 132) and
  builds `customProperties` from it alone (line 133), then resolves
  `.hero-name`'s `font-family: var(--font-display)` through that map — while
  `src/styles/site.css:39-41` declares `:root { --font-display: 'Onest',
  'Onest Fallback', system-ui, … }`, which is what the page actually applies.
- `test/work.test.ts` guards seven `CHIP_LITERALS` with `hasAnchoredLiteral()`
  (line 53) over `stripComments()`-preprocessed source: a quoted-string
  alternative plus a `>[^<]*\bX\b[^<]*<` element-text alternative. Six control
  and mutation tests pin that helper.
- `test/vendor-assets.test.ts` already has the harness A3a needs: `makeTreeCopy()`
  copies `scripts/`, `public/`, `src/data/assets.json` and `src/styles/site.css`
  into an `mkdtemp` directory and `runVendorOffline()` spawns the copied script
  with `VENDOR_FORCE_OFFLINE=1`, so an on-disk mutation can be proven without
  touching the repository tree.

### Serving and CI

`nginx.conf` gives `/_astro/`, `/assets/` and `/styles/` `expires 1y` plus
`add_header Cache-Control "public, immutable" always`, each including
`/etc/nginx/security-headers.conf` once. `public/assets/fonts/LICENSES/
{instrument-serif,jetbrains-mono,onest}.txt` are the only three tracked files
under `public/assets/` without a content hash (`git ls-files public` confirms),
and they sit under `location /assets/`. `.gitignore` lists `/public/styles/` as
generated output, so `.github/workflows/build.yml`'s `git diff --exit-code --
public/assets public/styles src/data/assets.json` names one pathspec that is
never tracked.

`src/components/CycleTable.astro:46` and `:54` call `leadTimeHours(entry.data)`
twice per row; `src/lib/journal.ts:70` parses two timestamps and can throw a
`RangeError`, so the duplicate is both wasted work and a second origin for the
same throw. `src/pages/colophon/journal/[...slug].astro:52` already does it the
right way (`const leadTime = leadTimeHours(data)`).

`src/styles/site.css:218` caps the hero with `calc(var(--content-max) / 9.6)`;
`--content-max: 768px` (line 72), so the cap is `80px`. The journal entry
`src/content/journal/2026-09-12-share-image-font-preload-cache-lifetime.md`
records the intent — "the hero name is capped so it stays on one line up to
1920px" — but `site.css` itself carries no comment, unlike every other magic
number in the file (e.g. the `table.cycles` note at line 574).

## Proposed solution

Fourteen changes, grouped exactly as the issue groups them. One new shared
module, four script edits, six test edits, three document edits, one nginx
block, one CI line.

### New module: `src/lib/content-hash.ts`

The Class A3 fix needs the same "does this name match these bytes" predicate in
four places (`vendor-assets.mjs`, `check-dist.mjs`, `check-headers.mjs`,
`test/cache.test.ts`). Following `src/lib/csp.ts` exactly — zero imports beyond
`node:crypto`, no `astro:content`, no `zod`, so plain `node --test` and every
`.mjs` script can import it — add:

```ts
export const HASHED_NAME_RE = /\.([0-9a-f]{8})\.[a-zA-Z0-9]+$/;
export function contentHash8(bytes: Buffer | string): string;   // sha256 → first 8 hex
export function hashInName(nameOrUrl: string): string | null;   // the embedded hash8
export function hashMismatch(nameOrUrl: string, bytes): string | null; // message or null
```

`emit()` in `scripts/vendor-assets.mjs` is rewritten to call `contentHash8()`
so the producer and every checker share one derivation by identity, which is
the property `docs/hardening-notes.md` already claims for the CSP hash.

### Class A

- **A1** — `staleHashProblems()` gains a leading
  `if (bodies.length === 0) { problems.push(\`${label}: CSP hash was not
  compared -- no inline <script> body found in the response\`); return problems; }`.
  `test/csp.test.ts` gains two cases (no `<script>` at all; only
  `<script src="…">`), both `assert.match`-ing the new wording, plus a
  re-assertion that the existing single-inline-script fixture still returns
  `[]`.
- **A2** — `test/fonts.test.ts` gains `collectFamilyWeightPairs(css, tokens,
  familyTokens)`: it splits the stylesheet into top-level rules (the
  `parseTopLevelRules` shape already used by `test/link-cascade.test.ts` and
  `test/work.test.ts`), and for each rule that resolves a numeric
  `font-weight`, resolves the rule's own `font-family` — literal stack or
  `var(--font-*)` chain resolved against `site.css` then `mctl.css` — to the
  first family `fonts.css` declares. Pairs with a family are asserted against
  `collectFaceRules(fontsCss)` as `(family, weight)`; rules with no family in
  their own block keep today's family-blind assertion. New mutation cases run
  the helper over synthetic stylesheets: `font-family: var(--font-mono);
  font-weight: 600` must be reported (JetBrains Mono 600 was pruned), the same
  at 500 must not, and the assertion message must name both family and weight.
- **A3** — `test/cache.test.ts` keeps its #66 test verbatim and adds one that
  walks the committed `public/assets/` tree, selects every filename matching
  `HASHED_NAME_RE`, and asserts `hashMismatch()` returns `null` for each —
  covering the 24 non-manifest `.woff2` files and `fonts.<hash>.css`.
  `verifyExistingTree()` adds the same predicate to each file it already
  stats (manifest hrefs, every `url()` in fonts.css), so the offline path
  rejects a name/bytes divergence instead of accepting non-emptiness.
  `checkHashedSubresources()` becomes `async`, reads the referenced file under
  `DIST_DIR`, and pushes a problem when the file is missing or its bytes do not
  hash to the URL's segment. `scripts/check-headers.mjs` GETs the discovered
  hashed asset (instead of HEADing it) and compares `contentHash8(body)` to the
  URL's segment.

### Class B

- **B1** — both `isEntryPoint()` bodies stay as they are; a new
  `test/entry-point.test.ts` reads both script files, isolates the
  `function isEntryPoint()` block, and asserts it contains both
  `import.meta.main` and a `realpathSync(` comparison against
  `fileURLToPath(import.meta.url)`. The matcher is a local
  `entryPointProblems(source, label)` so the same function can be run over
  synthetic bare-`process.argv[1]` and bare-`import.meta.main` sources, each
  asserted to produce a message naming the missing half.
- **B2** — `HREF_ATTR_RE` widens to
  `/\shref=(?:"([^"]*)"|'([^']*)'|([^\s"'>=`]+))/i`, and `collectHrefs()`
  returns `{ hrefs, unparsed }` where `unparsed` collects the opening tags of
  `<a>` elements that carry an `href=` substring no alternative matched.
  `run()` threads `unparsed` into `problems` with a count and the offending
  tags, so the "counted or skipped, never dropped" guarantee holds in both
  branches the issue allows. `test/links.test.ts` gains fixture pages with
  single-quoted and unquoted hrefs (resolved, counted in `checked`) and a
  malformed `<a href=>` (reported by message).
- **B3/B3a** — `discoverHashedAssetPath(html, problems)` returns `null` and
  pushes `check-headers: no hashed /assets/ href found in the home page
  markup` instead of throwing; the caller skips the asset probe and continues.
  `discoverAstroAsset()` is wrapped so a failed `fetch` of `/` becomes a
  problem plus a null home page rather than an abort, and `main()` is wrapped
  in a `try/catch` that turns any residual throw into one final problem before
  the report prints. The same treatment is applied to
  `scripts/check-dist.mjs`'s `siteOrigin()`: `checkSitemap()` catches it and
  returns a problem, so the sitemap failure no longer truncates the report.
- **B4** — a `discoverStylesPath(html)` mirroring the `/_astro/` fallback
  pattern: match `/styles/[^"'<>]+\.[0-9a-f]{8}\.css` in the home-page markup
  (Base.astro always links `assets.json`'s styles[4]), else probe
  `/styles/probe-check-headers.css` expecting 404. Either way the response
  goes through `checkHeaders()`, so `/styles/`'s eight headers are verified
  at runtime. The `/assets/fonts/LICENSES/onest.txt` probe from F1b joins the
  same target list, with an explicit assertion that its `Cache-Control`
  carries neither `immutable` nor `max-age=31536000`.

### Class C

- **C1** — extract `contentLinkChecks({ siteCssText, tokens })` returning
  `{ problems, report }`; `contentLinkProblems()` becomes a one-line wrapper
  returning `.problems` (unchanged signature and return shape, so every
  assertion in `test/check-contrast.test.ts` stands untouched), and a new
  exported `contentLinkReport()` returns `.report`. Report lines reuse the
  existing shape — `check-contrast: [<theme>] content link "<label>" (<hex>)
  over <bg> (<hex>) = N:1 (min 4.5:1, text)` and a `[print]` line — and
  `main()` prints them alongside the existing seven-pair report, before the
  problem list. The final `OK` line's count becomes `report.length` over both
  sets. `test/check-contrast.test.ts` gains an assertion that
  `contentLinkReport()` yields thirteen lines and that the figures
  `docs/accessibility-checklist.md` quotes (4.81, 5.62) appear among them.
- **C2** — `CycleTable.astro`'s `entries.map((entry) => (…))` becomes a block
  body with `const leadTime = leadTimeHours(entry.data);` used for both the
  `null` test and `formatLeadTime(leadTime)`.

### Class D

- **D1** — `test/home.test.ts` builds `customProperties` by merging
  `parseCustomProperties(mctlCss)` with `parseCustomProperties(siteCss)`,
  site.css winning on conflict, and adds an assertion that `--font-display`'s
  resolved source was site.css (its value contains `Onest Fallback`, which
  mctl.css does not declare) so the fallback cannot silently take over.
- **D2** — `hasAnchoredLiteral()`/`stripComments()` are replaced by
  `chipLiteralProblems(source, label)`, which for each of the seven literals
  applies `new RegExp(escapeRegExp(literal))` to the raw file and returns a
  message naming file and literal. The guard test becomes
  `assert.doesNotMatch(work, …)` / `assert.doesNotMatch(card, …)` in effect,
  via that helper. The six control/mutation cases are retargeted at the new
  helper, including the two whose expected result inverts (comment-only
  occurrences are now reported — broader, and named in the commit message per
  criterion 3), plus two new cases for the previously blind positions: a
  literal after a regex terminator's `//`, and a literal in a frontmatter shape
  outside both former alternatives.

### Class E

- **E1** — `docs/hardening-notes.md`'s "Open Graph image" section is retitled
  and rewritten to describe `/og.png` rendered by `scripts/render-og.mjs` from
  `public/og.svg` with `@resvg/resvg-wasm`, the 1200x630 IHDR check in
  `checkOgPngDimensions()`, and the `og:image`/`twitter:image` equality check
  in `checkOgImageMeta()`; the no-raster attribution moves off ADR-0005, whose
  text is about third-party origins only.
  `docs/accessibility-checklist.md`'s line-20 "SVG text alternatives" row says
  `public/og.svg` is the build-time source of `/og.png`; the "Link purpose" row
  names the repository GitHub href and the bare-version release anchor.
  `scripts/vendor-assets.mjs`'s stop-path `ValidationError` message drops the
  `docs/og-image.md` instruction and points at the actual remedy (revert the
  meta tags to `/og.svg` and record it in the journal entry).
- **E2** — `site.css` declares `--hero-name-cap: calc(var(--content-max) /
  9.6); /* 768px / 9.6 = 80px -- the largest size at which the longer hero
  string ("Дмитрий Машков") stays on one line inside --content-max; see the
  2026-09-12 journal entry */` next to `--content-max`, and `.hero-name` reads
  `min(var(--mctl-typography-font-size-hero), var(--hero-name-cap))`.
  `test/home.test.ts`'s existing `.hero-name` assertions are unaffected
  (they read `font-family`, not `font-size`).

### Class F

- **F1** — `nginx.conf` gains, before `location /assets/`:

  ```
  location /assets/fonts/LICENSES/ {
      add_header Cache-Control "public, max-age=3600" always;
      include /etc/nginx/security-headers.conf;
      try_files $uri =404;
  }
  ```

  nginx picks the longest matching prefix location, so licence texts leave the
  immutable block without any change to `/assets/`. `test/nginx.test.ts`'s
  block-count expectations and `test/cache.test.ts` are extended accordingly,
  and `check-headers.mjs` proves it at runtime (B4 above).
- **F2** — `.github/workflows/build.yml`'s guard becomes
  `git diff --exit-code -- public/assets src/data/assets.json`, with a comment
  noting that `/public/styles/` is gitignored generated output whose hash is
  pinned by `src/data/assets.json`'s fifth entry.

## Alternatives

1. **Fix only the eleven Class A/B items and defer C-F to another cycle.**
   Rejected: the issue's own argument is that fixing them together is the
   point, and C1/E1 are the evidence and documentation halves of the same
   defect (a number computed but never shown; a document asserting what the
   code no longer does). Splitting would leave `docs/` false for another cycle.
2. **Duplicate the hash predicate in each checker instead of adding
   `src/lib/content-hash.ts`.** Rejected for the reason `src/lib/csp.ts`
   exists: two hand-kept copies of "the hash a name claims" is precisely the
   drift that Class A3 is about. The cost is one new file with four tiny
   exports and no dependency beyond `node:crypto`.
3. **F1 by hashing the three licence texts through `emit()`.** Considered and
   documented as the reviewer-selectable branch. Dropped as the default: a
   licence must stay reachable at a stable path to satisfy the OFL's
   "distributed with the font" intent, nothing links to it so a hashed URL
   would be undiscoverable, and it would drag
   `public/assets/fonts/LICENSES/` into `pruneManaged()`, which both
   `pruneDir()`'s and `pruneManaged()`'s comments currently exclude on purpose.
4. **B2 by widening the regex only, without an unparsed counter.** Rejected:
   the issue allows either branch, but a regex can always meet a shape it does
   not anticipate, and the counter is what makes the guarantee in
   `docs/link-check.md` structurally true instead of true-for-now. Both are
   implemented; the counter is the backstop.
5. **D2 by keeping `hasAnchoredLiteral()` alongside the unanchored form.**
   Rejected: the issue asks for replacement, and keeping a matcher whose only
   consumer is gone leaves a second definition of "hard-coded" in the file —
   the same two-copies problem again. Retargeting its controls preserves the
   coverage without preserving the matcher.

## Platform impact

- **Migrations:** none. No data, no schema, no deployment-time change. No file
  under `public/assets/` changes bytes, so no content hash moves and no cached
  URL is invalidated.
- **Backward compatibility:** `contentLinkProblems()`'s signature and return
  shape are preserved deliberately so `test/check-contrast.test.ts` needs no
  edit. `checkHashedSubresources()` becoming `async` is internal to
  `check-dist.mjs` (its one call site is already inside an `await` loop).
  `collectHrefs()`'s return shape changes from `string[]` to
  `{ hrefs, unparsed }`, which `test/links.test.ts` asserts on directly — that
  test is updated in the same commit, and its existing assertions are
  preserved, not weakened.
- **Runtime/resource impact:** `npm test` gains a walk of `public/assets/`
  (36 files, ~1.5 MB of SHA-256) — a fraction of a second. CI gains two HTTP
  requests against the local container (`/styles/…`, the LICENSES probe) and
  turns one HEAD into a GET. `nginx` gains one `location` block.
- **Risks and mitigations:**
  - *A1 could fail a real build.* `scripts/csp-hash.mjs` already fails on zero
    inline bodies, so the new problem is reachable only if that guard is
    removed first — which is exactly when it should fire. Mitigated by the two
    new `test/csp.test.ts` cases pinning the message.
  - *A2's family resolution could produce false failures* on a rule whose
    family is inherited rather than declared. Mitigated by the explicit
    fallback to today's family-blind assertion when a rule declares no family,
    so the check can only become stricter where it has real information.
  - *A3a could reject a legitimate committed tree* if any hashed file's bytes
    ever diverged from its name. That is the defect the check exists to find;
    the mitigation is to run `npm run vendor` with network access, which
    re-derives both name and bytes from `emit()`.
  - *F1's new location block could shadow `/assets/` unexpectedly.* nginx
    longest-prefix semantics make this deterministic; it is proven twice — at
    source level by `test/nginx.test.ts`, at runtime by the
    `check-headers.mjs` probe against the built image.
  - *D2's inverted control assertions* are the one place an existing
    assertion's meaning changes. Mitigated by rewriting rather than deleting
    them and naming the change in the commit message, as acceptance criterion 3
    requires.
  - *Scope.* Fourteen items in one pull request is a large diff for a
    one-cycle-at-a-time repository (`AGENTS.md`). Mitigated by the task
    ordering below: the shared module lands first, then one commit per class,
    each self-contained and independently revertible.
