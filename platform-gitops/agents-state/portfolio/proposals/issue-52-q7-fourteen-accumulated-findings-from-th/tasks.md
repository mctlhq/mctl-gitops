# Tasks: issue-52-q7-fourteen-accumulated-findings-from-th

- [ ] 1. Add `src/lib/content-hash.ts` — a zero-import module (only
      `node:crypto`, modelled on `src/lib/csp.ts`) exporting `HASHED_NAME_RE`,
      `contentHash8(bytes)`, `hashInName(nameOrUrl)` and
      `hashMismatch(nameOrUrl, bytes)`. — DoD: importable from both `.mjs`
      scripts and `node --test` with no build step; `hashMismatch` returns
      `null` on a match and a message naming the expected and actual hash on a
      mismatch.
- [ ] 2. Rewrite `emit()` in `scripts/vendor-assets.mjs` to derive its hash via
      `contentHash8()` (depends on 1) — DoD: `npm run vendor` under
      `VENDOR_FORCE_OFFLINE=1` still exits 0; no committed filename changes;
      the producer and every checker now share one derivation.
- [ ] 3. A1: `staleHashProblems()` in `src/lib/csp.ts` pushes a problem when
      `extractInlineScripts(html)` returns zero bodies — DoD: the message
      carries `label` and states that no inline `<script>` body was found, so
      `check-headers` can no longer print `OK` without having compared a hash.
- [ ] 4. A2: make `test/fonts.test.ts`'s reachable-weight check family-aware
      via a local `collectFamilyWeightPairs()` that resolves each rule's own
      `font-family` (literal or `var()` chain through site.css then mctl.css)
      and asserts `(family, weight)` against `collectFaceRules(fontsCss)`;
      rules declaring no family keep today's family-blind assertion — DoD:
      JetBrains Mono 600/700 reachable from a stylesheet fails; no existing
      assertion in the file is removed.
- [ ] 5. A3: extend content verification (depends on 1) — `test/cache.test.ts`
      keeps its #66 test and adds a walk of `public/assets/` asserting
      `hashMismatch()` is `null` for every `*.{hash8}.*` file; `verifyExistingTree()`
      in `scripts/vendor-assets.mjs` applies the same predicate to every file it
      stats; `checkHashedSubresources()` in `scripts/check-dist.mjs` becomes
      async and verifies the referenced `dist/` file's bytes;
      `scripts/check-headers.mjs` GETs the hashed asset and compares
      `contentHash8(body)` to the URL segment — DoD: all four call sites use the
      shared helper, and a byte flipped in any hashed file fails `npm test`.
- [ ] 6. B1: add `test/entry-point.test.ts` with an
      `entryPointProblems(source, label)` matcher run over
      `scripts/check-contrast.mjs` and `scripts/check-links.mjs` — DoD: both
      files pass today; a bare `process.argv[1]` comparison and a bare
      `import.meta.main` each produce a message naming the missing half; the
      new file is added to `package.json`'s `test` script.
- [ ] 7. B2: widen `HREF_ATTR_RE` in `scripts/check-links.mjs` to double, single
      and unquoted forms, and return `{ hrefs, unparsed }` from `collectHrefs()`,
      threading `unparsed` into `run()`'s `problems` with a count — DoD: an
      `<a>` with a single-quoted or unquoted href is counted in `checked`; an
      unparseable `href=` is reported by message and exits non-zero; nothing is
      both uncounted and unrecorded.
- [ ] 8. B3: `discoverHashedAssetPath()` in `scripts/check-headers.mjs` returns
      `null` and pushes a problem instead of throwing; `discoverAstroAsset()`'s
      fetch failure becomes a problem; `main()` gains a `try/catch` that turns a
      residual throw into a final accumulated problem — DoD: with no hashed
      asset in the markup, every remaining probe still runs and the report is
      complete before the non-zero exit.
- [ ] 9. B3a: `checkSitemap()` in `scripts/check-dist.mjs` catches
      `siteOrigin()`'s throw and returns it as a problem — DoD: a missing
      `site:` in `astro.config.mjs` no longer truncates the report at that
      point.
- [ ] 10. B4: add a `/styles/` probe to `scripts/check-headers.mjs` (discovered
      from the home-page markup, falling back to a guaranteed-404
      `/styles/probe-check-headers.css`, mirroring the `/_astro/` pattern)
      (depends on 8) — DoD: the `/styles/` response goes through
      `checkHeaders()` so all eight headers are verified at runtime; the fallback
      branch logs why it was taken.
