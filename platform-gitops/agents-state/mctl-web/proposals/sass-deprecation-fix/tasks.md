# Tasks: sass-deprecation-fix

- [ ] 1. Bump sass to `1.99.0` in `package.json` and update lockfile — DoD: `package.json` contains `"sass": "1.99.0"`; `npm install` completes without errors; `package-lock.json` is updated and committed together.
- [ ] 2. Run `nuxt build` with sass 1.99.0 and capture all deprecation warnings (depends on 1) — DoD: a complete list of deprecated patterns found in the mctl-web SCSS source is documented (file, line, pattern type) for use in task 3.
- [ ] 3. Fix all deprecated SCSS patterns identified in task 2 (depends on 2) — DoD: every deprecated call (global built-in functions, legacy color functions, etc.) is replaced with its `sass:*` module equivalent; all changed files pass a manual review confirming the computed CSS values are semantically identical.
- [ ] 4. Verify zero deprecation warnings in a clean build (depends on 3) — DoD: `nuxt build` completes with zero sass deprecation warnings; the build log is captured as evidence and linked in the PR description.
- [ ] 5. Visual regression check on the built site (depends on 4) — DoD: pages `/`, `/docs`, and `/privacy` render without visible style differences compared to the production build; checked in at least one Chromium-based browser and one Firefox build.
- [ ] 6. Deploy to production and update `context/current-version.md` (depends on 5) — DoD: deploy pipeline runs green; an ADR is added to `context/decisions/` documenting the sass 1.99.0 upgrade and SCSS remediation.

## Tests

- [ ] T1. `nuxt build` exits with code 0 and zero lines matching `Deprecation Warning` in stdout/stderr — verified in CI log.
- [ ] T2. `grep -r 'darken\|lighten\|saturate\|desaturate\|mix\|adjust-hue\|rgba(' app/` (or equivalent sass global built-in patterns) returns no matches in `.scss` files after remediation.
- [ ] T3. A snapshot or screenshot comparison of `/`, `/docs`, and `/privacy` shows no visual difference from the pre-change build — recorded in the PR.
- [ ] T4. The CI pipeline (lint + build steps) runs green on the PR branch before merge.

## Rollback
1. Revert the `package.json`, `package-lock.json`, and any modified `.scss` files via a single `git revert` commit or by reverting the PR.
2. The build pipeline will revert to sass 1.98.0 on the next CI run.
3. Deprecation warnings will reappear but the build will not fail (sass 2.0 is not yet released).
4. No runtime state, database, or secrets are affected; rollback is instantaneous.
