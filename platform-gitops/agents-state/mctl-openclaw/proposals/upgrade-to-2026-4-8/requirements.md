# Patch four openclaw CVEs (batch, minimum safe version 2026.4.8)

## Context
On 2026-04-28 four CVEs were published that all affect openclaw versions earlier than 2026.4.8. All three tenants (`labs`, `admins`, `ovk`) are currently running 2026.3.14 and are therefore fully exposed. Two vulnerabilities carry a CVSS score of 8.8: CVE-2026-42422 allows minting tokens for unapproved roles via `device.token.rotate`, and CVE-2026-42426 permits unprivileged users to approve exec-capable node pairing via `node.pair.approve`. Two additional vulnerabilities score 7.1: CVE-2026-42428 omits integrity verification on downloaded plugin archives, and CVE-2026-42429 causes the gateway plugin HTTP auth layer to widen `operator.read` requests to `operator.write` runtime permissions.

The stable release 2026.4.8 addresses all four CVEs. Upstream has moved on to 2026.4.29-beta.4, which is not considered here — this proposal targets the minimum safe stable version only. Because the upgrade touches the openclaw core, the rollout must follow ADR-0001 order (`labs` → `admins` → `ovk`) with the s3-sync canary and restore-state probe guards from ADR-0002 honoured at every step.

## User stories
- AS a platform operator I WANT all three tenants upgraded to openclaw 2026.4.8 SO THAT the four known CVEs are remediated before they can be exploited.
- AS a security reviewer I WANT a documented, ordered rollout with canary and probe checks SO THAT a bad upgrade does not silently break S3 state persistence.
- AS the `ovk` customer I WANT the upgrade to reach production only after it has been validated on `labs` and `admins` SO THAT the risk of a production outage is minimised.
- AS a platform operator I WANT the memory footprint of 2026.4.8 on `labs` evaluated before deploying SO THAT we do not violate the `labs` memory limit.

## Acceptance criteria (EARS)
- WHEN the `labs` tenant helm release is updated to 2026.4.8 THE SYSTEM SHALL stop the s3-sync canary before the rollout begins and restart it after the pod is ready.
- WHEN the `labs` pod starts after the upgrade THE SYSTEM SHALL pass the restore-state readiness probe before ArgoCD marks the rollout successful.
- WHILE the `labs` rollout is in progress THE SYSTEM SHALL NOT proceed with the `admins` rollout.
- WHEN the `labs` rollout is confirmed healthy (canary passing, probe passing) for the observation period THE SYSTEM SHALL allow the `admins` rollout to begin.
- WHEN the `admins` rollout is confirmed healthy THE SYSTEM SHALL allow the `ovk` rollout to begin.
- WHEN any rollout step fails the restore-state probe THE SYSTEM SHALL halt the rollout and trigger an alert.
- IF the measured RSS memory of the 2026.4.8 pod on `labs` exceeds the current 2026.3.14 baseline by more than 50 MB THEN THE SYSTEM SHALL block promotion to `admins` and `ovk` until a justified mitigation is in place.
- WHEN all three tenants are running 2026.4.8 THE SYSTEM SHALL have `context/current-version.md` updated to reflect the new version.
- WHEN the upgrade is complete THE SYSTEM SHALL have an ADR in `context/decisions/` recording the version change and any memory-footprint findings.

## Out of scope
- Upgrading beyond 2026.4.8 (e.g., to the 2026.4.29-beta.4 upstream beta).
- Backporting individual CVE patches to 2026.3.14 as a standalone fix.
- Merging tenants or changing the three-tenant architecture.
- Any change to S3 bucket layout, canary polling interval, or probe timeout.
- Remediating vulnerabilities in plugins or extensions not shipped by openclaw core.
