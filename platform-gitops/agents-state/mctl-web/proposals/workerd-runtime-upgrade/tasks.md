# Tasks: workerd-runtime-upgrade

- [ ] 1. Verify workerd version resolved by wrangler@4.86.0 — run `npm install wrangler@4.86.0` inside `cloudflare-worker/` and then `npm ls workerd` to confirm whether the resolved workerd version is v1.20260430.1 or later. Document the finding. — DoD: the resolved workerd version is recorded; it is either already v1.20260430.1+ (proceed to Task 2 without a pin) or below (proceed to Task 2 with a pin required).

- [ ] 2. Add explicit workerd pin if required (depends on 1) — if Task 1 shows the resolved version is below v1.20260430.1, add `"workerd": "1.20260430.1"` to the `devDependencies` section of `cloudflare-worker/package.json` and run `npm install` to regenerate `package-lock.json`. — DoD: `npm ls workerd` inside `cloudflare-worker/` reports `workerd@1.20260430.1`; `package-lock.json` is committed.

- [ ] 3. Update `compatibility_date` in `wrangler.toml` (depends on 1) — set `compatibility_date = "2026-04-30"` in `cloudflare-worker/wrangler.toml`. Review Cloudflare's compatibility flags changelog for 2026-04-30 and add any necessary `compatibility_flags` entries to disable risky new behaviors. — DoD: `wrangler.toml` contains `compatibility_date = "2026-04-30"`; any new compatibility flag that could alter Worker semantics is explicitly documented as safe or suppressed.

- [ ] 4. Local smoke-test with `wrangler dev` (depends on 2, 3) — start the Worker locally with `wrangler dev` and exercise all four endpoints: send a GET to `/api/github/login`, simulate the OAuth callback at `/api/github/callback`, POST a tenant provisioning request to `/api/submit`, and POST a contact submission to `/api/contact`. Confirm rate-limit headers are present and correct. — DoD: all four endpoints respond without 5xx errors or runtime panics in `wrangler dev` output; rate limits (5/5min on /submit, 3/5min on /contact, 10/min on /github/login) behave as before.

- [ ] 5. Staging deploy and `wrangler tail` verification (depends on 4) — deploy the updated Worker to a staging slot (or a named staging environment in `wrangler.toml`) using `wrangler deploy --env staging`. Attach `wrangler tail` and trigger at least one request to each endpoint. Confirm richer fetch error messages are visible for a deliberately forced external-service error (e.g., an invalid Backstage token). — DoD: `wrangler tail` output shows improved fetch error message format (error type and cause visible); no use-after-free or runtime crash messages appear in the tail stream; the Cloudflare dashboard for the staging Worker shows runtime version v1.20260430.1.

- [ ] 6. Production deploy via GitHub Actions (depends on 5) — merge the changes (`package.json`, `package-lock.json`, `wrangler.toml`) to the main branch and let `deploy.yml` run the production deploy. — DoD: the `deploy.yml` workflow completes without errors; `wrangler versions list` or the Cloudflare dashboard confirms the production Worker is running on workerd v1.20260430.1; no alerts fire in the 30 minutes following deployment.

- [ ] 7. Post-deploy acceptance verification (depends on 6) — run a live acceptance check against production: verify `/api/github/login` redirects correctly, confirm `/api/contact` returns the expected response to a test submission, and confirm rate limiting is intact by sending a burst of requests to `/api/submit`. — DoD: all four `/api/*` endpoints return correct responses; rate limits behave as specified; no new errors appear in `wrangler tail` during the verification window.

## Tests

- [ ] T1. Unit — confirm `wrangler.toml` `compatibility_date` is set to `2026-04-30` or later in a CI lint step (e.g., a simple `grep` assertion in the workflow or a `wrangler.toml` schema check).
- [ ] T2. Integration (local) — `wrangler dev` must start and serve all four `/api/*` endpoints without exit code 1; verified by the smoke-test script introduced in Task 4.
- [ ] T3. Integration (staging) — `wrangler tail` output from staging contains at least one response log entry per endpoint with no `use-after-free` or `undefined behavior` keywords.
- [ ] T4. Rate-limit regression — send 6 consecutive POST requests to `/api/submit` within a 5-minute window against staging; the 6th request must receive HTTP 429.
- [ ] T5. Version assertion — a post-deploy CI step calls `wrangler versions list` and asserts the active version reports workerd v1.20260430.1 or later; fails the pipeline if the assertion is not met.

## Rollback
The rollback procedure is a revert of the `cloudflare-worker/package.json`, `package-lock.json`, and `wrangler.toml` changes followed by a re-run of `deploy.yml`:

1. `git revert <merge-commit>` or manually restore the previous `wrangler.toml` (`compatibility_date = "2026-04-26"` or the prior value) and remove the `workerd` pin from `package.json`.
2. Run `npm install` inside `cloudflare-worker/` to restore the prior `package-lock.json`.
3. Push to main; `deploy.yml` will redeploy the Worker with the previous workerd version.
4. Confirm via `wrangler versions list` that the active version has reverted.

Because all changes are in source-controlled configuration files and no secrets or external integration settings are modified, rollback is fast (one pipeline run, approximately 2-3 minutes) and fully reversible. Cloudflare retains the previous deployment as a version in the Workers dashboard, allowing an instant rollback via the Cloudflare UI (`wrangler rollback`) as an alternative to the git-based path.
