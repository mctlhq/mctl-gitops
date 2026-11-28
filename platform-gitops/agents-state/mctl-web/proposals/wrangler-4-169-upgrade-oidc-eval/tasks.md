# Tasks: wrangler-4-169-upgrade-oidc-eval

- [ ] 1. Bump wrangler to >=4.169.0 — DoD: lockfile updated.
- [ ] 2. Dry-run deploy in CI (depends on 1) — DoD: passes.
- [ ] 3. Write OIDC feasibility note (depends on 1) — DoD: note lists Backstage verification requirements and decision.

## Tests
- [ ] T1. CI build and prerender of /, /docs, /privacy succeed.
- [ ] T2. Smoke test of the affected behaviour (wrangler-4-169-upgrade-oidc-eval).

## Rollback
Revert the PR (lockfile / config) and redeploy; for the Worker, redeploy the previous wrangler deploy.
