# Design: argocd-repo-server-feature-lockdown

## Current state
Argo CD config lives in this repo's platform-gitops (context/architecture.md). Feature usage is unaudited.

## Proposed solution
Audit all Applications/ApplicationSets and repo secrets for kustomize+Helm, Jsonnet and proxy usage; then set `kustomize.buildOptions` and related argocd-cm settings accordingly through a GitOps commit.

## Alternatives
- Rely on patching only: rejected, no defense in depth.
- NetworkPolicy only: covered by existing argocd-repo-server-hardening.

## Platform impact
- Migrations: Apps using disabled features would fail to render; audit first.
- Resources: none; no labs impact.
- Risks: broken rendering; mitigate with a render dry-run of every App.
