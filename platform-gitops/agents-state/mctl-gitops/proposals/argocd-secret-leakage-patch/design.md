# Design: argocd-secret-leakage-patch

## Current state
ArgoCD is deployed in the `admins` tenant and is the sole GitOps sync engine for the platform (see `context/architecture.md`). It is configured via a Helm chart pinned in `platform-gitops/bootstrap/` (App-of-Apps pattern). The current version is vulnerable to CVE-2026-42880: the `ServerSideDiff` endpoint leaks plaintext Secret values when the `IncludeMutationWebhook` annotation is present. ArgoCD holds a ClusterRole that permits read access to all Secrets across all namespaces, making the exposure platform-wide.

## Proposed solution
Bump the ArgoCD Helm chart version to `3.3.9` (upstream chart `argo-cd`) in the values or dependency file that pins it inside `platform-gitops/bootstrap/` (or the relevant ApplicationSet / App definition). Commit the change to this GitOps repository. ArgoCD detects the drift and reconciles itself via its own Application, performing a rolling restart of the argocd-server, application-controller, and repo-server Deployments.

No structural changes to ArgoCD configuration, RBAC, or ApplicationSet definitions are required. The upgrade is a pure image-tag bump delivered through the standard GitOps promotion path.

Why this approach:
- It is the established platform pattern: every platform change is a git commit (see `context/architecture.md` — "Every platform change = a git commit here").
- ArgoCD supports self-management via its own Application; a chart bump triggers a clean rolling update.
- v3.3.9 is a patch release; the upstream changelog notes no breaking changes to the Application or ApplicationSet API.

## Alternatives

**Alternative 1 — Apply only the `IncludeMutationWebhook` server-side flag as a workaround.**
Disabling mutation-webhook inclusion via an ArgoCD config flag could reduce exposure without a version bump. Dropped because it is an undocumented workaround that may not fully close the attack surface, it leaves a known-critical version running, and it would need to be reverted after the eventual upgrade anyway.

**Alternative 2 — Upgrade directly to the latest ArgoCD v3.x minor (e.g., v3.4.x).**
A minor-version jump could introduce API changes or behavioral differences in ApplicationSet directory scanning that would require additional testing. The architecture notes explicitly warn against combination upgrades on patch-day. v3.3.9 is the smallest safe step that closes the CVE.

**Alternative 3 — Rotate all Secrets that may have been leaked and delay the patch.**
Secret rotation is a compensating control, not a fix. It does not close the endpoint; a follow-up attacker could re-extract newly rotated values. This alternative was dropped; the patch must come first.

## Platform impact

**Migrations:** None. v3.3.9 is a drop-in patch upgrade with no CRD schema changes.

**Backward compatibility:** The ArgoCD Application API and ApplicationSet API remain unchanged at this patch level. Existing Application manifests in `platform-gitops/apps/` require no edits.

**Resource impact (`labs`):** The ArgoCD workload runs entirely in the `admins` tenant. No pods, sidecars, or init containers are added. `labs` memory usage is unaffected.

**Risks and mitigations:**
- Risk: ArgoCD rolling restart causes a brief period where sync is unavailable. Mitigation: schedule the commit during a low-traffic window; Kubernetes rolling-update ensures at least one healthy replica remains available during the restart.
- Risk: The new image has a regression. Mitigation: Kubernetes deployment rollout history is retained; `kubectl rollout undo` is available as an immediate fallback (see tasks.md Rollback section).
- Risk: ArgoCD self-sync loop during upgrade. Mitigation: ArgoCD Application for itself is set to `syncPolicy: automated`; the rolling update is atomic and idempotent.
