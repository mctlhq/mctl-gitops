# Tasks: workerd-runtime-2026-05-15

- [ ] 1. Identify the wrangler version that bundles workerd v1.20260515.1 — Run `npm info wrangler` or inspect the `workers-sdk` changelog to find the wrangler release that ships workerd 1.20260515.1. — DoD: target wrangler version identified and documented in the PR description.

- [ ] 2. Update `wrangler` pin in `cloudflare-worker/package.json` (depends on 1) — Change `"wrangler"` to the version identified in task 1 (or `>=<that-version> <5.0.0`). Optionally add `"workerd": "1.20260515.1"` as a devDependency for explicit drift prevention. — DoD: `cloudflare-worker/package.json` reflects the target wrangler version; `package-lock.json` is updated.

- [ ] 3. Local smoke test with `wrangler dev` (depends on 2) — Run `wrangler dev` inside `cloudflare-worker/`; send requests to `/api/github/login`, `/api/submit`, and `/api/contact` using curl or a browser. — DoD: all three endpoints respond correctly; runtime version in wrangler output shows `workerd/1.20260515.1`.

- [ ] 4. Verify rate-limit behaviour (depends on 3) — Send more than the allowed requests within the time window for each rate-limited endpoint and confirm 429 responses are returned as expected. — DoD: rate-limit behaviour is unchanged from pre-upgrade.

- [ ] 5. Open PR and pass CI (depends on 3, 4) — Create a pull request; `deploy.yml` must complete the wrangler deploy step without error. — DoD: CI green; Worker deployed to Cloudflare; reviewer approves.

## Tests

- [ ] T1. `/api/github/login` smoke test — GET `https://mctl.ai/api/github/login`; expect HTTP 302 redirect to GitHub OAuth.
- [ ] T2. `/api/contact` smoke test — POST a well-formed contact payload; expect HTTP 200 and Telegram notification delivered.
- [ ] T3. Rate-limit regression — Exceed the rate limit for `/api/submit` (>5 in 5 min); confirm HTTP 429 response with appropriate headers.

## Rollback
Revert `cloudflare-worker/package.json` and `cloudflare-worker/package-lock.json` to the previous wrangler pin. Re-run `npm install` inside `cloudflare-worker/` and redeploy via `deploy.yml`. The Worker is stateless (rate-limit state is in Cloudflare KV/DO); rollback completes in one deploy cycle.
