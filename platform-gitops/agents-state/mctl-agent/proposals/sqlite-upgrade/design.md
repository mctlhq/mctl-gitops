# Design: sqlite-upgrade

## Current state
mctl-agent uses `modernc.org/sqlite v1.34` (see `context/architecture.md`: "pure Go SQLite (no CGO) for tickets DB and skill metrics"). `modernc.org/sqlite` is chosen specifically because it requires no CGO, making cross-compilation and container builds straightforward. The library is a transpiled version of the upstream SQLite C source; CVE-2025-70873 (heap info disclosure in the `zipfileInflate` function) is present in the transpiled code in v1.34 and fixed in the upstream SQLite version bundled with v1.50.0.

## Proposed solution
Update `go.mod` to declare `modernc.org/sqlite v1.50.0`. Run `go mod tidy`. The public API of `modernc.org/sqlite` is stable across this range — the upgrade adds the new `ColumnInfo` type but does not remove or change existing functions. The tickets DB and skill-metrics schema remain unchanged.

**Migration check:** run the existing table-driven SQLite tests (referenced in `context/architecture.md`: "All Go skills — table-driven tests") against v1.50.0 to confirm no behavioural regression. Run the benchmark suite to verify read/write latency is within ±10 %.

**Why modernc.org/sqlite (not mattn/go-sqlite3)?**
The architecture explicitly calls for pure-Go SQLite (no CGO). This is a hard constraint — the existing choice is correct and is not re-evaluated here.

**Why not upgrade to the absolute latest?**
v1.50.0 is the latest as of 2026-04-24 (confirmed via pkg.go.dev). This is the target version.

## Alternatives

### A. Stay on v1.34, accept CVE risk
The zipfile extension is not called by mctl-agent today, so exploitation requires a future code change that introduces ZIP processing. The risk is low but non-zero. Rejected — a module bump is trivial and eliminates the risk permanently.

### B. Switch to mattn/go-sqlite3
Requires CGO, complicates cross-compilation and container layer caching, contradicts the explicit architecture decision in `context/architecture.md`. Rejected.

### C. Switch to an in-process key-value store (e.g., bbolt)
Eliminates SQLite entirely and the CVE with it. However, this is a significant refactor of the tickets DB schema and the skill-metrics queries, and the architecture.md note ("switching SQLite to Postgres — single-pod design, SQLite is fine") implies the data model is intentionally relational. Rejected — out of scope.

## Platform impact

### Migrations
No schema changes. The existing SQLite database file format is compatible across this version range. The upgrade is transparent to existing deployments.

### Backward compatibility
The `modernc.org/sqlite` Go API is stable. The new `ColumnInfo` struct is additive; no existing call sites are affected.

### Resource impact
`modernc.org/sqlite` v1.50.0 is a pure-Go library; memory and CPU behaviour is expected to be equivalent to v1.34. No impact on memory quotas in either `admins` or `labs`. **No risk to `labs` tenant.**

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|---|---|---|
| Behavioural change in a SQLite function between v1.34 and v1.50 | Low | Run full table-driven test suite; include benchmark regression check |
| Database file corruption on first open | Very Low | Test against a copy of the production schema in CI |
| Transitive dependency conflict with another module | Very Low | Review `go mod tidy` output and `go.sum` diff |
