# Tasks: vue-patch-3-5-34

- [ ] 1. Update `vue` version specifier — In `app/package.json`, change `"vue"` to `"^3.5.34"`. — DoD: `package.json` contains `"vue": "^3.5.34"` or higher patch; file is committed.

- [ ] 2. Refresh lockfile (depends on 1) — Run `npm install` inside `app/` to regenerate `package-lock.json` with the resolved 3.5.34 patch. — DoD: `package-lock.json` reflects `vue@3.5.34`; no unrelated dependency changes appear in the diff.

- [ ] 3. Build verification (depends on 2) — Run `nuxt build` locally; confirm `dist/` is produced without errors or new TypeScript diagnostics. — DoD: build exits 0 with no new warnings above the 3.5.30 baseline.

- [ ] 4. Lint and type-check (depends on 2) — Run the project's lint + `nuxt typecheck` commands. — DoD: both commands exit 0 with no new errors.

- [ ] 5. Open PR and pass CI (depends on 3, 4) — Create a pull request; the `deploy.yml` CI pipeline must pass (build + deploy to preview). — DoD: CI green on the PR; reviewer approves.

## Tests

- [ ] T1. Smoke test prerendered routes — After deploy, request `https://mctl.ai/`, `https://mctl.ai/docs`, `https://mctl.ai/privacy` and verify HTTP 200 and correct HTML content.
- [ ] T2. Browser console check — Open each prerendered route in a Chromium browser; confirm zero new Vue runtime warnings or errors in the console.
- [ ] T3. Memory regression check — Run a quick Lighthouse or DevTools memory snapshot on `/` before and after; confirm no obvious increase in detached DOM nodes.

## Rollback
Revert the `app/package.json` and `package-lock.json` changes to restore `vue@3.5.30`. Re-run `npm install` and redeploy via `deploy.yml`. The prerendered `dist/` is stateless, so rollback is a simple redeploy of the previous commit.
