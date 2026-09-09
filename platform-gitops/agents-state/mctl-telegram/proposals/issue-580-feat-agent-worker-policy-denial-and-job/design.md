# Design: issue-580-feat-agent-worker-policy-denial-and-job

## Current state

### Metrics registry

`internal/metrics/metrics.go` is the single source of every metric family. A
`Registry` struct holds typed collectors; `New()` (line ~165) constructs them on
a fresh, non-global `prometheus.Registry` and `MustRegister`s them in one block
at the end. Subsystems receive a `*metrics.Registry` by injection:
`executor.New(store, sender, globalKill, m)`
(`internal/agent/executor/executor.go:138`), `queue.New(store, replicaID, m)`
(`internal/agent/queue/queue.go:25`), `listener.New(...)`, `db.Store`,
`internal/agentapi.Server`. The agent block registers six families
(`mctl_agent_events_received_total`, `mctl_agent_jobs_total`,
`mctl_agent_dead_letter_total`, `mctl_agent_actions_executing_stuck`,
`mctl_agent_approval_latency_seconds`, `mctl_agent_executor_restarts_total`).
`grep -n "denied\|Denied" internal/metrics/metrics.go` returns nothing, and no
family carries a cost.

There is an existing info-gauge precedent: `TelegramReplicaID`, a `GaugeVec`
named `mctl_telegram_replica_id` labelled `replica_id` and set to 1.

`/metrics` is served only by `cmd/server` (`cmd/server/main.go:365`), wrapped by
`metricsHandler(m, cfg.MetricsAllowCIDR)` (`:619`) which optionally restricts by
source CIDR and fails closed on a malformed CIDR (`:626`). **The agent-worker
binary has no `/metrics` endpoint and no metrics registry at all** — its only
HTTP surface is `newHealthServer` in `cmd/agent-worker/health_server.go`, three
plain-text probe routes on `AGENT_HEALTH_ADDR` (default `:8080`, the port
`Dockerfile.agent-worker` EXPOSEs).

### Policy

`policy.Evaluate(Input) Result` (`internal/agent/policy/policy.go:285`) is a
pure function performing no I/O, as its `Input` doc comment states. `Result` is
`{Decision Decision; Reasons []string}`; every hard denial goes through
`func deny(reasons ...string) Result` (`:61`). There are 17 `deny(...)` call
sites (lines 287, 298, 303, 305, 308, 323, 325, 327, 329, 332, 338, 343, 346,
350, 367, 370, 373). Three of them interpolate a runtime value —
`"unrecognized agent mode " + strconv.Quote(in.Profile.Mode)` (`:305`),
`"unrecognized conversation state " + ...` (`:329`),
`"unrecognized action type " + ...` (`:338`) — so **the reason strings are not
a closed set** and cannot be used directly as a Prometheus label value.

Four call sites consume the decision, all outside the policy package:

| Site | File | Meaning |
|---|---|---|
| `handleProposeReply` | `internal/agentapi/actions.go:207` | model proposed a reply |
| owner-facing notify/approval | `internal/agentapi/actions.go:429` | summary / approval request |
| `Executor.send` | `internal/agent/executor/executor.go:283` | about to send an approved action |
| `Executor.recoverOne` | `internal/agent/executor/executor.go:561` | crash-recovery re-evaluation |

Both `internal/agentapi/server.go` and `internal/agent/executor/executor.go`
already hold a `*metrics.Registry`.

### Cost and job completion

`ClaudeResult` (`internal/agentworker/worker.go:168-179`) has
`TotalCostUSD float64` with tag `json:"total_cost_usd"`. `ParseClaudeResult`
(`:184`) is a plain `json.Unmarshal`. `ClaudeInvoker.Run`
(`internal/agentworker/claudeinvoker.go:104`) calls it at `:182`, then
`CheckResult(res)` at `:186`, then verifies durable completion via
`GetJobStatus` (`:196`). `TotalCostUSD` is never read anywhere in the repo.

