# Tasks: vueuse-upgrade-14-3

- [ ] 1. Bump @vueuse/core in package.json — Update the version specifier for `@vueuse/core`
  from `14.2.1` to `^14.3.0` (or `14.3.0` exact if project uses exact pins) in the Nuxt app's
  `package.json`. DoD: `package.json` contains the new version and no other unrelated changes.

- [ ] 2. Regenerate lock file (depends on 1) — Run `npm install` in the Nuxt app root to update
  `package-lock.json`. DoD: `package-lock.json` resolves `@vueuse/core` to `14.3.0` and
  `npm ci` succeeds from a clean state.

- [ ] 3. Verify build (depends on 2) — Run `nuxt build` locally and confirm it exits 0 with no
  new warnings or errors attributable to @vueuse/core. DoD: build artefact in `dist/` is
  produced cleanly; no @vueuse-related console errors.

- [ ] 4. Smoke-test dev server (depends on 2) — Run `nuxt dev` and manually verify `/`,
  `/docs`, `/privacy`, and the tenant onboarding form render correctly and all interactive
  composable-backed behaviours (form validation, navigation) work as before. DoD: no JavaScript
  console errors referencing @vueuse/core on any of the four routes.

- [ ] 5. Commit (depends on 3, 4) — Commit `package.json` and `package-lock.json` atomically
  with a message referencing this proposal. DoD: single commit containing exactly two changed
  files; CI pipeline passes.

## Tests

- [ ] T1. `npm ci && nuxt build` exits 0 in a clean CI environment — verifies the lock file is
  consistent and the build is reproducible.
- [ ] T2. No new `@vueuse/core` warnings or errors appear in the browser console when navigating
  all three prerendered routes (`/`, `/docs`, `/privacy`).
- [ ] T3. The tenant onboarding form (multi-step registration with GitHub OAuth) submits and
  validates without errors after the upgrade.

## Rollback
Revert `package.json` and `package-lock.json` to the prior committed versions and run `npm ci`.
No Worker code, Kubernetes manifests, or Cloudflare configuration need to be changed.
