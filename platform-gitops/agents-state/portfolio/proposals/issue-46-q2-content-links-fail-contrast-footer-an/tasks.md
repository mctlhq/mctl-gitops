# Tasks: issue-46-q2-content-links-fail-contrast-footer-an

- [ ] 1. Add the content-link rules to `src/styles/site.css`: `main a, main
      a:visited { color: var(--accent) }`, `main a:hover { color:
      var(--accent-highlight) }`, plus the specificity pins `.cta:visited {
      color: var(--surface-fg) }` and `.project-links a:visited { color:
      var(--surface-fg) }`. Head the block with a comment stating that the
      `main a` approach was chosen over `class="mctl-prose"` on `<main>`
      because `.mctl-prose a` (0,1,1) beats `.cta` (0,1,0) and would restyle
      the call-to-action links, and because `Base.astro` has no `<main>` to
      put the class on. — DoD: the four rules exist, no `text-decoration` is
      added or removed anywhere, and the comment names the rejected option and
      the reason.
- [ ] 2. Extend the `@media print` `:root` override in `src/styles/site.css`
      with `--accent: var(--mctl-accent-terracotta-light-primary);` and a
      comment giving the measured 5.62:1 against the forced white background
      (versus 3.64:1 for the dark primary). (depends on 1) — DoD: the
      declaration is present inside the existing `@media print` block and
      nothing outside that block changes.
- [ ] 3. Run `npm run vendor` and commit the regenerated
      `public/styles/site.css`. (depends on 1, 2) — DoD:
      `public/styles/site.css` is byte-identical to `src/styles/site.css` in
      the committed tree.
- [ ] 4. Refactor `scripts/check-contrast.mjs` for import: add
      `accent-highlight` to `SEMANTIC_TOKENS` for both themes
      (`mctl-accent-terracotta-dark-highlight`,
      `mctl-accent-terracotta-light-highlight`), export `parseTokens`,
      `contrastRatio`, `resolveColour` and `linkColourProblems`, and guard the
      top-level `await main()` with
      `import.meta.url === pathToFileURL(process.argv[1]).href`. — DoD:
      `node scripts/check-contrast.mjs` prints the same 14 existing pair lines
      plus the new link lines and exits 0; `import('../scripts/check-contrast.mjs')`
      from a test produces no output and no exit code change.
- [ ] 5. Implement `linkColourProblems(siteCss, tokens)` in
      `scripts/check-contrast.mjs`: for each of `main a`, `main a:visited` and
      `main a:hover`, locate the rule block whose comma-separated selector list
      contains that selector, read its `color` declaration, resolve
      `var(--accent)` / `var(--accent-highlight)` / `var(--surface-fg)` through
      `SEMANTIC_TOKENS` per theme and a literal `#rrggbb` as itself, and check
      each resolved colour at 4.5:1 against `surface-bg` and
      `surface-elevated` in both themes. A missing selector, a rule without a
      `color`, or an unresolvable value is itself a problem whose message names
      the browser default that would then apply (`#0000EE` at 2.10:1 on dark,
      `#551A8B` at 1.79:1 on dark). Wire the result into `main()` alongside the
      existing `PAIRS` loop. (depends on 4) — DoD: `npm test` passes on the
      committed stylesheet and prints one report line per link state per theme
      per surface.
- [ ] 6. Add `src/lib/links.ts` exporting `REPO_URL`
      (`https://github.com/mctlhq/portfolio`), `PACKAGES_URL`
      (`${REPO_URL}/packages`), `releaseTagUrl(version)` returning
      `${REPO_URL}/releases/tag/${version}`, `CHAIN_LINKS` (the two
      text/href pairs) and `splitByLinks(item)` returning ordered
      `{ text, href? }` segments using longest-match-at-position. — DoD:
      `splitByLinks` never loses or reorders a character; `astro check` is
      clean; no literal version string appears in the file.
- [ ] 7. Update `src/components/Footer.astro`: point the source link at
      `REPO_URL`, replace the `:` separator with an explicit `{' '}`, and wrap
      `<span data-release>{pkg.version}</span>` in
      `<a href={releaseTagUrl(pkg.version)}>`. Keep `ui.footerReleaseLabel`
      (`Release` / `Релиз`) exactly as it is. (depends on 6) — DoD: the
      rendered footer reads `Release 0.1.11` / `Релиз 0.1.11` with one space
      and the version linking to
      `https://github.com/mctlhq/portfolio/releases/tag/0.1.11`; the file still
      contains no `\d+\.\d+\.\d+` literal.
- [ ] 8. Update `src/pages/colophon/index.astro` to render both chain lists
      through `splitByLinks`, emitting `<a href=…>` for
      `github.com/mctlhq/portfolio` (to `REPO_URL`) and
      `ghcr.io/mctlhq/portfolio` (to `PACKAGES_URL`). (depends on 6) — DoD:
      both the `class="l en"` and the `class="l ru"` list render two links
      each, every other character of `ui.colophonChainItems` is unchanged, and
      `ui.ts` itself is not edited.
