# Tasks: issue-21-docs-license-file-reference-in-readme

- [ ] 1. Confirm current state — verify `README.md`'s `## License` section
      links to `./LICENSE` and that `LICENSE` exists at the repo root
      (already true as of this proposal; re-check at implementation time in
      case `main` has moved) — DoD: implementer notes in the PR description
      that no README prose change was needed, citing the existing section.
- [ ] 2. Add `scripts/check-license.mjs` (depends on 1) — modeled on
      `scripts/check-versions.mjs`: verifies `LICENSE` exists at the repo
      root, verifies `README.md` contains a link to `./LICENSE` (or
      `LICENSE`) inside a License heading, and verifies the root
      `package.json` `license` field matches every non-private workspace
      package's `license` field — DoD: script runs standalone via
      `node scripts/check-license.mjs`, exits 0 on the current repo state,
      and exits 1 with a clear message when any of the three checks is
      violated (verify by temporarily breaking each check locally).
- [ ] 3. Add `"check:license": "node scripts/check-license.mjs"` to the root
      `package.json` `scripts` block (depends on 2) — DoD: `pnpm
      check:license` runs the script and exits 0.
- [ ] 4. Add a `Check license reference` step to
      `.github/workflows/ci.yml`, running `pnpm check:license`, placed after
      the existing `Check lockstep versions` step (depends on 3) — DoD: CI
      workflow YAML is valid, the new step appears in the `validate` job,
      and it runs after install/lint/typecheck/build/build:storybook/
      check:versions, matching the existing step ordering and style.
- [ ] 5. Update `CONTRIBUTING.md`'s "Local development" command list to
      include `pnpm check:license` alongside the existing `pnpm
      check:versions` mention, if and only if `check:versions` is listed
      there (depends on 3) — DoD: `CONTRIBUTING.md` command list stays
      consistent with `package.json` scripts; skip this task if
      `check:versions` is not actually listed in that section (re-verify
      against the file at implementation time).

## Tests
- [ ] T1. Run `node scripts/check-license.mjs` against the unmodified repo
      and confirm it exits 0 with a success message.
- [ ] T2. Temporarily rename `LICENSE` locally (not committed) and re-run
      the script, confirming it exits 1 with a message identifying the
      missing file.
- [ ] T3. Temporarily edit `README.md`'s License section to remove the
      `(./LICENSE)` link locally (not committed) and re-run the script,
      confirming it exits 1 with a message identifying the missing link.
- [ ] T4. Temporarily edit one workspace package's `license` field to a
      different value locally (not committed) and re-run the script,
      confirming it exits 1 identifying the mismatched package.
- [ ] T5. Run `pnpm check:license` (via the new package.json script) and
      confirm it behaves identically to invoking the script directly.
- [ ] T6. Confirm the full CI workflow (`pnpm install`, `pnpm lint`, `pnpm
      typecheck`, `pnpm build`, `pnpm build:storybook`, `pnpm
      check:versions`, `pnpm check:license`) still passes end to end on the
      PR branch.

## Rollback
This change is purely additive tooling with no runtime, published-package,
or README-content impact. To roll back:
1. Revert the PR (single commit/PR expected, per repo convention of merge
   commits, no squash).
2. This removes `scripts/check-license.mjs`, the `check:license` entry in
   `package.json`, and the CI step in `.github/workflows/ci.yml`.
3. No data migrations, deployments, or published package versions are
   affected — reverting is a plain git revert with no follow-up cleanup
   required.
