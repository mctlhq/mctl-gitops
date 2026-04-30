# ArgoCD Image Updater Cross-Namespace Privilege Escalation (CVE-2026-6388)

## Context
CVE-2026-6388 (Critical, CVSS 9.1) affects ArgoCD Image Updater. The component does not
validate that an ImageUpdater resource is restricted to the namespace of the owning tenant.
An authenticated user who has write access to ImageUpdater resources in their own namespace
(e.g., `labs`) can craft a resource that triggers unauthorized image updates on applications
managed by a different tenant (e.g., `admins`). This breaks the hard tenant-isolation
boundary that the platform relies on at the GitOps control plane layer.

The platform runs two tenants, `admins` and `labs`, with separate namespaces. ArgoCD
manages all application state via the App-of-Apps pattern. A cross-namespace privilege
escalation at the Image Updater level allows a `labs` actor to silently mutate images in
`admins`-owned workloads — an unacceptable blast radius. The fix is either an upgrade to
a patched ArgoCD Image Updater release or disabling the component entirely if it is not
actively in use.

## User stories
- AS a platform operator I WANT ArgoCD Image Updater to be patched or disabled SO THAT
  a tenant cannot trigger image updates on applications they do not own.
- AS a security engineer I WANT evidence that the cross-namespace vector is closed SO THAT
  the platform passes its next security audit without an open Critical CVE.
- AS a `labs` tenant I WANT my namespace operations to be confined to my own applications
  SO THAT I cannot accidentally or maliciously affect `admins` workloads.

## Acceptance criteria (EARS)
- WHEN an ImageUpdater resource is created or modified in the `labs` namespace THE SYSTEM
  SHALL restrict the scope of any triggered image update to applications that reside in the
  `labs` namespace only.
- WHEN an ImageUpdater resource targets an application outside its own namespace THE SYSTEM
  SHALL reject or ignore the update and emit an audit-level log entry.
- WHILE ArgoCD Image Updater is running THE SYSTEM SHALL enforce namespace-scoped RBAC so
  that the Image Updater service account cannot write to Application resources in namespaces
  it does not own.
- IF ArgoCD Image Updater is confirmed to be inactive or undeployed THEN THE SYSTEM SHALL
  have the component removed from the bootstrap chart and all related RBAC manifests deleted.
- IF the patched Image Updater version is deployed THEN THE SYSTEM SHALL produce a passing
  integration test demonstrating that a cross-namespace update attempt is rejected.
- WHEN the upgrade or removal is applied via an ArgoCD sync THE SYSTEM SHALL complete
  reconciliation without sync errors or health degradation in either tenant.

## Out of scope
- Changes to ArgoCD core (server, application-controller, repo-server) — only Image Updater
  is in scope.
- Modifications to ApplicationSet definitions or the App-of-Apps bootstrap chart beyond
  removing Image Updater references.
- Broader RBAC hardening of ArgoCD beyond namespace scoping for Image Updater.
- Remediation of any other CVE in the ArgoCD ecosystem (e.g., those covered by
  `argocd-informer-cache-patch`).