- [ ] 11. C1: split `contentLinkChecks({ siteCssText, tokens })` out of
      `contentLinkProblems()` in `scripts/check-contrast.mjs`, returning
      `{ problems, report }`; keep `contentLinkProblems()` as a wrapper
      returning `.problems`; export `contentLinkReport()`; print the thirteen
      report lines from `main()` in the existing
      `[theme] fg over bg = N:1 (min M:1, kind)` shape — DoD: a passing run's
      CI log carries 4.81:1 and 5.62:1; `test/check-contrast.test.ts`'s existing
      assertions compile and pass unchanged.
- [ ] 12. C2: compute `leadTimeHours(entry.data)` once per row in
      `src/components/CycleTable.astro` — DoD: exactly one call per row;
      `npm run build` and `node scripts/check-dist.mjs` still green (the
      colophon cycle table renders identically).
- [ ] 13. D1: merge `parseCustomProperties(siteCss)` over
      `parseCustomProperties(mctlCss)` in `test/home.test.ts` so
      `--font-display` resolves against `src/styles/site.css` first — DoD: the
      resolved stack contains `Onest Fallback` (declared only in site.css), and
      an assertion pins that so a silent fallback to mctl.css cannot pass.
- [ ] 14. D2: replace `hasAnchoredLiteral()`/`stripComments()` in
      `test/work.test.ts` with a plain escaped-literal regex over the raw file,
      retargeting the six control/mutation cases at the new matcher — DoD: the
      two cases whose expected result inverts (comment-only occurrences are now
      reported) are rewritten, not deleted, and named in the commit message per
      acceptance criterion 3; the seven literals still pass against
      `work.astro` and `ProjectCard.astro`.
- [ ] 15. E1: correct `docs/hardening-notes.md`'s Open Graph section (PNG via
      `scripts/render-og.mjs` + `@resvg/resvg-wasm`; no-raster rule no longer
      attributed to ADR-0005), `docs/accessibility-checklist.md`'s line-20 "SVG
      text alternatives" row and its "Link purpose" row (repository GitHub href;
      bare-version release anchor), and drop the `docs/og-image.md` instruction
      from `scripts/vendor-assets.mjs`'s stop-path `ValidationError` message —
      DoD: no sentence in the three documents contradicts the code as it stands
      after this cycle; `grep -r "og-image.md"` returns nothing.
- [ ] 16. E2: declare `--hero-name-cap: calc(var(--content-max) / 9.6)` next to
      `--content-max` in `src/styles/site.css` with a comment deriving it
      (`768px / 9.6 = 80px`, the cap that keeps the longer hero string on one
      line), and have `.hero-name` read it — DoD: no undocumented magic number
      remains in that declaration; the computed value is unchanged at 80px.
- [ ] 17. F1: add a `location /assets/fonts/LICENSES/` block to `nginx.conf`
      that sets no year-long immutable lifetime and includes
      `security-headers.conf` exactly once; extend `test/nginx.test.ts` and
      `test/cache.test.ts`; add the LICENSES probe to `scripts/check-headers.mjs`
      (depends on 10) — DoD: a licence text is served with the eight security
      headers and without `immutable`/`max-age=31536000`, proven at source level
      and against the built image.
- [ ] 18. F2: drop `public/styles` from the `git diff --exit-code` pathspec in
      `.github/workflows/build.yml` and add a comment recording that
      `/public/styles/` is gitignored generated output pinned by
      `src/data/assets.json` — DoD: the guard names only tracked paths; the
      vendored-tree check still fails on a drifted `public/assets` or manifest.
- [ ] 19. Write the cycle journal entry
      `src/content/journal/<date>-q7-polish-wave-findings.md` with `issue`,
      `proposal_slug`, `pr`, the five timestamps, `interventions: []` and EN/RU
      title and summary, recording any item a reviewer judged wrong and closed
      rather than fixed — DoD: `npm test` (`test/journal.test.ts`) and
      `node scripts/check-dist.mjs`'s colophon counts stay green with the new
      entry.
- [ ] 20. Full gate: `npm test`, `npm run build`, `node scripts/check-dist.mjs`,
      `node scripts/check-links.mjs` (depends on 1-19) — DoD: all green,
      `dist/` carries no `.js`, and `class="l en"` equals `class="l ru"` on
      every built page.

## Tests

