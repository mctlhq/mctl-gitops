# Tasks: issue-55-q2-content-link-contrast-footer-and-colo

- [ ] 1. Add the content-link rules to `src/styles/site.css`, after the
  `.project-links` block: `main a { color: var(--accent) }`,
  `main a:visited:not(:hover) { color: var(--accent) }`,
  `main a:hover { color: var(--accent-highlight) }` — DoD: the three rules are
  present, carry the comment explaining the measured ratios (5.40:1 / 5.19:1
  dark, 4.81:1 / 5.11:1 light; hover 8.53:1 / 8.19:1 dark, 6.30:1 / 6.70:1
  light), and no `.mctl-prose` class is added to any `<main>` element anywhere in
  `src/`.

- [ ] 2. Add the order-independent pins (depends on 1) — DoD: `site.css`
  contains `.cta:visited:not(:hover) { color: var(--surface-fg) }` and
  `.project-links a:hover, .project-links a:visited:not(:hover) { color:
  var(--surface-fg) }`; the existing `.cta`, `.cta:hover`, `.site-nav a`,
  `.site-nav a:hover`, `.site-footer a` and `.project-links a` rules are
  byte-identical to before; no bare `:visited` selector exists in the file.

- [ ] 3. Override `--accent` inside the existing `@media print` `:root` block in
  `site.css` to `#b83d28` (depends on 1) — DoD: the declaration sits alongside
  the existing `--surface-bg: #fff` line, carries a comment naming 3.64:1 before
  and 5.62:1 after, and the rest of the print block is unchanged.

- [ ] 4. Refactor `scripts/check-contrast.mjs` into pure helpers plus a thin
  `main()`, and add the content-link checks (depends on 1, 2, 3) — DoD: the file
  exports `parseContentLinkColours(siteCssText)` and
  `contentLinkProblems({ siteCssText, tokens })`; `main()` reads both
  `public/assets/mctl/mctl.css` and `src/styles/site.css`; the normal,
  `:visited` and `:hover` content-link colours are checked against
  `--surface-bg` and `--surface-elevated` in both themes at 4.5:1, and the print
  colour (the print override if present, otherwise the dark `--accent`) against
  `#fff` at 4.5:1; the existing `PAIRS` output is unchanged; `node
  scripts/check-contrast.mjs` exits 0 on the committed tree.

- [ ] 5. Guard the entry points of `scripts/check-contrast.mjs` and
  `scripts/check-links.mjs` with `import.meta.main` (depends on 4, 9) — DoD:
  both files exit 1 with a named diagnostic when `import.meta.main` is
  `undefined`, call `main()` only when it is `true`, and contain no comparison
  between `import.meta.url` and `process.argv[1]`.

- [ ] 6. Update `src/components/Footer.astro` — DoD: the GitHub anchor points at
  `https://github.com/mctlhq/portfolio` with `ui.footerGithubLabel` unchanged;
  the release block renders the label, an explicit `{' '}`, then
  `<a href={releaseTagUrl} data-release>{pkg.version}</a>` where
  `releaseTagUrl` is
  `` `https://github.com/mctlhq/portfolio/releases/tag/${pkg.version}` ``; the
  colon is gone; `data-release` is the last attribute on the anchor; the file
  contains no literal semver.

- [ ] 7. Add `src/lib/chain.ts` with `CHAIN_LINKS` and `chainSegments(item)`
  — DoD: `github.com/mctlhq/portfolio` maps to
  `https://github.com/mctlhq/portfolio` and `ghcr.io/mctlhq/portfolio` to
  `https://github.com/mctlhq/portfolio/packages`; `chainSegments` returns
  segments whose concatenated `text` is byte-identical to its input for any
  string; matching is earliest-position, longest-text-first.

- [ ] 8. Render the chain list through `chainSegments` in
  `src/pages/colophon/index.astro` (depends on 7) — DoD: both the `.l.en` and
  `.l.ru` lists map each item to segments, rendering a linked segment as
  `<a href={seg.href}>{seg.text}</a>` and a plain one as escaped text; no
  `set:html`; `src/i18n/ui.ts` is not modified; the `<ul class="l en">` /
  `<ul class="l ru" lang="ru">` structure is unchanged.

