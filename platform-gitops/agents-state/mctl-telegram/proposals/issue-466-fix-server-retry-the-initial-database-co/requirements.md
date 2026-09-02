# Retry the initial database connection instead of exiting on first ping failure

## Context

`cmd/server/main.go` opens the database once at boot via `db.Open` (`internal/db/db.go`),
which issues a single `dbConn.PingContext(ctx)` and returns an error immediately if it
fails. `main` treats that error as fatal: it logs at `ERROR` and calls `os.Exit(1)`
(`cmd/server/main.go:83-86`), leaving the kubelet to restart the container.

On `mctl-preprod` this failure path is triggered routinely by a known cluster issue
(mctl-gitops#866): a freshly scheduled pod's first outbound connection can leave the
node before the CNI has programmed that pod's NetworkPolicy rules, so the very first
TCP dial to Postgres gets `connection refused`. Loki evidence in the issue shows the
refusal always lands 14-18 ms after process start and a manual retry ~600 ms later
always succeeds — a signature of a network-plane race, not a database outage. The
issue reports a 4-of-6 hit rate on pod starts in a 24h window, meaning roughly two
thirds of rollouts pay for one extra container restart, plus a `restartCount` metric
and an `ERROR` log line that are noise for a condition nobody needs to act on.

The issue explicitly rules out fixing this by raising retries/backoff at the
orchestration layer (Kubernetes restarting the container): per mctl-gitops#866, a pod
restart is faster than NetworkPolicy convergence, so restarting the whole process
races and loses against the very thing it's trying to outlast. The fix has to be a
bounded poll loop inside the single process attempt, before the point where `main`
currently gives up.

## User stories

- AS an operator watching rollouts on mctl-preprod/mctl-prod I WANT the server to
  ride out a transient "connection refused" on its first database ping SO THAT
  routine NetworkPolicy programming delays do not cost a container restart on every
  other deploy.
- AS an on-call engineer I WANT the log to say how many attempts a startup needed to
  reach the database SO THAT I can tell a masked netpol race (a handful of retries)
  apart from a real outage (deadline reached, process exits).
- AS a maintainer I WANT the retry to stay bounded and still fail loudly SO THAT a
  genuinely unreachable database still crashes the pod instead of hanging forever.

## Acceptance criteria (EARS)

- WHEN `cmd/server/main.go` calls into the database-open path at startup AND the
  first connection attempt fails with a dial/connection error THE SYSTEM SHALL retry
  the connection attempt on a short fixed or bounded-backoff interval without exiting
  the process.
- WHEN a retried attempt during the startup connection wait succeeds THE SYSTEM SHALL
  proceed with server startup exactly as it does today on an immediate success (same
  `*sql.DB`, same subsequent `db.Migrate` call, same pool tuning from
  `cfg.DBMaxOpenConns`/`cfg.DBMaxIdleConns`).
- WHILE the startup connection wait is retrying THE SYSTEM SHALL log one line per
  attempt (or per failed attempt) at a non-`ERROR` level identifying the attempt
  number, so `reachable after 0 retries` and `reachable after N retries` are
  distinguishable in the log, per the issue's acceptance criterion.
- IF the bounded deadline for the startup connection wait is reached without a
  successful connection THEN THE SYSTEM SHALL log the failure at `ERROR` (as it does
  today) and call `os.Exit(1)`, preserving today's fail-fast behavior for a database
  that is genuinely unreachable for minutes.
- WHEN `SIGINT`/`SIGTERM` is received while the startup connection wait is in progress
  THE SYSTEM SHALL stop retrying and exit promptly rather than continuing to poll
  until its deadline, consistent with the `signal.NotifyContext`-derived `ctx` already
  threaded through `main`.
- WHERE the retry loop lives (inside `db.Open`, or a thin wrapper called from
  `cmd/server/main.go` before/around `db.Open`) THE SYSTEM SHALL NOT change `db.Open`'s
  behavior for any other caller that wants a single non-retrying attempt (e.g. tests
  in `internal/db/db_test.go` that expect `Open` to fail immediately against an
  unreachable/malformed DSN), unless those tests are updated as part of this change to
  reflect the new contract.

## Out of scope

- Raising retry counts, backoff limits, or restart policy at the Kubernetes/orchestration
  layer (Deployment `restartPolicy`, probe timing, etc.) — the issue explicitly asks for
  this to happen inside a single process attempt instead.
- Fixing the underlying NetworkPolicy race itself (mctl-gitops#866) — that is tracked
  in `mctl-gitops`, not `mctl-telegram`.
- Retrying `db.Migrate` or any other startup step after the connection succeeds — only
  the initial connection/ping is in scope.
- Adding retry/backoff to steady-state database calls made after startup (e.g. inside
  request handlers or the agent queue) — this proposal only covers the one-time
  startup connection.
- Making the retry window, interval, or backoff shape independently configurable via
  new environment variables beyond what is needed to satisfy the acceptance criteria
  (see Open questions).

## Open questions

- Exact interval/backoff shape and total deadline: the issue says "a short interval"
  and "on the order of a few minutes" without pinning exact numbers. This proposal
  adopts a fixed short interval (2s) capped by a bounded total deadline (2 minutes) as
  the most reasonable interpretation, mirroring the existing exponential-backoff
  precedent in `cmd/local/daemon.go` (`reconnectBase`/`reconnectMax`) in spirit but
  using a simpler fixed-interval poll since the netpol race resolves in under a
  second and a long exponential ramp would slow down recovery from the common case.
  If a future need arises for cluster-specific tuning, both values can be exposed as
  env vars (e.g. `DB_CONNECT_RETRY_INTERVAL`, `DB_CONNECT_RETRY_TIMEOUT`) without
  changing today's defaults.
- Whether to retry on every ping error or only on classified "connection refused"
  network errors: this proposal retries on any ping failure during the startup
  window (matching how `db.Migrate`'s own dependent failures are still fatal, and
  keeping the change simple), since distinguishing error causes reliably across the
  pgx and modernc/sqlite drivers adds complexity the issue does not ask for. A
  misconfigured DSN or bad credentials will still exhaust the deadline and exit with
  the same `ERROR` log as today, just after the bounded wait instead of immediately.
- Whether SQLite (local-dev) callers should also go through the retry wrapper: SQLite
  file-backed opens do not experience a NetworkPolicy-style race, so this proposal
  applies the same code path to both dialects for simplicity (a `file:` DSN either
  succeeds immediately or fails for a reason retries will not fix, so the loop exits
  fast either way via the existing bounded deadline) rather than branching on driver.
