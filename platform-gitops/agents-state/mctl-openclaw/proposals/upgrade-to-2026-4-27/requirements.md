# Upgrade openclaw from 2026.3.14 to 2026.4.27

## Context

The currently deployed version of openclaw across all three tenants (`admins`, `labs`, `ovk`) is **2026.3.14** (March 14, 2026). Upstream has advanced to **2026.4.27** (April 29, 2026), a gap of 6 weeks and multiple minor releases.

This gap is security-critical. Five HIGH-severity CVEs disclosed between March 22 and April 27, 2026 are unpatched in 2026.3.14:

| CVE | CVSS | Fixed in | Impact |
|-----|------|----------|--------|
| CVE-2026-41353 | 8.1 HIGH | 2026.3.22 | `allowProfiles` access control bypass |
| CVE-2026-41371 | 8.5 HIGH | 2026.3.28 | Privilege escalation via `chat.send` |
| CVE-2026-41349 | 8.7 HIGH | 2026.3.28 | Agentic consent bypass via `config.patch` |
| CVE-2026-41342 | TBD HIGH | 2026.3.28 | Auth bypass in remote onboarding |
| CVE-2026-41359 | HIGH | 2026.3.28 | Telegram config privilege escalation via send endpoint |
| CVE-2026-41352 | 8.8 HIGH | 2026.3.31 | Node-pairing authorization bypass → RCE |

In addition, 2026.4.26 closes a bearer-token echo vulnerability in `device.token.rotate`, and 2026.4.27 delivers Telegram and Slack reliability fixes directly relevant to production (`ovk`). All patch versions between 2026.3.14 and 2026.4.27 must be traversed to land on a fully patched baseline.

## User stories

- AS an operator I WANT all three tenant deployments to run openclaw 2026.4.27 SO THAT known HIGH/CRITICAL CVEs are remediated and the production `ovk` tenant is no longer exposed to privilege escalation and RCE-class vulnerabilities.
- AS a platform engineer I WANT the upgrade to follow the labs→admins→ovk promotion sequence SO THAT any compatibility issue is caught before it reaches the high-SLA production tenant.
- AS an on-call engineer I WANT the s3-sync canary to be stopped before each rollout and restarted with a delay afterwards SO THAT false canary alerts do not mask real S3-sync failures during the upgrade window.

## Acceptance criteria (EARS)

- WHEN the upgrade is applied to `labs` THE SYSTEM SHALL run openclaw 2026.4.27 with all three tenants' `restore-state` readiness probes passing within the configured timeout before ArgoCD marks the rollout successful.
- WHEN the upgrade has soaked in `labs` for at least 24 hours without incident THE SYSTEM SHALL be eligible for promotion to `admins`.
- WHEN the upgrade is applied to any tenant THE SYSTEM SHALL stop the s3-sync canary workflow before the rollout begins and restart it with the configured post-rollout delay after the pod is ready.
- WHILE the s3-sync canary is stopped during rollout THE SYSTEM SHALL NOT page on missing canary cycles for the duration of that tenant's upgrade window.
- WHEN openclaw 2026.4.27 is running on all three tenants THE SYSTEM SHALL report no unpatched CVEs with CVSS ≥ 7.0 against the deployed version.
- IF the `restore-state` readiness probe fails to pass within its configured timeout on any tenant THE SYSTEM SHALL abort the rollout and ArgoCD SHALL NOT route traffic to the new pod.
- WHEN bearer tokens are rotated via `device.token.rotate` THE SYSTEM SHALL NOT echo the rotated token value in the response body (fix from 2026.4.26).
- WHILE upgrading `labs` (close to memory limit) THE SYSTEM SHALL be monitored for memory delta; IF memory usage increases by more than 50 MB above pre-upgrade baseline THE UPGRADE SHALL be flagged as risky and require explicit operator approval before proceeding to `admins`/`ovk`.

## Out of scope

- Upgrading Baileys to v7 (separate proposal, pre-release dependency).
- Changes to S3 bucket structure or canary alert thresholds (separate proposals).
- Migrating to a different runtime (Node.js 24 LTS) in this same change; runtime and openclaw upgrades should be sequenced, not bundled.
- Cherry-picking individual CVE patches to 2026.3.14; full version upgrade to 2026.4.27 is the only supported fix path.
