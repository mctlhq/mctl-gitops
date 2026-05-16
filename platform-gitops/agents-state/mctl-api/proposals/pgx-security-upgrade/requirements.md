# pgx-security-upgrade: Upgrade pgx from v5.8 to v5.9.2

## Context
mctl-api uses `github.com/jackc/pgx/v5` (currently v5.8) as its sole Postgres driver for identity
storage and audit-log writes. CVE-2026-41889 (CWE-89, CVSS 4.0) discloses a SQL-injection
vulnerability triggered when the non-default simple protocol is combined with dollar-quoted string
literals and attacker-controlled input. A second open advisory, CVE-2026-33816, identifies a
memory-safety issue in pgx v5 with no confirmed fixed version yet; upgrading to v5.9.2 is the
closest available mitigation.

v5.9.2 is backward-compatible with v5.8 in the standard extended protocol. The upgrade also brings
SCRAM-SHA-256-PLUS, OAuth authentication, and PostgreSQL protocol 3.2 support (v5.9.0) as
non-breaking additions.

## User stories
- AS a platform security engineer I WANT pgx upgraded to v5.9.2 SO THAT the SQL-injection vector
  described in CVE-2026-41889 is eliminated from the mctl-api attack surface.
- AS a platform engineer I WANT pgx upgraded SO THAT any memory-safety issues tracked under
  CVE-2026-33816 are mitigated to the extent that the patched release allows.
- AS a developer I WANT the upgrade to be drop-in SO THAT no query-layer refactoring is required.

## Acceptance criteria (EARS)
- WHEN mctl-api starts, THE SYSTEM SHALL import `github.com/jackc/pgx/v5` at version v5.9.2 or
  higher, as verified by `go list -m github.com/jackc/pgx/v5`.
- WHEN a query is executed via the default extended protocol, THE SYSTEM SHALL behave identically
  to the v5.8 implementation for all existing query patterns.
- WHEN a query is executed via the simple protocol with dollar-quoted string literals, THE SYSTEM
  SHALL not be susceptible to the placeholder-confusion injection described in CVE-2026-41889.
- WHILE mctl-api is running after the upgrade, THE SYSTEM SHALL maintain Postgres connection pool
  stability with zero unexpected connection drops over a 24-hour observation window.
- IF the v5.9.2 module checksum does not match the Go checksum database, THEN THE SYSTEM SHALL
  refuse to build and surface a clear error.
- WHEN the CI pipeline runs, THE SYSTEM SHALL pass all existing database integration tests without
  modification.

## Out of scope
- Switching from the extended protocol to the simple protocol (not recommended; increases risk).
- Migrating to an ORM such as gorm (explicitly rejected in `context/architecture.md`).
- Enabling OAuth authentication for Postgres (v5.9.0 feature) — separate proposal if needed.
- Upgrading to pgx v6.x (does not exist at time of writing; would be a breaking major bump).