- [ ] 9. Add `scripts/check-links.mjs`: walk `dist/**/*.html`, dedupe every
      `href`, resolve internal ones against the tree (`/colophon/` →
      `dist/colophon/index.html`), skip and report `mailto:`, and `GET` each
      external URL sequentially with redirects, a 30s timeout and one retry.
      Fail on any status other than 200, except the release-tag URL, where 404
      prints a warning and passes (release-please bumps `package.json` before
      the tag exists). A transport-level failure prints
      `check-links: network unreachable, skipping external checks` and exits 0.
      — DoD: `npm run build && node scripts/check-links.mjs dist` exits 0 and
      prints one line per checked URL with its status.
- [ ] 10. In `.github/workflows/build.yml`, replace the `test` job's
      `- run: npm test` with `- run: npm run build` and add
      `- run: node scripts/check-links.mjs dist`. (depends on 9) — DoD: the
      job still runs the full test suite exactly once (via `prebuild`) and the
      link-check output appears in the run log.
- [ ] 11. Add `docs/link-check.md` recording the exact command, the run date
      and a status table for every URL the script checked, plus the two
      documented exceptions (`mailto:` skipped, release tag soft). (depends
      on 9) — DoD: every external URL that appears on a changed page is listed
      with its observed status.
- [ ] 12. Update `docs/accessibility-checklist.md`: add a "Content link
      contrast" row citing `main a` / `main a:visited` / `main a:hover`, the
      measured ratios (dark 5.40:1 and 5.19:1, light 4.81:1 and 5.11:1, hover
      8.53:1 / 8.19:1 and 6.30:1 / 6.70:1) and the mutation test; correct the
      existing pair count in the "Contrast in both themes" row to the number
      `check-contrast.mjs` now prints; and record that the `main a` approach
      was chosen over `.mctl-prose`, with the reason. Add the Lighthouse re-run
      of `/colophon/` as a `reviewer step` row. (depends on 5) — DoD: no stale
      count or claim remains in the file.
- [ ] 13. Add `test/contrast-link.test.ts` and `test/links.test.ts` to the
      `node --test` list in `package.json`'s `test` script, with the two files
      written as described under "Tests" below. (depends on 5, 6) — DoD:
      `npm test` runs both new files and they pass.

## Tests

- [ ] T1. `test/contrast-link.test.ts` — green direction: importing
      `linkColourProblems` and feeding it the committed `src/styles/site.css`
      plus the tokens parsed from `public/assets/mctl/mctl.css` yields zero
      problems.
- [ ] T2. `test/contrast-link.test.ts` — red direction, three mutations of
      that same stylesheet text: `main a` colour replaced with `#0000EE`,
      `main a:visited` colour replaced with `#551A8B`, and the whole `main a`
      rule deleted. Each must produce at least one problem, and the message
      must name the `dark` theme and the state that failed.
- [ ] T3. `test/links.test.ts` — `releaseTagUrl('0.1.11')` equals
      `https://github.com/mctlhq/portfolio/releases/tag/0.1.11`;
      `splitByLinks` on each of the seven English and seven Russian chain
      items rejoins to the original string exactly, and yields exactly one
      linked segment for the source item and one for the image item.
- [ ] T4. `test/a11y.test.ts` — extend `TARGET_SELECTORS`-style source
      assertions with: `site.css` declares `main a` and `main a:visited` with a
      `color`, and declares `.cta:visited` and `.project-links a:visited` so
      the classed links keep their colour; the existing no-animation and
      no-transition assertions still pass over the enlarged file.
- [ ] T5. `test/colophon.test.ts` — the footer's source `href` is
      `https://github.com/mctlhq/portfolio` (not the bare org), the release
      line contains an explicit `{' '}` separator and no `:` between label and
      version, `<span data-release>` is wrapped in an `<a>` built from
      `releaseTagUrl(pkg.version)`, and the existing no-semver-literal
      assertion still holds.
- [ ] T6. Post-build, run `node scripts/check-dist.mjs` and confirm the
      `class="l en"` / `class="l ru"` parity and the no-`.js` rule still hold
      with the new colophon markup, and that `data-release` still matches
      `package.json`.
- [ ] T7. `npm run build && node scripts/check-links.mjs dist` exits 0 with
      every internal link resolved and every external link at 200 (release tag
      soft).
- [ ] T8. Reviewer step, not an acceptance criterion: re-run Lighthouse mobile
      on `/colophon/` and confirm the `color-contrast` finding is gone, and tab
      through `/`, `/colophon/` and a journal entry in both themes to confirm
      the focus ring and the new link colour read well together.

## Rollback

Every change is additive and confined to files the DevLoop owns, so a revert of
the merge commit restores the previous behaviour exactly; the site is static and
holds no state that could outlive it.

Partial rollbacks, in the order they are most likely to be wanted:

1. *A classed link changed appearance.* Delete the `main a` / `main a:visited`
   block from `src/styles/site.css`, re-run `npm run vendor`, and commit. The
   build then fails `check-contrast.mjs` by design, which is the correct signal
   that the accessibility defect is back and needs a different rule rather than
   no rule.
2. *The link check is flaky in CI.* Remove the
   `node scripts/check-links.mjs dist` step from `.github/workflows/build.yml`;
   the script and `docs/link-check.md` stay as the committed record. Nothing
   else depends on that step.
3. *The footer release link points at a tag that does not exist.* Revert
   `Footer.astro` to the plain `<span data-release>` (keeping the added space)
   — one line, no other file involved.
4. *Deployed site needs to go back immediately.* `mctl_rollback_service` to the
   previous image tag; no database, no migration, no cache to clear.
