# Design: pgx-sql-injection-fix

## Current state
mctl-api v4.14.0 (Go 1.24, tenant `admins`) uses `jackc/pgx/v5 v5.8` as declared
in `go.mod`. The driver is used directly (no ORM, per the architecture decision
in `context/architecture.md`) for all Postgres operations: identity lookups and
audit-log writes. The simple protocol is in use for some query paths, which is
the attack surface described by CVE-2025-54236.

Four open CVEs exist against v5.8:
| CVE | Severity | Vector |
|-----|----------|--------|
| CVE-2025-54236 (GHSA-j88v-2chj-qfwx) | Critical | SQL injection via dollar-quoted literal / simple protocol |
| CVE-2026-4427 | High | Panic (DoS) on negative DataRow field length |
| CVE-2026-33815 | High | Out-of-bounds read in pgx/v5 |
| CVE-2026-33816 | High | Out-of-bounds read in pgx/v5 |

## Proposed solution
Bump the single dependency `jackc/pgx/v5` from `v5.8` to `v5.9.2` in `go.mod`
and regenerate `go.sum`. No code changes are required: v5.9.2 is a
security-patch release that preserves the public API of v5.8.

Steps:
1. Run `go get jackc/pgx/v5@v5.9.2` in the module root to update `go.mod` /
   `go.sum`.
2. Run `go mod tidy` to drop any now-unused indirect pins.
3. Rebuild the binary (`make build` or the existing CI target) and verify
   `go version -m ./bin/mctl-api` reports `pgx/v5 v5.9.2`.
4. Merge via normal PR → CI → GitOps flow; ArgoCD rolls out the new image to
   `admins`.

No database migrations, no API changes, no configuration changes are needed.

## Alternatives

**Option A — Pin only pgproto3 (partial fix)**
`pgproto3` can be pinned independently because it is a sub-module. This would
close CVE-2026-4427 without touching the pgx core, but CVE-2025-54236,
CVE-2026-33815, and CVE-2026-33816 would remain open. Rejected: incomplete
security posture for negligible extra effort saved.

**Option B — Switch to the extended (prepared-statement) protocol explicitly**
Forcing `PreferSimpleProtocol: false` in the pgx config would eliminate the
dollar-quoting attack surface without a library upgrade. However, this does not
address the three other CVEs, requires code review of all connection pool setup,
and is orthogonal to a version bump. Rejected for this proposal; may be pursued
as a defense-in-depth hardening in a follow-up.

**Option C — Replace pgx with database/sql + lib/pq**
`lib/pq` is in maintenance mode and does not have pgx's performance or
pgx-specific type support that the codebase already relies on. Rejected:
significant migration effort with no security benefit relative to the patch bump;
also inconsistent with the architecture decision against ORM/driver changes
without a strong benchmark.

## Platform impact

**Migrations:** None. v5.9.2 is API-compatible with v5.8.

**Backward compatibility:** The change is fully transparent to callers. All
existing REST endpoints, MCP tools, and audit-log writes continue to work
without modification.

**Resource impact:** The pgx/v5 v5.9.2 binary footprint is not materially
different from v5.8 (security patch only). No memory allocation patterns change.
The `labs` tenant does not run mctl-api and is therefore unaffected by this
change. No labs memory-limit risk.

**Risks and mitigations:**

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Subtle behavioral change in query encoding | Low | Full integration-test suite runs against real Postgres in CI |
| New indirect dependency introduced by `go mod tidy` | Very low | `go.sum` diff reviewed in PR; Dependabot / govulncheck added to CI |
| ArgoCD rollout causes a brief pod restart | Certain (expected) | Rolling update strategy with readiness probe; automatic rollback if probe fails |
| Patch release itself contains a regression | Very low | Upstream release notes confirm security-only scope; CHANGELOG reviewed |
