# Add a govulncheck gate to CI and a scheduled scan

## Context
Dependency CVE proposals are regenerated almost daily and handled one by one. There is no automated, reachability-aware check that fails builds on known vulnerabilities.

## User stories
- AS a maintainer I WANT CI to fail on reachable vulnerabilities SO THAT fixes are caught before release.
- AS a platform operator I WANT a weekly scan SO THAT new CVEs in unchanged code are surfaced.

## Acceptance criteria (EARS)
- WHEN a pull request is opened THE SYSTEM SHALL run `govulncheck ./...` and fail the check if reachable vulnerabilities exist.
- WHEN the weekly schedule fires THE SYSTEM SHALL run govulncheck on the default branch and report findings as an issue or notification.
- IF a vulnerability is accepted as a known risk THEN THE SYSTEM SHALL allow it via a documented, expiring exclusion list.
- WHILE govulncheck is unavailable THE SYSTEM SHALL fail visibly rather than pass silently.

## Out of scope
- Fixing individual vulnerabilities; changing the circuit breaker; container image scanning.
