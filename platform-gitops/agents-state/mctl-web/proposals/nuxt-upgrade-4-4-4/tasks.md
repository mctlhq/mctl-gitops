# Tasks: nuxt-upgrade-4-4-4

- [ ] 1. Create upgrade branch and bump Nuxt — DoD: `package.json` has `"nuxt": "4.4.4"`; `npm install` (or `pnpm install`) completes with no unresolved peer-dependency errors; lock file is committed.

- [ ] 2. Resolve any transitive peer-dependency warnings (depends on 1) — DoD: `npm ls` reports no peer-dep conflicts; if a transitive package must be pinned, the pin is documented in a comment in `package.json`.

- [ ] 3. Verify local dev server (depends on 1) — DoD: `nuxt dev` starts without errors; HMR works on at least one route change; no console errors related to the upgrade appear in the browser.

- [ ] 4. Run production build locally (depends on 2) — DoD: `nuxt build` exits 0; `dist/` contains the three prerendered routes (`/`, `/docs`, `/privacy`); no TypeScript compile errors; bundle size for the main entry point is equal to or smaller than the baseline from 4.3.1 (checked via `du -sh dist/`).

- [ ] 5. Deploy to staging / Cloudflare Pages preview (depends on 4) — DoD: Cloudflare Pages preview URL returns HTTP 200 for `/`, `/docs`, and `/privacy`; page content renders correctly; no JS console errors on load.

- [ ] 6. Smoke-test the tenant registration OAuth flow in staging (depends on 5) — DoD: GitHub OAuth login round-trip completes successfully; the Worker `/api/github/callback` sets the session cookie correctly; the tenant form submits without error.

- [ ] 7. Smoke-test async data and form validation in staging (depends on 5) — DoD: `useAsyncData` / `useFetch` calls on all pages hydrate without errors; the tenant form validates with vee-validate + yup and reports errors correctly.

- [ ] 8. Update `context/current-version.md` and supersede `nuxt-upgrade-4-4-2` (depends on 6, 7) — DoD: `current-version.md` reflects Nuxt 4.4.4; a note in `nuxt-upgrade-4-4-2/requirements.md` (or a stub file) states the proposal is superseded by `nuxt-upgrade-4-4-4`.

- [ ] 9. Merge to main and trigger production deploy (depends on 8) — DoD: CI pipeline (`deploy.yml`) passes; production site at `mctl.ai` serves all routes from the new build; `nuxt --version` in the build log shows 4.4.4.

## Tests

- [ ] T1. `nuxt build` exits 0 with zero TypeScript errors — run in CI on the upgrade branch.
- [ ] T2. Lighthouse or WebPageTest run on staging `/` — page load performance is not regressed versus the 4.3.1 baseline (LCP within 10% delta).
- [ ] T3. Full GitHub OAuth flow test in staging — login, callback, session cookie, and redirect all succeed.
- [ ] T4. Tenant registration form end-to-end test in staging — valid submission reaches Backstage mock; invalid input triggers correct vee-validate error messages.
- [ ] T5. All three prerendered routes return HTTP 200 and correct `content-type: text/html` from Cloudflare Pages preview.
- [ ] T6. Rate-limit endpoints (`/api/submit`, `/api/contact`, `/api/github/login`) respond with 429 after exceeding the configured thresholds — confirms Worker behavior is unchanged.

## Rollback
If a regression is detected after the production deploy:

1. Revert the merge commit on `main` using `git revert <merge-sha>`.
2. Push the revert commit; the CI pipeline (`deploy.yml`) triggers automatically and re-deploys the previous `dist/` artefact built from Nuxt 4.3.1.
3. Confirm `mctl.ai` is serving from the reverted build (check `nuxt --version` in the build log or inspect the `x-nuxt-version` header if exposed).
4. Open an incident note in `inbox/` describing the regression and block the upgrade until the root cause is identified.

No database migrations or Worker secret changes are involved, so rollback is purely a code revert and re-deploy.
