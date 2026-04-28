# pgx SQL Injection and Memory-Safety Fix (pgx/v5 upgrade to v5.9.2)

## Context
mctl-api v4.14.0 depends on `jackc/pgx/v5 v5.8` as its sole Postgres driver for
identity storage and audit log writes. Four CVEs affect this version. The most
critical is GHSA-j88v-2chj-qfwx (CVE-2025-54236): when the simple protocol is
used, pgx misinterprets dollar-quoted string literals as numbered placeholders,
allowing an attacker who controls query input to inject arbitrary SQL. Because
mctl-api authorizes tenant scope at the application layer, a SQL-injection
bypass here is a direct cross-tenant data-leak vector.

The remaining three CVEs compound the risk: CVE-2026-4427 (pgproto3 panics on
a negative DataRow field length — exploitable for denial-of-service by a
malicious Postgres server or a man-in-the-middle), and CVE-2026-33815 /
CVE-2026-33816 (two memory-safety issues in pgx/v5 that can cause out-of-bounds
reads). All four are resolved in the single patch release `pgx/v5 v5.9.2`, which
the upstream maintainers describe as a security-only update with no API changes.

## User stories
- AS a platform security engineer I WANT the pgx driver pinned to v5.9.2 SO THAT
  no known SQL-injection or memory-safety vulnerability is present in production.
- AS a mctl-api developer I WANT the upgrade to be API-compatible SO THAT no
  query code or migration needs to be rewritten.
- AS an on-call SRE I WANT confidence that the service restarts cleanly after
  the upgrade SO THAT the blast radius of the rollout is limited to a brief
  pod restart.

## Acceptance criteria (EARS)
- WHEN the service starts THEN THE SYSTEM SHALL report `pgx/v5 v5.9.2` (or
  newer) in `go.sum` and via `go version -m` on the compiled binary.
- WHEN a query parameter contains a dollar-quoted string literal (e.g.,
  `$$injected$$`) THEN THE SYSTEM SHALL treat it as a safe string value and
  SHALL NOT execute any statement derived from its content.
- WHEN the Postgres server sends a DataRow message with a negative field length
  THEN THE SYSTEM SHALL close the connection and return an error to the caller
  rather than panicking.
- WHILE the service is processing Postgres responses THEN THE SYSTEM SHALL NOT
  perform out-of-bounds memory reads as defined by CVE-2026-33815 and
  CVE-2026-33816.
- WHEN the upgraded binary is deployed to the `admins` tenant THEN THE SYSTEM
  SHALL pass all existing integration tests against the real Postgres instance
  with no new failures.
- IF the deployment to `admins` fails a readiness probe within the configured
  timeout THEN THE SYSTEM SHALL be automatically rolled back by ArgoCD to the
  previous revision.

## Out of scope
- Switching from the simple protocol to the extended protocol beyond what v5.9.2
  already enforces by default (a separate tuning proposal may follow).
- Any changes to query logic, schema, or the pgx connection-pool configuration.
- Upgrading other dependencies (Go runtime, chi, mcp-go, client-go) — those are
  tracked in separate proposals.
- Backporting the fix to any version other than the current production branch.
- Changes to the `labs` tenant infrastructure (this proposal touches only the
  `admins`-tenant mctl-api binary).
