# Design: argocd-image-updater-ns-escalation

## Current state
ArgoCD Image Updater runs as a separate Deployment alongside the ArgoCD control plane
(see `context/architecture.md`, ArgoCD App-of-Apps section). It is deployed via the
bootstrap chart and has a ClusterRole that allows it to list and patch Application
resources across all namespaces. Namespace validation of ImageUpdater resources is absent
in affected versions, meaning the service account can be abused to write to Application
resources in any tenant namespace — including `admins` — from a resource defined in `labs`.

The platform currently tracks version 4.10.1 of `mctl-gitops` (git tag). ArgoCD itself
is managed through the App-of-Apps pattern under
`platform-gitops/apps/` and `platform-gitops/bootstrap/`.

## Proposed solution
**Option A — Upgrade (preferred if Image Updater is in active use).**
Upgrade ArgoCD Image Updater to the first release that carries the CVE-2026-6388 fix.
The upgrade is applied by bumping the image tag in the Image Updater Deployment manifest
under `platform-gitops/services/<tenant>/argocd-image-updater/` (or the equivalent
bootstrap values). ArgoCD will perform a rolling update.

Additionally, tighten the Image Updater ClusterRole (or convert it to a namespaced Role)
so that the service account is only authorized to patch Application resources within its
own namespace. This is a defence-in-depth layer that limits blast radius regardless of
future upstream bugs.

**Option B — Disable/remove (preferred if Image Updater is not actively used).**
Remove the Image Updater Deployment, ServiceAccount, and all associated RBAC manifests
from the bootstrap chart. ArgoCD will sync the deletion. This is the lowest-risk path
when the component provides no current value.

The team should first audit whether any Application resource carries an
`argocd-image-updater.argoproj.io/update-strategy` annotation. If none do, Option B is
the recommended action.

**Implementation path (Option A):**
1. Identify the patched Image Updater release tag from upstream.
2. Update the image reference in the relevant Helm values or raw manifest.
3. Narrow the ClusterRole to a per-namespace Role bound only to the tenant namespace
   where Image Updater legitimately operates.
4. Commit, push; ArgoCD auto-syncs the Deployment rolling update.
5. Verify with an integration test (see tasks.md).

**Implementation path (Option B):**
1. Confirm zero active `argocd-image-updater` annotations across all Application resources.
2. Delete or comment out the Image Updater Application definition from the bootstrap chart.
3. Delete RBAC manifests (ClusterRole, ClusterRoleBinding or Role/RoleBinding,
   ServiceAccount).
4. Commit, push; ArgoCD syncs deletions.

## Alternatives

**Alternative 1 — Network policy isolation only.**
Apply a NetworkPolicy that blocks Image Updater egress to the ArgoCD API server for
cross-namespace paths. Dropped because NetworkPolicy does not stop Kubernetes API calls
that go through the same API server endpoint; the RBAC boundary is the correct enforcement
layer, not network-layer policy.

**Alternative 2 — Admission webhook to reject cross-namespace ImageUpdater resources.**
Deploy a validating admission webhook that inspects ImageUpdater resources on creation/
update and rejects those referencing out-of-namespace Applications. Dropped because it adds
operational complexity (webhook cert management, failure policy risk) and is redundant if
the upstream fix is applied or the component is removed.

**Alternative 3 — Wait for upstream auto-update (no action now).**
Accept the risk and wait for the next scheduled maintenance window. Dropped because CVSS
9.1 Critical with a straightforward exploit path is not acceptable to defer; the fix
effort is classified as low (Impact 5, Effort 2 per analyst scoring).

## Platform impact

**Migrations**
- Option A: image tag bump only; no CRD changes expected.
- Option B: Deployment and RBAC resources are deleted; no data migration required.

**Backward compatibility**
- Option A: no API surface change; existing Application annotations continue to function
  with the patched version.
- Option B: any Application that does rely on Image Updater annotations will lose automated
  image updates. This must be confirmed as zero before choosing Option B.

**Resource impact**
- Option A: the existing Image Updater Pod footprint is unchanged (typically ~64 Mi / 50m).
  No new components. No impact on `labs` memory budget.
- Option B: the Pod is removed, freeing a small amount of memory in the namespace it runs
  in. Positive for `labs` if Image Updater currently runs there, but the saving is minor.

**Risks and mitigations**
- Risk: upgrade introduces a regression in image update behavior.
  Mitigation: run the existing application test suite post-upgrade; roll back via git revert
  if sync fails (see tasks.md Rollback section).
- Risk: removing Image Updater silently breaks an undocumented use.
  Mitigation: audit all Application resources for Image Updater annotations before removing.
- Risk: tightened Role still leaves a gap if the upstream bug is in the controller logic
  rather than RBAC.
  Mitigation: the version upgrade addresses the controller bug; RBAC tightening is a
  defence-in-depth layer, not the sole control.
