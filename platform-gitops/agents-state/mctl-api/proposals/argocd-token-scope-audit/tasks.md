# Tasks: argocd-token-scope-audit

- [ ] 1. Audit the current `ARGOCD_TOKEN` scope — DoD: written record (in the incident tracker or PR description) stating whether the token is project-scoped; includes the result of calling `/api/v1/projects/{project}/detailed` (200 = vulnerable, 403 = compliant); finding is reviewed and signed off by the security engineer
- [ ] 2. Draft and review the minimal ArgoCD RBAC policy (`role:mctl-api-appstatus-ro`) granting only `applications, get` and `applications, list` on the target AppProject (no dependencies, can run in parallel with 1) — DoD: RBAC policy YAML reviewed in PR; platform team confirms it is sufficient for all application-status calls mctl-api makes; policy applied to staging ArgoCD
- [ ] 3. Generate and validate new minimal-scope token against staging ArgoCD (depends on 2) — DoD: `argocd account generate-token` produces a token that (a) returns correct application status from the existing mctl-api status endpoint in staging, (b) returns HTTP 403 from `/api/v1/projects/{project}/detailed` — both results documented in PR
- [ ] 4. Add a CI validation script `scripts/validate-argocd-token-scope.sh` that probes `/api/v1/projects/{project}/detailed` with the current Vault-stored token and exits non-zero if response is 200 (depends on 3) — DoD: script runs in CI against staging; PR includes a GitHub Actions workflow step that executes it on every push to `main`
- [ ] 5. Rotate the production `ARGOCD_TOKEN` in Vault to the new minimal-scope token (depends on 3, 4) — DoD: `vault kv put secret/mctl-api/argocd token=<new-token>` executed; old token still valid at this point
- [ ] 6. Trigger rolling restart of mctl-api production Deployment and verify health (depends on 5) — DoD: all pods healthy; `/services/{name}/status` returns correct data for at least three different services; Prometheus shows no increase in ArgoCD-related errors
- [ ] 7. Revoke the old ArgoCD token and update Vault policy documentation (depends on 6) — DoD: `argocd account delete-token` executed for the old token; Vault policy at `mctl-api-argocd-write` updated with a comment stating the required ArgoCD RBAC role; change committed to the `infra/` repository

## Tests

- [ ] T1. Audit probe: direct HTTP call from a developer workstation with the current token to `/api/v1/projects/{project}/detailed` — expected result documented (200 or 403)
- [ ] T2. Staging validation: new minimal-scope token returns HTTP 200 from `GET /api/v1/applications` and HTTP 403 from `GET /api/v1/projects/{project}/detailed`
- [ ] T3. mctl-api integration: after Vault rotation and restart, `GET /services/{name}/status` returns the correct ArgoCD health status for a known application
- [ ] T4. CVE probe CI script: `scripts/validate-argocd-token-scope.sh` exits 1 when run with a project-scoped token (verified in staging), exits 0 with the new minimal-scope token
- [ ] T5. Post-rotation regression: Prometheus `argocd_request_errors_total` (or equivalent) does not increase in the 30 minutes following the rolling restart

## Rollback
1. The old token is not revoked until Task 7, which runs only after production health is confirmed. To roll back at any point before Task 7: re-run `vault kv put secret/mctl-api/argocd token=<old-token>` and trigger another rolling restart.
2. If the old token has already been revoked (Task 7 completed) and issues are found: generate a new temporary token with the same minimal scope using `argocd account generate-token` and rotate Vault immediately. Do not recreate a project-scoped token.
3. The ArgoCD RBAC policy change (Task 2) does not affect mctl-api's token directly; rolling it back requires the platform team to revert the `argocd-rbac-cm` patch, which is independent of the mctl-api rollback.
