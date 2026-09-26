# Argo Rollouts dashboard unauthenticated mutation (CVE-2026-82277) — interim mitigation

## Context
The Argo Rollouts dashboard (through our tracked latest, v1.10.0) binds to all interfaces and
exposes a set of mutating operations — PromoteRollout, AbortRollout, RestartRollout,
SetRolloutImage, UndoRollout, RetryRollout — without any authentication or CSRF protection.
Any caller with network access to the dashboard can invoke these operations against any
Rollout in the cluster, spanning both the `admins` and `labs` tenants. CVE-2026-82277 rates
this CVSS 9.8. No upstream fix exists yet.

Because there is no patched release to adopt, this proposal follows the same shape as
`argo-workflows-strict-mode-bypass-ghsa-3775`: an interim compensating control (disable the
dashboard or restrict it to authenticated/internal-only network access) plus a tracked
follow-up to adopt the eventual upstream fix.

## User stories
- AS a platform operator I WANT the Argo Rollouts dashboard to be unreachable from outside a
  trusted, authenticated network path SO THAT unauthenticated callers cannot promote, abort,
  restart, retry, undo, or change the image of any Rollout in `admins` or `labs`.
- AS the mctl-gitops owner I WANT a tracked follow-up for the upstream patch SO THAT the
  interim mitigation is reconciled or relaxed once CVE-2026-82277 is actually fixed upstream.
- AS a security reviewer I WANT the exposure closed without waiting on upstream SO THAT the
  9.8-CVSS window is not left open indefinitely.

## Acceptance criteria (EARS)
- WHEN the Argo Rollouts dashboard is deployed via `platform-gitops`, THE SYSTEM SHALL NOT
  expose it on a publicly reachable ingress or a Service bound to all interfaces without an
  authentication layer in front of it.
- IF the dashboard is not required for day-to-day operation, THEN THE SYSTEM SHALL disable it
  entirely (remove the Deployment/Service/ingress from the rendered manifests) as the default
  interim posture.
- IF the dashboard must remain enabled for operational reasons, THEN THE SYSTEM SHALL restrict
  access to it via NetworkPolicy scoped to trusted internal callers (or equivalent ingress
  removal plus internal-only Service), so that neither `admins` nor `labs` network paths can
  reach it unauthenticated.
- WHILE CVE-2026-82277 remains unfixed upstream, THE SYSTEM SHALL keep the interim network
  restriction active for both tenants.
- IF upstream publishes a fix version for CVE-2026-82277, THEN THE SYSTEM SHALL trigger a
  follow-up review to adopt the patched release and to retire or relax the interim mitigation
  once the upgrade is verified.

## Out of scope
- Upgrading Argo Rollouts to a version that fixes CVE-2026-82277 — no such version exists yet;
  tracked as a follow-up task, not delivered here.
- The unrelated BlueGreen analysis premature-success bug covered by
  `argo-rollouts-v1-9-0-upgrade`.
- Building a standalone authentication/SSO layer for the dashboard — the interim mitigation is
  network-level restriction or removal, not adding a new auth stack.
- Changes to Argo CD, Argo Workflows, or ArgoCD ApplicationSet behavior.
