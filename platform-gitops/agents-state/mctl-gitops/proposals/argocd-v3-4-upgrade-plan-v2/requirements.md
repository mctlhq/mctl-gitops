# Execute ArgoCD v3.4.0 Upgrade (Now GA)

## Context

ArgoCD v3.4.0 reached General Availability on May 5, 2026. The predecessor proposal
`argocd-v3-4-upgrade-plan` was a preparation-only spec written when RC7 was available; it
explicitly deferred final execution to "a separate sign-off once labs is confirmed stable for
24 hours." That gate condition is now met: the GA tag is published and the preparation work
(changelog review, deprecated-field correction, RC7 staging in `labs`) is complete. This
proposal is the **execution spec** that carries the upgrade from the end of Phase 1 through
to `admins` promotion.

ArgoCD v3.4.0 bundles all v3.3.x security patches, including the fix for CVE-2026-42880
(captured in `argocd-secret-leakage-patch`). Upgrading to GA consolidates the platform on a
single, fully patched minor line and enables new operational capabilities: cluster
reconciliation pausing for planned maintenance windows, Microsoft Teams Adaptive Cards
webhook notifications, and Helm value globs for more flexible chart templating.

## User stories

- AS a platform engineer I WANT ArgoCD v3.4.0 GA deployed to `labs` first SO THAT any
  regression between RC7 and GA is caught before it reaches `admins`.
- AS a platform engineer I WANT ArgoCD v3.4.0 GA promoted to `admins` after 24 hours of
  `labs` stability SO THAT production is upgraded with confirmed confidence.
- AS a platform operator I WANT the `labs` memory delta documented between RC7 and GA
  SO THAT any memory regression introduced in the GA build is identified before it affects
  the `labs` quota.
- AS a security engineer I WANT `admins` running ArgoCD v3.4.0 SO THAT all v3.3.x CVEs
  are subsumed and no future v3.3-branch patch carries unmitigated risk.
- AS an on-call engineer I WANT a clearly defined rollback path SO THAT I can revert the
  upgrade within minutes if a production regression is detected.

## Acceptance criteria (EARS)

- WHEN the ArgoCD version pin in the `labs` Application manifest is updated to v3.4.0 GA,
  THE SYSTEM SHALL complete a rolling restart of all ArgoCD pods in `labs` while maintaining
  at least one replica available throughout the restart sequence.
- WHEN ArgoCD v3.4.0 GA is running in `labs`, THE SYSTEM SHALL show all ApplicationSets and
  Applications in `labs` as `Synced` and `Healthy` within ten minutes of pod stabilization.
- WHEN ArgoCD v3.4.0 GA is running in `labs`, THE SYSTEM SHALL NOT cause total ArgoCD pod
  memory consumption in `labs` to exceed the tenant memory quota.
- IF the `labs` memory consumption after GA deployment differs from the RC7 baseline by more
  than 10 percent, THEN THE SYSTEM SHALL produce a written assessment before the `admins`
  promotion step proceeds.
- WHILE ArgoCD v3.4.0 GA is under 24-hour observation in `labs`, THE SYSTEM SHALL NOT
  initiate the `admins` promotion step.
- WHEN the 24-hour `labs` stability window has elapsed without pod restarts, reconciliation
  errors, or memory quota alerts, THE SYSTEM SHALL permit the `admins` promotion step to
  proceed.
- WHEN the ArgoCD version pin in the `admins` bootstrap Application manifest is updated to
  v3.4.0 GA, THE SYSTEM SHALL complete a rolling restart of all ArgoCD pods in `admins`
  while maintaining at least one replica available throughout.
- WHEN ArgoCD v3.4.0 GA is running in `admins`, THE SYSTEM SHALL show all ApplicationSets
  and Applications in `admins` as `Synced` and `Healthy` within ten minutes of pod
  stabilization.
- IF ArgoCD v3.4.0 GA causes any ApplicationSet or Application health check to fail in
  `admins`, THEN THE SYSTEM SHALL support rollback to v3.3.9 by reverting the version pin
  commit and triggering an ArgoCD self-sync within five minutes of the decision to roll back.
- WHILE the upgrade is in progress in either tenant, THE SYSTEM SHALL NOT modify the
  App-of-Apps ApplicationSet pattern defined in ADR 0001.

## Out of scope

- Changing the App-of-Apps ApplicationSet pattern (accepted ADR 0001 — do not change).
- Upgrading to ArgoCD v3.5 or later (out of scope for this proposal).
- Upgrading Argo Workflows or Argo Rollouts as part of this change (separate proposals).
- Enabling or configuring new v3.4.0 features (cluster reconciliation pausing, Teams webhook,
  Helm value globs) — feature enablement is deferred to follow-on proposals.
- Any changes to the Go CLI tool at `cli/mctl/` unless an ArgoCD API client library version
  bump is strictly required.
- Applying the upgrade to `admins` before the 24-hour `labs` stability window is complete.
- Revisiting or altering the preparation work already merged by `argocd-v3-4-upgrade-plan`.
