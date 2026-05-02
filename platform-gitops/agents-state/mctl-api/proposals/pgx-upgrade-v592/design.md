# Design: pgx-upgrade-v592

## Current state
mctl-api v4.14.0 uses `github.com/jackc/pgx/v5` at 5.8.x as its sole Postgres driver (see `context/architecture.md`). The driver is used for two workloads: serving tenant data reads/writes and appending audit log records. A pgxpool connection pool is configured at startup and shared across all request goroutines. Three CVEs are present in the currently pinned version: CVE-2025-54236 (SQL injection via placeholder confusion), CVE-2026-33815 (improper array index validation, CWE-129), and CVE-2026-33816 (incorrect comparison, CWE-697).

## Proposed solution
Bump the single direct dependency entry in `go.mod` from `github.com/jackc/pgx/v5 v5.8.x` to `github.com/jackc/pgx/v5 v5.9.2`, then run `go mod tidy` to update `go.sum` and prune transitive entries. No application code changes are anticipated because pgx v5 semantic versioning guarantees API stability across minor releases; all existing call-sites are expected to compile without modification. After the bump, `govulncheck ./...` must report zero findings for the three CVE IDs, and the full integration test suite must pass against a Postgres instance to confirm query semantics are unchanged.

## Alternatives
1. Remain on v5.8 until a scheduled maintenance window — rejected: CVE-2025-54236 is a SQL injection vector; delay is unjustifiable.
2. Upgrade directly to latest pgx (if a v5.9.x+ exists beyond 5.9.2) — valid but 5.9.2 is the known fix target; go with the minimal safe bump.
3. Replace pgx with database/sql + lib/pq — explicitly rejected per architecture.md (loss of query control).

## Platform impact
- Migrations: none — no schema changes
- Backward compatibility: pgx v5 minor bumps maintain API compatibility; verify call-sites compile
- Resource impact: negligible; memory usage unchanged; no `labs` impact
- Risks: minor API signature changes between 5.8 and 5.9; mitigated by compile-time checks and integration tests
