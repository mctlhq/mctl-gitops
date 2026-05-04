# Tasks: patch-dep-refresh

- [ ] 1. Review changelogs for all three packages — read the release notes for vue 3.5.31–3.5.33, @vueuse/core 14.2.2–14.3.0, and sass 1.98.1–1.99.0. Note any deprecations or behaviour changes relevant to this project. DoD: a brief note in the PR description confirms no breaking changes apply, or lists required code fixes.

- [ ] 2. Grep SCSS source files for reserved function names (depends on 1) — search all `.scss` / `.sass` files under `app/` for `@function` declarations whose names match CSS built-in functions (`calc`, `clamp`, `min`, `max`, `round`, `abs`). DoD: no matches found, or any matches are renamed in this task.

- [ ] 3. Update version constraints in root `package.json` (depends on 1, 2) — set `"vue": "^3.5.33"`, `"@vueuse/core": "^14.3.0"`, `"sass": "^1.99.0"`. DoD: `package.json` reflects the three updated constraints.

- [ ] 4. Regenerate the root lockfile (depends on 3) — run `npm install` (or `pnpm install`) in the project root. DoD: the lockfile resolves vue to ≥ 3.5.33, @vueuse/core to ≥ 14.3.0, and sass to ≥ 1.99.0; the diff contains only these three packages and their direct transitive changes.

- [ ] 5. Run local build and verify output (depends on 4) — execute `nuxt build`. DoD: build completes without errors; zero deprecation warnings related to sass function names; `dist/` contains correct prerendered HTML for `/`, `/docs`, and `/privacy`.

- [ ] 6. Run security audit (depends on 4) — execute `npm audit --audit-level=high`. DoD: no new High or Critical vulnerabilities introduced by the three bumps; audit exits 0.

- [ ] 7. Open PR and obtain review (depends on 5, 6) — create a pull request titled "chore: patch-level dep refresh — vue 3.5.33, @vueuse/core 14.3.0, sass 1.99.0". Include changelog summary and build confirmation. DoD: at least one peer review approval; CI build step is green.

## Tests

- [ ] T1. `nuxt build` exits with code 0 with no error or deprecation output in stderr.
- [ ] T2. Prerendered `dist/index.html`, `dist/docs/index.html`, and `dist/privacy/index.html` exist and contain expected landmark elements (spot-check against 4.3.1 baseline).
- [ ] T3. `npm audit --audit-level=high` exits 0 after lockfile regeneration.
- [ ] T4. `grep -r "@function calc\|@function clamp\|@function min\|@function max" app/` returns no matches.
- [ ] T5. CI pipeline (lint + build) passes on the PR branch without manual intervention.

## Rollback
If the batched bump causes a build regression:
1. Revert the PR (GitHub "Revert" button on the merged PR). The committed lockfile restores the previous versions on the next `npm install`.
2. To isolate the offending package, re-apply the bumps one at a time (vue, then @vueuse/core, then sass) in separate local branches and identify which one causes the failure.
3. Open a targeted follow-up PR for the two packages that do not regress; file an issue for the offending package and monitor its upstream tracker for a fix.
