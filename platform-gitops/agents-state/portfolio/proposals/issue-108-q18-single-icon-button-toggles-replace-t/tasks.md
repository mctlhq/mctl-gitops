# Tasks: issue-108-q18-single-icon-button-toggles-replace-t

Work on a single branch, one commit (or a small series merged as one PR).
Every code block referenced below lives in design.md, sections A-I, and must
be copied character for character.

- [ ] 1. Add the four new keys to `src/i18n/ui.ts` (design.md section C) near
      the existing `langEn` / `langRu` / `themeDark` / `themeLight` entries,
      and delete `langToggleLabel` and `themeToggleLabel`. — DoD:
      `src/i18n/ui.ts` contains `themeSwitchToDark`, `themeSwitchToLight`,
      `langSwitchToEn` and `langSwitchToRu` with the exact EN/RU values from
      design.md section C; `grep -n "langToggleLabel\|themeToggleLabel" src
      test scripts docs` returns nothing; `langEn`, `langRu`, `themeDark`,
      `themeLight`, `langNoScript`, `themeNoScript` are still present;
      `node --test test/ui.test.ts` passes.

- [ ] 2. Replace `src/components/ThemeToggle.astro` and
      `src/components/LangToggle.astro` in full (design.md sections A and B),
      depends on 1. — DoD: each file is byte-identical to its block in
      design.md; each renders exactly two `<button … class="… icon-toggle …">`
      elements, no `<div class="toggle-group">`, no `role="group"`, no
      `aria-label`, no `aria-pressed`; each keeps its `<noscript><p>`
      paragraph; `src/components/Nav.astro` is not modified (`git diff --stat`
      shows no entry for it).

- [ ] 3. Rewrite the toggle styles in `src/styles/site.css` (design.md
      section D), depends on 2. — DoD: no `.toggle-group*` selector remains
      anywhere in the file except none at all (`grep -c "toggle-group"
      src/styles/site.css` is 0); the `.toggle-bar` and `.toggle-bar noscript`
      rules are byte-identical to before; exactly one `.icon-toggle` rule
      block declares `min-block-size: 32px`; the new `.icon-toggle`,
      `.icon-toggle:hover`, `.icon-toggle svg` and `.lang-toggle` rules match
      design.md character for character; the `@media print` selector list
      reads `.site-header, .icon-toggle, .ctas`; `grep -nE
      "\b(animation|transition)(-[a-z]+)?\s*:" src/styles/site.css` returns
      nothing.

- [ ] 4. Update `test/nav.test.ts`: replace the `role="group"` test with the
      `.icon-toggle` test from design.md section E, and refresh the file's
      top comment. — DoD: the new test body is byte-identical to design.md;
      `node --test test/nav.test.ts` passes with every other case in the file
      unchanged.

- [ ] 5. Update `test/a11y.test.ts` (`'.toggle-group button'` ->
      `'.icon-toggle'` in `TARGET_SELECTORS`) and `test/header.test.ts`
      (remove T4 and T5, add the replacement `.icon-toggle` block test, point
      T6 at `.icon-toggle`, refresh the top comment), depends on 3. — DoD:
      `node --test test/a11y.test.ts test/header.test.ts` passes; the
      `TARGET_SELECTORS` array has the same length as before; `grep -c
      "toggle-group" test/a11y.test.ts test/header.test.ts` is 0 for both.

- [ ] 6. Extend `scripts/check-contrast.mjs` (design.md section F). — DoD:
      both `SEMANTIC_TOKENS.dark` and `SEMANTIC_TOKENS.light` carry a
      `surface-card` key mapping to `mctl-surface-dark-card` /
      `mctl-surface-light-card`; `PAIRS` carries exactly one new entry
      `{ fg: 'surface-fg-muted', bg: 'surface-card', kind: 'text' }` and no
      `focus-ring` pair for those colours; `EXEMPTIONS` is still `[]`;
      `node scripts/check-contrast.mjs` exits 0 and its output includes a
      `[dark] surface-fg-muted (#a4a8ae) over surface-card (#15181d) = 7.45:1`
      line and a `[light] … (#3a3f47) over surface-card (#fffdf8) = 10.42:1`
      line; `node --test test/check-contrast.test.ts` passes.

- [ ] 7. Patch `checkApproachPage()` in `scripts/check-dist.mjs` to skip
      `aria-hidden="true"` SVG slices (design.md section G), depends on 2. —
      DoD: the replacement line and its comment are byte-identical to
      design.md; `npm run build && node scripts/check-dist.mjs` exits 0 and
      prints its `check-dist: OK -- dist/index.html is N bytes (cap 40960) …
      approach.astro <svg> total M bytes (cap 12288)` line with N < 40960 and
      M < 12288; `node --test test/check-dist.test.ts` passes.

