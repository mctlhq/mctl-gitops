# Design: pgx-critical-memory-safety-cve

## Current state
Per `context/architecture.md`, mctl-api uses `pgx/v5 5.8` as its sole Postgres driver, serving two
workloads: tenant identity reads/writes and audit-log appends. A `pgxpool` connection pool is
configured at startup and shared across request goroutines. Three CVEs apply to the pinned
version: CVE-2026-33815 (CWE-129, improper array index validation), CVE-2026-33816 (CWE-697,
incorrect comparison) — both fixed in 5.9.0 — and CVE-2026-41889 (SQL injection via dollar-quoted
placeholder confusion under the simple protocol) — fixed in 5.9.2. A prior proposal,
`proposals/pgx-upgrade-v592`, already scoped the first two CVEs but was never merged (no
`.status.yaml` present).

## Proposed solution
Bump the single direct `go.mod` entry for `github.com/jackc/pgx/v5` from `v5.8.x` to `v5.9.2`, run
`go mod tidy`, and re-vendor `go.sum`. Per pgx v5's semver guarantees, no application-code changes
are expected across a minor-version bump; all call-sites should compile unmodified. As part of
this same change, audit every call-site that issues raw SQL with dollar-quoted string literals to
confirm mctl-api uses the extended (parameterized) query protocol exclusively — this is the
condition under which CVE-2026-41889 does not apply even pre-upgrade, and the upgrade closes the
gap regardless. After the bump: run `govulncheck ./...` (expect zero findings for the three CVE
IDs) and the full Postgres integration suite.

This proposal explicitly takes over the scope of `proposals/pgx-upgrade-v592` — same target
version, same mechanism — and adds CVE-2026-41889 to its acceptance criteria. Rather than
duplicating a parallel draft, the recommendation is to merge this proposal (or fast-track the
existing one with CVE-2026-41889 added) and mark `pgx-upgrade-v592` as superseded.

## Alternatives
1. **Wait for a scheduled maintenance window.** Rejected — CVSS 9.8 memory-safety CVEs on the sole
   Postgres driver behind identity and audit-log data is not deferrable.
2. **Upgrade past 5.9.2 to whatever is latest (5.10.0 per this cycle's researcher findings).**
   Considered but rejected for this proposal: 5.9.2 is the precise, minimal fix target for all
   three CVEs; jumping further introduces unreviewed surface area. A follow-up version-currency
   proposal can track 5.10.0 separately once 5.9.2 has landed and soaked.
3. **Replace pgx with `database/sql` + `lib/pq` or an ORM.** Explicitly rejected per
   `context/architecture.md` — loses query control mctl-api depends on.

## Platform impact
- **Migrations:** None. No schema changes.
- **Backward compatibility:** pgx v5 minor-version bumps preserve API compatibility; verified by
  compile + integration tests. No client-facing API changes.
- **Resource impact:** Negligible; no measurable change to memory/CPU footprint expected from a
  driver patch bump. mctl-api runs only in the `admins` tenant — **no `labs` resource impact**.
- **Risks and mitigations:**
  - Risk: minor API surface changes between 5.8 and 5.9 break a call-site. Mitigation: CI compile
    + full integration test suite before merge.
  - Risk: CVE-2026-41889's simple-protocol trigger condition is present somewhere unaudited.
    Mitigation: explicit call-site audit task (see `tasks.md`) before declaring the CVE closed.
  - Risk: this proposal and `pgx-upgrade-v592` both merge independently, causing conflicting
    `go.mod` edits. Mitigation: explicitly note supersession in both proposals' review notes.
