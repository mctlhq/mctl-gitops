# Design: argocd-serversidediff-secret-leak

## Current state
ArgoCD is the core reconciliation engine of the platform, deployed at `ops.mctl.ai` and configured via the App-of-Apps pattern described in `context/architecture.md`. The bootstrap ApplicationSet under `platform-gitops/bootstrap/` drives all tenant Applications for both `admins` and `labs`. The current ArgoCD version predates v3.3.9 and is therefore affected by CVE-2026-43824: any user with read-only access to the ArgoCD API can invoke the ServerSideDiff endpoint with `IncludeMutationWebhook=true` and receive the plaintext content of Kubernetes Secrets that ArgoCD has access to during diff computation.

ArgoCD has read access to Secrets in all namespaces it manages. Under the current App-of-Apps layout this includes secrets in both `admins` and `labs` tenants, making the blast radius platform-wide. No mitigating controls (e.g., network policies blocking the API, removal of read-only accounts) are in place that would reduce the severity.

## Proposed solution
Pin the ArgoCD image to v3.3.9 in the Helm values file (or raw YAML manifest) that controls the ArgoCD deployment under `platform-gitops/services/admins/argocd/` (or the equivalent bootstrap chart). The change is a single-line image tag update. No CRD migrations are required between the current version and v3.3.9 — this is a patch release on the v3.3.x line.

Steps:
1. Update the `image.tag` value (and optionally pin the image digest) to `v3.3.9` in the ArgoCD values file tracked by GitOps.
2. Commit and push. ArgoCD's own self-managed Application will detect the diff and trigger a rolling upgrade of the ArgoCD server, repo-server, and application-controller pods.
3. Verify all Applications are healthy and synced after rollout.

Because ArgoCD manages its own deployment (self-managed pattern), the rolling upgrade proceeds automatically via the normal GitOps reconciliation loop. The rollout strategy on the ArgoCD server Deployment uses `RollingUpdate` with `maxUnavailable: 0` by default, keeping availability during the upgrade.

## Alternatives

### Option A: Disable `IncludeMutationWebhook` via ArgoCD feature flags
Setting `IncludeMutationWebhook=false` at the ArgoCD config level would prevent the vulnerable code path from being exercised without upgrading. However, this disables a useful diff feature and does not address the underlying vulnerability — if the flag is ever re-enabled, the risk returns immediately. This approach also requires a separate config change and does not clean up the CVE from an audit perspective. Dropped in favour of patching.

### Option B: Restrict read-only account access to the ServerSideDiff endpoint via network policy or RBAC
Blocking the endpoint at the network layer or tightening RBAC would reduce the attack surface. However, this is operationally complex (ArgoCD RBAC does not natively gate individual API endpoints at the HTTP path level without a proxy), introduces ongoing maintenance burden, and still leaves a known-vulnerable binary in production. Dropped in favour of patching.

### Option C: Upgrade to v3.4.x (next minor)
A minor-version jump could introduce additional API or behavior changes that require broader regression testing. The v3.3.9 patch release is the minimal-risk remediation on the current minor track. A minor-version upgrade can be planned separately for feature uptake. Dropped to minimize blast radius of this security-driven change.

## Platform impact

### Migrations
None. v3.3.9 is a patch release; no CRD version bumps or Application manifest changes are required.

### Backward compatibility
Full backward compatibility is maintained. All existing ApplicationSet generators, Application definitions, and sync policies continue to function unchanged.

### Resource impact
The ArgoCD server runs under the `admins` tenant. Resource limits for the ArgoCD pods are not changed by this upgrade. No impact on the `labs` tenant's memory envelope. This proposal does not increase memory consumption in any tenant and is not flagged as a memory risk.

### Risks and mitigations
- **Risk:** The self-managed ArgoCD rollout briefly reduces API availability while pods restart.
  - **Mitigation:** Default rolling-update strategy (`maxUnavailable: 0`) keeps at least one server pod live. Schedule the commit during low-traffic hours.
- **Risk:** A regression in v3.3.9 affects sync behavior for one or more Applications.
  - **Mitigation:** Monitor ArgoCD Application health in `admins` and `labs` for 30 minutes post-rollout. The previous image tag is known and can be reverted in one commit if a regression is detected.
- **Risk:** The ArgoCD self-managed sync loop is in a degraded state at time of upgrade.
  - **Mitigation:** Verify all Applications are `Synced` and `Healthy` before merging the version-pin commit.
