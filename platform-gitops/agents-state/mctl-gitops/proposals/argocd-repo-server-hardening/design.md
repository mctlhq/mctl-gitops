# Design: argocd-repo-server-hardening

## Current state
Argo CD (`ops.mctl.ai`) is the sync engine for this repo (see `/app/agents/mctl-gitops/context/architecture.md`, App-of-Apps via `apps` and `tenants` ApplicationSets). The running Argo CD version is not recorded in `context/` and must be read from the cluster or mctl. It is unknown whether a NetworkPolicy already restricts repo-server, and whether any App uses kustomize with Helm. Existing proposals such as `argocd-repo-server-rce-network-isolation` may already cover part of the NetworkPolicy; check their status before authoring manifests.

## Proposed solution
Two config-only changes, no image change:

1. NetworkPolicy in the Argo CD namespace selecting repo-server pods (and Redis pods). Ingress on 8081 (gRPC) and Redis 6379 is allowed only from pods labelled as Argo CD application-controller, server, applicationset-controller, notifications-controller (and commit-server if present). Metrics ports are allowed from the Prometheus namespace. Egress is not restricted in this change (repo-server needs Git and Helm registries). Delivered as a manifest in this repo so ArgoCD reconciles it (every platform change is a git commit).
2. Kustomize Helm hardening. Inventory Apps for `--enable-helm` / `helmCharts`. If none use it, remove `--enable-helm` from `kustomize.buildOptions` in `argocd-cm`. If some do, keep it but set `helmGlobals.configHome` to a path outside the repo checkout (for example a tmp dir under repo-server) in those kustomizations or via build options.

Verification of the CVE IDs against NVD and the Argo CD GHSA comes first. The mitigations proceed regardless, but documents mark unverified IDs. Rollout is staged: apply in audit style (confirm labels and ports with a dry run and connection tests) before enforcing.

## Alternatives
- Upgrade Argo CD to a fixed version only: rejected here because it is a version bump with larger blast radius and the fixed versions are not yet verified; it is handled separately in `argocd-patch-serversidediff-fix`.
- Disable Helm for kustomize globally without inventory: rejected, it could silently break Apps.
- Service mesh mTLS between Argo CD components: rejected as too heavy, adds pods and memory.

## Platform impact
- Migrations: none beyond adding one NetworkPolicy manifest and possibly one `argocd-cm` key change.
- Backward compatibility: Apps relying on kustomize-with-Helm would fail to render if Helm is disabled; mitigated by the inventory task and the configHome-pin fallback. A wrong NetworkPolicy label selector could break sync platform-wide.
- Resource impact: no new pods; no memory change. `labs` is unaffected (Argo CD runs in `admins`), so no labs memory risk.
- Risks and mitigations: policy blocks legitimate traffic (test connections from each component before and after; keep a one-command rollback by removing the manifest); CNI may not enforce NetworkPolicy (verify enforcement with a negative test); unverified CVE IDs (flagged, mitigations are harmless either way).