Job completion is **model-driven**: the `complete_agent_job` MCP tool
(`internal/agentworker/mcpserver.go:359`) calls `Client.CompleteJob`
(`client.go:399`) → `POST /jobs/{id}/complete`
(`internal/agentapi/server.go:125` → `events.go` `handleJobComplete`) →
`queue.CompleteWithResult` → `Store.CompleteAgentJobWithResult`
(`internal/db/agent_jobs.go:453`). Crucially, that happens **inside** the
`claude` process, i.e. *before* the CLI prints its result JSON — so the cost is
not knowable at completion time. The only worker-side (non-model) API surface
today is `GET /jobs/{id}` (`handleGetJob`, `events.go:178`), added for exactly
this kind of out-of-band postcondition check.

`agent_jobs` is created in both dialect paths (`internal/db/agent_schema.go:424`
SQLite, `:635` Postgres) with no cost column. Columns added after the table
first shipped use `addColumnIfMissing(ctx, dbConn, pg, table, col, pgType,
sqliteType)` (`agent_schema.go:39-160`), which is the only mechanism that
reaches an already-deployed database, since `CREATE TABLE IF NOT EXISTS` is a
no-op there. `agent_schema_test.go:139` documents the exact failure mode a
missing `addColumnIfMissing` pass caused before.

### Error classification

`CheckResult` (`worker.go:212`) returns
`fmt.Errorf("%w: subtype=%s (result: %d bytes, see run logs)",
ErrClaudeReportedError, subtype, len(res.Result))` for any `IsError` result. Its
doc comment explains at length why `res.Result` is deliberately excluded from
the error: `Worker.Loop` logs the error verbatim with `slog.Warn`
(`worker.go:120-124`), and the redaction handler in
`internal/audit/redact.go` operates on structured attribute keys, not on
free-form error string values.

`Worker.Loop` (`worker.go:65`) has no retry or dead-letter logic of its own: on
a `Run` error it logs a warning with `job_id` and an `outcome` label and moves
on. Retry/backoff/dead-letter live server-side in `queue.Retry` /
`queue.RequeueStale` (`internal/agent/queue/queue.go:104`, `:115`) driven by
`db.AgentJobBackoff` (`internal/db/agent_jobs.go`).

### Configuration

`cmd/agent-worker/main.go` `run()` reads `AGENT_API_BASE_URL` and
`AGENT_API_TOKEN` through `requireEnv` (`:64`, `:68`), which returns an error on
an empty value, causing a non-zero exit via `main()`. Optional values go through
`os.Getenv` or `envFloat` (`:206`). `docs/agent-worker.md:75-82` documents the
table.

## Proposed solution

Five changes, deliberately additive.

### 1. Bounded denial codes in `policy`, counted at the consumption sites

Add to `internal/agent/policy/policy.go`:

```go
// DenyCode is a stable, closed-set machine identifier for a denial, safe to
// use as a Prometheus label value. Result.Reasons stays free text for humans
// and the audit trail; three of those strings interpolate a runtime value
// (strconv.Quote of a mode/state/action type) and are therefore unbounded.
type DenyCode string

const (
    DenyGlobalKill        DenyCode = "global_kill"
    DenyUserMismatch      DenyCode = "user_mismatch"
    DenyModeOff           DenyCode = "mode_off"
    DenyModeUnrecognized  DenyCode = "mode_unrecognized"
    DenyAutopilotPaused   DenyCode = "autopilot_paused"
    DenyConvTakenOver     DenyCode = "conversation_taken_over"
    DenyConvClosed        DenyCode = "conversation_closed"
    DenyConvPaused        DenyCode = "conversation_paused"
    DenyConvStateUnknown  DenyCode = "conversation_state_unrecognized"
    DenySenderBlocked     DenyCode = "sender_blocked"
    DenyActionTypeUnknown DenyCode = "action_type_unrecognized"
    DenyPeerMismatch      DenyCode = "peer_mismatch"
    DenyNoDisclosure      DenyCode = "no_disclosure_text"
    DenyEmptyReply        DenyCode = "empty_reply"
    DenyReplyTooLong      DenyCode = "reply_too_long"
    DenyReplyURL          DenyCode = "reply_contains_url"
    DenyReplyCredentials  DenyCode = "reply_contains_credentials"
    DenyUnknown           DenyCode = "unknown" // fallback only
)
```

