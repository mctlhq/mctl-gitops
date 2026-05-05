# Design: eso-cross-namespace-bypass-patch

## Current state
External Secrets Operator (ESO) is deployed on the platform as the single secrets delivery mechanism for all tenants (see `context/architecture.md`). It uses a Vault ClusterSecretStore (`vault-backend`) to fetch secrets from `secrets.mctl.ai` and materialise them as Kubernetes Secrets via ExternalSecret CRs. ESO runs with a ClusterRoleBinding that grants it cluster-wide read access to Kubernetes Secrets and write access to create/update Secrets in any namespace. ExternalSecret manifests for workflow-related secrets are under `platform-gitops/argo-workflows/secrets/`; other service secrets follow the same pattern under `platform-gitops/services/<tenant>/<svc>/`.

The current ESO Helm chart version is vulnerable to CVE-2026-22822: a malicious or misconfigured ExternalSecret in the `labs` namespace can instruct the ESO controller to cross namespace boundaries and retrieve secrets intended for `admins`, and vice versa. The patched version is available in ESO helm-chart-2.4.1 (April 28, 2026).

## Proposed solution
Bump the ESO Helm chart version to `helm-chart-2.4.1` in the file within `platform-gitops/` that pins the chart (Application manifest or values file in the bootstrap App-of-Apps). Commit the change to this GitOps repository. ArgoCD detects the drift and reconciles the ESO Deployment with a rolling restart of the ESO controller pod.

The patch in helm-chart-2.4.1 adds namespace-scoped validation to the ExternalSecret admission and reconciliation path: the controller now enforces that an ExternalSecret may only request secret paths that are authorised for its own namespace, regardless of the ClusterRoleBinding held by the controller itself. This is an internal enforcement change; the ClusterSecretStore and existing ExternalSecret manifests require no modification.

Why this approach:
- Standard GitOps promotion path: a single chart-version bump triggers ArgoCD reconciliation, consistent with platform conventions.
- helm-chart-2.4.1 is a patch-level update; no CRD schema changes are introduced that would require migration of existing ExternalSecret resources.
- No new workloads, sidecars, or controllers are added, keeping resource consumption flat.

## Alternatives

**Alternative 1 — Replace ClusterSecretStore with per-namespace SecretStores.**
Namespace-scoped SecretStores would eliminate the broad ClusterRoleBinding exposure at the architectural level. However, this requires creating and maintaining a SecretStore in every namespace that consumes secrets, updating every ExternalSecret to reference the namespace-scoped store, and coordinating Vault policy changes. This is a significant refactor with broad blast radius across both tenants. It is a valid follow-on hardening step but is disproportionate as a CVE patch response. Dropped for this proposal.

**Alternative 2 — Add an admission webhook or OPA policy to block cross-namespace ExternalSecret references.**
A custom admission policy could enforce namespace constraints at creation time. However, it does not patch the underlying controller vulnerability (an attacker could still submit a Workflow that uses the ESO service account directly). It also introduces a new admission webhook component that adds latency and operational overhead. Dropped; the upstream patch is cleaner and sufficient.

**Alternative 3 — Restrict ESO ClusterRoleBinding to only `admins` and `labs` namespaces via a custom ClusterRole.**
Tightening the ClusterRole reduces blast radius but does not fix the cross-namespace fetch logic in the controller. Any future namespace added to the platform would require a manual RBAC update, creating operational friction. Dropped; upstream patch preferred.

## Platform impact

**Migrations:** No CRD migrations required. helm-chart-2.4.1 is a patch release; existing ExternalSecret, ClusterSecretStore, and SecretStore resources are fully compatible.

**Backward compatibility:** All existing ExternalSecret manifests in `platform-gitops/argo-workflows/secrets/` and per-service directories continue to work unchanged, as long as they correctly reference only secrets within their own namespace's authorised Vault paths (which is the intended configuration). Any ExternalSecret that was previously exploiting the cross-namespace bypass would now be rejected — but no legitimate manifest should be doing this.

**Resource impact (`labs`):** ESO controller runs in the `admins` tenant. No new pods, sidecars, or init containers are introduced. `labs` memory usage is unaffected. No risk to `labs` memory limit.

**Risks and mitigations:**
- Risk: ESO controller restart causes a brief period where new ExternalSecret reconciliation is paused. Mitigation: existing Kubernetes Secrets previously synced by ESO remain in place during the restart; applications continue to read them normally. Only net-new or expiring secrets are delayed.
- Risk: A legitimate ExternalSecret is misconfigured in a way that looked like cross-namespace access and is now rejected. Mitigation: review all ExternalSecret manifests in `platform-gitops/` before merging the upgrade PR to confirm all references stay within their intended namespace and Vault path.
- Risk: Vault ClusterSecretStore token expiry coincides with the upgrade window. Mitigation: verify Vault token renewal status before scheduling the upgrade commit.
