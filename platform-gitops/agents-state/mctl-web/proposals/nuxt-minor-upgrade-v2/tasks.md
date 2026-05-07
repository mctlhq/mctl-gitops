# Tasks: nuxt-minor-upgrade-v2

- [ ] 1. Review Nuxt 4.3.1 → 4.4.3 changelogs — DoD: A PR comment documents any breaking changes, deprecations, or prerender-relevant changes found in the Nuxt 4.4.x release notes. If no breaking changes affect mctl-web, the comment states this explicitly.

- [ ] 2. Bump nuxt in package.json to 4.4.3 and regenerate lockfile (depends on 1) — DoD: `package.json` shows `"nuxt": "4.4.3"` (or `"^4.4.3"`), `package-lock.json` is regenerated with `npm install`, and the lockfile is committed. The resolved Vue version in the lockfile is confirmed to be >= 3.5.34.

- [ ] 3. Run nuxt build locally and inspect dist/ output (depends on 2) — DoD: `nuxt build` completes without errors. The `dist/` directory contains prerendered HTML for `/`, `/docs`, and `/privacy`. No console errors or unresolved imports appear in the build output.

- [ ] 4. Address any compatibility issues found in step 3 (depends on 3) — DoD: If any secondary dependency (e.g., vite-svg-loader, @vueuse/core) requires a version bump for compatibility with Nuxt 4.4.3, that bump is applied and documented in the PR description. If no issues are found, this task is marked N/A.

- [ ] 5. Deploy to Cloudflare Pages preview (depends on 3) — DoD: A Cloudflare Pages preview URL is accessible and serves HTTP 200 for `/`, `/docs`, and `/privacy` with correct HTML. The tenant request form renders and client-side validation (vee-validate + yup) functions correctly.

- [ ] 6. Merge to main and confirm production deploy (depends on 5) — DoD: The `deploy.yml` workflow completes successfully on main. The production Cloudflare Pages deployment serves the upgraded build. No error spikes observed in Cloudflare analytics for 30 minutes post-deploy.

## Tests

- [ ] T1. Build smoke test — `nuxt build` exits 0 with no errors or unresolved imports.
- [ ] T2. Prerender completeness — `dist/` contains `index.html`, `docs/index.html`, and `privacy/index.html` after build.
- [ ] T3. Vue version confirmation — `grep -r "\"version\"" node_modules/vue/package.json` shows >= 3.5.34.
- [ ] T4. Form regression — on the preview URL, submit the tenant request form with invalid data and confirm vee-validate error messages appear; submit with valid data and confirm the request is accepted.
- [ ] T5. Route HTTP check — `curl -I <preview-url>/`, `curl -I <preview-url>/docs`, `curl -I <preview-url>/privacy` all return HTTP 200.

## Rollback
If the upgrade causes a production regression:
1. Revert the `package.json` and `package-lock.json` changes via a revert commit on main.
2. Trigger `deploy.yml` on the revert commit to restore the Nuxt 4.3.1 build to Cloudflare Pages.
3. No Kubernetes or ArgoCD changes are needed — the service is served entirely via Cloudflare Pages.
4. Open a follow-up issue documenting the regression before reattempting the upgrade.
