# Tasks: eso-confused-deputy-patch

- [ ] 1. Identify the exact ESO Helm chart release that packages ESO v2.5.0 — DoD: chart version string confirmed from the `external-secrets/external-secrets` Helm repository; recorded in the PR description.

- [ ] 2. Update the ESO Helm chart version in the platform GitOps repository (depends on 1) — DoD: the chart version field in `platform-gitops/apps/` (or the equivalent ESO `Application`/values file) is changed to the v2.5.0 chart release; `livenessProbe` referencing `/healthz` is enabled in Helm values with `initialDelaySeconds: 30`; the commit is pushed to the GitOps repo and a PR is opened.

- [ ] 3. Verify ArgoCD sync succeeds (depends on 2) — DoD: ArgoCD shows the ESO Application in `Synced / Healthy` state; the running ESO controller pod reports image tag `v2.5.0` via `kubectl describe pod`.

- [ ] 4. Validate ExternalSecret reconciliation is unaffected (depends on 3) — DoD: all ExternalSecret objects in all tenant namespaces show `Ready=True` in `.status.conditions` within 5 minutes of the controller restart; no new error events are present on the objects.

- [ ] 5. Confirm CVE-2026-42876 vector is closed (depends on 3) — DoD: a test ExternalSecret crafted to trigger the confused-deputy pattern (requesting a Service Account token Secret) is rejected or produces no escalated Secret; result is documented in the PR.

- [ ] 6. Update the `eso-cross-namespace-bypass-patch` proposal notes to reflect that v2.5.0 supersedes its v2.4.1 target (depends on 3) — DoD: a comment or amendment is added to that proposal's `design.md` noting the supersession; no functional change to that proposal.

## Tests

- [ ] T1. ESO controller image tag check — `kubectl get pod -l app.kubernetes.io/name=external-secrets -o jsonpath='{.items[0].spec.containers[0].image}'` returns an image containing `v2.5.0`.

- [ ] T2. ExternalSecret readiness sweep — a script iterates all ExternalSecret objects across all namespaces and asserts `.status.conditions[?(@.type=="Ready")].status == "True"` for each; passes with zero failures.

- [ ] T3. Confused-deputy rejection test — apply a test ExternalSecret manifest that specifies a `serviceAccountToken` creation template in a namespace where the applying user has only `ExternalSecret` create rights; confirm no corresponding Kubernetes Secret with a `type: kubernetes.io/service-account-token` is created.

- [ ] T4. Liveness probe health check — `kubectl exec` into the ESO controller pod and `curl -s http://localhost:<healthz-port>/healthz` returns HTTP 200.

- [ ] T5. labs namespace memory unchanged — compare `kubectl top pod -n labs` output before and after the upgrade; confirm ESO-related pod memory delta is within 5 MiB.

## Rollback
If the upgrade causes unexpected failures, revert by reverting the Git commit that changed the chart version and pushing the revert to the GitOps repository. ArgoCD will detect the diff on the next sync and roll the ESO controller back to the previous image. Because no CRD migrations were applied, no schema cleanup is needed. Expected time to restored service: one ArgoCD sync cycle (typically under 3 minutes).
