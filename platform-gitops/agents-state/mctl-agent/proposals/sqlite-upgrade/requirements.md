# SQLite Upgrade: modernc.org/sqlite v1.34 → v1.50.0

## Context
mctl-agent uses `modernc.org/sqlite` at v1.34 as its embedded database for the tickets DB and skill metrics. `modernc.org/sqlite` is a pure-Go port of the upstream SQLite C library achieved via automated C-to-Go transpilation, which means it inherits all upstream SQLite vulnerabilities.

CVE-2025-70873 (CVSS 7.5 High) is a heap information disclosure in SQLite's zipfile extension: the `zipfileInflate` function allows an attacker to read heap memory by supplying a crafted ZIP archive. While mctl-agent's current workload does not process ZIP files, the vulnerable code is present in the compiled binary. The v1.50.0 upgrade incorporates upstream patches for this CVE and covers 16 additional minor releases of bug fixes. It also adds the `ColumnInfo` API, which exposes richer schema metadata and may be useful for future diagnostic tooling.

## User stories
- AS a security auditor I WANT the SQLite binary in mctl-agent to be free of known CVEs SO THAT vulnerability scans pass.
- AS a platform engineer I WANT to upgrade modernc.org/sqlite to v1.50.0 SO THAT all upstream SQLite fixes from the past 16 minor releases are included.
- AS a developer I WANT access to the `ColumnInfo` API SO THAT future schema inspection tooling can be built without a further upgrade.

## Acceptance criteria (EARS)
- WHEN `go.mod` is updated, THE SYSTEM SHALL declare `modernc.org/sqlite v1.50.0` or later.
- WHEN `govulncheck` and dependency scanners are run, THE SYSTEM SHALL report no findings for CVE-2025-70873.
- WHEN mctl-agent starts, THE SYSTEM SHALL open and migrate the tickets database without error.
- WHEN the skill-metrics store is read or written, THE SYSTEM SHALL return correct results matching the schema defined in `internal/`.
- IF any existing table-driven test for SQLite interactions fails after the upgrade, THE SYSTEM SHALL have that test fixed before merge.
- WHILE mctl-agent is processing tickets, THE SYSTEM SHALL exhibit no regression in database read/write latency compared to v1.34 (within 10 % on the existing benchmark suite).

## Out of scope
- Switching from SQLite to any other database engine (rejected in architecture.md — single-pod design, SQLite is the correct fit).
- Using the new `ColumnInfo` API in this proposal (exploratory use is a follow-on task).
- Changes to the tickets or skill-metrics schemas.
