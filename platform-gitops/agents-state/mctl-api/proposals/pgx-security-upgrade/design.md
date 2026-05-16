# Design: pgx-security-upgrade

## Current state
mctl-api imports `github.com/jackc/pgx/v5` at v5.8 (see `context/architecture.md`). The driver
uses the extended protocol (default) for all queries. The Postgres connection pool is tuned for
the `admins` tenant; connection pool configuration lives in the service config layer. No ORM
is used — raw SQL with pgx (by architectural decision, `context/architecture.md`).

## Proposed solution
Bump `github.com/jackc/pgx/v5` from v5.8 to v5.9.2 in `go.mod` / `go.sum`. This is an in-place
patch that targets the exact release that closes CVE-2026-41889.

**Why v5.9.2 and not v5.9.0 or v5.9.1?**
v5.9.2 is the first release to fully close CVE-2026-41889; v5.9.0 introduced the vulnerability
surface by expanding simple-protocol parsing, and v5.9.1 only partially addressed it.

**Protocol note:** mctl-api does not use the simple protocol (non-default). However:
1. The CVE affects simple-protocol paths that may be reachable via pgx internals under certain
   query patterns (COPY, batch fallback).
2. CVE-2026-33816 (memory-safety, no fix yet) is partially mitigated by upgrading to the latest
   patch release, which typically incorporates memory-handling improvements from upstream.

**Migration path:**
1. `go get github.com/jackc/pgx/v5@v5.9.2`
2. `go mod tidy`
3. Review the v5.9.0 release notes for any behavior changes affecting connection pool options.
4. Run integration tests; validate connection pool stability.

No query rewrites are expected. v5.9.x maintains backward compatibility with v5.8 for the
extended-protocol API surface mctl-api uses.

## Alternatives

### Stay on v5.8 until CVE-2026-33816 has a confirmed patch
Risk: CVE-2026-41889 remains open on a service that handles multi-tenant audit writes. Rejected —
the SQL injection vector is too high-impact even if the simple protocol is non-default.

### Upgrade to pgx v6.x
Does not exist at time of writing. Rejected — speculative.

### Replace pgx with database/sql + lib/pq
Rejected explicitly in `context/architecture.md`: we lose prepared-statement control, COPY
support, and pgx's type system.

## Platform impact
- **Migrations:** None. No schema changes. No data migrations.
- **Backward compatibility:** v5.9.2 is a drop-in replacement for v5.8 on the extended protocol.
- **Resource impact:** Negligible change in binary size and memory footprint. No `labs` tenant
  impact (mctl-api runs in `admins`).
- **Risks and mitigations:**
  - Risk: v5.9.0 added new features (SCRAM-SHA-256-PLUS, OAuth auth, protocol 3.2) that may
    change handshake behavior with the production Postgres instance. Mitigation: staging
    integration test before rolling to production.
  - Risk: v5.9.2 changelog mentions connection reset behavior changes. Mitigation: 24-hour
    pool stability observation window in staging before prod promotion.
