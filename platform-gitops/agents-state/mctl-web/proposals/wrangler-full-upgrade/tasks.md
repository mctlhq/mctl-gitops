# Tasks: wrangler-full-upgrade

- [ ] 1. Bump wrangler in `cloudflare-worker/package.json` to `"4.86.0"` — DoD: the file contains `"wrangler": "4.86.0"` as a devDependency; `npm install` completes without errors; `package-lock.json` is updated and committed.
- [ ] 2. Update `deploy.yml` to install wrangler v4.86.0 (depends on 1) — DoD: the Actions workflow step specifies `wrangler@4.86.0` (or equivalent pinned version via `cloudflare/wrangler-action`); no other wrangler version reference remains in the file.
- [ ] 3. Run a staging deploy smoke-test (depends on 2) — DoD: `wrangler deploy` completes successfully against the staging Cloudflare account; no resource-leak warnings appear in output; `wrangler tail` shows stack traces for a manually triggered error.
- [ ] 4. Promote to production deploy (depends on 3) — DoD: `deploy.yml` pipeline runs green on the main branch; Worker version in Cloudflare Dashboard reflects the new deploy; no regressions observed in `/api/*` endpoint responses.
- [ ] 5. Update `context/current-version.md` and add an ADR in `context/decisions/` (depends on 4) — DoD: version file reflects the upgraded wrangler version; ADR documents the rationale for going to v4.86.0 beyond the CVE floor.

## Tests

- [ ] T1. `wrangler --version` in CI prints `4.86.0` — verified in the GitHub Actions log for the deploy job.
- [ ] T2. `wrangler deploy` exits with code 0 against the staging environment — no error or warning lines in stdout/stderr.
- [ ] T3. `wrangler tail` output for a Worker exception includes a JavaScript stack trace — confirmed manually after triggering a test error in the staging Worker.
- [ ] T4. `/api/submit` and `/api/contact` return expected HTTP status codes after the production deploy — verified via a brief manual smoke-test or existing integration test suite.

## Rollback
1. Revert the `cloudflare-worker/package.json` and `deploy.yml` changes in git (single revert commit or `git revert`).
2. Re-run the deploy pipeline; `wrangler deploy` will redeploy the previously pinned version (v4.59.1 or whatever was in place before this change).
3. Confirm the Worker is back at the previous version in the Cloudflare Dashboard.
4. No database migrations or secrets were changed, so no additional rollback steps are needed.
