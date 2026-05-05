# Tasks: argocd-secret-leakage-patch

- [ ] 1. Identify the exact file in `platform-gitops/bootstrap/` (or the ArgoCD Application manifest) that pins the ArgoCD Helm chart version — DoD: file path and current version string are documented in the PR description.
- [ ] 2. Update the ArgoCD Helm chart version to `3.3.9` in that file (depends on 1) — DoD: a single-line diff shows the version string changed from the current value to `3.3.9`; no other fields are modified.
- [ ] 3. Open a pull request with the change and obtain at least one peer review (depends on 2) — DoD: PR is approved by a second platform engineer and all CI checks pass.
- [ ] 4. Merge the PR to the main branch (depends on 3) — DoD: commit is visible on main; ArgoCD detects the Application drift within its polling interval (default: 3 minutes).
- [ ] 5. Verify ArgoCD self-reconciliation completes successfully (depends on 4) — DoD: all ArgoCD Deployments show `READY` with pods running image tag `v3.3.9`; the ArgoCD Application for itself shows `Synced / Healthy` in the UI at `ops.mctl.ai`.
- [ ] 6. Validate no Applications are left in a degraded state post-upgrade (depends on 5) — DoD: `kubectl get applications -A` shows no `Degraded` or `Unknown` status; any transient `Progressing` states resolve within 10 minutes.

## Tests

- [ ] T1. Confirm the running ArgoCD server version via the UI (`ops.mctl.ai/settings/about`) or CLI (`argocd version --server ops.mctl.ai`) shows `v3.3.9`.
- [ ] T2. Send a synthetic ServerSideDiff request (with `IncludeMutationWebhook` annotation set) against the patched endpoint and confirm no plaintext Secret data appears in the response body; expect a sanitized or error response.
- [ ] T3. Trigger a manual sync of one non-critical Application (e.g., a `labs` service) and confirm it completes with `Synced / Healthy` status, verifying core sync functionality is intact.
- [ ] T4. Review ArgoCD pod logs for error-level messages in the 15 minutes following rollout completion and confirm no unexpected exception loops.

## Rollback
If the upgraded ArgoCD pods fail readiness probes or the platform behaves unexpectedly after the merge:

1. Revert the chart-version commit on the main branch (or push a revert commit) — ArgoCD will detect the new desired state and roll back to the previous Helm release.
2. If ArgoCD itself is unable to self-sync (e.g., argocd-server crash-loops), run `kubectl rollout undo deployment/argocd-server -n admins` (and equivalents for `argocd-application-controller`, `argocd-repo-server`) to restore the previous pod revision immediately.
3. Confirm the previous version is running and all Applications return to `Synced / Healthy` before investigating the failure.
