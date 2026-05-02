# Tasks: wrangler-4-87-upgrade

- [ ] 1. Confirm current wrangler version in cloudflare-worker/ — Read
  `cloudflare-worker/package.json` and record the current pinned wrangler version. DoD: version
  confirmed in writing; if already >= 4.87.0, this proposal is a no-op and can be closed.

- [ ] 2. Bump wrangler in cloudflare-worker/package.json (depends on 1) — Update the `wrangler`
  version to exactly `4.87.0` (exact pin, no `^` or `~`). DoD: `package.json` shows
  `"wrangler": "4.87.0"` and no other unrelated changes.

- [ ] 3. Regenerate lock file (depends on 2) — Run `npm install` inside `cloudflare-worker/`.
  DoD: `package-lock.json` resolves wrangler to `4.87.0`; `npm ci` succeeds from clean state.

- [ ] 4. Verify local Worker dev (depends on 3) — Run `npx wrangler dev` inside
  `cloudflare-worker/` and confirm all four `/api/*` endpoints respond correctly (GitHub login
  redirect, OAuth callback, submit endpoint, contact endpoint). DoD: `wrangler --version` prints
  `4.87.0`; all endpoints return expected responses; no startup errors.

- [ ] 5. Test-deploy to preview environment (depends on 4) — Trigger the `deploy.yml` workflow
  against a Cloudflare Pages preview environment (or run `wrangler deploy --env preview`). DoD:
  `wrangler deploy` exits 0; CI log shows wrangler version 4.87.0; all rate-limit headers are
  present in endpoint responses.

- [ ] 6. Add inline comment to deploy.yml (depends on 5) — Add a brief comment in `deploy.yml`
  noting the pinned wrangler version and the date of this upgrade for future maintainers. DoD:
  comment present; no functional change to the workflow.

- [ ] 7. Commit (depends on 5, 6) — Commit `cloudflare-worker/package.json`,
  `cloudflare-worker/package-lock.json`, and the updated `deploy.yml` atomically. DoD: CI
  pipeline passes end-to-end; production deployment succeeds.

## Tests

- [ ] T1. `npm ci && npx wrangler --version` inside `cloudflare-worker/` prints `4.87.0`.
- [ ] T2. `wrangler deploy` in CI exits 0 with no deprecation warnings that were absent in the
  previous version.
- [ ] T3. All four `/api/*` endpoints respond correctly after deployment:
  - `/api/github/login` returns a GitHub OAuth redirect (or rate-limit 429 after 10 req/min).
  - `/api/github/callback` processes a valid state token without error.
  - `/api/submit` accepts a valid JSON body and forwards to Backstage.
  - `/api/contact` accepts a valid message and dispatches Telegram notification.
- [ ] T4. Rate limits are enforced unchanged: 5/5 min on `/api/submit`, 3/5 min on
  `/api/contact`, 10/min on `/api/github/login`.

## Rollback
Revert `cloudflare-worker/package.json` and `package-lock.json` to the prior pinned wrangler
version, run `npm ci`, and re-run `wrangler deploy` (or re-trigger `deploy.yml`). The rollback
is complete when `wrangler --version` in CI confirms the previous version and all `/api/*`
endpoints respond normally.
