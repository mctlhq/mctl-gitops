# Tasks: nuxt-minor-upgrade-v3

- [ ] 1. Review changelogs for all three bumped packages — read the release notes for
  Nuxt 4.4.0 through 4.4.3 (https://github.com/nuxt/nuxt/releases/tag/v4.4.3),
  @vueuse/core 14.3.0, and sass 1.99.0. Note any breaking changes, deprecations, or
  prerender-relevant changes that affect mctl-web's usage of Nuxt composables,
  `nuxt.config.ts`, prerender configuration, VueUse composables, or SCSS syntax.
  DoD: a PR description section titled "Changelog review" lists any findings and confirms
  either that none apply to mctl-web, or documents the code changes required.

- [ ] 2. Update `package.json` with the three version bumps (depends on 1) — change
  `nuxt` to `^4.4.3`, `@vueuse/core` to `^14.3.0`, and `sass` to `^1.99.0` in the root
  `package.json`.
  DoD: `package.json` reflects all three updated constraints and the file is saved.

- [ ] 3. Regenerate the lockfile (depends on 2) — run `npm install` in the project root.
  DoD: `package-lock.json` resolves `nuxt` to 4.4.3, `@vueuse/core` to 14.3.0, `sass` to
  1.99.0, and Vue to >= 3.5.34. No unrelated package versions change. The lockfile is
  committed to the branch.

- [ ] 4. Run local build and inspect `dist/` output (depends on 3) — execute `nuxt build`
  locally.
  DoD: the build completes without errors; `dist/` contains prerendered HTML for `/`,
  `/docs`, and `/privacy`; spot-check confirms correct page titles, copy, and SVG assets;
  no JavaScript console errors appear when the built output is served locally.

- [ ] 5. Address deprecation warnings from Nuxt, VueUse, or sass (depends on 4) — if
  `nuxt build` or the sass compiler emits deprecation warnings, update the relevant
  composable calls, config options, or SCSS syntax.
  DoD: `nuxt build` output is free of deprecation warnings, or a follow-up issue is filed
  and linked in the PR before merge.

- [ ] 6. Run security audit (depends on 3) — execute `npm audit --audit-level=high` in
  the project root.
  DoD: `npm audit` exits 0; no new High or Critical CVEs are introduced by the upgrade.

- [ ] 7. Deploy to Cloudflare Pages preview and verify routes (depends on 4, 5, 6) —
  push the branch to GitHub; the Actions workflow deploys a preview build.
  DoD: Cloudflare Pages preview URL is accessible; HTTP 200 is returned for `/`, `/docs`,
  and `/privacy`; the tenant onboarding form renders and client-side validation
  (vee-validate + yup) functions correctly on the preview deployment.

- [ ] 8. Open PR, obtain review, and merge (depends on 7) — create a pull request titled
  `chore: bump nuxt 4.3.1→4.4.3, @vueuse/core 14.2.1→14.3.0, sass 1.98.0→1.99.0`.
  Include the changelog summary, build output confirmation, audit result, and preview URL
  in the PR description.
  DoD: at least one peer review approval; CI (lint, type-check, build) is green; PR is
  merged to main; production Cloudflare Pages deployment completes successfully.

## Tests

- [ ] T1. Build exit code — `nuxt build` exits 0 with no error output.
- [ ] T2. Prerender completeness — `dist/` contains `index.html`, `docs/index.html`, and
  `privacy/index.html` after the build completes.
- [ ] T3. Vue version pin — `node -e "console.log(require('./node_modules/vue/package.json').version)"`
  prints a version >= 3.5.34.
- [ ] T4. Package version verification — `node -e "console.log(require('./node_modules/nuxt/package.json').version)"`
  prints 4.4.3; equivalent checks for @vueuse/core (14.3.0) and sass (1.99.0).
- [ ] T5. Security audit — `npm audit --audit-level=high` exits 0 after the lockfile
  is regenerated.
- [ ] T6. Route HTTP check — `curl -I <preview-url>/`, `curl -I <preview-url>/docs`, and
  `curl -I <preview-url>/privacy` all return HTTP 200.
- [ ] T7. Form regression — on the preview URL, submit the tenant request form with invalid
  data and confirm vee-validate error messages appear; submit with valid data and confirm
  the `/api/submit` request is dispatched without error.
- [ ] T8. SVG regression — at least one inline SVG is present and renders correctly in
  the prerendered `dist/index.html`, confirming `vite-svg-loader 5.1.1` compatibility
  with the Vite version bundled in Nuxt 4.4.3.

## Rollback
If the upgraded build causes a production regression after merging to main:

1. Use GitHub's "Revert" button on the merged PR to create a revert commit. This restores
   `package.json` and `package-lock.json` to the Nuxt 4.3.1 / @vueuse/core 14.2.1 /
   sass 1.98.0 state.
2. Push the revert commit to main; the `deploy.yml` workflow triggers automatically and
   redeploys the previous build to Cloudflare Pages.
3. No Kubernetes or ArgoCD changes are needed — the service is served entirely via
   Cloudflare Pages static output.
4. If the regression is detected before merge: close the PR without merging. The main
   branch is unaffected.
5. File an issue documenting the regression, link it to the relevant Nuxt 4.4.x GitHub
   issue if one exists, and wait for a patch release (e.g., 4.4.4 or later) before
   re-attempting the upgrade.