`Result` gains one additive field, `Code DenyCode`, set only on `Deny`. `deny`
becomes `func deny(code DenyCode, reasons ...string) Result`, and all 17 call
sites gain their code as the first argument. `Evaluate` stays pure: it neither
imports `internal/metrics` nor logs. A `Result.DenyCode() DenyCode` accessor
returns `DenyUnknown` for an empty code so a future `deny` site that forgets one
degrades to a bounded fallback rather than an empty label.

In `internal/metrics/metrics.go`, next to the existing agent block:

```go
// AgentPolicyDenialsTotal counts hard policy denials, labeled by the closed-set
// denial code and the call site that consumed the decision. Deliberately NOT
// labeled by account, conversation or peer: those become cardinality and, for
// peers, personal data.
AgentPolicyDenialsTotal *prometheus.CounterVec // {reason, surface}
```

registered as `mctl_agent_policy_denials_total` with labels
`[]string{"reason", "surface"}`, plus a helper
`func (r *Registry) CountPolicyDenial(reason, surface string)` so call sites do
not repeat the label order. Bound: 18 reasons x 4 surfaces = 72 series, all
compile-time fixed.

Surfaces are exported as constants in `internal/metrics`:
`PolicySurfaceProposeReply`, `PolicySurfaceOwnerNotify`,
`PolicySurfaceExecutorSend`, `PolicySurfaceExecutorRecover`. Each of the four
call sites increments immediately after `Evaluate` returns, guarded by
`if result.Decision == policy.Deny`. In `executor.recoverOne` the increment
covers the hard-`Deny` branch only, not the
`requireApprovalBypassesUnreviewedAllow` escalation — that is a
`RequireApproval`, not a denial, and conflating them would make the counter mean
two different things.

Why the second dimension is `surface` and not `action_type`: an
`executor_send` / `executor_recover` denial means an action a human (or guarded
mode) already approved was stopped at the last moment, which is operationally a
different and far more alarming event than the model proposing something the
policy engine rejects at `propose_reply`. Action type is largely recoverable
from the reason code anyway (owner-facing actions short-circuit to `Allow`
before any conversation-scoped gate).

### 2. Cost: a metric in the worker, a column on the job

**Distinguishing absent from zero.** `ClaudeResult.TotalCostUSD` changes from
`float64` to `*float64`. This is the whole reason NULL-vs-0 is achievable:
`json.Unmarshal` leaves a pointer field nil when the key is absent or JSON
`null`, whereas a `float64` field is indistinguishable from a genuine `0.0`. The
type change touches `worker_test.go:270` and is contained within
`internal/agentworker` (the field has no other reader today).

**The metric.** New in `internal/metrics`:

```go
// AgentJobCostUSDTotal is monotonic total Claude spend attributed to agent
// jobs, labeled by whether the CLI's own result reported is_error. Recorded
// before CheckResult so a job that fails afterwards still reports its spend.
AgentJobCostUSDTotal *prometheus.CounterVec // {result}
```

exposed as `mctl_agent_job_cost_usd_total`, labels `[]string{"result"}` with
values `success` / `error`. `ClaudeInvoker` gains a nil-safe
`Metrics *metrics.Registry` field; `Run` records between `:182` and `:186`:

```go
res, parseErr := ParseClaudeResult(stdout.Bytes())
if parseErr != nil { ... }                       // unchanged
c.recordCost(ctx, job, res)                      // NEW: metric + API report
if err := CheckResult(res); err != nil {         // unchanged position
    c.countResultError(err)                      // NEW: usage_limit vs other
    return err
}
```

`recordCost` is a no-op when `res.TotalCostUSD == nil`.

**The transport.** The cost is only knowable in the worker process after
`claude` exits — after the model already called `complete_agent_job`. So the
worker reports it out of band, exactly like `GetJobStatus` already does:

- `POST /api/agent/v1/jobs/{id}/cost`, registered in
  `internal/agentapi/server.go`'s route block next to
  `mux.Post("/jobs/{id}/complete", ...)`, body
  `{"attempt": <int>, "cost_usd": <float>}`, decoded with the existing
  `decodeStrict`, user-scoped via `identity(w, r)` and an existing-job check
  with `s.Store.GetAgentJob`, matching `handleJobComplete`'s shape.
