# Design: sqlite-v150-upgrade

## Current state

`mctl-agent` imports `modernc.org/sqlite v1.34` (see `context/architecture.md`). This version was released in early 2025 and bundles a SQLite version older than 3.50.2. The library provides a pure-Go, CGO-free SQLite implementation used for two internal stores:

- **Tickets DB** — stores alert ticket state (open, in-progress, resolved) and fix PR references.
- **Skill metrics** — stores per-skill success/failure counts consumed by the circuit breaker.

CVE-2025-6965 describes a buffer overflow in SQLite < 3.50.2 triggered when the number of aggregate terms in a query exceeds the number of available columns. In `mctl-agent`'s single-process Kubernetes pod architecture, a crafted SQL query (whether from an alert payload interpolated into a query or from an upstream skill bug) could corrupt the Go heap and cause undefined behaviour.

## Proposed solution

**Bump `go.mod` from `modernc.org/sqlite v1.34` to `modernc.org/sqlite v1.50.0`.**

`modernc.org/sqlite` v1.50.0 (released 2026-04-24) bundles SQLite ≥ 3.50.x, which includes the fix for CVE-2025-6965. The v1.50.0 release also introduces a `ColumnInfo` struct for richer introspection but makes no changes to the existing query or connection APIs.

No query rewrites or schema migrations are required. The upgrade is a pure `go.mod`/`go.sum` change followed by a rebuild.

### Verification approach

1. After the upgrade, call `SELECT sqlite_version()` in a startup diagnostic and log the result at `INFO` level. This gives an auditable confirmation that the bundled SQLite is ≥ 3.50.2 in every deployed pod.
2. Run the existing table-driven skill tests (mandatory per `context/architecture.md`) — they exercise the tickets and skill-metrics DB paths and will catch any silent behavioural regression.

## Alternatives

1. **Stay on v1.34 and add input validation to prevent crafted aggregates** — Rejected: defense-in-depth is good, but patching the underlying CVE is the correct primary remediation; input validation alone cannot cover all code paths through SQLite's aggregate machinery.
2. **Switch to Postgres** — Explicitly prohibited by `context/architecture.md` ("single-pod design, SQLite is fine") and the `What NOT to do` section.
3. **Use the system SQLite via CGO** — Rejected: `modernc.org/sqlite` was chosen specifically to eliminate CGO (no system library dependency in the container image). Reverting to CGO increases image complexity and breaks the pure-Go build.

## Platform impact

- **Migrations:** None. Schema is unchanged between v1.34 and v1.50.0.
- **Backward compatibility:** `modernc.org/sqlite` maintains a stable Go API. All existing query code compiles without changes.
- **Resource impact for `labs`:** None. The SQLite store is local to the `admins`-tenant `mctl-agent` pod. No cross-tenant memory or CPU impact.
- **Risks:**
  - *Risk*: A subtle behavioural change in SQLite 3.50.x alters query results → *Mitigation*: The existing table-driven DB tests cover the full ticket and skill-metrics lifecycle; a staging deployment before production rollout is standard practice.
  - *Risk*: `modernc.org/sqlite` v1.50.0 introduced a regression in the `ColumnInfo` API that affects build → *Mitigation*: The new struct is additive; existing code does not reference it and will not be impacted.
