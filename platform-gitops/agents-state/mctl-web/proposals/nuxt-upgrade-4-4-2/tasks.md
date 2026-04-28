# Tasks: nuxt-upgrade-4-4-2

- [ ] 1. Read the official Nuxt 4.3→4.4 migration guide and the vue-router v4→v5 changelog; capture the list of breaking changes applicable to mctl-web. — DoD: the breaking-changes list is recorded in the PR description.
- [ ] 2. Update `nuxt` to `"^4.4.2"` and `vue-router` to `"^5.0.6"` in `package.json`; run `npm install` / `pnpm install`. — DoD: lockfile is fixed at Nuxt 4.4.x and vue-router 5.x with no peer-dependency conflicts.
- [ ] 3. Inspect and fix direct imports from `vue-router` in every `.vue` file and composable (`app/pages/`, `app/components/`, `app/composables/`). — DoD: there are no direct `import ... from 'vue-router'` other than types; everything is moved to Nuxt wrappers or to the vue-router v5 API.
- [ ] 4. Inspect `nuxt.config.ts` for options deprecated between v4.3 and v4.4; apply needed changes. — DoD: `nuxt build` emits no deprecation warnings.
- [ ] 5. Run `nuxt typecheck` — confirm no TypeScript errors. — DoD: exit code 0.
- [ ] 6. Run `nuxt generate` — confirm the prerender produces HTML for `/`, `/docs`, `/privacy`. — DoD: three HTML files are present in `dist/`, no console errors.
- [ ] 7. Smoke test in staging: navigate through all three pages, submit the tenant form (calls `/api/submit`). — DoD: no console errors, the form submits correctly.
- [ ] 8. Open and merge the PR; deploy via `deploy.yml`. — DoD: prod returns valid HTML for `mctl.ai`, `mctl.ai/docs`, `mctl.ai/privacy`.

## Tests

- [ ] T1. `nuxt build` finishes with exit code 0.
- [ ] T2. `nuxt typecheck` finishes with exit code 0.
- [ ] T3. `nuxt generate` produces HTML for `/`, `/docs`, `/privacy` (verified via `ls dist/`).
- [ ] T4. In browser DevTools — no Vue hydration warnings on any of the three pages.
- [ ] T5. `curl https://mctl.ai` returns HTTP 200 with valid HTML after the deploy.
- [ ] T6. `curl https://mctl.ai/docs` and `https://mctl.ai/privacy` — HTTP 200.

## Rollback

Restore the previous versions of `nuxt` and `vue-router` in `package.json`, regenerate the lockfile, rebuild and deploy via `deploy.yml`. The Cloudflare Worker is untouched — only the frontend is rolled back.
