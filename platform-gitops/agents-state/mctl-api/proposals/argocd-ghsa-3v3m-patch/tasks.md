# Tasks: argocd-ghsa-3v3m-patch

- [ ] 1. Determine current ArgoCD version in `admins` cluster — DoD: Version string recorded in the P1 ticket and in the audit log entry; confirmed whether the cluster is exposed (version < v3.3.9). If already at v3.3.9+, close proposal as resolved.

- [ ] 2. Publish internal exposure notice (depends on 1) — DoD: On-call channel and security officer notified with: current version, advisory identifier GHSA-3v3m-wc6v-x4x3, exposure classification (exposed / not exposed), and decision to restrict non-emergency prod deploys if exposed.

- [ ] 3. Validate mctl-api API compatibility against ArgoCD v3.3.9 in staging (depends on 1) — DoD: mctl-api integration tests pass against a staging ArgoCD v3.3.9 instance; the following endpoints confirmed working: `GET /api/v1/applications`, `GET /api/v1/applications/{name}/resource-tree`; any response-shape differences documented and shim written if needed.

- [ ] 4. Write compatibility shim in mctl-api if breaking change found (depends on 3) — DoD: mctl-api compiles and all ArgoCD-related integration tests pass against both the current production ArgoCD version and v3.3.9; shim covered by a unit test. (Skip if task 3 finds no breaking changes.)

- [ ] 5. Prepare GitOps upgrade PR for ArgoCD v3.3.9 (depends on 3) — DoD: Pull request open in the GitOps repo updating the ArgoCD Helm chart / Kustomize image tag to v3.3.9 for the `admins` namespace; PR reviewed and approved; staging deploy confirmed healthy.

- [ ] 6. Schedule and execute production upgrade (depends on 5, and 4 if applicable) — DoD: ArgoCD v3.3.9 running in `admins` production; GitOps PR merged; upgrade completed within the agreed 30-minute maintenance window; all ArgoCD application sync/health checks green.

- [ ] 7. Post-upgrade mctl-api smoke test (depends on 6) — DoD: mctl-api `/healthz` returns 200; at least one real application status successfully retrieved via mctl-api REST endpoint and verified against ArgoCD UI; no error-rate spike in Prometheus metrics for ArgoCD-backed endpoints.

- [ ] 8. Emit audit log entry and close P1 ticket (depends on 7) — DoD: Structured audit log entry written containing previous ArgoCD version, new version (v3.3.9), upgrade timestamp, and operator identity; P1 ticket closed with remediation date; security officer notified.

## Tests

- [ ] T1. Staging integration test — mctl-api ArgoCD status endpoint returns a well-formed application-status response when pointed at ArgoCD v3.3.9. Covers `GET /api/v1/applications` and resource-tree paths.
- [ ] T2. Auth continuity test — `ARGOCD_TOKEN` fetched from Vault staging instance authenticates successfully against ArgoCD v3.3.9 without a 401/403.
- [ ] T3. Degraded-mode test — while ArgoCD pod is not yet ready (simulated by scaling to 0 replicas in staging), mctl-api returns a graceful cached/unavailable response rather than a 500 to callers.
- [ ] T4. Post-production smoke test — after the production upgrade, mctl-api Prometheus metric `mctl_api_argocd_requests_total` (or equivalent) shows no increase in error-rate compared to the 24-hour baseline.
- [ ] T5. Version assertion test — a one-shot script or CI check that queries `/api/version` on the production ArgoCD server and asserts the version is >= v3.3.9. Intended to run as a post-deploy gate.

## Rollback

If the production upgrade causes an incident:

1. Revert the GitOps PR (open a revert PR or `git revert` the merge commit and push). ArgoCD will self-reconcile back to the previous image tag within one sync cycle (default: 3 minutes).
2. If ArgoCD itself is broken and cannot self-reconcile, run `kubectl rollout undo deployment/argocd-server -n <admins-namespace>` to revert the server pod directly, then revert the GitOps repo to prevent re-application.
3. If a mctl-api compatibility shim was deployed alongside the upgrade (task 4), revert that release via the normal mctl-api rollback procedure (ArgoCD-managed rollout undo for mctl-api).
4. Notify on-call and security officer; reopen the P1 ticket; document the failure mode before re-attempting the upgrade.

The rollback does not re-introduce the vulnerability in a way that is worse than the pre-patch state; the cluster simply returns to its previous exposure level.
