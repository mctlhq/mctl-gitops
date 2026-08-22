# Design: sqlite-stack-dependency-update

## Current state
Per `context/architecture.md`, mctl-agent uses `modernc.org/sqlite
1.34` (pure Go, no CGO) as the storage engine for the tickets DB and
skill-metrics store, in a single-pod design in tenant `admins`. The
transitive dependency `modernc.org/libc` is pulled in at whatever
version `modernc.org/sqlite` 1.34 required — reported as v1.41.0 in the
CVE advisory for CVE-2025-26519. No ADR in `context/decisions/`
addresses the SQLite version specifically; `architecture.md`'s "What
NOT to do" section only forbids switching the engine away from SQLite,
which this proposal does not do.

## Proposed solution
1. Bump `modernc.org/sqlite` from 1.34 to 1.57.0 in `go.mod`/`go.sum`
   via `go get modernc.org/sqlite@v1.57.0 && go mod tidy`, which will
   transitively pull a current `modernc.org/libc` release past
   v1.41.0 (closing CVE-2025-26519).
2. Independently verify CVE-2026-50812 before citing it as a fix
   delivered by this bump:
   - Check sqlite.org/cves.html (or the upstream SQLite/modernc.org
     issue tracker) for CVE-2026-50812 or the equivalent upstream
     commit reference (`ext/session/sqlite3session.c`, commit
     b869ed6b).
   - Check whether mctl-agent's codebase touches the SQLite Session
     Extension at all (grep for `sqlite3session` / session-extension
     bindings). If unused, the CVE is not exploitable in mctl-agent
     regardless of its authenticity, and this is recorded as the
     closure for the verification task.
   - Document the verification outcome (confirmed real / confirmed
     fabricated / inconclusive) in the task log rather than asserting
     either way without evidence.
3. Run the full tickets-DB and skill-metrics-store test suite against
   the upgraded driver, including a directed regression pass on
   read/write/migration paths (open DB file, insert ticket, query
   ticket, update skill-metrics counters) to confirm the driver bump
   introduces no on-disk-format or query-behavior regressions.
4. No schema changes; `go.mod`/`go.sum` and, if the Session Extension
   audit surfaces active usage requiring a workaround, the relevant
   data-access code are the only files touched.

## Alternatives
1. **Update only `modernc.org/libc` transitively via `go mod tidy`
   without bumping `modernc.org/sqlite`.** Rejected: `go.mod`'s
   `require` graph pins libc through sqlite's own `go.mod`; the way to
   reliably get a fixed libc version is to bump sqlite itself, since
   otherwise `go mod tidy` may retain the older libc requirement
   declared by sqlite 1.34.
2. **Treat CVE-2026-50812 as confirmed and lead with it as the primary
   driver.** Rejected: per the inbox rationale, 54/55 recent advisories
   from the same reporting account are suspected fabricated; leading
   with an unverified claim would misrepresent the proposal's actual
   justification. CVE-2025-26519 alone is sufficient and independently
   sourced.
3. **Defer the update until CVE-2026-50812 is fully resolved
   one way or the other.** Rejected: CVE-2025-26519 (libc, CVSS 8.1) is
   independent of that question and already justifies moving now; no
   reason to block a clearly beneficial bump on an unrelated
   uncertainty.

## Platform impact
- **Migrations:** none. Same on-disk SQLite file format (modernc.org/sqlite
  targets standard SQLite file compatibility across this version range);
  no schema or migration script changes.
- **Backward compatibility:** fully compatible — existing tickets DB
  and skill-metrics store files continue to work unchanged; this is a
  pure Go dependency bump with no CGO implications, consistent with
  the existing "no CGO" architecture constraint.
- **Resource impact (tenant `labs`):** none — this proposal is scoped
  entirely to the `admins`-tenant mctl-agent binary's SQLite driver and
  does not touch `labs` in any way, so it carries no risk to `labs`'s
  memory headroom, which is already close to its limit per platform
  notes.
- **Resource impact (tenant `admins`):** expected to be neutral; newer
  modernc.org/sqlite releases have historically been performance-
  neutral-to-positive relative to older ones for typical read/write
  workloads. Current `admins` tenant usage (3200Mi/5Gi memory per
  latest metrics) has ample headroom regardless.
- **Risks and mitigations:**
  - *Risk:* a 20+ minor version jump in a pure-Go SQLite implementation
    could carry subtle query-behavior or on-disk-format differences.
    *Mitigation:* directed regression tests on read/write/migration
    paths (task 3) before merge; deploy is a straightforward binary
    swap with immediate rollback available (no data-layer changes
    required to revert).
  - *Risk:* citing CVE-2026-50812 as "fixed" without verification could
    misrepresent the security posture. *Mitigation:* explicit
    verification task with a documented, evidence-based outcome
    regardless of which way it resolves.
  - *Risk:* CVE-2025-26519 detail (exact affected libc version range)
    is not independently re-confirmed beyond the inbox's summary.
    *Mitigation:* task 1 below includes checking the resolved
    `modernc.org/libc` version after `go mod tidy` against the
    known-affected v1.41.0 to confirm the fix is actually picked up.
