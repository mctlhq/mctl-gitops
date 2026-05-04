# Patch pgx to v5.9.2 to fix SQL Injection CVE

## Context

mctl-api imports `jackc/pgx/v5` at v5.8 as its sole Postgres driver. The database it manages holds tenant identities and audit logs — the two data assets whose cross-tenant exposure is classified as the service's known critical failure mode. CVE-2025-54236 (GHSA-j88v-2chj-qfwx), disclosed in 2025, describes a SQL injection vulnerability in pgx triggered by placeholder confusion with dollar-quoted string literals. Exploitability is conditioned on use of pgx's **simple query protocol**; the extended (prepared-statement) protocol, which is pgx's default, is not affected. A second vulnerability fixed in the same release series, CVE-2026-4427, describes a denial-of-service in pgproto3 via a negative field length in `DataRow.Decode` and is exploitable regardless of protocol mode.

The fix for both CVEs is available in pgx v5.9.2, which carries no breaking API changes relative to v5.8. The upgrade is therefore a low-effort, high-impact security patch. Before closing the proposal, the team must confirm and document which query protocol mctl-api uses so that the CVE-2025-54236 exploitability posture is on record.

## User stories

- AS a platform security engineer I WANT pgx upgraded to v5.9.2 SO THAT the SQL injection and DoS vulnerabilities are no longer present in the production binary.
- AS a platform operator I WANT the query protocol used by mctl-api confirmed and documented SO THAT I can assess current exposure and prevent protocol-mode drift in future changes.
- AS a tenant administrator I WANT tenant identity data protected from SQL injection SO THAT cross-tenant data leaks caused by driver bugs are eliminated.

## Acceptance criteria (EARS notation)

- WHEN the Go module graph is resolved, THE SYSTEM SHALL declare `github.com/jackc/pgx/v5 v5.9.2` (or later) as the selected version, with no downgrades introduced by indirect dependencies.
- WHEN the CI pipeline runs, THE SYSTEM SHALL pass `govulncheck ./...` with zero findings referencing CVE-2025-54236 or CVE-2026-4427.
- WHEN a query is executed against Postgres, THE SYSTEM SHALL use the extended (prepared-statement) query protocol unless an explicit, reviewed exception is recorded in `context/decisions/`.
- IF mctl-api uses the simple query protocol for any query path, THEN THE SYSTEM SHALL have a corresponding Architecture Decision Record documenting the reason, the accepted risk, and any compensating controls.
- WHILE the service is running after the upgrade, THE SYSTEM SHALL emit no new Postgres connection errors at a rate higher than the pre-upgrade baseline (verified via the `/metrics` endpoint).
- WHEN the container image is built, THE SYSTEM SHALL produce a `govulncheck` SARIF report that is archived as a CI artefact and contains zero HIGH or CRITICAL findings for the `jackc/pgx` module.

## Out of scope

- Upgrading any other dependency beyond pgx/v5 and its transitive requirements (`pgconn`, `pgproto3`, `pgtype`).
- Switching from pgx to an ORM (explicitly prohibited in `context/architecture.md`).
- Changing the Postgres schema, connection pool configuration, or query logic.
- Remediating CVEs in dependencies unrelated to pgx.
- Enabling new pgx v5.9.x features (SCRAM-SHA-256-PLUS, OAuth for PostgreSQL 18, protocol 3.2, tsvector type) — those may be proposed separately.
