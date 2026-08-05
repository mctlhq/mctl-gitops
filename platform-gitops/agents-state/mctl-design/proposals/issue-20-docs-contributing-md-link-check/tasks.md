# Tasks: issue-20-docs-contributing-md-link-check

- [ ] 1. Verify `CONTRIBUTING.md` currency against present repo state
      (`package.json` scripts, `pnpm-workspace.yaml`, `.claude/CLAUDE.md`
      conventions) — DoD: each command/convention mentioned in
      `CONTRIBUTING.md` (`corepack enable`, `pnpm install`, `pnpm dev`,
      `pnpm build`, `pnpm build:storybook`, `pnpm lint`, `pnpm typecheck`,
      `pnpm check:versions`, branch naming, conventional commits, lockstep
      versioning, `M`-prefixed component workflow) is confirmed to still
      match the repo; any drift found is fixed in the same PR with a short
      note in the PR description of what changed and why.
- [ ] 2. Verify `CODE_OF_CONDUCT.md` currency (depends on 1, can run in
      parallel) — DoD: enforcement contact (`security@mctl.ai`) confirmed
      consistent with `SECURITY.md`; content confirmed to still be the
      intended Contributor Covenant v2.1 text with no stale
      placeholders/dates.
- [ ] 3. Add a `## Contributing` section to `README.md`, placed after
      `## Components` and before `## License`, linking
      `[CONTRIBUTING.md](./CONTRIBUTING.md)` and
      `[Code of Conduct](./CODE_OF_CONDUCT.md)` (depends on 1, 2) — DoD:
      section added with relative links matching the existing
      `[LICENSE](./LICENSE)` style; `README.md` renders correctly in a
      Markdown preview with both links resolving to files that exist at the
      repo root.
- [ ] 4. Spot-check that no other root-level doc (`SECURITY.md`, PR/issue
      templates) needs a matching update as a side effect of this change —
      DoD: confirm via `grep -rn "CONTRIBUTING\|CODE_OF_CONDUCT"` that no
      other file was silently relying on the previous unlinked state; no
      changes required unless something surfaces (none expected based on
      investigation).

## Tests
- [ ] T1. Manual Markdown render check (e.g. GitHub PR preview or a local
      Markdown viewer) confirms the new `## Contributing` section displays
      correctly and both links are clickable.
- [ ] T2. Confirm `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` exist at the
      exact relative paths used in the new links (`./CONTRIBUTING.md`,
      `./CODE_OF_CONDUCT.md`) via `ls` at repo root — both already exist
      today, so this is a no-op guard against typos introduced by the edit.
- [ ] T3. Run `pnpm lint` if the repo's lint config covers Markdown files;
      otherwise confirm via `.prettierrc` / `eslint.config.js` whether
      `README.md` is in scope, and if so run the formatter/linter over the
      edited file to keep formatting consistent with the rest of the repo.
- [ ] T4. Re-run the currency checks from tasks 1-2 as a final pass before
      merge, confirming no other PR merged in the meantime changed the
      commands or conventions documented in `CONTRIBUTING.md`.

## Rollback
This is a documentation-only, single-file (plus at most the two governance
files if a currency fix is needed) change with no build, runtime, or
published-package impact. To roll back: revert the merge commit on `main`
(`git revert <sha>`) per this repo's merge-commit, no-squash branch
strategy documented in `CONTRIBUTING.md`. No data migration, no cache
invalidation, no service redeploy is required — `README.md` is not consumed
by CI (`ci.yml`), the Docker image build, or `publish.yml`.
