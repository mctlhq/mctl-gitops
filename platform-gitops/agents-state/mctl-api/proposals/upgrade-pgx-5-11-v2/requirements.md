# Upgrade pgx/v5 from 5.8 to 5.11.0

## Context
pgx 5.8 predates fixes for two critical memory-safety CVEs (5.9.0) and CVE-2026-41889 SQL injection (5.9.2). Postgres holds identities and audit logs. v5.11.0 also tightens connection-string parsing to match libpq. Supersedes `upgrade-pgx-5-11`.

## User stories
- AS a platform operator I WANT pgx at 5.11.0 SO THAT the platform stays secure and stable.

## Acceptance criteria (EARS)
- WHEN the service starts THE SYSTEM SHALL connect to Postgres with the existing DSN.
- WHEN identity and audit queries run THE SYSTEM SHALL return the same results as before the upgrade.
- IF the DSN is parsed differently under libpq rules THEN THE SYSTEM SHALL fail fast at startup with a clear error.
- WHILE the pool is under load THE SYSTEM SHALL honour the configured MaxConns.

## Out of scope
- Unrelated dependency bumps and API changes.
