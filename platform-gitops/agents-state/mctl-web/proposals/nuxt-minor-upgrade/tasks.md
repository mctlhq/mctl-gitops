# Tasks: nuxt-minor-upgrade

- [ ] 1. Review Nuxt 4.4.x changelog — read the release notes for 4.4.0 through 4.4.4 at https://github.com/nuxt/nuxt/releases and note any deprecations or changes relevant to this project's usage of Nuxt composables, `nuxt.config.ts`, and the prerender configuration. DoD: a brief note in the PR description lists any breaking or deprecation notices and confirms none apply, or lists required code changes.

- [ ] 2. Update nuxt version constraint in `package.json` (depends on 1) — change the `nuxt` entry to `"nuxt": "^4.4.4"` in the root `package.json`. DoD: `package.json` declares the updated constraint and the file is saved.

- [ ] 3. Regenerate the lockfile (depends on 2) — run `npm install` (or `pnpm install`) in the project root. DoD: the lockfile resolves nuxt to 4.4.4; the diff contains only nuxt and its direct transitive changes; no unrelated package versions change.

- [ ] 4. Run local build and inspect output (depends on 3) — execute `nuxt build` locally. DoD: the build completes without errors or warnings; `dist/` contains prerendered HTML for `/`, `/docs`, and `/privacy`; spot-check confirms correct page titles, copy, and SVG assets render as expected.

- [ ] 5. Address any deprecation warnings (depends on 4) — if `nuxt build` emits deprecation warnings for API usages, update the relevant composable calls or config options. DoD: `nuxt build` output is clean (zero deprecation warnings) or a follow-up issue is filed and linked in the PR.

- [ ] 6. Run security audit (depends on 3) — execute `npm audit --audit-level=high` in the project root. DoD: no new High or Critical CVEs are introduced by the upgrade; audit exits 0.

- [ ] 7. Open PR and obtain review (depends on 4, 5, 6) — create a pull request titled "chore: upgrade nuxt 4.3.1 → 4.4.4". Include the changelog summary, build output confirmation, and audit result in the PR description. DoD: at least one peer review approval; CI build step is green.

## Tests

- [ ] T1. `nuxt build` exits with code 0 and produces files at `dist/index.html`, `dist/docs/index.html`, and `dist/privacy/index.html`.
- [ ] T2. Each of the three prerendered HTML files contains the expected `<title>` tag and at least one known landmark element (confirmed against the 4.3.1 baseline output).
- [ ] T3. `npm audit --audit-level=high` exits 0 after the lockfile is updated.
- [ ] T4. CI pipeline (lint + build) passes on the PR branch without manual intervention.
- [ ] T5. If SVG assets are present in the build output, verify at least one inline SVG is correctly rendered in `dist/index.html` (regression test for `vite-svg-loader` compatibility).

## Rollback
If the upgraded build regresses or the CI pipeline fails:
1. Revert the PR (GitHub "Revert" button on the merged PR).
2. The previous lockfile (committed to the repo) restores nuxt 4.3.1 automatically on the next `npm install`.
3. Investigate the regression against the Nuxt 4.4.x issue tracker before retrying the upgrade.
4. If a patch release (e.g., 4.4.5) addresses the regression, re-run this proposal against the new patch version.
