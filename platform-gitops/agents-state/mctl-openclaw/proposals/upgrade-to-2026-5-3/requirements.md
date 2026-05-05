# Upgrade all tenants to openclaw v2026.5.3 to patch six open HIGH CVEs

## Context

All three mctl-openclaw tenants (`labs`, `admins`, `ovk`) currently run openclaw **2026.3.14**. Six vulnerabilities confirmed present in that version have not yet been remediated: CVE-2026-41394 (CVSS 8.8 — unauthenticated plugin-auth HTTP routes receive operator write scope), CVE-2026-42422 (CVSS 8.8 — `device.token.rotate` role bypass), CVE-2026-33579 (directory traversal and command injection in device pairing), CVE-2026-41390 (CVSS 7.3 — exec allowlist bypass via shell-script wrappers), CVE-2026-41395 (CVSS 7.5/8.2 — Plivo webhook replay bypass via query-parameter reordering), and CVE-2026-41358 (CVSS 5.4 — Slack prompt injection). All six are fixed in upstream v2026.5.3.

The predecessor release v2026.5.2 (tracked in `proposals/upgrade-to-2026-5-2/`) contained two known regressions: a gateway crash after approximately 12 hours of uptime and an incompatibility with Feishu channel authentication. Both regressions are resolved in v2026.5.3, making it the correct single promotion target. The rollout must follow the mandatory promotion order defined in ADR-0001: `labs → admins → ovk`.

## User stories

- AS a platform operator I WANT all tenants running openclaw v2026.5.3 SO THAT the six open HIGH CVEs are no longer exploitable against any tenant.
- AS a platform operator I WANT the `labs` tenant upgraded first SO THAT regressions are caught before they reach the production `ovk` tenant.
- AS a platform operator I WANT the `ovk` tenant upgraded only after a clean 24-hour soak on `admins` SO THAT the high-SLA production deployment is not exposed to undetected regressions.
- AS a security reviewer I WANT a documented upgrade record for each tenant SO THAT audit requirements are satisfied.

## Acceptance criteria (EARS)

- WHEN the gitops PR for `labs` is merged THE SYSTEM SHALL update the `labs` openclaw image tag from `2026.3.14` to `2026.5.3` and trigger an ArgoCD sync.
- WHEN the `labs` pod starts THE SYSTEM SHALL pass the `restore-state` readiness probe within the configured timeout before ArgoCD marks the rollout successful.
- WHILE the `labs` 24-hour soak period is active THE SYSTEM SHALL maintain s3-sync canary success for all canary cycles that execute after the post-rollout canary restart.
- WHEN the `labs` soak period completes without failure THE SYSTEM SHALL allow the `admins` gitops PR to be opened (promotion gate).
- WHEN the `admins` pod starts THE SYSTEM SHALL pass the `restore-state` readiness probe within the configured timeout before ArgoCD marks the rollout successful.
- WHILE the `admins` 24-hour soak period is active THE SYSTEM SHALL maintain s3-sync canary success for all canary cycles that execute after the post-rollout canary restart.
- WHEN the `admins` soak period completes without failure THE SYSTEM SHALL allow the `ovk` gitops PR to be opened (promotion gate).
- WHEN the `ovk` pod starts THE SYSTEM SHALL pass the `restore-state` readiness probe within the configured timeout before ArgoCD marks the rollout successful.
- WHILE any tenant soak is active THE SYSTEM SHALL maintain pod RSS memory within 50 MB of the pre-upgrade baseline for that tenant.
- IF the `labs` pod RSS memory increases by more than 50 MB above the pre-upgrade baseline THEN THE SYSTEM SHALL block promotion to `admins` until an operator provides explicit written sign-off.
- IF the gateway crashes or the s3-sync canary fails continuously for more than two consecutive cycles during any soak THEN THE SYSTEM SHALL treat the rollout as failed and trigger rollback for that tenant.
- WHEN v2026.5.3 is active on a tenant THE SYSTEM SHALL respond to unauthenticated requests on plugin-auth HTTP routes with an authentication error (CVE-2026-41394 remediated).
- WHEN v2026.5.3 is active on a tenant THE SYSTEM SHALL enforce role checks on `device.token.rotate` regardless of request origin (CVE-2026-42422 remediated).
- WHEN v2026.5.3 is active on a tenant THE SYSTEM SHALL reject device-pairing requests containing path-traversal sequences (CVE-2026-33579 remediated).
- WHEN v2026.5.3 is active on a tenant THE SYSTEM SHALL reject exec commands that attempt allowlist bypass via shell-script wrappers (CVE-2026-41390 remediated).
- WHEN v2026.5.3 is active on a tenant THE SYSTEM SHALL reject Plivo webhook requests that fail replay-protection validation (CVE-2026-41395 remediated).
- IF a Slack message contains prompt injection markers THEN THE SYSTEM SHALL sanitize the input before passing it to the skill runtime (CVE-2026-41358 remediated).
- WHEN the upgrade is complete on all tenants THE SYSTEM SHALL continue to serve the Feishu channel without authentication errors (v2026.5.2 Feishu regression must be absent in v2026.5.3).
- WHILE any tenant is running v2026.5.3 THE SYSTEM SHALL not crash the gateway at or around the 12-hour uptime mark (v2026.5.2 gateway crash regression must be absent).

## Out of scope

- Activation of the `git:` plugin install feature introduced in the 2026.5.x series (tracked separately in `git-plugin-install-allowlist`).
- Upgrading to any version beyond 2026.5.3.
- Changes to the 3-layer skills architecture or YAML skill content.
- Changes to the s3-sync canary or restore-state probe configuration.
- Any changes to `ovk` outside of the mandatory image tag bump and its verification steps.
- Addressing CVEs in npm dependencies (tracked in `baileys-lockfile-audit`, `npm-supply-chain-audit`).
