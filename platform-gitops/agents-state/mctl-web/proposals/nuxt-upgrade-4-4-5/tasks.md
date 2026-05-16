# Tasks: nuxt-upgrade-4-4-5

- [ ] 1. Update `nuxt` version specifier — In `app/package.json`, change `"nuxt": "4.3.1"` to `"nuxt": "^4.4.5"`. — DoD: `package.json` contains `"nuxt": "^4.4.5"`; file is committed.

- [ ] 2. Refresh lockfile (depends on 1) — Run `npm install` inside `app/` to regenerate `package-lock.json`. — DoD: `package-lock.json` resolves `nuxt@4.4.5`; no unrelated dependency changes appear in the diff.

- [ ] 3. Local build verification (depends on 2) — Run `nuxt build` locally; confirm `dist/` is produced without errors. — DoD: build exits 0; all three prerendered routes appear in `dist/`.

- [ ] 4. Lint and type-check (depends on 2) — Run lint + `nuxt typecheck`. — DoD: both commands exit 0 with no new errors relative to the 4.3.1 baseline.

- [ ] 5. Review `nuxt.config.ts` compatibility (depends on 1) — Check Nuxt 4.4.x changelog for any deprecated configuration keys used in `nuxt.config.ts`. — DoD: no deprecated keys present, or keys updated if deprecation warnings appear.

- [ ] 6. Open PR and pass CI (depends on 3, 4, 5) — Create a pull request; `deploy.yml` must complete successfully (build + Cloudflare Pages deploy). — DoD: CI green; reviewer approves.

## Tests

- [ ] T1. Prerender smoke test — After deploy, verify HTTP 200 from `https://mctl.ai/`, `https://mctl.ai/docs`, `https://mctl.ai/privacy`.
- [ ] T2. Form functionality check — Submit the tenant request form on `/` to confirm the `/api/submit` Worker endpoint responds correctly (rate-limit and Backstage call remain intact).
- [ ] T3. Build time measurement — Compare `nuxt build` wall-clock time before (4.3.1) and after (4.4.5) to confirm the caching/isIgnored improvements produce a measurable improvement.

## Rollback
Revert `app/package.json` and `package-lock.json` to `nuxt@4.3.1`. Re-run `npm install` and redeploy via `deploy.yml`. The prerendered output is stateless; rollback is a full redeploy of the previous commit with no data migration needed.
