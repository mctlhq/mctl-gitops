# Design: argocd-image-updater-ns-escalation

## Current state

ArgoCD Image Updater is an optional ArgoCD companion component that watches container registries
and automatically updates the image tags of ArgoCD-managed Applications. When deployed, it runs
with a ClusterRole that grants write access to ArgoCD `Application` resources across all namespaces.

CVE-2026-6388 exploits the absence of a namespace boundary check in the ImageUpdater admission
path: a resource created in namespace A can reference and mutate an Application in namespace B.
On the mctl platform both `admins` and `labs` Applications live under the same ArgoCD instance,
making cross-tenant escalation trivial for any user with `create` on ImageUpdater objects.

See `context/architecture.md` for the App-of-Apps topology (`platform-gitops/apps/`,
`platform-gitops/services/<tenant>/<svc>/`).

## Proposed solution

**Option A (preferred): Upgrade to the patched argocd-image-updater release**

1. Identify the version that ships the fix for CVE-2026-6388 (check the upstream
   `argoproj-labs/argocd-image-updater` release notes).
2. Update the image tag in the argocd-image-updater Helm values file (likely under
   `platform-gitops/services/admins/argocd-image-updater/values.yaml`).
3. Add the `--namespace` startup flag (or the equivalent Helm value) to restrict the controller
   to the `admins` namespace only, blocking cross-namespace writes at the process level.
4. Commit and let ArgoCD sync.

**Option B (fallback if no patched release is available): Disable the component**

1. Set `replicaCount: 0` or remove the ArgoCD Application manifest for argocd-image-updater.
2. Document the disable decision with a reference to CVE-2026-6388.
3. Re-enable once a patched release is confirmed.

In both options, tighten the ClusterRole to a namespaced Role bound only to the `admins`
namespace as defence-in-depth.

## Alternatives

**A. Network policy restriction** — Restricting egress from the image-updater pod to the registry
does not prevent the privilege escalation, which operates at the Kubernetes API level. Dropped.

**B. OPA/Kyverno admission policy** — A validating webhook could reject cross-namespace
ImageUpdater references. Effective but introduces an additional dependency; heavier than a version
pin. Dropped in favour of the upstream fix.

**C. Do nothing / wait** — CVSS 9.1 with active multi-tenant exposure; not acceptable. Dropped.

## Platform impact

- **Migrations:** Helm values file update only; no CRD changes expected in a patch release.
- **Backward compatibility:** Applications that legitimately used cross-namespace Image Updater
  references will need to be reviewed and re-scoped; none expected on mctl given the App-of-Apps
  structure where each tenant owns its own namespace.
- **Resource impact for `labs`:** No new components deployed to `labs`; image-updater already
  runs in `admins`. Zero memory increase for `labs`.
- **Risks:** If image-updater is fully disabled (Option B), automated image tag bumps stop; teams
  must pin image tags manually until the component is restored. Mitigated by documenting the
  interim process.
