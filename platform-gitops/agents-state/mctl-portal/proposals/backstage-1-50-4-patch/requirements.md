# Backstage v1.50.4 Security Patch

## Context
Backstage v1.50.4 was released on 2026-04-29 as a security patch on the 1.50.x minor line. It patches catalog security modules (including `@backstage/plugin-catalog-backend-module-unprocessed`) and upgrades `@backstage/integration` to 1.20.1, which fixes CVE-2026-29185 (path traversal via encoded SCM URLs, CVSS 2.7). mctl-portal is currently running a stale 1.50.x patch (last recorded update 2026-04-27, before the 1.50.4 release). Running any version below 1.50.4 against a published CVE constitutes a compliance risk regardless of CVSS score.

The 1.50.4 patch is within the same minor line and is therefore safe to apply without community-plugins compatibility risk, as confirmed by ADR-0001 which restricts only major-version increments. The update closes an outstanding compliance gap and aligns the service with the latest supported security baseline on the 1.50.x train.

## User stories
- AS a platform security engineer I WANT mctl-portal upgraded to Backstage v1.50.4 SO THAT CVE-2026-29185 (encoded SCM URL path traversal) is remediated and the portal is no longer running against a published CVE.
- AS a compliance officer I WANT the portal to run on the latest security patch of its current minor line SO THAT audit evidence shows the service applies security patches within a reasonable window of release.
- AS a portal operator I WANT the upgrade to remain within the 1.50.x minor line SO THAT no community-plugins re-validation or major regression testing cycle is required.

## Acceptance criteria (EARS)
- WHEN Backstage packages are built and deployed THE SYSTEM SHALL report the root `@backstage` package version as 1.50.4 (or the current highest patch on the 1.50.x line at time of release).
- WHEN `@backstage/integration` is resolved in the backend bundle THE SYSTEM SHALL be at version 1.20.1 or higher.
- IF a catalog integration request is made with an encoded SCM URL containing path traversal sequences (e.g., `%2F..%2F`) THEN THE SYSTEM SHALL reject or normalise the URL without traversing outside the intended SCM path (CVE-2026-29185 regression guard).
- WHEN the patched release is deployed THE SYSTEM SHALL pass all existing catalog, scaffolder, and integration tests without regression.
- WHILE the upgraded service is running THE SYSTEM SHALL remain fully compatible with all installed community-plugins at their current versions.
- WHEN the backstage-cli version check runs THE SYSTEM SHALL confirm all `@backstage/*` packages are consistent with the 1.50.4 release manifest (no mixed-version packages).

## Out of scope
- Upgrading beyond Backstage 1.50.x (a separate proposal is required for any minor or major bump).
- Updating community-plugins beyond their current versions unless required for 1.50.4 compatibility.
- Changes to RBAC policy, auth configuration, or catalog entity schemas.
- Remediation of CVEs in Node.js runtime (covered by the `nodejs-22-security-upgrade` proposal).
