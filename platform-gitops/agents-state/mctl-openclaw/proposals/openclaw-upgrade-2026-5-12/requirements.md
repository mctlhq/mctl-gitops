# Upgrade openclaw to v2026.5.12 to patch four "Claw Chain" CVEs and reduce core memory footprint

## Context

mctl-openclaw currently runs openclaw **2026.3.14** across all three tenants (`labs`, `admins`,
`ovk`). On 2026-05-14, the upstream project released **v2026.5.12** as the new stable release.
That same month, four OpenShell vulnerabilities — collectively named "Claw Chain" — were publicly
disclosed:

| CVE | CVSS | Summary |
|-----|------|---------|
| CVE-2026-44112 | 9.6 | TOCTOU race condition allows redirecting S**writes** outside the intended OpenShell sandbox mount root |
| CVE-2026-44115 | 8.8 | Incomplete allowlist validation lets attackers embed shell-expansion tokens in here-documents to execute unapproved commands |
| CVE-2026-44118 | 7.8 | Improper access control allows non-owner loopback clients to impersonate the gateway owner and reconfigure it |
| CVE-2026-44113 | 7.7 | TOCTOU race condition allows **reading** files outside the intended OpenShell sandbox mount root |

All four are present in our running version. v2026.5.12 is the fix target (the highest-CVSS flaw
is 9.6 — this is a security-emergency upgrade).

Beyond the CVE fixes, v2026.5.12 externalises heavyweight provider dependency cones
(WhatsApp/Baileys, Slack, Amazon Bedrock, Anthropic Vertex) out of the core runtime. This
directly reduces the resident memory footprint of the base openclaw process — a concrete
benefit for the `labs` tenant that is operating close to its Kubernetes memory limit.

A prior proposal (`openclaw-upgrade-cve-batch`) targeted v2026.5.6 for an earlier set of CVEs.
The current proposal supersedes that target by upgrading directly to v2026.5.12.

## User stories

- AS a security engineer I WANT all four "Claw Chain" CVEs remediated across every tenant SO THAT
  sandbox escapes and gateway impersonation attacks cannot be executed against our deployments.
- AS a platform engineer I WANT the upgrade rolled out in `labs` → `admins` → `ovk` order SO THAT
  any regression is caught before it reaches the production `ovk` customer.
- AS an ops engineer I WANT the s3-sync canary stopped before each tenant rollout and restarted
  after SO THAT S3 session-sync state is not corrupted during the upgrade window.
- AS a `labs` operator I WANT confirmed memory headroom after the upgrade SO THAT the `labs`
  tenant does not breach its Kubernetes memory limit as a result of the version change.

## Acceptance criteria (EARS)

- WHEN the upgraded Docker image is built, THE SYSTEM SHALL include openclaw version 2026.5.12
  or later and no earlier version.
- WHEN a rollout to any tenant begins, THE SYSTEM SHALL have the s3-sync Argo CronWorkflow
  paused before the new pod is started (per ADR-0002).
- WHEN the new pod passes its restore-state readiness probe, THE SYSTEM SHALL resume the
  s3-sync Argo CronWorkflow for that tenant with the delay configured in ADR-0002.
- WHEN the upgrade is deployed to the `labs` tenant, THE SYSTEM SHALL not exceed the tenant's
  configured Kubernetes memory limit as observed in mctl metrics within 15 minutes of pod startup.
- WHILE the upgraded service is running, THE SYSTEM SHALL not expose any OpenShell execution
  path that permits writes or reads outside the configured mount root
  (CVE-2026-44112 / CVE-2026-44113).
- WHILE the upgraded service is running, THE SYSTEM SHALL reject any here-document command body
  containing shell-expansion tokens that are not in the approved allowlist (CVE-2026-44115).
- WHILE the upgraded service is running, THE SYSTEM SHALL deny gateway-configuration API calls
  from any loopback client that has not authenticated as the owner (CVE-2026-44118).
- IF the restore-state readiness probe does not become healthy within the configured timeout
  after upgrade, THEN THE SYSTEM SHALL halt the rollout to that tenant and page the on-call
  engineer.
- IF memory usage in the `labs` tenant exceeds 90 % of its limit within 15 minutes of pod
  startup, THEN THE SYSTEM SHALL page the on-call engineer and the rollout to `admins` SHALL
  be blocked until the issue is resolved.
- WHEN the rollout to `ovk` is complete, THE SYSTEM SHALL have all three tenants running
  openclaw 2026.5.12, the s3-sync canary active, and zero open incidents.

## Out of scope

- Upgrading any dependency other than the openclaw application itself (Node.js base-image
  upgrade is tracked separately under `nodejs-security-patch`).
- Changes to the S3 session-storage design described in ADR-0002.
- Enabling new features introduced in v2026.5.12 (Telegram isolated polling, durable local
  spooling, voice call via Telnyx) — those require separate proposals.
- Automated rollback orchestration (rollback is manual per the existing runbook).
- Merging tenants or changing rollout order — both are permanently rejected by ADR-0001.
