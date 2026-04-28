# Tasks: workerd-clearweak-migration

- [ ] 1. Audit `cloudflare-worker/` source for direct ClearWeak references — DoD: a grep/search over all `.js`, `.ts`, and `.json` files in `cloudflare-worker/` confirms whether any file references ClearWeak, WeakRef finalizer registration, or `FinalizationRegistry` in a way that delegates to the V8 ClearWeak path; result is documented in the PR description.
- [ ] 2. Enumerate and assess transitive dependencies for ClearWeak exposure (depends on 1) — DoD: `npm list --all` output for `cloudflare-worker/` is reviewed; any dependency shipping native `.node` addons or known to use WeakRef internals is flagged; the full dependency list with risk assessment is documented.
- [ ] 3. Deploy Worker to staging and observe `wrangler tail` for ClearWeak warnings (depends on 2) — DoD: the Worker is deployed to a Cloudflare staging environment; `wrangler tail` is observed for at least 5 minutes with all four `/api/*` endpoints exercised; any ClearWeak deprecation warning lines are captured.
- [ ] 4. Remediate any ClearWeak usage found in tasks 1–3 (depends on 3) — DoD: if direct usage was found, the code is rewritten to use the updated API or a pure-JS equivalent; if a transitive dependency is responsible, it is upgraded or replaced; if no usage was found, this task is marked complete with "no action required" and the audit result is the deliverable.
- [ ] 5. Update `compatibility_date` in `wrangler.toml` to `2026-04-26` or later (depends on 4) — DoD: `wrangler.toml` contains `compatibility_date = "2026-04-26"` (or a later date); `wrangler dev` starts without ClearWeak warnings; the change is committed.
- [ ] 6. End-to-end smoke test of all `/api/*` endpoints on staging (depends on 5) — DoD: `/api/github/login`, `/api/github/callback`, `/api/submit` (with a test tenant name), and `/api/contact` all return expected HTTP status codes; no runtime errors appear in `wrangler tail` during the test.
- [ ] 7. Deploy to production and update `context/current-version.md` (depends on 6) — DoD: the deploy pipeline runs green; `wrangler tail` on the production Worker shows zero ClearWeak deprecation entries; an ADR is added to `context/decisions/` documenting the audit outcome and any changes made.

## Tests

- [ ] T1. `grep -ri 'clearweak\|ClearWeak\|clearWeak' cloudflare-worker/` returns no matches in source files after remediation.
- [ ] T2. `wrangler dev` against `cloudflare-worker/` starts with exit code 0 and produces no lines containing "deprecated" or "ClearWeak" in the first 30 seconds of output.
- [ ] T3. `wrangler tail` on the staging Worker shows zero ClearWeak deprecation entries during a 5-minute observation window with all endpoints exercised.
- [ ] T4. `POST /api/contact` with a valid test payload returns HTTP 200 on staging.
- [ ] T5. `GET /api/github/login` on staging returns an HTTP 302 redirect to GitHub OAuth with the correct `client_id` parameter.
- [ ] T6. `wrangler tail` on the production Worker shows zero ClearWeak deprecation entries in the 10 minutes following the production deploy.

## Rollback
1. If the `compatibility_date` change caused unexpected behaviour: revert `wrangler.toml` to the previous `compatibility_date` value in git and redeploy via `wrangler deploy`.
2. If a dependency was upgraded and introduced a regression: revert `cloudflare-worker/package.json` and `package-lock.json` to the previous versions in git and redeploy.
3. If Worker source was modified and a regression is observed: revert the source changes in git and redeploy.
4. All rollback paths are a single `git revert` + `wrangler deploy` away; no database migrations, secret rotations, or Kubernetes changes are involved.
5. Cloudflare preserves previous Worker deployment versions in the Dashboard; an immediate rollback to the last known-good version is also possible via the Cloudflare Dashboard "Rollback" button without waiting for CI.
