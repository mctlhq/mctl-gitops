# Tasks: issue-3-change-the-storybook-overview-brand-icon

- [ ] 1. Obtain the new mctl icon artwork — DoD: Two SVG variants exist (light
  foreground for dark chrome; dark foreground for light chrome) sourced from
  the MCTL landing design spec or approved by the mctl design owner. A 32x32
  standalone icon mark variant also exists for the favicon.

- [ ] 2. Replace `apps/storybook/public/mctl-logo-light.svg` (depends on 1) —
  DoD: File contains the new icon mark + "MCTL" wordmark, light-coloured
  foreground on transparent background, canvas `width="98" height="32"`,
  `viewBox="0 0 98 32"`. Old nested-square geometry is gone.

- [ ] 3. Replace `apps/storybook/public/mctl-logo-dark.svg` (depends on 1) —
  DoD: File contains the new icon mark + "MCTL" wordmark, dark-coloured
  foreground on transparent background, canvas `width="98" height="32"`,
  `viewBox="0 0 98 32"`. Old nested-square geometry is gone.

- [ ] 4. Replace `apps/storybook/public/favicon.svg` (depends on 1) — DoD:
  File contains the new standalone icon mark at 32x32 px. If the mark uses a
  transparent background, a `prefers-color-scheme` media query is embedded in
  the SVG so it is legible in both OS light and dark contexts. Old
  nested-square geometry is gone.

- [ ] 5. Run `pnpm build:storybook` from the `apps/storybook` package (depends
  on 2, 3, 4) — DoD: Build completes without errors; `storybook-static/`
  contains `mctl-logo-light.svg`, `mctl-logo-dark.svg`, and `favicon.svg` with
  the new content.

- [ ] 6. Visual smoke-test in a browser (depends on 5) — DoD: Opening the
  built Storybook (`npx http-server storybook-static`) shows the new brand
  image in the sidebar in both dark and light mode (toggle with the toolbar
  sun/moon icon); the browser tab shows the new favicon; the
  Introduction/Overview story renders its prose content without error;
  no console errors.

- [ ] 7. (Conditional) Add explicit favicon link to `managerHead` in
  `apps/storybook/.storybook/main.ts` — DoD: If step 6 reveals the favicon is
  not auto-detected, insert `<link rel="icon" type="image/svg+xml" href="/favicon.svg">`
  into the `managerHead` template string in `main.ts`; rebuild and re-verify.
  If the favicon renders correctly in step 6 without this change, skip.

- [ ] 8. Run full CI check suite (depends on 5, 7 if triggered) — DoD:
  `pnpm check:versions`, `pnpm lint`, `pnpm typecheck`, and
  `pnpm build:storybook` all pass cleanly (mirrors the checks in
  `.github/workflows/ci.yml`).

## Tests

- [ ] T1. Dark-mode brand image: with Storybook running in dark mode, the
  sidebar brand area shows the new icon using `mctl-logo-light.svg`; the old
  nested-square mark is absent.
- [ ] T2. Light-mode brand image: after toggling to light mode, the sidebar
  brand area shows the new icon using `mctl-logo-dark.svg` with appropriate
  dark foreground.
- [ ] T3. Favicon consistency: the browser tab favicon matches the new
  standalone icon mark in `favicon.svg`.
- [ ] T4. No story regression: the Introduction/Overview story and at least
  three additional component stories (e.g. MButton, MBadge, MAlert) render
  without console errors or visual breakage.
- [ ] T5. Build artefact check: `ls storybook-static/*.svg` lists the three
  expected SVG files after a clean `pnpm build:storybook`.

## Rollback

1. Revert the three SVG files in `apps/storybook/public/` to their previous
   content (recoverable from git: `git checkout HEAD -- apps/storybook/public/`).
2. If task 7 was executed, revert the `managerHead` change in
   `apps/storybook/.storybook/main.ts` similarly.
3. Re-run `pnpm build:storybook` and verify the old brand images are restored.
4. No package version bump is required for this rollback — the SVG files are
   not part of any published package artefact.
