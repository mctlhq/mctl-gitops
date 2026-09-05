# Design: argocd-repo-server-rce-network-isolation

## Current state
Per `context/architecture.md`, Argo CD (`ops.mctl.ai`) is the sync engine
for the whole platform, using App-of-Apps + ApplicationSets defined via the
bootstrap chart (`platform-gitops/bootstrap/`) and Application definitions
under `platform-gitops/apps/`. The repo-server component clones this git
repo and renders Helm/Kustomize/raw-YAML manifests for the
`argocd-application-controller` to apply. Today, network access controls
between Argo CD's internal components are presumably whatever the default
chart/namespace posture provides — no repo-server-specific NetworkPolicy is
currently documented in `context/architecture.md`. The unpatched RCE means
any pod with network reach to the repo-server's internal gRPC/manifest
port (unauthenticated) can potentially execute code in that context.

## Proposed solution
1. Author a Kubernetes `NetworkPolicy` manifest scoped to the repo-server
   pod (selected via its standard `app.kubernetes.io/name: argocd-repo-server`
   label or equivalent), placed alongside the other Argo CD control-plane
   manifests (e.g. under `platform-gitops/apps/` or wherever the Argo CD
   Application/bootstrap definition lives — following the repo's existing
   raw-YAML convention).
2. The policy's `ingress` rules allow traffic to the repo-server's internal
   port only from pods labeled `app.kubernetes.io/name: argocd-server` and
   `app.kubernetes.io/name: argocd-application-controller` within the same
   namespace (the Argo CD control-plane namespace). All other ingress is
   denied by default (NetworkPolicy default-deny semantics once any policy
   selects the pod).
3. Confirm the cluster's CNI enforces NetworkPolicy (this is a
   precondition, not a design choice — see risks below).
4. Commit the manifest to this repo so it is picked up by the standard
   ArgoCD sync flow like any other manifest — no ApplicationSet generator
   changes, no new pattern.
5. No changes to the repo-server's own code, image, or configuration — this
   is purely a network-layer control around the existing, unpatched
   component.

## Alternatives
- **Wait for an upstream patch** — rejected: reported since January 2025,
  still unpatched as of July 2026 with no committed timeline; leaving the
  repo-server fully reachable in the meantime is an unacceptable exposure
  window for a component this central.
- **Migrate off Argo CD's repo-server (e.g. to Flux, which has a different
  architecture)** — rejected outright per ADR-0001 ("do not propose
  migrating from ArgoCD to Flux — too expensive, broad blast radius").
- **Add a manual approval gate before repo-server renders untrusted input**
  — rejected per ADR-0001 ("do not propose adding manual approval gates
  around ApplicationSet — process escalation, requires social buy-in"); also
  doesn't address the actual network-reachability vector.
- **Service mesh mTLS/authorization policy instead of a plain
  NetworkPolicy** — considered but not chosen as the primary proposal: adds
  a new dependency (mesh sidecar, resource overhead) for a problem a native
  NetworkPolicy already solves; can be a future enhancement if the platform
  already runs a mesh, but this proposal keeps the fix minimal and
  dependency-free.

## Platform impact
- **Migrations:** None. This adds one new NetworkPolicy manifest; no
  existing resources are modified or migrated.
- **Backward compatibility:** No API/CRD version changes. Existing Argo CD
  sync flows are unaffected as long as `argocd-server` and
  `argocd-application-controller` retain their expected labels — this
  should be verified against the actual deployed labels before finalizing
  selectors (see tasks.md).
- **Resource impact (labs):** None. The repo-server runs in the Argo CD
  control-plane namespace, not in `labs`, and a NetworkPolicy consumes no
  pod CPU/memory (it's enforced by the CNI's existing dataplane). This
  change does not affect the `labs` memory budget, consistent with the
  analyst's rationale.
- **Risks and mitigations:**
  - Risk: cluster CNI does not enforce NetworkPolicy, making this a
    silent no-op. Mitigation: explicit verification task before considering
    this proposal complete (acceptance criteria call this out as blocking).
  - Risk: incorrect label selectors accidentally block legitimate
    repo-server traffic (e.g. from a Notifications controller or CLI
    port-forward used for debugging), causing sync failures. Mitigation:
    stage the policy, verify sync health across a sample of Applications
    before considering it final, and keep an easy one-line revert path.
  - Risk: policy only covers ingress; if the RCE is exploitable via a
    different vector (e.g. compromised sidecar already inside the allowed
    set), this does not fully close the gap. Mitigation: document this as
    defense-in-depth, not a full fix, and revisit once an upstream patch or
    CVE ships.
