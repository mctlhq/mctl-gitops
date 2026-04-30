# ArgoCD Image Updater Cross-Namespace Privilege Escalation (CVE-2026-6388)

## Context

CVE-2026-6388 (CVSS 9.1 Critical) is a privilege escalation vulnerability in ArgoCD Image Updater
where insufficient namespace validation allows an authenticated user who can create or modify an
ImageUpdater resource to bypass tenant namespace boundaries and trigger unauthorized image updates
on applications owned by other tenants.

The mctl platform hosts two tenants — `admins` and `labs` — sharing the same ArgoCD control plane
at `ops.mctl.ai`. Any cross-namespace escalation at the GitOps layer undermines the fundamental
isolation guarantee between tenants and could allow a `labs` user to trigger image rollouts in
`admins` (or vice versa), corrupting production workloads.

## User stories

- AS a platform operator I WANT argocd-image-updater to be restricted to its own namespace SO THAT
  no user can weaponize it to update applications outside their tenant boundary.
- AS a security engineer I WANT the patched or disabled image-updater configuration committed to
  this repo SO THAT the remediation is auditable via git history and re-applied on every ArgoCD sync.
- AS a tenant in `labs` I WANT assurance that another tenant cannot trigger a rollout into my
  namespace SO THAT my workloads are not disrupted by unauthorized image updates.

## Acceptance criteria (EARS)

- WHEN a user creates or modifies an ImageUpdater resource in any namespace, THE SYSTEM SHALL
  enforce that the resource's `argocd-image-updater.argoproj.io/app-name` annotation references
  only applications within the same tenant namespace.
- WHEN argocd-image-updater is deployed, THE SYSTEM SHALL run with a scoped ClusterRole or
  namespaced Role that denies write access to ArgoCD Application resources outside its designated
  namespace.
- IF the installed argocd-image-updater version is earlier than the release that patches
  CVE-2026-6388, THE SYSTEM SHALL either upgrade to the patched version or have the component
  disabled in the ArgoCD Application manifest.
- WHEN argocd-image-updater is disabled or upgraded, THE SYSTEM SHALL confirm that all existing
  ArgoCD Applications continue to sync and reconcile without errors.
- WHILE argocd-image-updater is absent or at the patched version, THE SYSTEM SHALL not expose any
  endpoint that allows cross-namespace Application write operations.

## Out of scope

- Changes to the ArgoCD ApplicationSet templates or the bootstrap App-of-Apps chart.
- Changes to the `base-service` Helm chart used by tenant workloads.
- Broader ArgoCD RBAC overhaul beyond the Image Updater component.
- Rotation of ArgoCD admin credentials or deploy keys.
