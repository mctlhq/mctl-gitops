# Add NetworkPolicy to restrict access to Argo CD repo-server's internal port

## Context
An unauthenticated attacker with network reach to Argo CD's repo-server
internal port can achieve remote code execution. This was reported to
maintainers in January 2025 and remains unpatched as of the July 2026
disclosure — there is no upstream version bump available to fix it. The
repo-server is a core component of the sync engine
(`context/architecture.md`: Argo CD at `ops.mctl.ai`) that clones and
renders this repo's manifests, so an RCE there is effectively an RCE on the
GitOps source-of-truth pipeline, with blast radius across every tenant
(`admins`, `labs`, others) whose Applications it renders.

Since no patched version exists, the actionable mitigation is
defense-in-depth at the network layer: a Kubernetes NetworkPolicy that
restricts ingress to the repo-server pod to only the other Argo CD
control-plane components that legitimately need it (`argocd-server`,
`argocd-application-controller`). This can be authored as a plain
Kubernetes manifest applied via the existing raw-YAML/App-of-Apps flow,
without changing the ApplicationSet pattern, adding approval gates, or
touching the ArgoCD-to-Flux question — respecting ADR-0001's "what not to
propose" list.

## User stories
- AS a platform operator I WANT the repo-server's internal port reachable
  only from authorized Argo CD control-plane pods SO THAT an unauthenticated
  attacker elsewhere in the cluster cannot reach the unpatched RCE surface.
- AS the mctl-gitops maintainer I WANT this mitigation expressed as a
  version-controlled manifest in this repo SO THAT it is auditable and
  reconciled by ArgoCD like every other platform change.
- AS a tenant workload owner (e.g. in `labs`) I WANT this policy to add no
  new compute/memory overhead to my namespace SO THAT it does not further
  strain the `labs` memory budget.

## Acceptance criteria (EARS)
- WHEN the NetworkPolicy is applied THE SYSTEM SHALL allow ingress to the
  repo-server pod's internal port only from pods labeled as
  `argocd-server` and `argocd-application-controller` in the Argo CD
  control-plane namespace.
- WHEN a pod outside those two labeled sets attempts to connect to the
  repo-server's internal port THE SYSTEM SHALL deny the connection at the
  network layer.
- WHILE the NetworkPolicy is active THE SYSTEM SHALL continue to allow
  normal Argo CD sync operations (manifest rendering, Application
  reconciliation) to proceed without disruption.
- IF the cluster's CNI does not enforce NetworkPolicy resources THEN THE
  SYSTEM SHALL surface this as a blocking finding before the manifest is
  considered a complete mitigation (the policy is a no-op without
  enforcement).
- WHEN the NetworkPolicy manifest is committed THE SYSTEM SHALL apply it
  through the existing ArgoCD Application/App-of-Apps sync flow, not a
  manual `kubectl apply` outside git.

## Out of scope
- Migrating away from Argo CD or its repo-server (e.g. to Flux) — excluded
  per ADR-0001.
- Adding manual approval gates around ApplicationSet or sync operations —
  excluded per ADR-0001.
- Patching the RCE itself — no upstream fix exists yet; this proposal is
  network-layer mitigation only, to be revisited once a CVE/patch is
  published.
- Broader network segmentation of the entire cluster beyond the
  repo-server's ingress rules.
