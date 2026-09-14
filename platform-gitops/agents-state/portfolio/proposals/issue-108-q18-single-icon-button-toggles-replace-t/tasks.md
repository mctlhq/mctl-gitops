# Tasks: issue-108-q18-single-icon-button-toggles-replace-t

Every verbatim block referenced below lives in `requirements.md`, Appendices
A-J. Copy from there character for character; do not retype or reflow.

- [ ] 1. Add the four new `ui` keys and remove the two retired ones in
  `src/i18n/ui.ts`, per Appendix C — DoD: `themeSwitchToDark`,
  `themeSwitchToLight`, `langSwitchToEn` and `langSwitchToRu` are present
  with their exact EN/RU values, placed near the existing
  `langEn`/`langRu`/`themeDark`/`themeLight` keys; `langToggleLabel` and
  `themeToggleLabel` are gone; `langEn`, `langRu`, `themeDark`, `themeLight`,
  `langNoScript` and `themeNoScript` are untouched;
  `grep -rn "langToggleLabel\|themeToggleLabel" src test scripts docs`
  returns nothing.

- [ ] 2. Replace `src/components/ThemeToggle.astro` in full with Appendix A
  (depends on 1) — DoD: the file is byte-identical to Appendix A; it contains
  exactly two `<button>` elements, both with `icon-toggle` in `class`, no
  `<div>`, no `role="group"`, no `aria-pressed`, no `aria-label`; the
  `.t.dark` button carries the moon `<path>` and `data-set-theme="light"`,
  the `.t.light` button carries the sun `<circle>`/`<line>` set and
  `data-set-theme="dark"`; both `<svg>` elements are `aria-hidden="true"`
  `focusable="false"`; the `<noscript>` paragraph is retained.

- [ ] 3. Replace `src/components/LangToggle.astro` in full with Appendix B
  (depends on 1) — DoD: the file is byte-identical to Appendix B; exactly two
  `<button>` elements with `icon-toggle lang-toggle` in `class`; the `.l.en`
  button carries `data-set-lang="ru"` and `aria-labelledby="lang-toggle-to-ru"`,
  the `.l.ru` button carries `data-set-lang="en"` and
  `aria-labelledby="lang-toggle-to-en"`; the `<noscript>` paragraph is
  retained.

- [ ] 4. Rewrite the toggle CSS in `src/styles/site.css` per Appendix D
  (depends on 2, 3) — DoD: the `/* Toggle groups. */` region's six
  `.toggle-group*` rules are gone and the `.toggle-bar` / `.toggle-bar
  noscript` rules that sat among them are byte-identical to before; the
  second `.toggle-group button` rule under the "Tap targets" comment, and its
  three-line comment, are gone; Appendix D's `.icon-toggle`,
  `.icon-toggle:hover`, `.icon-toggle svg` and `.lang-toggle` blocks are
  present character for character;
  `grep -n "toggle-group" src/styles/site.css` returns only the single
  `@media print` selector-list line, which is deliberately left alone; no
  `animation` or `transition` appears anywhere in the file.

- [ ] 5. Update `test/nav.test.ts` per Appendix E1 (depends on 2, 3) — DoD:
  the old `.toggle-group` `role="group"` test is gone, the Appendix E1 test is
  present character for character, no other test in the file is edited, and
  `node --test test/nav.test.ts` passes.

- [ ] 6. Update `test/a11y.test.ts` per Appendix E3 (depends on 4) — DoD:
  `TARGET_SELECTORS` reads `'.icon-toggle'` where it read
  `'.toggle-group button'`, every other array entry is unchanged, no other
  test in the file is edited, and `node --test test/a11y.test.ts` passes.

- [ ] 7. Update `test/header.test.ts` per Appendix E2 (depends on 4) — DoD:
  T4 and T5 are removed outright, Appendix E2's replacement test is present
  character for character in their place, T6's name and its
  `minBlockSizes(siteCss, …)` argument read `.icon-toggle`, T1/T2/T3 are
  untouched, and `node --test test/header.test.ts` passes (T6's
  `assert.deepEqual(minBlockSizes(siteCss, '.icon-toggle'), [32])` resolves to
  exactly one declaration).

- [ ] 8. Extend `scripts/check-contrast.mjs` per Appendix F (depends on 4) —
  DoD: `SEMANTIC_TOKENS.dark` has `'surface-card': 'mctl-surface-dark-card'`
  and `SEMANTIC_TOKENS.light` has `'surface-card': 'mctl-surface-light-card'`;
  `PAIRS` has exactly one new entry
  `{ fg: 'surface-fg-muted', bg: 'surface-card', kind: 'text' }` and no
  `EXEMPTIONS` entry is added; `node scripts/check-contrast.mjs` exits 0 and
  its final line reports 29 pairs checked; the two new report lines show
  7.45:1 (dark) and 10.42:1 (light).

- [ ] 9. Add the `ThemeToggle.astro` `ALLOW` entry to
  `scripts/check-no-metrics.mjs` per Appendix G (depends on 2) — DoD: the
  entry is present character for character in the same array as the existing
  `CycleDiagram.astro` and `Base.astro` entries; `node
  scripts/check-no-metrics.mjs` exits 0, prints no "not permitted" line and no
  "stale ALLOW entry" line. If any coordinate in Appendix A was altered, the
  value list is recomputed from the gate's own output, never hand-adjusted.

