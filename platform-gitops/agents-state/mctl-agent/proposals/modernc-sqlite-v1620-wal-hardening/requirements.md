# Upgrade modernc.org/sqlite 1.34 to v1.62.0 (SQLite 3.54.1) with WAL and migration validation

## Context
The pin `modernc.org/sqlite` 1.34 is about 28 minor versions behind v1.62.0 (tagged 2026-11-07, embeds SQLite 3.54.1). It misses CVE-2026-119591 (C-stack exhaustion on a crafted view, SQLite before 3.54.0) and CVE-2026-119375 (a crafted database with a WAL page-size mismatch can return uninitialized page-cache bytes). Exposure is limited because the tickets and skill-metrics DBs are local and single-pod, but a crafted or restored PVC file is a plausible vector. CVE-2026-11822 and CVE-2026-11824 need FTS5, DEFENSIVE off and attacker-controlled SQL, so they do not apply, but the same bump fixes them.

Existing proposals overlap: `modernc-sqlite-upgrade` (1.34 to v1.61.1, test on a DB copy, context-aware calls), `sqlite-upgrade`, `sqlite-v150-upgrade`, `sqlite-cve-patch`, `sqlite-stack-dependency-update`, `sqlite-zipfile-cve-audit`. This proposal only adds the target v1.62.0 / SQLite 3.54.1, the two new CVEs, and WAL-specific validation. If `modernc-sqlite-upgrade` is still open, retarget it to v1.62.0 rather than doing two bumps.

## User stories
- AS the service owner I WANT the SQLite engine on 3.54.1 SO THAT crafted database files cannot exhaust the stack or leak page-cache bytes.
- AS an operator I WANT a verified backup and restore test SO THAT the upgrade cannot lose ticket data.

## Acceptance criteria (EARS)
- WHEN the upgrade is prepared THE SYSTEM SHALL confirm v1.62.0 is the latest tag and that its minimum Go version is satisfied by the pinned toolchain.
- WHEN rollout starts THE SYSTEM SHALL first take a snapshot of the tickets and skill-metrics DB files, including `-wal` and `-shm` files.
- WHEN the new driver opens a copy of the production DB THE SYSTEM SHALL pass `PRAGMA integrity_check` and the full test suite.
- WHEN the DB is opened in WAL mode THE SYSTEM SHALL keep the same journal mode and pragmas as before (no pragma changes in this change), and a WAL checkpoint SHALL complete without error.
- IF a DB file fails `PRAGMA integrity_check` or has a WAL page-size mismatch at startup THEN THE SYSTEM SHALL refuse to use it, log the error, and not start serving from it.
- WHEN the new build runs THE SYSTEM SHALL have RSS no more than an agreed threshold above the pre-upgrade baseline (threshold set in task 5).
- WHILE the rollout is in progress THE SYSTEM SHALL keep the old image and the DB snapshot available for rollback.
- IF the SQLite code or binary is shared with a `labs` workload THEN THE SYSTEM SHALL not roll out there until its memory is measured, since `labs` is near its memory limit.

## Out of scope
- Moving to Postgres or any other database.
- Schema changes or pragma tuning.
- Context-propagation refactor of DB call sites beyond what `modernc-sqlite-upgrade` already specifies.
- FTS5 enablement.
