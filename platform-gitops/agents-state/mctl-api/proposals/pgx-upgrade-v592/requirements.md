# Upgrade pgx/v5 to 5.9.2 — Fix CVE-2025-54236, CVE-2026-33815, CVE-2026-33816

## Context
mctl-api v4.14.0 currently depends on `github.com/jackc/pgx/v5` at version 5.8.x. Three CVEs have been disclosed against this version range: CVE-2025-54236 (SQL injection via placeholder confusion, Low severity), CVE-2026-33815 (memory-safety, improper array index validation, CWE-129), and CVE-2026-33816 (memory-safety, incorrect comparison, CWE-697). All three are fixed in pgx v5.9.2.

pgx is the sole database driver used by mctl-api to serve tenant data and write audit logs in Postgres. A SQL injection vector in the driver (CVE-2025-54236) is a critical risk in a multi-tenant environment, because a confused placeholder could cause one tenant's data to be exposed to or altered by another. The two memory-safety issues introduce potential panic or undefined behaviour under load. Immediate remediation via a minimal version bump is required.

## User stories
- AS a platform engineer I WANT the pgx dependency upgraded to 5.9.2 SO THAT the three known CVEs are eliminated from the production database driver.
- AS a security auditor I WANT evidence that CVE-2025-54236 is remediated SO THAT the audit log proves no SQL-injection vector exists in the DB layer.

## Acceptance criteria (EARS)
- WHEN a request triggers any SQL query via pgx THE SYSTEM SHALL use pgx v5.9.2 or later at runtime.
- WHEN the build pipeline runs THE SYSTEM SHALL produce zero `govulncheck` findings for CVE-2025-54236, CVE-2026-33815, and CVE-2026-33816.
- WHILE the service is running THE SYSTEM SHALL maintain the existing connection-pool behaviour and query semantics with no regressions.
- IF pgx v5.9.2 introduces any breaking API changes THEN THE SYSTEM SHALL compile cleanly with all existing pgx call-sites updated.

## Out of scope
- CVE-2026-4427 (pgproto3 panic — no fix available yet)
- Upgrading to pgx v6 or switching to a different driver
- Connection pool re-tuning (separate concern)
