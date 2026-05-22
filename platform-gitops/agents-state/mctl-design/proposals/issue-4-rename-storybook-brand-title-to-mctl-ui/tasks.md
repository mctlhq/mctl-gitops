# Tasks: issue-4-rename-storybook-brand-title-to-mctl-ui

- [ ] 1. Edit `brandTitle` in `apps/storybook/.storybook/mctl-theme.ts` —
  DoD: line 8 reads `brandTitle: 'MCTL UI',`; the `brand` constant contains
  no occurrence of the string `'MCTL Design System'`; no other line in the
  file is modified; the file parses without TypeScript errors.

- [ ] 2. Verify the Storybook build passes (depends on 1) —
  DoD: `pnpm build:storybook` exits with code 0 in the repo root; no new
  errors or warnings are introduced.

- [ ] 3. Commit using conventional-commit format (depends on 2) —
  DoD: commit message begins with `fix:`, subject line is under 72 characters,
  no `v` prefix on any version reference, and `pnpm check:versions` passes
  (lockstep version check is unchanged because no package version is bumped
  by this task).

## Tests

- [ ] T1. Grep `apps/storybook/.storybook/mctl-theme.ts` for
  `'MCTL Design System'` — expect zero matches.
- [ ] T2. Grep `apps/storybook/.storybook/mctl-theme.ts` for `'MCTL UI'` —
  expect exactly one match (inside the `brand` constant).
- [ ] T3. Run `pnpm build:storybook` from the repo root — expect exit code 0.
- [ ] T4. Confirm that `brandUrl`, `brandImage` (both dark and light),
  `brandTarget`, and all hex color values in `mctl-theme.ts` are identical
  to their pre-change values (no unintended edits).

## Rollback

Revert the single-line change to `apps/storybook/.storybook/mctl-theme.ts`:
restore `brandTitle: 'MCTL Design System',` in the `brand` constant. Because
this is a UI-only label with no effect on packages or APIs, no further
rollback steps are needed. If the commit has already been merged, open a
follow-up `fix:` commit that reverts the line.