- [ ] T1. A1 mutation (`test/csp.test.ts`): HTML with no `<script>`, and HTML
      with only `<script src="…">`, each produce a problem whose message
      matches the new "no inline `<script>` body" wording; the existing
      single-inline-script fixture still returns `[]`. Fails before task 3.
- [ ] T2. A2 mutation (`test/fonts.test.ts`): a synthetic stylesheet declaring
      `font-family: var(--font-mono); font-weight: 600` is reported with a
      message naming both `JetBrains Mono` and `600`; the same at 500 is not.
      Fails before task 4 (600 currently resolves through Onest).
- [ ] T3. A3 content-addressing (`test/cache.test.ts`): every
      `*.{hash8}.*` file under `public/assets/` hashes to its own name,
      including the 24 non-manifest `.woff2` files and `fonts.<hash>.css`.
- [ ] T4. A3a offline mutation (`test/vendor-assets.test.ts`, reusing
      `makeTreeCopy()` + `runVendorOffline()`): appending one byte to a hashed
      `.woff2` in the copied tree, without renaming it, makes the offline run
      exit 1 with `vendor: no valid existing tree`. Fails before task 5.
- [ ] T5. A3b (`test/` coverage for `check-dist.mjs`): over a temporary
      `dist/`-shaped fixture, a page referencing `/assets/x.deadbeef.css` whose
      file's bytes hash differently produces a problem naming both hashes.
- [ ] T6. B1 (`test/entry-point.test.ts`): both scripts pass; a synthetic bare
      `process.argv[1] === fileURLToPath(import.meta.url)` source and a
      synthetic bare `import.meta.main` source are each reported by message.
- [ ] T7. B2 (`test/links.test.ts`): fixture pages with a single-quoted href and
      an unquoted href resolve and are counted in `checked`; a malformed
      `<a href=>` is reported with a count and the offending tag; the existing
      mailto/off-origin skip assertions are unchanged. Fails before task 7.
- [ ] T8. B3/B3a/B4 (`test/check-headers.test.ts`, new): the pure helpers
      (`discoverHashedAssetPath`, `discoverStylesPath`) are exercised over
      home-page markup fixtures — markup with no hashed `/assets/` href
      produces a problem and returns `null` rather than throwing; markup with
      no `/styles/` href selects the 404 fallback path. Fails before tasks 8
      and 10.
- [ ] T9. C1 (`test/check-contrast.test.ts`): `contentLinkReport()` returns
      thirteen lines, each matching the
      `\[(dark|light|print)\] .* = \d+\.\d\d:1 \(min 4\.5:1, text\)` shape, and
      the set contains `4.81` and `5.62`.
- [ ] T10. D1 (`test/home.test.ts`): the resolved `--font-display` stack
      contains `Onest Fallback`, proving the value came from `site.css`, not
      from the shadowed `mctl.css` declaration. Fails before task 13.
- [ ] T11. D2 (`test/work.test.ts`): the retargeted matcher reports a chip
      literal following a regex terminator's `//`, and a chip literal in a
      frontmatter shape outside both former alternatives — the two blind spots
      the anchored form had; `work.astro` and `ProjectCard.astro` still pass
      clean.
- [ ] T12. F1 (`test/nginx.test.ts`, `test/cache.test.ts`): the
      `location /assets/fonts/LICENSES/` block exists, includes
      `security-headers.conf` exactly once, and matches neither `immutable` nor
      `max-age=31536000`; `location /assets/` is unchanged.
- [ ] T13. Runtime (CI only, `scripts/check-headers.mjs` against the built
      image): `/styles/…` carries the eight headers; the LICENSES text carries
      the eight headers and no immutable lifetime; the hashed `/assets/` body
      hashes to the hash in its own URL.

## Rollback

Every task is source-only — no deployment, no migration, no byte change under
`public/assets/`, no content hash moved — so rollback is `git revert` of the
merge commit, after which `npm test`, `npm run build` and
`node scripts/check-dist.mjs` return to the pre-cycle state with no cleanup.

Partial rollback is supported by the commit ordering: task 1-2 (shared module),
then one commit per class (A, B, C, D, E, F), then the journal entry. Reverting
a single class commit leaves the others intact; only Class A's commits depend
on the shared module, so `src/lib/content-hash.ts` is reverted last if at all.

If the cycle is already deployed when a defect appears, `mctl_rollback_service`
to the previous image tag restores the prior nginx configuration (the only
runtime-visible change is F1's licence `location` block); the guard, test and
documentation changes have no runtime effect at all.
