# Design: modernc-sqlite-v1620-wal-hardening

## Current state
`modernc.org/sqlite` 1.34, pure Go (no CGO), used for the tickets DB and skill metrics in a single-pod `admins` deployment (see `context/architecture.md`). SQLite stays by design. Earlier proposals (`modernc-sqlite-upgrade`, `sqlite-upgrade`, `sqlite-v150-upgrade`, `sqlite-cve-patch`, `sqlite-stack-dependency-update`, `sqlite-zipfile-cve-audit`) cover older targets; the newest, `modernc-sqlite-upgrade`, targets v1.61.1.

## Proposed solution
1. Check the status of `modernc-sqlite-upgrade`. If not yet implemented, apply its plan with target v1.62.0 and add the steps below. If implemented at v1.61.1, do only the bump to v1.62.0 plus the validation here.
2. Confirm v1.62.0 release notes, SQLite 3.54.1, and its minimum Go version versus the current toolchain (sequence after `go-1274-nethttp-maxbytes-patch` if needed).
3. Snapshot the DB files (main, `-wal`, `-shm`) from the PVC before the change.
4. On a copy: open with the new driver, run `PRAGMA integrity_check`, `PRAGMA journal_mode` (must equal the current mode), `PRAGMA wal_checkpoint(TRUNCATE)`, then the test suite and a replay of typical queries.
5. Startup guard: run `PRAGMA quick_check` when opening the DB. On failure, log and exit rather than serve from a suspect file. This is a small addition, and a bad file already needs manual restore.
6. Measure RSS and latency before and after in staging or `admins`; set the threshold (for example +10% RSS) before rollout.
7. Roll out through ArgoCD to `admins` only.

## Alternatives
- Stay on 1.34: leaves two CVEs and 28 versions of drift; rejected.
- Stop at v1.61.1 (as in `modernc-sqlite-upgrade`): it embeds SQLite 3.53.x per the CVE data and lacks the 3.54.0 fix for CVE-2026-119591; rejected.
- CGO `mattn/go-sqlite3`: brings back CGO and build complexity; rejected.
- Step through intermediate versions: more churn; only used if the direct jump fails tests.

## Platform impact
- Migrations: no schema change. The on-disk format is SQLite-stable. Rolling back the driver can read the file as long as no new features or pragmas were enabled; this change does not change them.
- Backward compatibility: possible differences in error text, type affinity or pragma defaults across 1.34 to 1.62; covered by tests on the DB copy.
- Resource impact: the pure-Go footprint and binary size may grow, so measure RSS before rollout. The agent runs in `admins`, so there is no direct `labs` impact. FLAG: if any shared tooling or image used in `labs` embeds this driver, treat the change as risky for `labs` (near its memory limit) and measure first. The startup `quick_check` adds a short read pass at start; negligible for a small DB.
- Risks and mitigations: data loss (snapshot, integrity check, restore test); new error paths (tests); Go minimum version mismatch (sequence after toolchain bump); overlap with the unfinished earlier proposal (check status first and supersede it).
