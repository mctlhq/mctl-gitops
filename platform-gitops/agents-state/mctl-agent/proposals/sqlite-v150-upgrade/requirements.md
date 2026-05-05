# sqlite-v150-upgrade: Upgrade modernc.org/sqlite v1.34 → v1.50.0 (CVE-2025-6965 remediation)

## Context

`mctl-agent` uses `modernc.org/sqlite` — a pure-Go, CGO-free SQLite binding — to persist two data stores: the **tickets database** (alert lifecycle) and the **skill metrics store** (circuit breaker counters). The current pinned version is **v1.34**, which bundles a SQLite version older than 3.50.2.

**CVE-2025-6965** is a memory corruption (buffer overflow) vulnerability in SQLite versions prior to 3.50.2: when the number of aggregate terms in a query exceeds the number of available columns, an out-of-bounds write can occur. In a single-process deployment (Kubernetes pod), exploitation could corrupt in-process Go heap memory, leading to unpredictable behaviour in the skill dispatch pipeline or, in an adversarial scenario, possible code execution.

`modernc.org/sqlite` v1.50.0 (released 2026-04-24) bundles SQLite ≥ 3.50.x and resolves the CVE. The Go API is backward-compatible; no schema migration is required.

## User stories

- AS the `mctl-agent` service I WANT the SQLite engine to be free of known CVEs SO THAT the ticket and skill-metrics stores cannot be exploited via crafted SQL inputs.
- AS a platform security engineer I WANT the transitive SQLite version embedded in `mctl-agent` to be ≥ 3.50.2 SO THAT CVE-2025-6965 is not present in the deployed binary.
- AS a developer I WANT `modernc.org/sqlite` to be on a recent version SO THAT I benefit from upstream bug fixes and new introspection helpers (`ColumnInfo`).

## Acceptance criteria (EARS)

- WHEN `go.mod` is updated to `modernc.org/sqlite` v1.50.0 THE SYSTEM SHALL compile without errors.
- WHEN the compiled binary is inspected for the bundled SQLite version THE SYSTEM SHALL report a SQLite version ≥ 3.50.2.
- WHEN all existing ticket-lifecycle and skill-metrics integration tests are run against the upgraded library THE SYSTEM SHALL pass without modification.
- IF an aggregate SQL query is executed against the tickets or skill-metrics database THEN THE SYSTEM SHALL not exhibit memory corruption under CVE-2025-6965 triggering conditions.
- WHILE the upgrade is applied THE SYSTEM SHALL NOT require any database schema migration or data transformation.

## Out of scope

- Migrating from SQLite to any other database engine (explicitly prohibited per `context/architecture.md`).
- Changing the schema of the tickets or skill-metrics tables.
- Enabling WAL mode or other SQLite configuration changes (separate proposal if needed).
- Addressing CVE-2026-32767 or CVE-2026-33906 (unrelated SQLite-using Go applications, not `mctl-agent`).
