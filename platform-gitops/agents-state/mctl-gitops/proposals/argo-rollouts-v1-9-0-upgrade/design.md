# Design: argo-rollouts-v1-9-0-upgrade

## Current state

Argo Rollouts is deployed cluster-wide as an ArgoCD-managed Application. Its manifests live under `platform-gitops/apps/` or an equivalent path within the App-of-Apps bootstrap structure (see `context/architecture.md`). The Application points to a specific version of the upstream Argo Rollouts install manifests (controller Deployment, RBAC, and CRDs). The current pinned version is below v1.9.0 and is subject to the bug where a BlueGreen analysis step is prematurely marked successful when the incoming ReplicaSet loses saturation mid-rollout. No existing proposal addresses Argo Rollouts; this is the first.

## Proposed solution

Bump the version pin in the ArgoCD Application manifest that manages Argo Rollouts from its current value to `v1.9.0`. ArgoCD will detect the diff and reconcile the cluster by performing a rolling replacement of the controller Deployment. Because v1.9.0 introduces no CRD schema changes, existing Rollout, AnalysisTemplate, and AnalysisRun resources remain valid and require no migration.

Concretely, the change is a single-line edit to the image tag (or Helm values `tag:`) in the Argo Rollouts Application manifest:

```
# platform-gitops/apps/argo-rollouts.yaml  (or equivalent)
# Change:
#   tag: <current-version>
# To:
#   tag: v1.9.0
```

ArgoCD reconciles the Application on its next sync cycle (or immediately on a manual sync). The controller Pod is replaced; the new binary contains the fix for the premature-success condition. No other manifests need to change.

## Alternatives

**A. Do nothing / defer.** The bug is silent — production BlueGreen promotions may already be passing degraded revisions to stable without any gate catching the regression. Deferring keeps the risk open indefinitely. Rejected because impact is a correctness/safety failure in the delivery pipeline, not merely a performance or convenience concern.

**B. Patch the premature-success logic in-cluster via a mutating webhook.** A custom webhook could intercept AnalysisRun status updates and reject transitions from `Running` to `Successful` when the ReplicaSet is not fully saturated. This avoids touching the controller image but introduces a new, non-standard in-cluster component that must itself be maintained, tested, and secured. Rejected because the fix is already upstream in v1.9.0 and a webhook adds significant operational complexity for zero long-term benefit.

**C. Pin to a nightly / release-candidate build.** The fix could be obtained from a pre-release artifact before the official v1.9.0 tag. Rejected because nightly builds are not supported for production use and the official release is available.

## Platform impact

### Migrations
None. v1.9.0 carries no CRD schema changes. All existing Rollout and AnalysisTemplate custom resources are forward-compatible. No `kubectl` migration steps are required.

### Backward compatibility
The controller replacement is in-place. Active rollouts in progress at the moment of the controller restart will be re-evaluated from their last persisted state; this is standard Argo Rollouts behavior (the controller is stateless beyond etcd). No breaking changes to the Rollout API.

### Resource impact (labs)
Argo Rollouts is a cluster-wide controller — it runs once, not per-tenant. The v1.9.0 release notes contain no mention of increased memory or CPU requirements. The fix is a logic correction in the analysis reconciliation loop and does not introduce new goroutines, caches, or additional API calls. Memory footprint is expected to be unchanged.

Risk rating for `labs`: **Low.** No additional memory pressure is anticipated. If post-upgrade monitoring shows unexpected controller memory growth, the rollback procedure below applies.

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Controller restart briefly interrupts in-flight rollout reconciliation | Low | Argo Rollouts controller re-reads all Rollout objects on startup; brief gap is expected and tolerated by design |
| v1.9.0 contains an unrelated regression | Low | Upgrade is tested in a staging sync before enabling auto-sync to production; see Tasks |
| labs memory limit breached | Very low | Controller is cluster-scoped; resource usage does not scale with tenant count; monitor post-upgrade |
