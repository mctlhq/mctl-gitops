# Tasks: argocd-serversidediff-secret-leak

- [ ] 1. Confirm current ArgoCD version in cluster — DoD: The running ArgoCD server image tag is documented (e.g., via `kubectl get deployment argocd-server -n argocd -o jsonpath='{.spec.template.spec.containers[0].image}'`); the version is confirmed to be below v3.3.9 and therefore affected by CVE-2026-43824.

- [ ] 2. Locate and update the ArgoCD image tag in the GitOps repository (depends on 1) — DoD: The `image.tag` field (or equivalent) for the ArgoCD server, repo-server, and application-controller in the relevant Helm values file or raw manifest under `platform-gitops/services/admins/argocd/` is updated to `v3.3.9`. The commit message references CVE-2026-43824 and GHSA-3v3m-wc6v-x4b3. PR is opened and approved by a second engineer.

- [ ] 3. Merge and verify ArgoCD self-upgrade rollout (depends on 2) — DoD: The PR is merged to the default branch. ArgoCD detects the diff and completes a rolling upgrade of all ArgoCD pods to v3.3.9. All pods report `Running` and `Ready`. `kubectl get pods -n argocd` shows no pods still running the old image tag.

- [ ] 4. Verify all Applications are healthy post-upgrade (depends on 3) — DoD: All ArgoCD Applications in both `admins` and `labs` tenants report `Synced` and `Healthy` in the ArgoCD UI (`ops.mctl.ai`) and via `argocd app list`. No OutOfSync or Degraded Applications are present that were not already in that state before the upgrade.

- [ ] 5. Document resolution in decisions/ ADR (depends on 4) — DoD: A new ADR entry under `context/decisions/` records the version pin, the CVE reference, the date of remediation, and the rationale. The ADR is committed to the repository.

## Tests

- [ ] T1. Regression test — ServerSideDiff endpoint no longer leaks Secret data: After upgrade, authenticate to ArgoCD as a read-only user and invoke the ServerSideDiff API endpoint with `IncludeMutationWebhook=true` for an Application that references a Secret. Confirm that the response does not contain plaintext Secret values. Expected result: Secret data is redacted or the endpoint returns an authorisation error.

- [ ] T2. Application sync smoke test: Trigger a manual sync for one Application in `admins` and one in `labs` via `argocd app sync <app-name>`. Confirm both complete successfully (status `Synced`, health `Healthy`) within 5 minutes.

- [ ] T3. ArgoCD API availability test: Confirm the ArgoCD API server is reachable and returns a valid response on `GET /api/v1/applications` with a valid token. Expected result: HTTP 200 with the application list; no 5xx errors.

- [ ] T4. Version confirmation: Run `argocd version --server ops.mctl.ai` (or equivalent) and confirm the server version reported is `v3.3.9`. Record the output in the PR comments.

## Rollback
If the upgrade introduces a regression (e.g., ApplicationSet generators produce incorrect Applications, sync failures appear, ArgoCD API is unresponsive):

1. Revert the image tag commit in the GitOps repository to the previous ArgoCD version tag and merge to the default branch.
2. ArgoCD's self-managed Application will detect the revert and roll the pods back to the previous image.
3. Monitor pod health and Application sync status as during the initial upgrade.
4. If the ArgoCD self-managed sync loop is itself broken, use `kubectl set image deployment/argocd-server argocd-server=quay.io/argoproj/argocd:<previous-tag> -n argocd` as an out-of-band emergency rollback, then fix the GitOps state to match.
5. Open a new incident ticket referencing the regression before attempting any subsequent upgrade.
