# Tasks: issue-6-align-storybook-page-title-og-title-with

- [ ] 1. Update `<title>` in `managerHead` — In
  `apps/storybook/.storybook/main.ts` line 16, replace the string
  `MCTL Design System` inside the `<title>` element with `MCTL UI`.
  DoD: line 16 reads `    <title>MCTL UI</title>` and no other line in the
  file is modified.

- [ ] 2. Update `og:title` in `managerHead` (depends on 1) — In
  `apps/storybook/.storybook/main.ts` line 17, replace
  `content="MCTL Design System"` with `content="MCTL UI"` in the
  `og:title` meta tag.
  DoD: line 17 reads
  `    <meta property="og:title" content="MCTL UI">` and no other line in
  the file is modified.

- [ ] 3. Verify no residual occurrences (depends on 2) — Run
  `grep -r "MCTL Design System" apps/storybook/.storybook/` from the repo
  root and confirm zero matches.
  DoD: the grep exits with no output (or exit code 1).

- [ ] 4. Run build gate (depends on 3) — Execute `pnpm build:storybook` and
  confirm it exits with code 0.
  DoD: build completes without errors; the output `storybook-static/` directory
  is produced.

- [ ] 5. Commit — Create a single conventional-commit on a feature branch:
  `fix: align Storybook page title and og:title with MCTL UI`.
  DoD: commit contains only changes to
  `apps/storybook/.storybook/main.ts`; `pnpm check:versions` passes;
  commit message is under 72 characters.

## Tests

- [ ] T1. Grep assertion — `grep "MCTL Design System" apps/storybook/.storybook/main.ts`
  returns no matches (exit 1). Confirms the old string is fully removed.
- [ ] T2. Grep assertion — `grep "<title>MCTL UI</title>" apps/storybook/.storybook/main.ts`
  returns exactly one match. Confirms the new title is present.
- [ ] T3. Grep assertion —
  `grep 'og:title" content="MCTL UI"' apps/storybook/.storybook/main.ts`
  returns exactly one match. Confirms the new og:title is present.
- [ ] T4. Build smoke test — `pnpm build:storybook` exits 0 with no TypeScript
  or Vite errors in the output.
- [ ] T5. Diff scope check — `git diff --name-only` shows only
  `apps/storybook/.storybook/main.ts`. No other file is modified.

## Rollback

Revert the single commit introduced in task 5:

```
git revert <commit-sha>
```

This restores both string literals in `main.ts` to `MCTL Design System` and
returns the Storybook page title and og:title to their pre-change state. No
other files were modified, so no further rollback steps are needed.
