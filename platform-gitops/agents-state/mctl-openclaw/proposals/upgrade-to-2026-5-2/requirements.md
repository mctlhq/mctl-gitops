# Upgrade openclaw to v2026.5.2

## Context

All three mctl-openclaw tenants (`admins`, `labs`, `ovk`) currently run openclaw 2026.3.14. This version is exposed to ten unpatched CVEs. Seven of those CVEs were identified before 2026-05-02 and were tracked under the now-superseded `upgrade-to-2026-4-29` proposal (CVE-2026-42422, CVE-2026-42426, CVE-2026-42428, CVE-2026-42429, CVE-2026-42423, CVE-2026-41912, CVE-2026-41914). Three additional CVEs published on or around 2026-05-02 further extend the exposure: CVE-2026-41394 (unauthenticated access to operator-write scopes via plugin-auth HTTP routes), CVE-2026-41395 (Plivo V3 webhook replay bypass via query-parameter reordering), and CVE-2026-41390 (exec allowlist bypass via shell wrappers). Beyond the ten CVEs, the current version contains a CWE-532 credential leak: `?password=`, `?token=` query parameters and `Authorization:` headers are written to logs in plain text, creating a persistent audit-trail risk across all three tenants.

openclaw v2026.5.2 (released 2026-05-02) resolves all ten CVEs and the CWE-532 log sanitization defect in a single release. It also externalizes two previously bundled packages — `@openclaw/acpx` and `@openclaw/diagnostics-otel` — as opt-in peer dependencies, reducing the base package footprint. This is especially significant for the `labs` tenant, which is close to its memory limit, and represents a net positive memory impact. The proposal supersedes `upgrade-to-2026-4-29`; no intermediate upgrade to 2026.4.29 will be performed.

## User stories

- AS a platform engineer I WANT all ten outstanding CVEs and the CWE-532 credential-leak defect to be resolved in a single rollout SO THAT the mctl-openclaw security exposure is eliminated without multiple intermediate upgrade cycles.
- AS a security engineer I WANT `?password=`, `?token=`, and `Authorization:` header values to be redacted from logs after the upgrade SO THAT credentials captured before the upgrade are not further leaked and compliance obligations are met.
- AS an operator I WANT the restore-state probe failure rate to decrease after the upgrade SO THAT ArgoCD rollouts complete successfully and `ovk` channel downtime is minimized.
- AS an operator I WANT the rollout to follow the mandatory labs → admins → ovk promotion sequence SO THAT `labs` acts as a canary for `ovk` and a regression does not reach the production tenant undetected.
- AS a platform engineer I WANT evidence that the `labs` pod memory footprint does not increase after the upgrade SO THAT the `labs` memory limit is not breached.
- AS an `ovk` customer I WANT the upgrade to be performed during a pre-approved low-traffic window SO THAT any brief restart does not coincide with peak usage.

## Acceptance criteria (EARS)

- WHEN the gitops PR bumping the openclaw image tag to `2026.5.2` is merged for the `labs` tenant, THE SYSTEM SHALL apply the image tag change via ArgoCD without requiring manual intervention beyond the merge.
- WHEN a tenant rollout begins, THE SYSTEM SHALL have the s3-sync canary CronWorkflow suspended for that tenant before the new pod is scheduled.
- WHILE the new pod is starting on any tenant, THE SYSTEM SHALL NOT be marked ready by ArgoCD until the restore-state readiness probe passes, confirming that auth and sessions have been restored from S3.
- WHEN the restore-state readiness probe passes on `labs`, THE SYSTEM SHALL trigger a 24-hour soak observation period before any gitops change is made to `admins`.
- WHEN the restore-state readiness probe passes on `admins`, THE SYSTEM SHALL trigger a 24-hour soak observation period before any gitops change is made to `ovk`.
- WHEN the s3-sync canary is restarted after a rollout, THE SYSTEM SHALL apply the post-rollout start delay defined in ADR-0002 to prevent false alert storms.
- WHEN the `labs` pod is running v2026.5.2 during the soak period, THE SYSTEM SHALL have a pod RSS measurement no greater than 50 MB above the pre-upgrade baseline; IF the delta exceeds 50 MB, THE SYSTEM SHALL block promotion to `admins` until an operator provides explicit written sign-off.
- WHEN a log line is produced by any tenant running v2026.5.2, THE SYSTEM SHALL NOT include `?password=` or `?token=` query parameter values or `Authorization:` header values in plain text in log output.
- WHEN the upgrade is complete on all three tenants, THE SYSTEM SHALL report all ten CVEs (CVE-2026-42422, CVE-2026-42426, CVE-2026-42428, CVE-2026-42429, CVE-2026-42423, CVE-2026-41912, CVE-2026-41914, CVE-2026-41394, CVE-2026-41395, CVE-2026-41390) as resolved with no remaining critical or high CVEs in the 2026.3.14 → 2026.5.2 change range.
- IF the `ovk` rollout must be scheduled, THE SYSTEM SHALL execute the rollout during the pre-approved low-traffic maintenance window.
- WHILE any tenant is mid-rollout, THE SYSTEM SHALL NOT initiate a rollout for any other tenant.
- WHEN gateway startup completes on any tenant running v2026.5.2, THE SYSTEM SHALL skip plugin-backed auth-profile overlays during secrets preflight, reducing startup latency and the risk of restore-state probe timeout.

## Out of scope

- Enabling the `git:` plugin install capability introduced in v2026.5.2 — tracked separately in the `git-plugin-install-allowlist` proposal; this proposal explicitly leaves `git:` plugin installs disabled.
- Installing or activating `@openclaw/acpx` or `@openclaw/diagnostics-otel` as explicit opt-in packages — they are not installed by default and are not needed by the current skill set; activation is a separate proposal.
- Enabling Grok 4.3 (xAI chat model), ClawHub artifact metadata persistence, enhanced Slack threading, or Discord component handling as explicit configuration changes — these are delivered passively by the upgrade and are observed during soak; no new configuration will be activated in this proposal.
- Activating Keychain credential handling for OpenAI Realtime sessions as an explicit configuration change — observed during soak only.
- Patching or auditing the `device.token.rotate` response-parsing tooling — tracked as a separate backlog item and is a prerequisite gate for the `ovk` step (see tasks.md).
- Merging tenants or altering the three-tenant topology (rejected by ADR-0001).
- Replacing S3 state storage with any alternative backend (rejected by ADR-0002).
- Upgrading the Node.js runtime — tracked in the `nodejs-runtime-upgrade` proposal.
- Performing any intermediate upgrade to openclaw 2026.4.29 — this proposal supersedes `upgrade-to-2026-4-29` and targets 2026.5.2 directly.
