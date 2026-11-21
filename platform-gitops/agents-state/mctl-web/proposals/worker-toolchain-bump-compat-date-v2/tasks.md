# Tasks: worker-toolchain-bump-compat-date-v2

- [ ] 1. Pin wrangler and update lockfile — DoD: wrangler --version recorded.
- [ ] 2. Test compat date bump in staging (depends on 1) — DoD: OAuth, submit, contact flows pass.
- [ ] 3. Audit outbound fetch error handling (depends on 1) — DoD: TypeError path returns a handled error.
- [ ] 4. Deploy via deploy.yml (depends on 2, 3) — DoD: production smoke test passes.

## Tests
- [ ] T1. Simulated malformed upstream response yields a handled 5xx.
- [ ] T2. Rate limits unchanged.

## Rollback
Revert the PR and redeploy the previous build (Worker: wrangler rollback).
