# Upgrade openclaw to 2026.4.26 (critical security)

## Context

All three mctl-openclaw tenants (`ovk`, `labs`, `admins`) run openclaw 2026.3.14.
Upstream released 2026.4.26 on 2026-04-28. The currently deployed version is below
the fix threshold for nine distinct CVEs — five rated HIGH (CVSS 8.1–8.8), covering
privilege escalation on `chat.send`, LLM agentic consent bypass on `config.patch`,
remote-onboarding auth bypass, missing node-pairing authorization (RCE possible),
and `allowProfiles` access-control bypass. A second batch of CVEs (35636, 35639,
35641, 35668 and others) filed in April are all fixed in 2026.4.5+. Additionally,
2026.4.26 stops rotated bearer tokens from being echoed in `device.token.rotate`
responses.

This upgrade is a security obligation, not an optional improvement. Remaining on
2026.3.14 while the above CVEs are publicly disclosed exposes channel auth tokens,
OAuth credentials stored in S3, and the node-pairing surface to active exploitation.
The upgrade supersedes the prior proposal `upgrade-to-2026-4-25` (target version
2026.4.25), targeting the newer 2026.4.26 release.

## User stories

- AS a platform operator I WANT all three tenants to run openclaw 2026.4.26 SO THAT
  all known CVEs affecting 2026.3.14 are remediated without service interruption.
- AS a security engineer I WANT the upgrade to follow the labs → admins → ovk
  rollout order SO THAT any regression surfaces in the lowest-blast-radius tenant
  first.
- AS an SRE I WANT the restore-state probe to remain active throughout the rollout
  SO THAT a failed S3-session restore blocks promotion rather than causing silent
  auth loss.
- AS a `labs` operator I WANT memory usage validated before promoting to `admins`
  and `ovk` SO THAT the `labs` tenant does not breach its memory limit during or
  after the upgrade.

## Acceptance criteria (EARS)

- WHEN the upgrade to 2026.4.26 is deployed to `labs` THE SYSTEM SHALL complete
  the restore-state readiness probe within the configured timeout before ArgoCD
  marks the rollout successful.
- WHEN the upgrade is deployed to `labs` THE SYSTEM SHALL NOT exceed the `labs`
  memory limit as measured by the mctl memory metric immediately after rollout
  stabilises.
- WHILE the `labs` rollout is in progress THE SYSTEM SHALL keep the s3-sync canary
  stopped and restart it with the configured delay after the pod is marked ready.
- WHEN the `labs` rollout has been observed healthy for the required observation
  period THE SYSTEM SHALL proceed with the `admins` rollout before the `ovk`
  rollout (ADR-0001 order).
- WHEN any tenant rollout is in progress THE SYSTEM SHALL keep the restore-state
  probe active so that ArgoCD does not mark the rollout successful if S3 session
  restoration fails.
- WHEN openclaw 2026.4.26 is running on a tenant THE SYSTEM SHALL NOT echo rotated
  bearer tokens in `device.token.rotate` API responses.
- IF the `labs` memory metric exceeds the tenant limit after the upgrade THEN THE
  SYSTEM SHALL halt promotion to `admins` and `ovk` until the memory regression is
  investigated and resolved.
- IF the restore-state probe does not pass within the configured timeout on any
  tenant THEN THE SYSTEM SHALL roll back that tenant to 2026.3.14 automatically via
  ArgoCD.
- WHEN all three tenants are running 2026.4.26 THE SYSTEM SHALL have no open CVE
  alerts for CVE-2026-41371, CVE-2026-41349, CVE-2026-41342, CVE-2026-41352,
  CVE-2026-41353, CVE-2026-41359, and the April 2026 batch (35636, 35639, 35641,
  35668).

## Out of scope

- Upgrading to any version beyond 2026.4.26 (future releases are a separate
  proposal).
- Changes to the 3-layer skills layout or tenant-specific YAML skills.
- Merging or restructuring the three tenant deployments.
- Modifying S3 bucket policies or canary thresholds beyond what is needed for a
  clean rollout.
- Cherry-picking upstream bug fixes unrelated to the listed CVEs (tracked
  separately in `gateway-ui-responsiveness-fix`).