- [ ] 8. Update `docs/accessibility-checklist.md` (design.md section H),
      depends on 3 and 7. — DoD: the "Target size at least 24px", "Group
      naming in the active language" and "No motion" rows are byte-identical
      to design.md section H; one new re-walk log entry for issue #108 sits
      after the issue #103 entry; `grep -c "toggle-group"
      docs/accessibility-checklist.md` is 0; no row is marked `fail`.

- [ ] 9. Add the cycle journal entry
      `src/content/journal/2026-09-13-q18-single-icon-button-toggles.md`
      (design.md section I, copy from requirements.md Appendix B), depends on
      1-8. — DoD: frontmatter only, no body; `status: in_progress`,
      `visibility: public`, `indexing: noindex`, `interventions: []`, a quoted
      real `issue_opened_at`, no `pr` / `release` / `merged_at` /
      `released_at` / `deployed_at`; `node --test test/journal.test.ts
      test/journal-status.test.ts test/journal-build.test.ts` passes and
      `npm run build` validates the collection schema.

- [ ] 10. Full gate run, depends on 1-9. — DoD: `npm test` passes; `npm run
      build` succeeds; `node scripts/check-dist.mjs`, `node
      scripts/check-links.mjs` and `node scripts/check-contrast.mjs` all exit
      0; `git diff --exit-code -- public/assets src/data/assets.json` is clean
      (the vendored tree is untouched); `git diff --stat` lists only
      `src/components/LangToggle.astro`, `src/components/ThemeToggle.astro`,
      `src/i18n/ui.ts`, `src/styles/site.css`, `scripts/check-contrast.mjs`,
      `scripts/check-dist.mjs`, `test/nav.test.ts`, `test/a11y.test.ts`,
      `test/header.test.ts`, `docs/accessibility-checklist.md` and the new
      journal entry.

## Tests

- [ ] T1. `test/nav.test.ts` — the replacement case asserts each component
      has exactly two `.icon-toggle` buttons, each with `aria-labelledby`, and
      that no `role="group"`, `aria-label` or `groupLabel` remains (design.md
      section E, verbatim).
- [ ] T2. `test/a11y.test.ts` — `.icon-toggle` is in `TARGET_SELECTORS`, so
      the existing 24px-floor walk proves the new control declares
      `min-block-size: 32px`; the `:focus-visible`, no-animation,
      `.toggle-bar` and `Lang.astro` cases keep passing unchanged.
- [ ] T3. `test/header.test.ts` — the new `.icon-toggle` block test asserts
      border + border-radius + background on some matching block and no
      `overflow` on any; T6 asserts `minBlockSizes(siteCss, '.icon-toggle')`
      is exactly `[32]` while `.site-nav a` / `.site-footer a` stay 44px; T1,
      T2, T3 unchanged.
- [ ] T4. `scripts/check-contrast.mjs` (runs first in `npm test`) — resolves
      `surface-card` in both themes and passes the new
      `surface-fg-muted`-over-`surface-card` text pair at 7.45:1 (dark) and
      10.42:1 (light); `test/check-contrast.test.ts` still passes.
- [ ] T5. `scripts/check-dist.mjs` against a real `dist/` — exits 0: the
      approach page's SVG audit sees only the two cycle-diagram variants, the
      bilingual `class="l en"` / `class="l ru"` parity holds on every page,
      `checkNavigationState()` finds no Latin/Cyrillic-mixing `aria-label`,
      and both byte caps are clear.
- [ ] T6. `node --test test/ui.test.ts` — the four new keys satisfy the
      en/ru non-empty parity walk, and no test references the two removed
      keys.
- [ ] T7. Reviewer steps (not acceptance criteria, per AGENTS.md): tab to
      both buttons in a real browser in both themes and confirm the focus
      ring is unclipped; click each button with JavaScript enabled and
      confirm the stance flips and persists across a reload; load a page with
      JavaScript disabled and confirm both `<noscript>` paragraphs render;
      read the header with a screen reader in both languages and confirm each
      button announces "Switch to …" in the active language.

## Rollback

The change is a single PR touching eleven files, with no migration, no build
config change, no vendored-asset change and no CSP hash change.

1. `git revert -m 1 <merge commit>` on `main` restores the Q16 segmented
   pills, the two removed `ui` keys, the `.toggle-group` CSS, the original
   three test files, the original `check-contrast.mjs` / `check-dist.mjs` and
   the previous checklist wording in one step. `npm test` and `npm run build`
   pass on the reverted tree because every gate this cycle touches is
   reverted with it.
2. If the site is already deployed when a problem is found, roll the running
   service back first with `mctl_rollback_service` to the previous image tag
   (`mctl_get_service_config` lists it), then revert on `main`; the next
   release rebuilds from the reverted source.
3. Partial rollback is not supported and must not be attempted: reverting the
   components without the CSS leaves `.toggle-group` markup with no rules,
   and reverting the CSS without `scripts/check-dist.mjs` leaves the
   approach-page SVG audit filtering nothing while decorative glyphs are gone
   — harmless but misleading. Revert the whole commit.
4. Record any manual intervention made during rollback in the
   `interventions: []` list of the cycle's journal entry, per AGENTS.md.