- `Client.ReportJobCost(ctx, jobID, attempt, cost)` in
  `internal/agentworker/client.go`.
- `Store.RecordAgentJobCost(ctx, userID, jobID, attempt, cost float64) error`
  in `internal/db/agent_jobs.go`, a single
  `UPDATE agent_jobs SET cost_usd = $1, updated_at = $2
   WHERE id = $3 AND user_id = $4 AND attempts = $5`. The `attempts` predicate
  is the same claim fencing `CompleteAgentJob` uses, so a stale worker whose
  claim was requeued cannot overwrite a newer attempt's cost. A zero-rows
  result returns `db.ErrAgentJobNotFound`, which the handler maps to 409
  (mirroring `handleJobComplete`'s "no longer claimed under that attempt"
  branch).
- The endpoint is **not** added to `allowedTools`
  (`claudeinvoker.go:49`) nor to `NewMCPServer`'s tool builders, so the model
  has no path to assert its own spend. This is a deliberate security property,
  not an omission.
- The call is best-effort in the worker: a failure is logged
  (`slog.Warn("agent-worker: report job cost failed", "job_id", ..., "err", ...)`)
  and never changes `Run`'s return value. Spend telemetry must not be able to
  fail a job.

**The column.** `cost_usd` added to `agent_jobs` in both `CREATE TABLE`
statements (`agent_schema.go:424` SQLite `REAL`, `:635` Postgres
`DOUBLE PRECISION`) *and* through an idempotent pass in the same block as the
existing ones:

```go
// agent_jobs.cost_usd: total Claude spend for the last reported attempt.
// Deliberately NO DEFAULT — an existing row must be NULL ("we never measured
// this job"), which a DEFAULT 0 would silently turn into "this job was free".
if err := addColumnIfMissing(ctx, dbConn, pg, "agent_jobs", "cost_usd",
    "DOUBLE PRECISION", "REAL"); err != nil {
    return err
}
```

`db.AgentJob` gains `CostUSD sql.NullFloat64` (not `float64`), and
`getAgentJob`/`ClaimAgentJobs` scan it as such — the `peer_access_hash`
regression documented at `agent_schema_test.go:139` is precisely the failure of
scanning a nullable added column into a non-nullable Go type, and this design
avoids repeating it. `jobStatusResponse` (`events.go:170`) is **not** extended:
that response is deliberately minimal and reaches the model's process.

### 3. Credential-domain identity and a worker `/metrics`

`cmd/agent-worker/main.go` `run()` gains, next to the other required reads:

```go
credentialDomainID, err := requireEnv("AGENT_CREDENTIAL_DOMAIN_ID")
if err != nil { return err }
if err := validateDomainID(credentialDomainID); err != nil { return err }
```

`validateDomainID` rejects anything outside `[A-Za-z0-9._:/-]` or longer than
128 characters — a bounded, exposition-safe label value, and a shape a pasted
API key does not fit.

`run()` constructs `m := metrics.New()` and sets
`m.AgentCredentialDomain.WithLabelValues(credentialDomainID).Set(1)`, a
`GaugeVec` named `mctl_agent_credential_domain` following the
`TelegramReplicaID` / `mctl_telegram_replica_id` precedent exactly. `m` is
passed to `ClaudeInvoker.Metrics` and to `newHealthServer`.

