# Verify Argo Workflows >= 4.1.6 (CVE-2025-58188, CVE-2026-110816)

## Context
A 11 Nov advisory batch lists CVE-2025-58188 (Go x509 DSA chain panic, CVSS 7.5) and CVE-2026-110816 (`qs`, CVSS 5.3) as fixed in argo-workflows 4.1.6-r1. The deployed version is not known to this run.

## User stories
- AS a platform operator I WANT to know and, if needed, fix the deployed Argo Workflows version SO THAT these CVEs are closed.

## Acceptance criteria (EARS)
- WHEN the check runs THE SYSTEM SHALL record the deployed Argo Workflows controller and server versions.
- IF the deployed version is below 4.1.6 (or 4.0.15 on the 4.0 line) THEN THE SYSTEM SHALL be upgraded to a fixed patch version in the same line where possible.
- WHILE the upgrade runs THE SYSTEM SHALL keep CronWorkflows and the archive worker functioning (no recurrence of the 3.7.10 archive NULL bug).
- IF the upgrade would cross a major line THEN THE SYSTEM SHALL defer it to a separate ADR-backed proposal.

## Out of scope
- Major upgrades; other Argo Workflows CVEs covered by existing proposals.
