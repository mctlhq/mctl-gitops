# Prepare Upgrade Path for ArgoCD v3.4.0 (RC7 Published, GA Imminent)

## Context

ArgoCD v3.4.0 RC7 was published on April 30, 2026. The release candidate cadence indicates
that General Availability (GA) is imminent. The platform currently runs ArgoCD v3.3.9, deployed
via the App-of-Apps ApplicationSet pattern. A minor version upgrade from v3.3 to v3.4 must be
planned and tested proactively to avoid a reactive scramble at GA.

Proactive planning provides three benefits: (1) any deprecated ApplicationSet API fields or
annotation changes in v3.4 are identified before the GA release forces the issue; (2) a staged
rollout through tenant `labs` before `admins` reduces production risk; (3) memory impact on
`labs` (which is near its memory limit) is measured and documented before the upgrade is
applied to `admins`.

This proposal covers the preparation and staged rollout plan only. It does not constitute
approval to apply the upgrade; final execution against `admins` requires a separate sign-off
once `labs` is confirmed stable for 24 hours.

## User stories

- AS a platform engineer I WANT a tested upgrade plan for ArgoCD v3.4.0 ready before GA
  SO THAT the upgrade can be applied promptly and safely once GA is announced.
- AS a platform engineer I WANT ArgoCD v3.4.0 tested in the `labs` tenant first SO THAT
  any ApplicationSet reconciliation regressions are detected before they affect `admins`.
- AS a platform engineer I WANT the `labs` memory delta documented before and after the
  upgrade SO THAT I can confirm the upgrade does not push `labs` beyond its memory limit.

## Acceptance criteria (EARS)

- WHEN ArgoCD v3.4.0 GA is released THE SYSTEM SHALL have a tested upgrade plan committed
  to this repository, including changelog review, API diff, and RC7 test results from `labs`.
- WHEN the ArgoCD v3.4.0 upgrade is applied to `labs` THE SYSTEM SHALL verify that all
  ApplicationSets continue reconciling and producing the expected Application objects.
- WHEN the ArgoCD v3.4.0 upgrade is applied to `labs` THE SYSTEM SHALL NOT increase
  `labs` memory consumption beyond its current quota limit.
- IF the ArgoCD v3.4.0 upgrade causes any ApplicationSet or Application health check to
  fail in `labs` THEN THE SYSTEM SHALL roll back automatically to v3.3.9 by reverting the
  version pin commit and re-syncing ArgoCD.
- WHEN the `admins` tenant upgrade is applied THE SYSTEM SHALL only proceed after `labs`
  has been confirmed healthy and stable on v3.4.x for a minimum of 24 hours.
- WHILE the upgrade is in progress THE SYSTEM SHALL ensure that at least one ArgoCD server
  replica is available to serve UI and CLI requests (rolling update strategy).

## Out of scope

- Changing the App-of-Apps ApplicationSet pattern (accepted ADR — do not change).
- Upgrading to ArgoCD v3.5 or later (out of scope for this proposal).
- Upgrading Argo Workflows as part of this change (separate service, separate proposal).
- Any changes to the Go CLI tool at `cli/mctl/` unless an ArgoCD API client library
  version bump is strictly required.
- Applying the upgrade to `admins` before `labs` stability is confirmed.
