# Tasks: worker-toolchain-bump-compat-date

- [ ] 1. Record current wrangler version and `compatibility_date`; verify latest wrangler release and advisories — DoD: values listed in the PR.
- [ ] 2. Bump and pin wrangler (depends on 1) — DoD: lockfile updated, `wrangler deploy --dry-run` passes in CI.
- [ ] 3. Prepare a staging/preview Worker with staging secrets (depends on 2) — DoD: reachable preview with no production secrets.
- [ ] 4. Set candidate compat date in staging and run OAuth, submit, contact and rate-limit checks (depends on 3) — DoD: checklist results recorded, comparison with old date.
- [ ] 5. Decide on promoting the date (depends on 4) — DoD: either production `compatibility_date` updated in its own commit, or the old date retained with a documented reason.
- [ ] 6. Confirm MemoryCache autogate is not enabled (depends on 2) — DoD: config reviewed.

## Tests
- [ ] T1. `wrangler deploy --dry-run` succeeds.
- [ ] T2. OAuth login/callback works end to end in staging.
- [ ] T3. `/api/submit` and `/api/contact` succeed with mocked or staging upstreams.
- [ ] T4. Rate limits (5/5min, 3/5min, 10/min) still enforced.
- [ ] T5. Redirects from `mctl.me` and `mctl.ru` still reach `mctl.ai`.

## Rollback
Revert the compat-date commit and redeploy; if needed revert the wrangler pin commit and redeploy via `deploy.yml`. Secrets are unchanged so no secret rotation is needed.
