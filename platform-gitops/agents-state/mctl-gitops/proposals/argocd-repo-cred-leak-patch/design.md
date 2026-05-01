# Design: argocd-repo-cred-leak-patch

## Current state
ArgoCD is deployed at `ops.mctl.ai` and serves as the single GitOps reconciliation engine for the
platform (see `context/architecture.md`). It uses the App-of-Apps bootstrap chart together with
three ApplicationSets (`apps`, `tenants`, `openclaw-skills`) that auto-generate Applications from
directory patterns (ADR `context/decisions/0001-app-of-apps-pattern.md`). Repository credentials
for GitHub push (deploy key `mctl-gitops-deploy-key`) and GitHub App bot credentials are stored in
ArgoCD's internal credential store. All secrets flow through Vault + ExternalSecrets — ArgoCD's own
repo credential store is the one exception still managed natively by ArgoCD.

The current installed version is not pinned in this file; the architecture doc references ArgoCD
at `ops.mctl.ai` as the sync engine without specifying the exact running version.

## Proposed solution
Upgrade ArgoCD to **v3.3.9** (released 2026-04-30). This version includes the security fix for
CVE-2025-55190 (originally patched in v3.1.2 / v3.0.14 / v2.14.16 / v2.13.9) and additionally
ships fixes for ApplicationSet generator panics, Redis cache issues, and pod-log UI crashes — all
of which are relevant to the platform's ApplicationSet-heavy topology.

The upgrade path:
1. Update the ArgoCD Helm values file (or Kustomize overlay) pinned in `platform-gitops/` to
   reference the v3.3.9 image tags.
2. Commit the change to this repository; ArgoCD's bootstrap Application will detect the diff and
   self-upgrade via the App-of-Apps reconciliation loop.
3. Validate that all ApplicationSets re-render without panics and all generated Applications reach
   Healthy/Synced.
4. Add a CI policy check (e.g., a `conftest` or shell gate in the platform CI pipeline) that
   rejects any future ArgoCD version pinned below v3.1.2, acting as a regression guard.

No API surface changes are required. The fix is purely a server-side enforcement change in ArgoCD's
project details endpoint handler.

## Alternatives

### Option A: Patch to the minimum safe version (v3.1.2) only
Upgrade only to the lowest version that carries the CVE fix rather than the latest. This reduces
upgrade surface but foregoes the ApplicationSet panic and Redis fixes already known to affect this
platform. Dropped in favour of v3.3.9 because the additional stability fixes outweigh the slightly
larger version delta.

### Option B: Revoke all project-scoped API tokens immediately, defer upgrade
Revoking tokens stops active exploitation but leaves the endpoint vulnerability in place; any
future token would be equally at risk. It also disrupts automation that relies on project-scoped
tokens. Dropped because it is a temporary workaround, not a fix.

### Option C: Network-level block of the `/api/v1/projects/{project}/detailed` endpoint
Applying an ingress policy or WAF rule to block the vulnerable path prevents exploitation without
requiring an upgrade, but breaks legitimate tooling that calls the project details endpoint.
Dropped because it is brittle and masks the underlying vulnerability.

## Platform impact

**Migrations**
- The ArgoCD image tag pin in `platform-gitops/` must be updated. If ArgoCD is installed via a
  Helm chart (argo-cd chart), the chart version targeting v3.3.9 must be identified and pinned.
- Any CRD changes between the current version and v3.3.9 must be applied before the controller
  rolls over; ArgoCD's standard upgrade procedure (CRDs first, then controller) applies.

**Backward compatibility**
- v3.3.9 is a patch release on the v3.x line. No breaking API changes are anticipated for
  Application, ApplicationSet, or AppProject CRDs relative to v3.x.
- The App-of-Apps pattern (ADR-0001) continues unchanged.

**Resource impact (`labs`)**
- ArgoCD runs in the `admins` tenant, not in `labs`. No additional memory or CPU is expected in
  `labs` as a result of this upgrade. This proposal has no impact on the `labs` memory budget.

**Risks and mitigations**
- Risk: ArgoCD self-upgrade via App-of-Apps could transiently lose sync state during the rollover.
  Mitigation: schedule the upgrade during a low-traffic window; keep the previous image tag in a
  separate git branch for quick rollback.
- Risk: CRD schema changes between versions could cause existing Application objects to fail
  validation.
  Mitigation: run `kubectl diff` against CRDs before applying; verify in a non-production cluster
  first if one is available.
- Risk: Redis cache changes in v3.3.9 could produce a cold-cache sync storm on startup.
  Mitigation: this is expected behaviour on first boot; monitor sync queue depth and allow
  ArgoCD a full reconciliation cycle (~10 min) before declaring the upgrade stable.
