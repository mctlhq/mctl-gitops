# Upgrade openclaw to v2026.4.29 stable

## Context

All three mctl-openclaw tenants (`admins`, `labs`, `ovk`) currently run openclaw 2026.3.14. This version is exposed to seven unpatched CVEs, four of which carry a CVSS score of 7.1 or higher: a token-role bypass via `device.token.rotate` (CVE-2026-42422, CVSS 8.8), improper authorization in `node.pair.approve` (CVE-2026-42426, CVSS 8.8), missing plugin integrity verification (CVE-2026-42428, CVSS 7.1), and a gateway plugin HTTP auth privilege escalation (CVE-2026-42429, CVSS 7.1). The remaining three — an approval-timeout bypass allowing arbitrary eval execution (CVE-2026-42423), an SSRF policy bypass (CVE-2026-41912), and a QQ Bot media SSRF (CVE-2026-41914) — increase the overall attack surface. Earlier proposals targeting intermediate 2026.4.x releases (`upgrade-to-2026-4-8`, `upgrade-to-2026-4-25`, `upgrade-to-2026-4-26`, `upgrade-to-2026-4-27`) are now superseded by v2026.4.29, which became the latest stable release on 2026-04-30.

v2026.4.29 closes all seven CVEs in a single upgrade and adds further security hardening — HTML tag sanitization against script-sequence injection and timing-safe credential comparison — as well as gateway slow-startup and stale-session recovery fixes that directly reduce restore-state probe failure risk under ADR-0002. No new library dependencies are introduced, so no memory footprint increase is expected for the `labs` tenant.

## User stories

- AS a platform engineer I WANT all seven outstanding CVEs to be resolved in a single rollout SO THAT the mctl-openclaw security exposure is eliminated without multiple intermediate upgrade cycles.
- AS an operator I WANT the restore-state probe failure rate to decrease after the upgrade SO THAT ArgoCD rollouts complete successfully and `ovk` channel downtime is minimized.
- AS an operator I WANT the rollout to follow the mandatory labs → admins → ovk promotion sequence SO THAT `labs` acts as a canary for `ovk` and a surprise regression does not reach the production tenant.
- AS a security engineer I WANT evidence that no new library dependency is added SO THAT the `labs` memory limit is not breached by this upgrade.
- AS an `ovk` customer I WANT the upgrade to be performed during a low-traffic window SO THAT any brief restart does not coincide with peak usage.

## Acceptance criteria (EARS)

- WHEN the gitops PR bumping the openclaw image tag to `2026.4.29` is merged for the `labs` tenant, THE SYSTEM SHALL apply the image tag change via ArgoCD without requiring manual intervention beyond the merge.
- WHEN a tenant rollout begins, THE SYSTEM SHALL have the s3-sync canary CronWorkflow stopped before the new pod is scheduled.
- WHILE the new pod is starting on any tenant, THE SYSTEM SHALL NOT be marked ready by ArgoCD until the restore-state readiness probe passes, confirming that auth and sessions have been restored from S3.
- WHEN the restore-state readiness probe passes on `labs`, THE SYSTEM SHALL trigger a 24-hour soak observation period before any gitops change is made to `admins`.
- WHEN the restore-state readiness probe passes on `admins`, THE SYSTEM SHALL trigger a 24-hour soak observation period before any gitops change is made to `ovk`.
- WHEN the s3-sync canary is restarted after a rollout, THE SYSTEM SHALL apply the post-rollout start delay defined in ADR-0002 to prevent false alert storms.
- WHEN the `labs` pod is running v2026.4.29 during the soak period, THE SYSTEM SHALL have a pod RSS delta no greater than 50 MB above the pre-upgrade baseline; IF the delta exceeds 50 MB, THE SYSTEM SHALL block promotion to `admins` until an operator provides explicit written sign-off.
- WHEN the upgrade is complete on all three tenants, THE SYSTEM SHALL report all seven CVEs (CVE-2026-42422, CVE-2026-42426, CVE-2026-42428, CVE-2026-42429, CVE-2026-42423, CVE-2026-41912, CVE-2026-41914) as resolved with no remaining critical or high CVEs in the 2026.3.14 → 2026.4.29 change range.
- IF the `ovk` rollout must be scheduled, THE SYSTEM SHALL execute the rollout during the pre-approved low-traffic maintenance window.
- WHILE any tenant is mid-rollout, THE SYSTEM SHALL NOT initiate a rollout for any other tenant.

## Out of scope

- Enabling the new NVIDIA or Bedrock Opus 4.7 provider support introduced in v2026.4.29 — those are separate feature proposals.
- Enabling the new QQ Bot, Discord, Slack Block Kit, Telegram, WhatsApp, Teams, or Matrix channel improvements as explicit configuration changes — they are delivered passively by the upgrade and observed during soak, but no new channels will be activated in this proposal.
- Activating active-run steering or people-aware wiki memory (new features in v2026.4.29) — out of scope for this security-focused upgrade.
- Patching or auditing the `device.token.rotate` response-parsing tooling — tracked as a separate task in the bearer-token remediation backlog.
- Merging tenants or altering the three-tenant topology (rejected by ADR-0001).
- Replacing S3 state storage with any alternative backend (rejected by ADR-0002).
- Upgrading the Node.js runtime — tracked in the `nodejs-runtime-upgrade` proposal.
