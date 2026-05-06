# Tasks: wrangler-4-88-upgrade

- [ ] 1. Confirm current wrangler version in cloudflare-worker/ — Read
  `cloudflare-worker/package.json` and record the currently pinned wrangler version. DoD: version
  confirmed in writing; if already >= 4.88.0, this proposal is a no-op and can be closed.

- [ ] 2. Bump wrangler in cloudflare-worker/package.json (depends on 1) — Update the `wrangler`
  version to exactly `4.88.0` (exact pin, no `^` or `~`). DoD: `package.json` shows
  `"wrangler": "4.88.0"` and no other unrelated dependency changes.

- [ ] 3. Regenerate lock file (depends on 2) — Run `npm install` inside `cloudflare-worker/`.
  DoD: `package-lock.json` resolves wrangler to `4.88.0`; `npm ci` succeeds from a clean state.

- [ ] 4. Validate wrangler.toml secrets block (depends on 3) — Run `npx wrangler deploy --dry-run`
  (or the equivalent wrangler 4.88.0 validation command) inside `cloudflare-worker/` against a
  preview environment. DoD: wrangler 4.88.0 validates all seven secret binding entries without
  error; if any validation error is surfaced, the misconfiguration is corrected in `wrangler.toml`
  in the same task before proceeding.

- [ ] 5. Verify local Worker dev (depends on 4) — Run `npx wrangler dev` inside
  `cloudflare-worker/` and confirm all four `/api/*` endpoints respond correctly (GitHub login
  redirect, OAuth callback, submit endpoint, contact endpoint). DoD: `wrangler --version` prints
  `4.88.0`; all endpoints return expected responses; no startup errors; all seven secrets are
  accessible via the local dev binding mechanism.

- [ ] 6. Test-deploy to preview environment (depends on 5) — Trigger the `deploy.yml` workflow
  against a Cloudflare Pages preview environment (or run `wrangler deploy --env preview`). DoD:
  `wrangler deploy` exits 0; CI log shows wrangler version 4.88.0; all seven secrets are bound
  successfully; all rate-limit headers are present in endpoint responses.

- [ ] 7. Update inline comment in deploy.yml (depends on 6) — Update the pinned-version comment
  in `deploy.yml` to reflect wrangler 4.88.0 and the date of this upgrade. DoD: comment present
  and accurate; no functional change to the workflow.

- [ ] 8. Commit (depends on 6, 7) — Commit `cloudflare-worker/package.json`,
  `cloudflare-worker/package-lock.json`, any `wrangler.toml` corrections from Task 4, and the
  updated `deploy.yml` atomically. DoD: CI pipeline passes end-to-end; production deployment
  succeeds; `wrangler --version` in CI confirms 4.88.0.

## Tests

- [ ] T1. `npm ci && npx wrangler --version` inside `cloudflare-worker/` prints `4.88.0`.
- [ ] T2. `wrangler deploy --dry-run` (or equivalent) exits 0 with no secrets-block validation
  errors when all seven secret names are correctly configured in `wrangler.toml`.
- [ ] T3. `wrangler deploy` in CI exits 0 with no deprecation warnings that were absent in the
  4.87.0 run.
- [ ] T4. All four `/api/*` endpoints respond correctly after deployment to the preview environment:
  - `/api/github/login` returns a GitHub OAuth redirect (or 429 after 10 req/min).
  - `/api/github/callback` processes a valid state token without error.
  - `/api/submit` accepts a valid JSON body and forwards to Backstage (requires
    `BACKSTAGE_LANDING_TOKEN` to be bound and valid).
  - `/api/contact` accepts a valid message and dispatches a Telegram notification (requires
    `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `RESEND_API_KEY` to be bound and valid).
- [ ] T5. Rate limits are enforced unchanged after the upgrade: 5/5 min on `/api/submit`, 3/5 min
  on `/api/contact`, 10/min on `/api/github/login`.
- [ ] T6. A deliberately misconfigured `secrets` block entry (e.g., an unknown key) causes
  `wrangler deploy` to exit non-zero with an explicit error message — confirming the stable
  validation is active. (Run on a scratch branch; revert before merging.)

## Rollback
Revert `cloudflare-worker/package.json` and `package-lock.json` to the prior pinned wrangler
version (4.87.0 or whatever was confirmed in Task 1), and if `wrangler.toml` was corrected in
Task 4, decide whether to revert those changes or keep them (the corrections are safe to retain).
Run `npm ci` inside `cloudflare-worker/` and re-run `wrangler deploy` (or re-trigger `deploy.yml`).
The rollback is complete when `wrangler --version` in CI confirms the previous version and all four
`/api/*` endpoints respond normally with all secrets bound.
