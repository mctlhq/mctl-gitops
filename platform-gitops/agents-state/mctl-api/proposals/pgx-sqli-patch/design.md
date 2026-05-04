# Design: pgx-sqli-patch

## Current state

As documented in `context/architecture.md`, mctl-api uses `github.com/jackc/pgx/v5` at **v5.8** as its Postgres driver. The database stores tenant identities and audit logs. Cross-tenant data leakage is the service's identified critical failure mode.

Two CVEs affect the v5.8 release series:

| CVE | Component | Class | Protocol condition |
|-----|-----------|-------|--------------------|
| CVE-2025-54236 / GHSA-j88v-2chj-qfwx | pgx query execution | SQL injection via dollar-quoted placeholder confusion | Simple query protocol only |
| CVE-2026-4427 | pgproto3 `DataRow.Decode` | DoS via negative field length | All protocols |

pgx uses the **extended (prepared-statement) protocol by default**. If mctl-api has not explicitly opted into `PreferSimpleProtocol: true` in its `pgxpool.Config` or per-connection `ConnConfig`, CVE-2025-54236 is not currently exploitable. However, this must be confirmed by code inspection and locked down via an ADR so future contributors cannot silently regress the posture.

CVE-2026-4427 affects all protocol modes. A malicious or compromised Postgres server (or a MITM attack on an unencrypted connection) could crash the driver's decode path, causing process-level panics or goroutine leaks in the connection pool.

## Proposed solution

**Bump `github.com/jackc/pgx/v5` from v5.8 to v5.9.2** in `go.mod` / `go.sum`, then rebuild and redeploy the service. No API changes are required: v5.9.2 is fully backward-compatible with v5.8 at the Go package level.

Steps:

1. Run `go get github.com/jackc/pgx/v5@v5.9.2` to update `go.mod` and `go.sum`. The sub-packages `pgconn`, `pgproto3`, and `pgtype` are part of the same module and will be updated atomically.
2. Audit every call-site that constructs a `pgxpool.Config` or `pgx.ConnConfig` and confirm `PreferSimpleProtocol` is `false` (the default) or absent. Record the result in a new ADR (`context/decisions/0002-pgx-query-protocol.md`).
3. Run the full test suite and `govulncheck ./...` locally and in CI.
4. Update the container image tag in the ArgoCD Application manifest. ArgoCD will perform a rolling replacement of the pod(s) in the `admins` namespace.

### Why a version bump is the right approach

pgx is imported directly, not through a wrapper. Forking or vendoring a patched v5.8 would add long-term maintenance burden with zero benefit, since v5.9.2 is a drop-in replacement. An in-process mitigation (e.g., allowlisting query strings) would be fragile and would not fix the DoS vector.

## Alternatives

### Option A: Vendor a backport patch against v5.8

Apply only the CVE fix commits to a local fork of v5.8. This avoids any risk of v5.9.x regressions, but introduces an untracked fork that must be manually kept in sync with upstream security advisories. The `context/architecture.md` constraint against losing control over the driver makes this worse, not better. Dropped.

### Option B: Wrap all database calls behind a query sanitizer

Intercept every query string before it reaches pgx and reject or escape dollar-quoted literals. This is both fragile (pgx's internal query generation could bypass a naive wrapper) and unnecessary (the vulnerability only manifests in simple protocol mode, which we likely do not use). It does not address CVE-2026-4427 at all. Dropped.

### Option C: Disable Postgres entirely and migrate to an in-process SQLite for local state

Eliminates the Postgres attack surface entirely but is architecturally incompatible with multi-tenant deployment and would require rewriting the identity and audit-log subsystems. Entirely out of scope. Dropped.

## Platform impact

### Migrations

None. The pgx wire protocol and Go API are unchanged between v5.8 and v5.9.2. No database schema changes are required.

### Backward compatibility

v5.9.2 introduces no breaking API changes. All existing query, pool, and type-mapping code compiles unchanged. New features (SCRAM-SHA-256-PLUS, OAuth for PostgreSQL 18, protocol 3.2) are additive opt-ins and are not activated by this proposal.

### Resource impact

The upgraded library binary is marginally larger due to additional feature code, but this is measured in kilobytes and is negligible relative to the mctl-api container image. No change to runtime memory allocation patterns is expected.

The `labs` tenant is not targeted by this service — mctl-api runs in `admins`. No impact on `labs` memory limits is expected. If the ArgoCD sync for `admins` triggers a rolling restart, the pod count and resource requests remain identical.

### Risks and mitigations

| Risk | Likelihood | Severity | Mitigation |
|------|-----------|----------|------------|
| v5.9.x introduces a latent regression in connection pool behaviour | Low | Medium | Full test suite + staging environment smoke test before ArgoCD sync to production |
| Simple protocol inadvertently enabled somewhere (exploit still possible until patch) | Low | Critical | Code audit in task 2 closes this; ADR locks it down permanently |
| Postgres connection errors during rolling restart | Very low | Low | Rolling update strategy in the Deployment spec ensures zero-downtime; `/metrics` baseline comparison post-deploy |
| govulncheck false-negative masks a related sub-package issue | Very low | Low | Pin to `v5.9.2` exactly in go.mod; Dependabot or equivalent watches for future advisories |
