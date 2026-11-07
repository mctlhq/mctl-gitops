# Upgrade modernc.org/sqlite 1.34 to 1.61.x with context-aware busy timeout

## Context
The tickets DB and skill metrics use pure-Go `modernc.org/sqlite` pinned at 1.34. Upstream is at v1.61.1 (31 Oct). It includes SQLite engine updates up to 3.53.4 (v1.58.0), which picks up upstream SQLite fixes, and v1.61.0 stops busy-timeout waits when the call's context is done, which helps the ticket pipeline and webhook handlers avoid hanging on a locked DB. No CVE was found for this library, so priority is below the toolchain and chi items.

The accepted single-pod SQLite design stays; this is not a move to Postgres. Open items to verify: the actual current pin and behavior, that the DB files remain compatible after the upgrade, and that the pure-Go engine's memory footprint does not regress.

## User stories
- AS the mctl-agent owner I WANT a current SQLite driver SO THAT we get upstream engine fixes.
- AS an operator I WANT DB calls to stop waiting when the request context is cancelled SO THAT webhook handlers and the ticket pipeline do not hang on a locked DB.

## Acceptance criteria (EARS)
- WHEN the upgrade starts THE SYSTEM SHALL confirm the current pin in `go.mod` and that v1.61.1 is the latest tag on the upstream repo (gitlab.com/cznic/sqlite), and check the release notes between 1.34 and 1.61.1 for breaking changes.
- WHEN the driver is upgraded to 1.61.x THE SYSTEM SHALL open a copy of the production tickets and skill-metrics DBs and pass integrity checks (`PRAGMA integrity_check`) and the full test suite.
- WHEN a DB call is made with a context that is cancelled while waiting on a busy lock THE SYSTEM SHALL return promptly with a context error instead of waiting for the full busy timeout.
- IF a DB call returns a context error from a busy wait THEN THE SYSTEM SHALL handle it as a retryable or failed operation without corrupting ticket state, and without tripping the circuit breaker incorrectly.
- WHILE the upgraded build runs in `admins` THE SYSTEM SHALL keep RSS within 15% of the pre-upgrade baseline.
- IF the memory or compatibility check fails THEN THE SYSTEM SHALL NOT roll out and SHALL record the findings.
- WHEN the rollout completes THE SYSTEM SHALL keep schema and data unchanged (no migration required).

## Out of scope
- Switching to Postgres or any other DB (single-pod SQLite is the accepted design).
- Schema changes or new tables.
- Changing circuit breaker thresholds.
- Go toolchain and chi upgrades (separate proposals; note modernc versions may require a minimum Go version).
