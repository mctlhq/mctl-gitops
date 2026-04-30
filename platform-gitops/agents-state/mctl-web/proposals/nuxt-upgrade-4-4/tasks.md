# Tasks: nuxt-upgrade-4-4

- [ ] 1. Bump `"nuxt"` in `package.json` from `"4.3.1"` to `"4.4.4"` — DoD: `package.json` shows the new version.
- [ ] 2. Run `npm install` and commit the updated `package-lock.json` — DoD: lockfile committed, no unresolved peer-dependency conflicts.
- [ ] 3. Run `nuxt build` locally and confirm zero errors and zero new deprecation warnings — DoD: build exits 0, no new warnings in output.
- [ ] 4. Deploy to a staging/preview environment (Cloudflare Pages preview branch) and verify prerendered pages — DoD: `/`, `/docs`, `/privacy` load correctly; no hydration mismatch errors in browser console.
- [ ] 5. Smoke-test the tenant onboarding form: submit a test registration request and confirm the OAuth cookie is set and serialized correctly — DoD: GitHub OAuth callback completes and sets a valid session cookie.
- [ ] 6. Merge and trigger the production deploy via `deploy.yml` — DoD: production site serves the new build; Cloudflare Pages deployment shows green.

## Tests
- [ ] T1. `nuxt build` exits with code 0 and output contains prerendered routes `/`, `/docs`, `/privacy`.
- [ ] T2. Browser console on `/` shows zero hydration mismatch warnings after upgrade.
- [ ] T3. Network tab on OAuth callback shows correctly formatted `Set-Cookie` header (no malformed attributes).

## Rollback
Revert the `package.json` and `package-lock.json` to `nuxt@4.3.1` and re-run the deploy workflow. Cloudflare Pages keeps the previous successful deployment available for instant rollback via the dashboard.
