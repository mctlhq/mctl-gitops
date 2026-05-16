# Tasks: argo-rollouts-v1-9-0-upgrade

- [ ] 1. Locate the current Argo Rollouts version pin — DoD: The exact file path and field (image tag or Helm values key) that controls the deployed Argo Rollouts version is identified and documented in the PR description.

- [ ] 2. Update the version pin to v1.9.0 (depends on 1) — DoD: A single commit changes the tag from its current value to `v1.9.0` in `platform-gitops/` (the ArgoCD Application manifest or equivalent Helm values file). No other files are modified.

- [ ] 3. Sync to staging / non-production ArgoCD target and verify (depends on 2) — DoD: ArgoCD reports the Argo Rollouts Application as `Synced` and `Healthy` in the staging environment. The controller Pod is running image `v1.9.0`. No CRD schema errors appear in ArgoCD or controller logs.

- [ ] 4. Verify existing Rollout and AnalysisRun resources are unaffected (depends on 3) — DoD: `kubectl get rollouts -A` and `kubectl get analysisruns -A` return all expected objects with no unexpected status transitions. No error events referencing schema incompatibility.

- [ ] 5. Promote to production sync (depends on 3, 4) — DoD: ArgoCD Application for Argo Rollouts is `Synced` and `Healthy` in production. Controller Pod shows `v1.9.0` in its image field. A post-sync BlueGreen rollout test (see T2) passes.

- [ ] 6. Update internal runbook / platform docs to record the new version (depends on 5) — DoD: Any internal version tracking document (e.g., a versions table in `context/current-version.md` or equivalent platform docs) reflects `argo-rollouts: v1.9.0`.

## Tests

- [ ] T1. Controller image version check — After ArgoCD sync, run `kubectl get deployment argo-rollouts -n argo-rollouts -o jsonpath='{.spec.template.spec.containers[0].image}'` and assert the output contains `v1.9.0`.

- [ ] T2. BlueGreen premature-success regression test — Trigger a BlueGreen rollout in a test namespace with an AnalysisTemplate that is configured to run for at least 60 seconds. While the analysis is running, scale the incoming ReplicaSet down to 0 replicas (simulating unsaturation). Assert that the AnalysisRun does NOT transition to `Successful` and the rollout does NOT promote. Restore the replica count and confirm analysis resumes and completes correctly.

- [ ] T3. CRD schema compatibility check — Run `kubectl diff -f <path-to-v1.9.0-crds>` against the live cluster and assert no destructive schema changes are reported.

- [ ] T4. Controller log health check — Inspect Argo Rollouts controller logs for 5 minutes post-upgrade and assert no `ERROR` or `panic` lines appear.

- [ ] T5. labs memory check — Query the cluster memory metrics for the `argo-rollouts` namespace (or the namespace where the controller runs) immediately before and 15 minutes after upgrade. Assert memory usage has not increased by more than 10 %.

## Rollback

Argo Rollouts manifests are managed by ArgoCD. To roll back:

1. Revert the version pin commit in `platform-gitops/` (either via `git revert` or by editing the tag back to the previous value).
2. Commit and push the revert to the main branch.
3. In ArgoCD, manually sync the Argo Rollouts Application if auto-sync is not enabled.
4. Confirm the controller Pod returns to the previous image version via `kubectl get pods -n argo-rollouts`.
5. Confirm `kubectl get rollouts -A` shows no unexpected status changes.

Because there are no CRD schema changes in v1.9.0, reverting the controller image is sufficient — no CRD downgrade is needed.