- [ ] 9. Add `scripts/check-links.mjs` with no network access at all — DoD: it
  exports `collectHrefs`, `classifyHref`, `resolveInternal` and
  `run({ distDir, origin })`; reads the origin from `astro.config.mjs` with the
  same regex `check-dist.mjs` uses; resolves internal hrefs honouring
  `trailingSlash: 'always'` after stripping query and fragment; treats a
  same-origin absolute href as internal by origin comparison, never by byte
  equality with the page's canonical; resolves an extensionless, slash-less path
  as `<path>/index.html` falling back to `<path>` and names both candidates on
  failure; reports `mailto:`, other schemes and off-origin `http(s)` as skipped,
  by count and listed, on success as well as failure; contains no `fetch`, no
  import of `node:http`/`node:https`/`node:net`/`undici`, no retry, no backoff,
  no timeout, no status-code table; exits 1 naming the page, the href and the
  expected file for every unresolved internal href.

- [ ] 10. Wire the link check into `.github/workflows/build.yml` (depends on 9)
  — DoD: in the `test` job, `- run: npm test` is replaced by `- run: npm run
  build` (a strict superset, since `prebuild` is `npm run vendor && npm test`)
  followed by `- run: node scripts/check-links.mjs`, with a comment saying why;
  no other job or step is loosened; `claude-review.yml`, `release-please.yml` and
  `dependabot.yml` are untouched.

- [ ] 11. Add the footer assertion to `scripts/check-dist.mjs` (depends on 6) —
  DoD: a `checkFooter()`-style check runs over every `dist/**/*.html` and fails
  unless the release block matches label, exactly one space, then an anchor whose
  `href` is `https://github.com/mctlhq/portfolio/releases/tag/<version>` and
  whose `data-release` text is `<version>`, with `<version>` read from
  `package.json`; the existing `data-release` parity check still passes.

- [ ] 12. Add `docs/link-check.md` (depends on 9) — DoD: it states what the
  check proves and what it deliberately does not (no claim about third-party
  reachability, fragment targets, nginx redirects or link text), how to run it
  locally, and the rate-limit rationale for external checking being out of
  scope; it contains no dated table of third-party URL statuses.

- [ ] 13. Update the "Contrast in both themes" row of
  `docs/accessibility-checklist.md` (depends on 4) — DoD: the row names the new
  pair count and the new tightest ratio produced by `check-contrast.mjs`, and
  mentions the content-link states and the print override; no other row is
  changed.

- [ ] 14. Add every new test file to the `test` script in `package.json`
  (depends on T1-T5) — DoD: `test/link-cascade.test.ts`,
  `test/check-contrast.test.ts`, `test/footer.test.ts`, `test/chain.test.ts` and
  `test/links.test.ts` all appear in the explicit `node --test` file list;
  `npm test` runs them.

- [ ] 15. Final verification (depends on all) — DoD: `npm test`,
  `npm run build` and `node scripts/check-dist.mjs` all exit 0;
  `node scripts/check-links.mjs` exits 0 against the fresh `dist/`; the built
  tree has no `.js` file and equal `class="l en"` / `class="l ru"` counts on
  every page (both already asserted by `check-dist.mjs`).

## Tests

- [ ] T1. `test/link-cascade.test.ts` — parse `src/styles/site.css` (comments
  stripped, `@media print` excluded), compute `(a,b,c)` specificity with
  `:not(x)` counted as `x`, and resolve the winning `color` by specificity then
  source order for three elements in four states. Asserts the twelve cells:
  class-less `<a>` in `<main>` → accent / accent / accent-highlight /
  accent-highlight; `.cta` → surface-fg / surface-fg / accent / accent;
  `.project-links a` → surface-fg in all four. Fails if a pin is written as a
  bare `:visited`, if a pin is deleted, or if the rules are reordered such that a
  tie flips. Also fails loudly if it meets a `color` rule whose selector shape it
  does not model.

- [ ] T2. `test/link-cascade.test.ts` (second test) — assert against
  `src/layouts/Base.astro` that `<Nav />` and `<Footer />` render outside the
  element receiving the page `<slot />`, so `main a` can never reach
  `.site-nav a` or `.site-footer a`. This is the reason no nav/footer pin is
  added.

