# Design: argocd-ghsa-3v3m-patch

## Current state

mctl-api (v4.14.0, Go 1.24) integrates with ArgoCD as one of its five external dependencies (see `context/architecture.md`). At startup, mctl-api fetches `ARGOCD_TOKEN` from Vault via Kubernetes auth, then calls the ArgoCD REST API to retrieve application sync and health status. This status is surfaced through mctl-api's REST endpoints and the 24-tool MCP server to the UI, CLI, and AI agents.

ArgoCD is deployed in the `admins` tenant namespace on the shared Kubernetes + ArgoCD platform and managed via ArgoCD itself (an ArgoCD-manages-ArgoCD topology is common and assumed here). The exact version currently running in the cluster is unknown until the assessment task is executed, but the advisory affects all ArgoCD server versions prior to v3.3.9.

No in-process ArgoCD client library (e.g., the `argoproj/argo-cd` Go module) is vendored inside mctl-api. All ArgoCD interaction is over HTTP/REST using standard Go HTTP primitives, which means API surface changes in v3.3.9 affect only the request/response shapes that mctl-api constructs and parses, not a compiled library.

## Proposed solution

The remediation is a controlled, in-place upgrade of the ArgoCD server deployment to v3.3.9 combined with a pre-upgrade API compatibility check in a staging environment.

**Step 1 — Exposure assessment.** Query the running ArgoCD server's `/api/version` endpoint (or the ArgoCD Application CR in the `admins` namespace) to record the current version. If the version is below v3.3.9, raise a P1 ticket and restrict non-emergency deploys until the patch window.

**Step 2 — Compatibility validation in staging.** Before touching production, stand up ArgoCD v3.3.9 in the staging environment. Run the mctl-api integration test suite against it, specifically the paths that call ArgoCD: `GET /api/v1/applications`, `GET /api/v1/applications/{name}/resource-tree`, and the watch/event stream if used. Confirm response shapes are backward compatible. If any breaking change is found, write a compatibility shim in mctl-api before proceeding.

**Step 3 — Production upgrade via GitOps.** Update the ArgoCD image tag in the GitOps repo (the Helm chart or Kustomize overlay that manages ArgoCD in `admins`). ArgoCD's rolling update will drain and replace the server pod. The ArgoCD application controller and repo-server should be upgraded in the same commit to stay version-aligned.

**Step 4 — Post-upgrade verification.** Confirm mctl-api health, confirm application status is correctly reflected in the UI/CLI, and emit the audit log entry.

This approach avoids any mctl-api binary change unless a breaking API incompatibility is discovered in Step 2. The change is entirely infrastructure-side (GitOps manifest bump), which keeps the mctl-api release cycle decoupled.

## Alternatives

**Option A — Emergency in-place `kubectl set image` patch (skip GitOps).** This would be faster for a true zero-day emergency but bypasses the GitOps audit trail, creates drift between the live cluster and the repo, and could be reverted by the next ArgoCD sync. Rejected: the GitOps path is only marginally slower and preserves auditability.

**Option B — Upgrade to latest ArgoCD (v3.4.x or beyond).** A larger version jump could introduce more API changes and require wider mctl-api testing. The advisory is patched at v3.3.9; jumping further is a separate concern. Rejected for this proposal: targeting the minimum safe version reduces blast radius and can be followed by a routine upgrade proposal later.

**Option C — Disable ArgoCD integration in mctl-api until patched.** Returning a static "unavailable" response from the ArgoCD-backed endpoints eliminates exposure via mctl-api but does not patch the underlying server, leaves the ArgoCD UI and other consumers exposed, and degrades mctl-api functionality. Rejected: patching the server is the correct fix.

## Platform impact

### Migrations
No database migrations. No mctl-api binary changes are expected unless a breaking API change is found during compatibility validation.

### Backward compatibility
ArgoCD v3.3.9 is a patch release on the v3.3.x line. Patch releases in the Argo project's release policy must not introduce breaking REST API changes. The compatibility validation step in staging exists to catch any exception to this. Existing `ARGOCD_TOKEN` credentials stored in Vault should remain valid across the patch upgrade.

### Resource impact (labs tenant)
The `labs` tenant is near its memory limit. This proposal affects the `admins` tenant's ArgoCD deployment; `labs` is not in scope. If `labs` runs its own ArgoCD instance, that is a separate remediation and must be assessed independently. No additional memory or CPU is introduced by upgrading ArgoCD in `admins` — the replacement pod targets the same resource limits as the existing one.

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| ArgoCD v3.3.9 REST API breaks mctl-api status calls | Low (patch release policy) | Staging compatibility test before prod upgrade |
| ArgoCD upgrade pod fails to start (image pull error, OOMKill) | Low | Rollback path: revert GitOps image tag; ArgoCD controller re-reconciles |
| Upgrade takes longer than 30-minute maintenance window | Medium | Pre-pull image to cluster nodes before window; test rollout time in staging |
| Full technical details of GHSA-3v3m published mid-upgrade revealing wider attack surface | Low-Medium | Pause upgrade, re-assess scope, continue if contained to server component |
| mctl-api cached status served stale during upgrade window | Low | Acceptable degradation per EARS criterion; document in runbook |
