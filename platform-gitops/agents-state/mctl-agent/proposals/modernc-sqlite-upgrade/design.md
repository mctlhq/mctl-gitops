# Design: modernc-sqlite-upgrade

## Current state
`modernc.org/sqlite` 1.34, pure Go, no CGO, used for the tickets DB and skill metrics in a single-pod deployment (see `context/architecture.md`). The pin is about 27 minor versions behind v1.61.1.

## Proposed solution
1. Verify: read release notes/tags 1.35 to 1.61.1, confirm the minimum Go version required (it may exceed 1.24; if so, sequence after go-toolchain-bump), and confirm the latest tag.
2. Upgrade the dependency in `go.mod` to v1.61.1 and run `go mod tidy`.
3. Test on a copy: restore a copy of the tickets and skill-metrics DB files, run `PRAGMA integrity_check`, run the test suite and a replay of typical queries.
4. Context handling: audit DB call sites; use `...Context` variants (`ExecContext`, `QueryContext`) so request/pipeline contexts propagate and the 1.61.0 busy-wait cancellation takes effect. Make sure context errors are handled without state corruption.
5. Measure RSS and latency before and after in staging or `admins`; roll out through ArgoCD only if within thresholds.

Rationale: a single bump of the driver, gated by tests on real data copies, keeps the accepted SQLite design while gaining the engine and context fixes.

## Alternatives
- Stay at 1.34: no risk now, but accrues drift and misses SQLite engine fixes; rejected.
- Step through intermediate versions: safer bisecting but more churn; used only if the direct jump fails tests.
- Move to CGO `mattn/go-sqlite3`: reintroduces CGO and build complexity; rejected.

## Platform impact
- Migrations: none to schema; the on-disk file format is SQLite-stable, but take a backup copy of the DB files before rollout.
- Backward compatibility: possible behavior differences in error text/codes, type affinity or pragma defaults between 1.34 and 1.61; covered by tests on a DB copy. Rolling back to the old driver can read the DB as long as no new SQLite features (such as a changed journal mode) were enabled; do not change pragmas in this change.
- Resource impact: the agent runs in `admins`, so there is no direct `labs` impact. Pure-Go footprint may change, so a memory check precedes rollout.
- Risks and mitigations: context cancellation surfacing new error paths (handle and test); Go minimum version mismatch (sequence after toolchain bump if needed); data safety (backup and integrity check).