- [ ] T3. `test/check-contrast.test.ts` — import `contentLinkProblems` from
  `scripts/check-contrast.mjs` and assert: empty problem list for the committed
  `src/styles/site.css`; non-empty for each of three in-memory mutations —
  content-link colour reverted to `#0000EE`, `:visited` reverted to `#551A8B`,
  and the `main a` rule deleted outright. A fourth case deletes the print
  `--accent` override and asserts the resulting 3.64:1 is reported.

- [ ] T4. `test/footer.test.ts` — against `src/components/Footer.astro`: no
  colon between the release label and the version; the tag URL is built from
  `pkg.version` (`assert.doesNotMatch(source, /\d+\.\d+\.\d+/)` for the literal
  semver ban); the GitHub anchor href is exactly
  `https://github.com/mctlhq/portfolio`; `data-release` is the final attribute on
  the version anchor.

- [ ] T5. `test/chain.test.ts` — for every item of `ui.colophonChainItems.en`
  and `.ru`: `chainSegments(item).map((s) => s.text).join('') === item`.
  Additionally: the English and Russian "Source" items each yield exactly one
  segment with `href === 'https://github.com/mctlhq/portfolio'` and text
  `github.com/mctlhq/portfolio`; the two "Image" items each yield exactly one
  segment with `href === 'https://github.com/mctlhq/portfolio/packages'` and
  text `ghcr.io/mctlhq/portfolio`; items containing neither identifier yield a
  single unlinked segment.

- [ ] T6. `test/links.test.ts` (no-network proof) — replace `globalThis.fetch`
  with a counting stub that throws, run `run({ distDir })` over a `mkdtemp`
  fixture, assert the stub count is 0; plus a static scan of
  `scripts/check-links.mjs` asserting the source matches none of `fetch(`,
  `node:http`, `node:https`, `node:net`, `undici`, `XMLHttpRequest`,
  `setTimeout`, `AbortSignal`, `retry`, `backoff`.

- [ ] T7. `test/links.test.ts` (behaviour) — over the same fixture tree
  (`index.html`, `colophon/index.html`, and a page holding the awkward cases),
  assert: a root-relative `/colophon/` resolves; a same-origin absolute
  `https://dmitriimashkov.com/colophon/#build` resolves; a same-origin absolute
  with no trailing slash `https://dmitriimashkov.com/colophon` resolves; a
  broken `/colophon/adr/does-not-exist/` appears in `problems` naming both the
  href and the expected file; `mailto:hello@dmitriimashkov.com` and
  `https://github.com/mctlhq/portfolio` both appear in `skipped` and neither is
  counted in `checked`.

- [ ] T8. `test/links.test.ts` (canonical handling) — a fixture page carrying
  `<link rel="canonical" href="https://dmitriimashkov.com/colophon/">` on a page
  whose own path differs resolves through the origin comparison, proving
  classification is not byte equality with the page's own canonical.

## Rollback

Each of the four parts is independent and reverts cleanly on its own:

1. **Whole change** — `git revert` the merge commit. Nothing outside the
   repository is affected: no deploy, no migration, no gitops value, no secret.
   The site redeploys on the next release tag exactly as before.
2. **Contrast only** — delete the `main a`, `main a:visited:not(:hover)`,
   `main a:hover` rules, the two pins and the print `--accent` line from
   `src/styles/site.css`, and revert `scripts/check-contrast.mjs` plus
   `test/link-cascade.test.ts`, `test/check-contrast.test.ts` and their entries
   in the `package.json` test list. Links return to the UA default; no other
   rule was modified, so nav, CTA, footer and project links are unaffected
   either way.
3. **Footer / colophon only** — revert `src/components/Footer.astro`,
   `src/pages/colophon/index.astro`, `src/lib/chain.ts`, the `checkFooter`
   addition to `scripts/check-dist.mjs` and the two tests. `src/i18n/ui.ts` was
   never modified, so no copy is at risk.
4. **Link check only** — if `scripts/check-links.mjs` turns out to flake or to
   be wrong about a route, restore `- run: npm test` in
   `.github/workflows/build.yml` and delete the `check-links` step; the script
   and its tests can stay in the tree while the CI step is off, since the script
   makes no network request and cannot block for external reasons. Note that
   this is the only rollback that loosens a gate, and it should be recorded as
   such.

If the `import.meta.main` guard fires in the Docker build (a `node:24-alpine`
digest older than 24.2), the correct response is re-pinning the base image in a
separate change, **not** weakening or removing the guard — a guard that fails
open is what the acceptance criteria forbid.
