# Verify and move Argo Workflows to 4.1.7

## Context
Argo Workflows v4.1.7 (25 Nov) is the latest on the 4.1 line and includes the 4.1.6 fixes for CVE-2025-58188 (Go x509 DSA panic, CVSS 7.5) and CVE-2026-110816 (`qs`, CVSS 5.3). The release page lists no changes, so the changelog must be read. Deployed version is unknown (MCP unavailable). Supersedes `argo-workflows-4-1-6-go-dsa-qs-verify` as the target version.

## User stories
- AS a platform operator I WANT Argo Workflows >= 4.1.7 SO THAT known CVEs are closed and builds/deploys pipelines stay reliable.

## Acceptance criteria (EARS)
- WHEN the check runs THE SYSTEM SHALL report the deployed Argo Workflows controller and server versions.
- IF the deployed version is below 4.1.6 on the 4.x line THEN THE SYSTEM SHALL bump to 4.1.7.
- IF the deployed version is 3.7.x THEN THE SYSTEM SHALL NOT upgrade as part of this proposal and SHALL defer to the existing CVE bundle proposal.
- WHEN the upgrade completes THE SYSTEM SHALL successfully archive a Succeeded workflow without NOT NULL constraint errors.
- WHILE the upgrade runs THE SYSTEM SHALL keep CronWorkflows scheduled.

## Out of scope
- Major version migrations (3.x to 4.x).
- Schema hotfixes for the 3.7.10 bug.