`newHealthServer(addr, health, m, credentialDomainID, allowCIDR)` gains a
`/metrics` route using `promhttp.HandlerFor(m.Prometheus,
promhttp.HandlerOpts{})`, wrapped by a CIDR guard copied in spirit from
`cmd/server/main.go:619` and driven by an optional `AGENT_METRICS_ALLOW_CIDR`
(unset means allow, matching the server's behaviour). Reusing `metrics.New()`
rather than a bespoke worker registry keeps every `mctl_*` name defined in
exactly one file, which is what `docs/runbook_test.go`'s
`TestRunbookMetricNamesRegistered` assumes; the cost is that a handful of
server-side scalar families are also exported at 0 from the worker, which is
harmless (vec families with no children simply do not appear).

`writeProbeResult` keeps its first line `ok` / `not ok` and its status codes
untouched — `cmd/agent-worker/health_server_test.go` asserts on them — and
appends a second line `credential_domain_id=<value>`. Content-Type stays
`text/plain; charset=utf-8`.

`docs/agent-worker.md:75-82` gains the row, marked required, alongside a note
about the new `/metrics` route on `AGENT_HEALTH_ADDR`.

Nothing is added to `internal/audit/redact.go`'s `sensitiveKeys`: no new
sensitive field name is introduced. `credential_domain_id` and `cost_usd` are
deliberately *not* registered there — redacting them would defeat the entire
purpose of this issue — and that deliberate absence is documented in a comment
next to the `device_pubkey` precedent already in that file.

### 4. Usage-limit classification

In `internal/agentworker/worker.go`:

```go
// ErrClaudeUsageLimit is the quota/usage-limit subclass of
// ErrClaudeReportedError. Declaring it by wrapping the general error means an
// error built on top of it satisfies errors.Is for BOTH, so no existing caller
// that tests the general case changes behaviour.
var ErrClaudeUsageLimit = fmt.Errorf("%w: usage limit or quota exhausted", ErrClaudeReportedError)

// usageLimitSubtypes are matched as lowercase substrings of res.Subtype.
// res.Result is deliberately NOT inspected: it can carry model-derived
// Telegram content and is prompt-injectable, exactly as CheckResult's existing
// doc comment explains for the error string.
var usageLimitSubtypes = []string{"usage_limit", "rate_limit", "quota", "credit_balance", "insufficient_credits"}
```

`CheckResult` picks its sentinel with `isUsageLimitSubtype(res.Subtype)` and
otherwise builds the identical message it builds today. The formatting,
`subtype=%s (result: %d bytes, see run logs)`, is unchanged, so the existing
"never leaks result text" test (`worker_test.go:302`) keeps passing for both
classes.

`CheckResult` itself stays side-effect free (same rule as `Evaluate`); the count
happens in `ClaudeInvoker.Run` where the error is consumed, into a new
`AgentClaudeResultErrorsTotal *prometheus.CounterVec`, exposed as
`mctl_agent_claude_result_errors_total`, label `class` with values
`usage_limit` / `other`. Two series.

`Worker.Loop` is **not touched**. Its `err != nil` branch already logs both
classes identically via the `invocation_failed` outcome, and retry/backoff/
dead-letter live server-side in `queue.Retry` / `queue.RequeueStale`, which this
proposal does not modify at all. A test locks that in (see tasks T7).

### 5. Not touched

`deploy/alerts/mctl-telegram.rules.yaml` and
`deploy/grafana/mctl-telegram-beta.json` are unchanged, per the issue's explicit
non-goal.

## Alternatives

**Increment the denial counter inside `policy.Evaluate`.** Rejected: the issue
forbids it, and correctly — `Input`'s doc comment states "Evaluate performs no
I/O", and the package's whole value is that it is a pure, exhaustively
unit-tested authority. Injecting a registry would force every one of its many
table-driven tests to carry one and would make the pure-function property
untestable.

**Use `Result.Reasons[0]` directly as the `reason` label.** Rejected: three
reasons interpolate `strconv.Quote(...)` of a DB-sourced value
(`policy.go:305`, `:329`, `:338`). Any bad row, or a future enum value, mints a
new time series permanently. Prometheus never garbage-collects a label value, so
this is a one-way cardinality leak in the exact place an anomaly signal is meant
to live. The `DenyCode` enum makes boundedness a compile-time property.

**Keep `TotalCostUSD float64` and treat `0` as absent.** Rejected explicitly by
the issue, and rightly: a job that legitimately costs nothing (cached, or
refused before any model call) is then indistinguishable from a job whose cost
we failed to observe, and the persisted column would systematically understate
spend. `*float64` is the only representation that carries the distinction from
JSON through to SQL NULL.

**Extend `complete_agent_job` / `POST /jobs/{id}/complete` with a `cost_usd`
field instead of adding an endpoint.** Rejected on two independent grounds.
First it is impossible: `complete_agent_job` runs inside the `claude` process,
before the CLI has printed the result JSON the cost comes from. Second it would
be unsafe: that tool is model-invoked, so the model would be asserting its own
spend, and `mcpserver.go:351` already documents a prior fix for exactly this
class of model-supplied-argument problem. A worker-only endpoint absent from
`allowedTools` keeps spend a fact the worker observes, not a claim the model
makes.

**Give the worker its own small bespoke Prometheus registry instead of reusing
`metrics.New()`.** Considered seriously — it would avoid exporting a dozen
always-zero server-side families from the worker. Dropped because it would split
`mctl_*` name definitions across two files, breaking the single-source-of-truth
that `docs/runbook_test.go`'s `TestRunbookMetricNamesRegistered` and
`internal/metrics/metrics_test.go`'s `expectedMetricNames` both rely on, and
inviting a future name collision between the two registries.

**Match the usage-limit case on `res.Result` text as well as `subtype`.**
Dropped for this iteration: `res.Result` is model output derived from a Telegram
message and is prompt-injectable, so a crafted message could mint a false
`usage_limit` classification. Because `Worker.Loop` behaviour is unchanged for
both classes the blast radius would only ever be a wrong metric label, but the
existing `CheckResult` doc comment already establishes a strict "never look at
result text" posture that is worth keeping until a real capture proves it is
necessary.

## Platform impact

**Migrations.** One additive nullable column, `agent_jobs.cost_usd`, applied by
both the fresh-database `CREATE TABLE` path and the `addColumnIfMissing` pass,
in both dialects. No DEFAULT, so the upgrade is a metadata-only `ALTER TABLE ADD
COLUMN` on Postgres (no table rewrite) and cheap on SQLite. Pre-existing rows
are NULL, which is the semantically correct "never measured". No backfill. Fully
backward compatible: an older API binary ignores the column, an older worker
never calls the new endpoint.

**Backward compatibility — one breaking configuration change.**
`AGENT_CREDENTIAL_DOMAIN_ID` is required, so an existing agent-worker deployment
crash-loops on upgrade until it is set. Mitigation: strict rollout ordering —
add the value to the worker's values in `mctl-gitops` and sync *before* rolling
the new image; the failure is loud, immediate and logged
(`AGENT_CREDENTIAL_DOMAIN_ID is required`), and the previous image is a
one-command `mctl_rollback_service` away. This ordering must be called out in
the PR description and in `docs/agent-worker.md`.

**New HTTP surface.** `/metrics` on the worker's existing
`AGENT_HEALTH_ADDR` port (already EXPOSEd 8080 in `Dockerfile.agent-worker`) and
`POST /jobs/{id}/cost` on the agent API. The former carries no PII by
construction (its only labels are `result`, `class` and the operator-chosen
`domain_id`) and is CIDR-guardable via `AGENT_METRICS_ALLOW_CIDR`; the platform
NetworkPolicy already restricts namespace ingress. The latter is bearer-authed
and user-scoped through the same `identity(w, r)` path as every other agent-API
handler, and is unreachable from the model because it is not an MCP tool.

**Resource impact.** Negligible. Seventy-two possible denial series, two cost
series, two error-class series, one info gauge. One extra HTTP round-trip per
job (the cost report), on a loop that already makes several and spawns a
subprocess. One extra single-row `UPDATE` per job.

**Risks and mitigations.**

- *Cardinality regression from a future `deny` site.* Mitigated by the
  `DenyUnknown` fallback plus a test that asserts every `DenyCode` constant is
  reachable and that no `deny(` call site omits a code (a `go vet`-visible
  signature change makes omission a compile error, not a runtime surprise).
- *Cost report silently failing forever.* Mitigated by the `result="..."` metric
  being recorded independently of the API call, so total spend is observable
  even if persistence is broken; a warning log names the job id.
- *Stale worker overwriting a newer attempt's cost.* Mitigated by the
  `attempts = $attempt` fence and a 409 response, mirroring the completion path.
- *Privacy.* No new label carries a Telegram id, username, peer or message body;
  no new log attribute carries content. `CheckResult`'s and `Run`'s existing
  "never embed result text or stderr in the error" invariants are preserved
  verbatim, including for the new usage-limit branch.
- *`ClaudeResult.TotalCostUSD` type change.* Contained to
  `internal/agentworker`; the field has exactly one existing reader
  (`worker_test.go:270`) and the compiler surfaces any miss.
