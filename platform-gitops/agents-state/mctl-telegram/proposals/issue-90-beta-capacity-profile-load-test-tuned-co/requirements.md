# Beta capacity profile: load test and tuned configuration defaults

## Context

`docs/hpa.md` documents per-pod memory estimates and TELEGRAM_MAX_SESSIONS
recommendations extrapolated from a 100-session benchmark. The capacity table
stops at 1 GiB pods and offers no guidance for the 2 GiB tier that Beta will
likely use. More importantly, the goal of up to ~1K concurrent users on a
single replica before scale-out has no measured saturation point, no committed
DB connection pool sizing, and no documented horizontal scale-out threshold.

This work produces: (1) a repeatable Go load-test binary in `test/load/` that
drives realistic MCP tool-call traffic against a staging deployment; (2)
committed benchmark results in `docs/load-test-beta.md` for 1 GiB and 2 GiB
pod sizes; (3) a Beta deployment profile (`deploy/profiles/beta.env`) with
tuned values for all key env vars; and (4) the missing DB pool env vars
(`DB_MAX_OPEN_CONNS`, `DB_MAX_IDLE_CONNS`) surfaced through
`internal/config/config.go` and consumed by `internal/db/db.go`.

## User stories

- AS a platform operator I WANT a load test binary I can run against staging
  SO THAT I can measure actual saturation points before promoting to Beta.
- AS a platform operator I WANT committed TELEGRAM_MAX_SESSIONS and DB pool
  values in a Beta env file SO THAT I have a validated starting configuration
  rather than extrapolated estimates.
- AS a platform operator I WANT documented horizontal scale-out thresholds
  SO THAT I can set HPA targets that keep p99 latency within SLOs at any
  pod count up to Beta's maximum.
- AS a developer I WANT DB_MAX_OPEN_CONNS and DB_MAX_IDLE_CONNS configurable
  via env vars SO THAT I can tune connection pool pressure without rebuilding
  the binary.

## Acceptance criteria (EARS)

- WHEN the load test binary is invoked with `-users N -ramp D -hold D
  -target URL -tokens FILE -peer PEER`, THE SYSTEM SHALL start N virtual-user
  goroutines, ramp to full concurrency over D, sustain for D, then produce a
  report covering per-tool throughput, p50/p95/p99 latency, error rate, peak
  pool size, peak goroutine count, peak RSS (derived from the target's
  /metrics scrape), and FLOOD_WAIT event count.
- WHEN a virtual user selects its next tool call, THE SYSTEM SHALL apply the
  70/25/5 mix (list_dialogs / get_messages / prepare_send_message+send_message
  dry-run) using weighted random selection seeded independently per goroutine.
- WHEN send_message is called in the load test, THE SYSTEM SHALL always omit
  mode="send" so the call remains a draft and no message is delivered to any
  real Telegram peer.
- WHILE the hold phase is active, THE SYSTEM SHALL scrape the target's
  /metrics endpoint at most every 5 seconds and track peak values of
  mctl_telegram_client_pool_size, mctl_sessions_active,
  process_resident_memory_bytes, and go_goroutines for the final report.
- WHEN DB_MAX_OPEN_CONNS is set to a non-zero integer, THE SYSTEM SHALL apply
  it as the Postgres SetMaxOpenConns limit in place of the hardcoded value of
  10 at internal/db/db.go:37.
- WHEN DB_MAX_IDLE_CONNS is set to a non-zero integer, THE SYSTEM SHALL apply
  it as the Postgres SetMaxIdleConns limit in place of the hardcoded value of
  2 at internal/db/db.go:38.
- IF DB_MAX_OPEN_CONNS or DB_MAX_IDLE_CONNS is unset or 0, THEN THE SYSTEM
  SHALL apply the current defaults (10 open / 2 idle for Postgres;
  1 open for SQLite) to preserve existing behavior.
- WHEN deploy/profiles/beta.env is sourced, THE SYSTEM SHALL receive tuned
  values for TELEGRAM_MAX_SESSIONS, IDLE_CLIENT_TIMEOUT, RATE_LIMIT_PER_USER,
  DB_MAX_OPEN_CONNS, DB_MAX_IDLE_CONNS, OAUTH_ACCESS_TOKEN_TTL,
  OAUTH_REFRESH_TOKEN_TTL, and AUDIT_RETENTION_DAYS derived from the
  load-test results for the 2 GiB pod tier.
- WHEN docs/load-test-beta.md is committed, THE SYSTEM SHALL contain: the
  saturation point (max sessions before p99 > 2 s or error rate > 1%) for
  each of the 1 GiB and 2 GiB pod tiers; a memory growth curve; DB connection
  pool pressure data (idle vs in-use over the hold phase); and FLOOD_WAIT
  event counts per tool.
- WHEN docs/hpa.md is updated, THE SYSTEM SHALL document the Beta scale-out
  trigger threshold (pool utilization fraction) tied to the SLOs from
  issue #88 and include the 2 GiB tier row in the capacity table.

## Out of scope

- Live (non-dry-run) Telegram message sending during load tests.
- Load testing the Local Bridge path (mode=local in telegram_accounts).
- Provisioning Telegram test accounts; the implementer uses existing
  canary account(s) from issue #89.
- Changes to Kubernetes HPA or Prometheus Adapter manifests; those live
  in mctl-gitops.
- SQLite pool tuning; SQLite uses a single-writer model (MaxOpenConns=1)
  and is not the production backend for Beta.
- Load testing the OAuth authorization flow; the test pre-authenticates
  once per virtual user before the ramp phase begins.

## Open questions

1. **Test-account pool size**: The issue requests "N concurrent users, each
   performing a representative tool mix" but also says "use the same canary
   account as #89 if convenient." A single Telegram session produces a single
   ClientPool entry; all N goroutines share it via Borrow() and the
   TELEGRAM_MAX_SESSIONS cap is never approached. This does not simulate
   N-user pool pressure. Clarify whether the test must provision N distinct
   Telegram sessions (requiring N test accounts) or whether a single canary
   session is acceptable with the understanding that pool saturation is not
   being measured. This proposal assumes N distinct sessions are required for
   an accurate pool saturation measurement and notes that caveat in the
   load-test results if only one account is available.

2. **SLO thresholds from issue #88**: The acceptance criterion for saturation
   (p99 > 2 s or error rate > 1%) is a placeholder. The implementer must
   align these thresholds with whatever #88 commits; the beta.env scale-out
   trigger must reference the same numbers.

3. **Test peer for get_messages**: The get_messages tool requires a non-empty
   peer argument. The canary account must have access to a reachable peer (a
   user, group, or channel). The specific peer should be configurable via the
   -peer flag rather than hardcoded; its value must be documented in the
   load-test results.

4. **RATE_LIMIT_PER_USER for Beta**: The current default (30 req/min, set via
   envInt in internal/config/config.go:75) was tuned for Pilot. The issue
   lists it as a Beta tuning target but gives no numeric target. The
   implementer should derive the Beta value from the load-test error profiles
   (429 rate) and the #88 SLO budget.
