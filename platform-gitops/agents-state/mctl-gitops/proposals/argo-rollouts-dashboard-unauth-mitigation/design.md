# Design: argo-rollouts-dashboard-unauth-mitigation

## Current state
Per `context/architecture.md`, Argo Rollouts is part of our deployment stack alongside Argo
Workflows and Argo CD, deployed through `platform-gitops/` like every other platform
component. The Rollouts dashboard, as shipped through our tracked latest v1.10.0, binds to all
interfaces and exposes mutating operations (PromoteRollout, AbortRollout, RestartRollout,
SetRolloutImage, UndoRollout, RetryRollout) with no authentication or CSRF protection
(CVE-2026-82277, CVSS 9.8). Wherever the dashboard's Service/ingress is currently rendered in
`platform-gitops/services/<tenant>/<svc>/` or a shared component chart, it is reachable without
any auth check, across both `admins` and `labs` namespaces. No upstream fix exists yet.

## Proposed solution
Since there is no patch to adopt, we apply a network-level interim control, repo-local to
`platform-gitops`, mirroring the approach taken for GHSA-3775-99mw-8rp4:

1. **Disable-by-default.** Where the dashboard is not actively required for operations, remove
   its Deployment/Service/ingress from the rendered Helm values so it simply is not deployed.
   This is the lowest-risk, zero-maintenance option and is the default posture for `labs`.
2. **Restrict-if-needed.** Where an operator genuinely needs the dashboard (e.g. `admins`
   tenant for release management), scope its Service to `ClusterIP` only, remove any public
   ingress, and add a NetworkPolicy that allows ingress only from an explicitly trusted
   internal source (e.g. a bastion/VPN-fronted pod range or an authenticated reverse-proxy
   sidecar), never from `0.0.0.0/0` or the general pod CIDR.
3. **No new auth stack.** We do not attempt to bolt on authentication to the dashboard itself
   in this proposal — that is a larger effort with its own risk surface, and the mutating
   operations are severe enough that "not reachable unauthenticated" is the priority, not
   "reachable but authenticated." Adding real auth is left to the eventual upstream fix.
4. **Upstream tracking.** A dedicated tracking task follows CVE-2026-82277 for a published fix.
   Once available, we run our normal Argo Rollouts upgrade proposal flow (as
   `argo-rollouts-v1-9-0-upgrade` did for its unrelated bug) and, upon verified adoption,
   revisit whether the network restriction can be relaxed.

This keeps the change entirely within `platform-gitops` manifests/NetworkPolicy — no new
cluster-side dependency, no fork, no controller patch.

## Alternatives
- **Do nothing until upstream ships a fix.** Rejected: CVSS 9.8 with unauthenticated mutating
  access to any Rollout in either tenant is an unacceptable open window.
- **Front the dashboard with a new auth proxy (e.g. oauth2-proxy) instead of restricting
  network access.** Rejected as the primary/initial delivery: more moving parts (new
  Deployment, session/cookie config, another thing to patch) for a control that network
  restriction already achieves more simply; can be reconsidered as a longer-term option if the
  dashboard turns out to be needed broadly.
- **Fork/patch the Rollouts dashboard binary to add auth ourselves.** Rejected: high
  maintenance burden (tracking/rebasing a patch against upstream) for a problem better solved
  at the network boundary we already control via `platform-gitops`.

## Platform impact
- **Migrations:** None. Manifest/NetworkPolicy changes only; no CRD or Rollouts controller
  version change.
- **Backward compatibility:** If the dashboard is disabled where currently deployed, any
  operator workflow that relies on browsing it loses that UI (CLI/kubectl-based Rollout
  management remains available). If restricted rather than disabled, only unauthenticated/
  external access paths are removed; legitimate internal access continues to work.
- **Resource impact (labs):** Net neutral-to-positive. Disabling the dashboard in `labs`
  removes a running Deployment/Service, slightly reducing CPU/memory footprint in a tenant
  already near quota (~83% CPU / ~70% memory this cycle). Restricting via NetworkPolicy where
  the dashboard stays deployed adds negligible resource cost (a NetworkPolicy object, not a
  workload). No configuration in this proposal increases `labs` resource pressure.
- **Risks and mitigations:**
  - Risk: an operator relies on the dashboard UI and is surprised when it disappears.
    Mitigation: communicate the change before rollout; keep CLI-based Rollout management as
    the documented alternative.
  - Risk: NetworkPolicy misconfiguration accidentally blocks legitimate internal access.
    Mitigation: validate the policy in a non-prod namespace first, and keep the "disable
    entirely" option as a simpler fallback if restriction proves fragile.
  - Risk: interim mitigation is forgotten once upstream ships a fix. Mitigation: explicit
    tracking task tied to CVE-2026-82277 (see `tasks.md`).
