# Design: argocd-secret-leak-cve

## Current state
The platform runs Argo CD at a version prior to v3.3.9 / v3.2.11 in the `admins`
Kubernetes tenant. The mctl-agent service (v1.5.0, see `context/architecture.md` and
`context/current-version.md`) is deployed and reconciled through this Argo CD instance.
Argo CD manages two critical secret-bearing resources for mctl-agent:

1. The GitHub App installation token, rotated every 30 minutes by the CronWorkflow
   `cwft-rotate-github-token` from Vault path `secret/platform/github-app`.
2. The Anthropic API key consumed during the diagnose phase.

CVE-2026-42880 allows an authenticated read-only Argo CD user to exfiltrate these
secrets via a crafted ServerSideDiff request. No exploit code changes are needed beyond
knowing the application and secret names, which are visible in the Argo CD UI.

## Proposed solution
Perform a same-major version bump of Argo CD to v3.3.9 (or v3.2.11 if the cluster is
pinned to the v3.2.x branch). The upgrade path:

1. Update the Argo CD image tag in the platform GitOps repository
   (`mctlhq/mctl-gitops`) under the `admins` overlay.
2. ArgoCD self-manages via the `argocd` Application; the sync will trigger a rolling
   update of the `argocd-server`, `argocd-repo-server`, and `argocd-application-controller`
   Deployments.
3. No CRD schema changes are introduced in these patch releases — the ApplicationSet,
   Application, and AppProject CRDs remain backward-compatible.
4. No changes to mctl-agent's own manifests, Go source, or its dependency tree are
   required.

The rationale for a patch-level bump (not a full minor/major upgrade) is that it carries
the smallest blast radius: no API contract changes, no migration scripts, and no changes
to the ArgoCD Application spec that the ArgoCDDrift builtin skill parses.

## Alternatives

### Option A: Apply the upstream security patch as a custom image build
Build a custom Argo CD image with the CVE-2026-42880 commit cherry-picked onto the
current version. Dropped because it creates an untracked divergence from upstream,
increases image-maintenance burden, and delays time-to-fix compared to pulling the
official patched tag.

### Option B: Disable the ServerSideDiff feature via Argo CD config flag
The ServerSideDiff feature can be disabled entirely with `server.enable.server.side.diff:
"false"` in `argocd-cmd-params-cm`. Dropped because (a) it degrades the drift-detection
UX used by the ArgoCDDrift skill, (b) it is a workaround not a fix, and (c) the upstream
advisory explicitly recommends the version bump over disabling the feature.

### Option C: Restrict Argo CD API access at the ingress/network layer
Tighten NetworkPolicy or Argo CD RBAC so no read-only role can reach the ServerSideDiff
endpoint. Dropped because Argo CD's RBAC does not expose per-endpoint granularity for
this API surface in versions prior to the patch, making this mitigation incomplete.

## Platform impact

### Migrations
None. The patch releases carry no CRD changes, no database migrations, and no
configuration file format changes.

### Backward compatibility
The Argo CD REST API and gRPC contract remain identical. The mctl-agent ArgoCDDrift
builtin skill, which parses Application and cluster resources, is unaffected.

### Resource impact (labs tenant)
This proposal targets the `admins` tenant. The `labs` tenant is close to its memory
limit; rolling out to `labs` is explicitly out of scope and must be assessed separately
with a dedicated memory-impact evaluation before proceeding.

### Risks and mitigations
| Risk | Mitigation |
|---|---|
| Rolling restart causes brief Argo CD unavailability | ArgoCD HA mode with PodDisruptionBudget ensures at least one replica stays ready; mctl-agent's reconciliation loop queues alerts during short outages |
| Patched image fails readiness probe | Kubernetes rollout strategy is RollingUpdate with maxUnavailable=0; automatic rollback triggers if readiness fails within the deadline |
| Upgrade inadvertently changes CRD version | Confirmed: v3.3.9 and v3.2.11 are patch releases with no CRD version bump — verified against upstream changelog |
| Credentials already exfiltrated before patch | Post-patch, a separate incident-response decision on whether to rotate GitHub App and Anthropic keys is required if exploitation evidence is found |
