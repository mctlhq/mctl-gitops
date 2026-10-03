# Tasks: argo-rollouts-dashboard-unauth-mitigation

- [ ] 1. Inventory where the Argo Rollouts dashboard is currently deployed across
  `platform-gitops/services/<tenant>/<svc>/` (both `admins` and `labs`) — DoD: written list of
  every location where the dashboard Deployment/Service/ingress is rendered, with current
  exposure (public ingress / cluster-internal / already restricted) noted for each.
- [ ] 2. For tenants/services where the dashboard is not actively needed, remove it from the
  rendered manifests (depends on 1) — DoD: dashboard Deployment/Service/ingress no longer
  present in the rendered output for those services; verified via `argocd app diff` (or
  equivalent) showing the resources removed.
- [ ] 3. For any location where the dashboard must remain, scope its Service to `ClusterIP`,
  remove public ingress, and add a NetworkPolicy allowing ingress only from an explicitly
  trusted internal source (depends on 1) — DoD: NetworkPolicy manifest merged and applied,
  verified that access from outside the allow-list is refused (connection refused/timeout).
- [ ] 4. Document the interim mitigation and its scope (which services are disabled vs.
  restricted, and why) as a short ADR under `context/decisions/` — DoD: ADR merged and
  referenced from this proposal.
- [ ] 5. Open and link a tracking issue for CVE-2026-82277 upstream fix status (depends on
  nothing, can run in parallel) — DoD: tracking issue exists, linked from this proposal's
  `requirements.md` Source and from the ADR in task 4, with an owner checking upstream status
  on a recurring basis until resolved.
- [ ] 6. Once CVE-2026-82277 has an upstream fix, open a follow-up Argo Rollouts upgrade
  proposal (depends on 5) and, after it is adopted and verified, revisit whether the network
  restriction from task 3 can be relaxed — DoD: follow-up proposal created and this proposal's
  tracking issue (task 5) closed with a decision recorded.

## Tests
- [ ] T1. Negative test: from outside the trusted allow-list (or from the public internet, for
  any service that previously had a public ingress), attempting to reach the dashboard's
  mutating endpoints (e.g. PromoteRollout) fails to connect.
- [ ] T2. Positive test: from within the trusted internal source (for services where the
  dashboard is restricted rather than disabled), the dashboard remains reachable and
  functional.
- [ ] T3. Regression test: `kubectl`/CLI-based Rollout operations (promote, abort, restart,
  set-image, undo, retry) continue to work normally after the dashboard is disabled/restricted,
  confirming operators retain a working management path.
- [ ] T4. Verify no `labs` Deployment/Service count regression occurs in the opposite direction
  (i.e. confirm the mitigation reduces or holds flat resource usage, not increases it).

## Rollback
Both the disable and restrict paths are additive/subtractive manifest changes local to
`platform-gitops`: if the mitigation breaks a legitimate workflow, revert the relevant commit
(task 2 or 3) to restore the prior dashboard deployment/exposure. No cluster-side controller
version or CRD changes are made, so rollback is a straightforward git revert followed by an
ArgoCD sync. The tracking issue (task 5) and ADR (task 4) remain in place regardless of
rollback to preserve the audit trail.