- [ ] 10. Scope `checkApproachPage()`'s SVG audit in
  `scripts/check-dist.mjs` per Appendix H (depends on 2) — DoD: the single
  `const slices = extractSvgSlices(html);` line inside `checkApproachPage()`
  is replaced by Appendix H's commented filtered form, character for
  character; nothing else in the file changes; after `npm run build`,
  `node scripts/check-dist.mjs` exits 0 and its summary line reports an
  `approach.astro <svg> total` that does not include the two header glyphs.

- [ ] 11. Update `docs/accessibility-checklist.md` per Appendix I (depends on
  4, 8) — DoD: the "Target size at least 24px", "Group naming in the active
  language" and "No motion" note cells are replaced character for character;
  the "Contrast in both themes" note's "Twenty-seven pairs now clear their
  threshold, up from fourteen:" sentence opening is replaced character for
  character and the rest of that note is unchanged; one new re-walk log entry
  for issue #108 follows the existing #103 entry; the file contains no
  remaining reference to `.toggle-group button` as a live selector.

- [ ] 12. Add the journal entry
  `src/content/journal/2026-09-14-q18-single-icon-button-toggles.md` per
  Appendix J (depends on 1-11) — DoD: frontmatter is character-for-character
  Appendix J with an empty body; `status: in_progress` with no `pr`,
  `release`, `merged_at`, `released_at` or `deployed_at`; it is the only
  `in_progress` entry in `src/content/journal`; `node --test
  test/journal.test.ts test/journal-status.test.ts test/journal-build.test.ts
  test/journal-closure.test.ts test/journal-workflow.test.ts test/indexing.test.ts`
  passes.

- [ ] 13. Full verification sweep (depends on 1-12) — DoD: `npm run vendor`
  produces no tracked diff under `public/assets` or `src/data/assets.json`;
  `npm test` passes end to end; `npm run check` (`astro sync && astro check`)
  reports no error; `npm run build` succeeds; `node scripts/check-dist.mjs`,
  `node scripts/check-links.mjs` and `node scripts/check-headers.mjs` all exit
  0. Commit on a branch with a conventional-commit message; never on `main`.

## Tests

- [ ] T1. `test/nav.test.ts` — Appendix E1's test: each component matches
  exactly two `<button type="button" class="…icon-toggle…">` tags, each tag
  has an `aria-labelledby`, and neither file contains `role="group"`,
  `aria-label=` or `groupLabel`.
- [ ] T2. `test/nav.test.ts` — the unchanged bilingual-template-literal test
  still passes for both rewritten components (no `${…en} / ${…ru}` literal is
  introduced).
- [ ] T3. `test/a11y.test.ts` — `.icon-toggle` declares a `min-block-size` of
  at least 24px; the global `:focus-visible` outline rule still exists; no
  `animation` or `transition` anywhere in `site.css`; the `.toggle-bar` rule
  still declares `display: flex`, `flex-wrap: wrap` and
  `gap: var(--mctl-space-4)`.
- [ ] T4. `test/header.test.ts` — Appendix E2's test: some `.icon-toggle`
  block declares `border`, `border-radius` and `background`, and no
  `.icon-toggle` block declares `overflow`.
- [ ] T5. `test/header.test.ts` T6 —
  `minBlockSizes(siteCss, '.icon-toggle')` deep-equals `[32]`, and
  `.site-nav a` / `.site-footer a` still include 44.
- [ ] T6. `test/header.test.ts` T3 — `.toggle-bar` still declares
  `margin-inline-start: auto` (proves the layout row was not disturbed).
- [ ] T7. `test/ui.test.ts` — every `ui` entry, including the four new keys,
  is a non-empty `{ en, ru }` pair of the same kind.
- [ ] T8. `scripts/check-contrast.mjs` — resolves `surface-card` in both
  themes and passes `surface-fg-muted` over it at 4.5:1; run reports 29 pairs.
- [ ] T9. `scripts/check-no-metrics.mjs` — exits 0 with zero unclassified
  matches and zero stale `ALLOW` values.
- [ ] T10. `scripts/check-dist.mjs` — exits 0 against a freshly built
  `dist/`, including `checkApproachPage()` now scoped to the two `cycle-svg`
  diagram variants, and the per-page `class="l en"` / `class="l ru"` parity
  count still balances on every built page.
- [ ] T11. Reviewer step (not an acceptance criterion, per `AGENTS.md`): tab
  to both buttons in a real browser in both themes and confirm the focus ring
  is fully visible and unclipped; run a screen reader over the header in both
  language stances and confirm each button announces its own name in the
  active language.

## Rollback

One commit, one branch, no data migration and no platform state.

1. If the problem is caught before merge: close the pull request and delete
   the branch. Nothing on `main` changed.
2. If the problem is caught after merge but before release: revert the merge
   commit on a branch and open a revert pull request. The revert restores
   `LangToggle.astro`, `ThemeToggle.astro`, the `/* Toggle groups. */` CSS
   region and the tap-target rule, the two `ui` keys, the three script edits,
   the checklist rows and the tests in one step, because every change lands in
   the same commit. Delete the journal entry in the same revert (it is the
   only `in_progress` entry, so removing it cannot leave the collection with
   two).
3. If the problem is caught after a release and deploy: `mctl_rollback_service`
   to the previous image tag (the tag before this cycle's release, visible via
   `mctl_get_service_config` for team `labs`, service `portfolio`), then land
   the revert pull request from step 2 so the source and the running image
   agree again. Per `AGENTS.md` this is an MCP-tool operation only — no
   `kubectl`, no hand-edited GitOps values.
4. Nothing here touches `public/assets/mctl/*`, `src/data/assets.json`,
   `Base.astro`'s inline script or its CSP hash, so a rollback cannot leave a
   stale hash, a broken subresource reference or a stored user preference that
   no longer resolves.
