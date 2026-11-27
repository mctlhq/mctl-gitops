# Design: issue-1445-feat-pa-end-to-end-tracing-and-stage-lat

## Current state

### PA request path (server, `cmd/server` with PA_ENABLED)

1. **Webhook**: `internal/pa/webhook.go` checks the secret, method and size.
   It runs `ingress.go` `Filter` and calls `AcceptPAUpdate(ctx, updateID, fn)`
   to dedup and apply the update in one transaction. Each delivery is counted
   once in `mctl_pa_updates_total{outcome}` (`accepted`, `duplicate`,
   `dedup_error`, `handler_error`, `gave_up`, ...; `metrics.PAUpdateOutcomes`).
2. **Enqueue**: `RunLoop.EnqueueRun` (`internal/pa/runloop.go:378`) inserts a
   `pa_jobs` row inside the update's transaction. The schema is in
   `internal/db/pa_jobs.go` `paJobsSchema`: `id, principal, conversation_id,
   update_id, status, attempts, ..., lease_until_ms, retry_at_ms,
   created_at_ms`. It has no correlation or trace column.
3. **Claim**: `RunLoop.serveClaim` (`runloop.go:602`) claims a job, builds the
   context and mints the pa-job token (`localjwt.PAJob{Principal, JobID,
   Attempt, ContextDigest, Tools}`). Before responding it calls
   `l.timer.claimed(j.ID, j.CreatedAt)`. The response (`claimResponse`)
   carries the job id, attempt, token, lease, tools, limits and fragments.
4. **Turn / tool / reply / draft**: `serveTurn`, `serveReply` and
   `serveDraft`, plus the connector tool route `/api/pa/v1/jobs/tool`
   (`internal/pa/connector`, `Executor.Execute` / `dispatchRecorded` /
   `refuse` in `execute.go`). Each verifies the token via `RunLoop.verify` /
   `Authenticate`, and checks `AdmitToolCall` and `StillRunning` for fencing
   and lease. The timer hooks are `turn` (`runloop.go:866`), `toolStart` /
   `toolEnd` (`1255`/`1276`), `replied` (`992`) and `drop` (`915, 1069, 1248,
   1273, 1315`).
5. **Outbox**: `internal/pa/outbox.go` `deliver` / `deliverItem` / `sendItem`
   send replies and cards via the Bot API. They count
   `mctl_pa_outbox_total{outcome}`. `jobs.OutboxItem` carries `JobID` for
   job-level rows. Delivery time is not measured.

### Existing PA instrumentation (inventory)

| Signal | Where | Covers | Gap |
|---|---|---|---|
| `mctl_pa_run_phase_seconds{phase=queue,model,tool,run,total}` | `internal/metrics/pa.go`, fed by `internal/pa/timing.go` `runTimer` | Replied runs that one replica saw from claim to reply | In-memory only; failed, cancelled and fenced runs are dropped; no delivery phase; "model" is the server-observed time between a turn admission and the next request, so it includes worker and network overhead, not the model call alone |
| `pa run timing` slog line | `timing.go` `replied` | job_id, turns, tool_calls, model/tool/run/queue/total ms | No trace id; replied runs only |
| `mctl_pa_job_failures_total{reason}` | `metrics/pa.go`, `RunLoop.recordFailure` | Count by closed reason (`jobs.FailureReasons()`) | No duration |
| `mctl_pa_updates_total`, `mctl_pa_outbox_total`, `mctl_pa_callback_answers_total`, `mctl_pa_webhook_*` | `metrics/pa.go` | Ingress and outbox outcomes, webhook health | No latency; no correlation |
| `pa worker: job finished` slog (job_id, attempt, outcome, reason) | `internal/agentworker/parunner.go:470-475` | Worker terminal outcome | No durations; no trace id |
| Worker `/metrics` | `cmd/agent-worker/health_server.go` reuses `metrics.Registry` | Shared agent metrics | No PA stage series |
| Shared agent series from #580/#583 (`mctl_agent_job_cost_usd_total`, `mctl_agent_usage_*`, `mctl_agent_jobs_total`, ...) | `internal/metrics/metrics.go:922-1002`, `agentworker/finishrun.go`, `claudeinvoker.go` | Managed-runtime cost and jobs (not PA; PA has its own `pa_usage` ledger) | Out of scope (model accounting sibling); must not be duplicated |
| `mctl_tool_invocation_duration_seconds` | `metrics.go:759` | User-facing MCP tool calls in `internal/mcp` | Not the PA connector path |
| OTel span attributes | `internal/mcp/audit_span.go` `setAuditSpanAttributes` | Writes attributes to an existing span only | No tracer provider installed; `go.mod` has only `go.opentelemetry.io/otel` and `otel/trace` (API), with no SDK or exporter |

The worker (`internal/agentworker/parunner.go` `PAWorker.Run`) loops: `chat`
(`turn` POST, then `ChatPA` or `ChatPAStream`), then `callTool` (POST
`PARouteTool`, `PAToolCallTimeout`), then `reply` / `reportAbandoned`. Its run
deadline is `LeaseUntil - paLeaseMargin`.

### Deployed state checked

- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`: image
  `main-c74249b`, `PA_ENABLED: "true"`, `PA_STREAMING_ENABLED: "true"`,
  `PA_EXTERNAL_TOOLS_ENABLED: "true"`, `PA_WRITES_ENABLED: "false"`, servers
  tg and alice. No `otel:` block and no `OTEL_*` env, so tracing export is not
  configured. `/metrics` is denied at the edge (#588).
- `$MCTL_GITOPS_ROOT/services/labs/agent-worker-pa-preview/values.yaml`:
  `replicaCount: 1`, image `main-c74249b`, `AGENT_PA_STREAMING: "true"`,
  `AGENT_PA_BASE_URL` points at the preview server service. No `otel:` block.
  (The issue cites `main-0ef3857` / `main-e64acda` on 2026-11-24. Gitops now
  shows newer tags.)
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml` comments that
  the server runs at `replicaCount` 1, so the in-memory `runTimer` currently
  sees whole runs.
- Convention reference: `services/admins/mctl-agents-worker-exec/values.yaml`
  and `services/admins/mctl-support/values.yaml` use the chart's
  `otel.enabled: true`, which renders the OTLP endpoint to the in-cluster
  Collector and then the permanent Tempo in `tracing` (mctl-gitops#1280,
  ADR 0001 producer amendment). mctl-agents scopes sampling with
  `MCTL_TRACE_WORKFLOW_TYPES` and has a kill switch (`otel.enabled: false`).
- `mctl_get_service_logs(labs, mctl-telegram-preview, 72h, 20)`: returned
  startup lines only (`pa bot enabled ... route /api/pa/v1/jobs/tool`,
  `replica identity replica_id=unknown`). No `pa run timing` line was in that
  window. This was not checked further, so whether that line is emitted on
  preview was not observed and is recorded as an open question.
- Tempo and Loki retention for `labs`: not observable with the tools in this
  run.

## Proposed solution

The work comes in four layers. Each layer is useful alone and can be turned
off.

### 1. Durable, server-generated correlation context

- Additive column `pa_jobs.trace_context TEXT NOT NULL DEFAULT ''`, added in
  `paJobsSchema` with a migration in `migratePAJobs` (the same
  `ALTER TABLE ... ADD COLUMN` pattern as other pa_* migrations). It holds a
  W3C `traceparent` string: version, trace id, root span id and flags.
- It is generated in `EnqueueRun` from `crypto/rand` by a new helper
  `internal/pa/trace.go` `newRunContext(sampled bool)`. Generation does not
  depend on the OTel SDK, so the column is filled even while tracing is off.
  That gives logs a stable correlation id from the first release.
- The sampling decision is taken once, at enqueue, from
  `PA_TRACE_SAMPLE_RATIO`, and stored in the flags. Every attempt and stage
  inherits it, so a run is traced completely or not at all.
- Trust boundary: no OTel propagator is installed on any HTTP handler. The
  webhook ignores `traceparent`, `tracestate` and `baggage`. Run-loop routes
  load the context from the job row found by the verified token (`jobs.Ref`),
  so the worker cannot attach server spans to a trace it picked. Downstream
  MCP calls (`connector/mcpclient.go`) get no `traceparent` injected, so no
  ids leave the platform.
- `jobs.Job` gains `TraceContext string`. `db` reads and writes it. The claim
  response gains `trace_parent`: the attempt span's context, derived from the
  stored trace id. A worker that ignores the field behaves exactly as it does
  today.
- Identifiers. The trace id (16 random bytes) and the root span id of
  `pa.job` (8 random bytes) are generated once at enqueue and stored in the
  traceparent. `pa.job` is the root of the trace and has no parent; it is
  created through a PA-scoped ID generator that returns the stored ids, and
  its sampling follows the stored flags rather than the `AlwaysOff` root
  sampler. Because the SDK consults the sampler before the ID generator for a
  parentless span, this needs a PA-aware sampler wrapper around
  `ParentBased(AlwaysOff)` that, for `pa.job` only, returns the decision carried
  in the stored trace flags; every other parentless span keeps `AlwaysOff`. Attempt
  span ids are derived, not stored: the first 8 bytes of
  SHA-256(trace id || root span id || attempt number), and `pa.attempt` is
  created through the same PA-scoped ID generator, which reads the derived
  span id from the context the attempt-end code passes in. Any replica therefore
  derives the same attempt span id for the same attempt, and retries are
  siblings under `pa.job`. Rows from before the migration have no context
  and produce no spans; their observations count as `missing`.
- Worker trust boundary. The worker uses `trace_parent` only to parent its
  own spans. Its HTTP clients for the model provider (via the AI gateway) and
  for the server get no propagator, so no trace context leaves the platform
  through the worker either.

### 2. Stage durations (metrics): extend, do not duplicate

- Keep `mctl_pa_run_phase_seconds` and its semantics unchanged. Add one phase,
  `delivery`: from the reply outbox row's creation to a terminal send outcome
  (`sent`, `failed`, `refused`), observed in `deliverItem`. Update
  `PARunPhases` / `RunPhases()` and `TestPARunPhaseLabels`.
- New `mctl_pa_run_unanswered_seconds{outcome}` with closed outcomes `failed`,
  `cancelled`, `fenced` and `lease_expired`. It is fed by turning
  `runTimer.drop(job)` into `runTimer.ended(job, outcome)`. The failure reason
  stays in `mctl_pa_job_failures_total{reason}` and is not repeated as a
  label.
- New worker-side `mctl_pa_worker_stage_seconds{stage,result}` with
  `stage ∈ {model_call, tool_call, reply_post}` and
  `result ∈ {ok, error, timeout, cancelled, denied, approval_pending}`. It is
  observed in `PAWorker.chat`, `callTool` and `reply`, and is the only place
  that measures the model call alone. The help text explains how it differs
  from the server's `model` phase.
- All three histograms use the existing bucket set
  (`0.25 ... 300` seconds), which supports `histogram_quantile` for
  p50/p95/p99. The unit is seconds. None has an id label. All label sets are
  closed constants pre-registered with `Add(0)` or exercised in tests, as the
  other PA collectors are.
- An absent stage records no observation. This matches the current `tool`
  phase rule and the rule for unknown creation time in `timing.go`.
- Observation completeness. `runTimer` is in memory: it holds the claim and
  turn boundaries only on the replica that saw them, and loses them on
  restart. It is therefore not cross-replica coverage, and the design does
  not claim that it is. A duration is observed only when both of its
  boundaries were seen by the observing process or come from a durable field
  (`created_at_ms`, `retry_at_ms`, the stored trace context, outbox row
  fields). Otherwise the duration is not observed, and the run's terminal
  observation is classified in a new counter
  `mctl_pa_run_observations_total{completeness,reason}`:
  - `completeness ∈ {complete, partial, missing}`;
  - `reason ∈ {none, timer_missing, unknown_created_at, no_trace_context}`
    (closed, pre-registered).
  `timer_missing` covers both a restart and a claim made by another replica,
  which a single process cannot tell apart. Missing is never rendered as
  zero.
- Dedup. The terminal observation (phase histograms, unanswered histogram,
  completeness counter) is recorded only by the process whose conditional
  terminal update on `pa_jobs` affected the row: finish, fail, cancel
  (including `ReleaseCancel`) and lease expiry (`ExpirePAJobs` sets status
  `expired`, which is terminal today). A release that returns the job to
  `queued` (`ReleaseBackoff`, or a claim-failure backoff) is not terminal: it
  ends only that `pa.attempt` and records no terminal observation and no
  `pa.job` end, so the next attempt continues the same trace. A losing or fenced request records nothing terminal.
  Duplicate webhook deliveries are already deduplicated by
  `AcceptPAUpdate`, so they never reach enqueue.

### 3. Spans (default off)

- New package `internal/telemetry`. `Setup(ctx, cfg) (shutdown, error)`
  installs an SDK `TracerProvider` with an OTLP/HTTP exporter and a
  `BatchSpanProcessor` (bounded queue; drop on overflow; export timeout), but
  only when `PA_TRACING_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT` is set.
  The endpoint is rendered by the chart's `otel.enabled`. Otherwise the
  provider is a no-op and nothing changes. The sampler is
  `ParentBased(AlwaysOff root)`: only contexts that the PA code builds from a
  stored sampled traceparent are recorded. Nothing else in mctl-telegram
  starts being traced, and `.github#55` keeps ownership of a global policy.
  The same `Setup` is called from `cmd/agent-worker`.
- Span tree, one trace per job, rooted at `pa.job`. Spans across the queue
  boundary are created with explicit timestamps
  (`trace.WithTimestamp(...)`) taken from durable fields where they exist:

  ```
  pa.job               (created -> terminal; outcome)  root, server
      ├ pa.update      (webhook accept; outcome)       server
      ├ pa.queue       (created -> claimed)            server
      ├ pa.attempt     (attempt=N; claim -> release/reply; outcome)
      │   ├ pa.turn            (admission result)
      │   ├ pa.tool.dispatch   (server, tool from pin; result ok|denied|error|approval_pending|fenced)
      │   │   └ pa.mcp.call    (downstream duration; result)
      │   ├ pa.worker.model_call   (worker; result, streaming bool)
      │   ├ pa.worker.tool_call    (worker; result)
      │   └ pa.reply           (accepted | refused | fenced)
      └ pa.delivery    (outbox send; outcome; retry count)
  ```

  Duplicate webhook deliveries are deduplicated by `AcceptPAUpdate`, never
  reach enqueue and produce no PA span; they stay counted in
  `mctl_pa_updates_total{outcome="duplicate"}`. Retries produce sibling
  `pa.attempt` spans in the same trace.
  Cancellation and lease or fencing refusals (`StillRunning`, `stopRun`) end
  the open spans with that outcome and add a span event; the error message is
  never recorded.
- Ownership and timestamps. Each span has one owner, which alone starts and
  ends it, so no span is emitted twice:

  | Span | Owner | Start | End |
  |---|---|---|---|
  | `pa.job` | winner of the terminal conditional update | `created_at_ms` (durable) | terminal transition time |
  | `pa.update` | webhook handler | request receipt | accept commit |
  | `pa.queue` | claiming process | `created_at_ms`, or `retry_at_ms` for attempt > 1 | claim commit |
  | `pa.attempt` | process that ends the attempt (reply, release, failure, lease expiry) | claim time if held locally, else marked partial | attempt end |
  | `pa.turn`, `pa.tool.dispatch`, `pa.mcp.call`, `pa.reply` | process handling that request | request receipt | response |
  | `pa.worker.*` | worker | call start | call end |
  | `pa.delivery` | outbox process that reaches a terminal send outcome | outbox row creation | terminal send outcome |

  When `pa.attempt` is ended by a process that did not see the claim, the
  span carries `mctl.pa.observation=partial` and starts at the earliest
  locally seen event; its duration is not observed in any histogram. A
  `pa.job` span is emitted only by the terminal winner, so a crash between
  the terminal commit and the export loses the span (counted as an export
  gap in the runbook) but never duplicates it.
- Attributes come from a single allowlist builder, `internal/pa/trace.go`
  `runAttrs`. It accepts only typed values: `mctl.pa.job_id`,
  `mctl.pa.attempt`, `mctl.pa.outcome`, `mctl.pa.failure_reason`,
  `mctl.pa.phase`, `mctl.pa.tool.server`, `mctl.pa.tool.name` (pinned
  catalog names only), `mctl.pa.result`, `mctl.pa.streaming`,
  `mctl.pa.observation` (`complete|partial`). There is no
  string-typed free field. Principal, chat id, conversation id, update id,
  text, arguments, results, prompts and tokens are not representable. PA spans
  do not call `internal/mcp` `auditSpanAttributes`, which carries
  `mctl.user.id`.

- Kill switch and Collector failure. `PA_TRACING_ENABLED=false` (or chart
  `otel.enabled: false`, which removes the endpoint) is read at start-up and
  takes effect on the next rollout; there is no in-process toggle. With the
  switch off the provider is a no-op: no exporter goroutine, no network
  connection, no spans. Correlation ids in the column and logs and the
  metrics stay on, because they do not depend on tracing. With the switch on
  and the Collector failing, the `BatchSpanProcessor` drops on overflow, the
  exporter uses a short export timeout and no retry beyond it, and drops are
  counted on `mctl_pa_trace_spans_dropped_total` (no labels). No tracing
  call returns an error into a request handler.

### Enablement preconditions (not merge preconditions)

Merging the default-off code does not enable tracing. Before any
environment sets `PA_TRACING_ENABLED=true`, the following must be confirmed
and written into the runbook, and the enablement PR must cite them:
- retention of PA traces in Tempo and of PA log lines carrying `trace_id` in
  Loki for the target tenant;
- RBAC and access isolation: who can query those traces and logs, and that
  tenant users cannot;
- deletion and expiry: `pa_jobs.trace_context` goes with the account delete
  and the retention sweep, but exported spans and log lines carry `job_id`
  and `trace_id` until their backend retention expires. The runbook states
  that limit, and the owner accepts it or asks for a shorter retention.

### 4. Logs

- `pa run timing`, `pa worker: job finished` and the run-loop's failure logs
  gain `trace_id`, taken from the stored context. The new keys contain no
  secrets. `internal/audit/redact.go` is reviewed, and any new sensitive key
  is added there (none is expected).
- The runbook gains a "Query one PA run" section. It shows how to find
  `trace_id` from a `job_id` in Loki
  (`{namespace="labs",instance="labs-mctl-telegram-preview"} | json | job_id="13"`),
  then open the trace in Tempo, then join the worker log by the same
  `trace_id`. It also gives PromQL for p50/p95/p99 per phase and stage, and
  explains what an absent stage means.

## Alternatives

- **Trust a `traceparent` from the worker or webhook (standard HTTP
  propagation).** This is simplest and idiomatic. It was dropped because the
  issue forbids trusting supplied trace metadata, and because a compromised
  worker could then attach spans to another principal's trace. Server-loaded
  context keyed by the verified token keeps correlation under the same
  authority as the run.
- **Persist per-stage timestamps in a new `pa_job_stages` table and compute
  every duration from the DB.** This gives exact cross-replica metrics. It was
  dropped for now because of the extra writes on the hot path, the new
  retention and deletion obligations (`pa_account.go` delete list), and
  because the server runs one replica today. Without it, cross-replica and
  post-restart coverage is incomplete: the design marks and counts those
  observations as partial instead of claiming them. The table stays an
  option if replicas increase and the partial rate shows it is needed.
- **One new combined histogram `mctl_pa_stage_seconds{stage,outcome}`
  replacing `mctl_pa_run_phase_seconds`.** It is cleaner, but it duplicates or
  breaks the existing series and any dashboards built on it, which the issue
  explicitly asks to avoid. Extending the closed phase set and adding two
  narrow histograms keeps old queries valid.
- **Wait for `mctlhq/.github#55` to ship a shared tracer.** This is the
  safest for ownership, but it blocks layers 1, 2 and 4, which need no
  tracer. The design isolates the provider in `internal/telemetry`, so #55
  can replace it later (see Open questions in requirements.md).

## Platform impact

- **Migration**: one additive column with a default. It is safe on SQLite and
  Postgres, and old rows read `''`, which means no correlation and no
  observation. Old servers ignore the column. The new claim field is additive
  JSON, so an old worker ignores it, and a new worker against an old server
  sees no field and starts no spans.
- **Compatibility**: `mctl_pa_run_phase_seconds` gains a label value, which
  existing queries tolerate. Two new histogram families exist: 4×11 buckets on
  the server and 3×6×11 on the worker, which is bounded and small.
- **Resources**: with tracing off, one `crypto/rand` read and about 55 bytes
  per job. With tracing on, about 10 spans per run, a batch exporter with a
  bounded queue, and new Go dependencies (`otel/sdk`,
  `otel/exporters/otlp/otlptrace/otlptracehttp`), which increase image size.
- **Risks and mitigations**:
  - Sensitive data in spans. Mitigation: allowlist-only builder, a recorder
    test that fails on any key not in the allowlist and on synthetic fixture
    values (`Alice` / `Bob` ids, message text), and no downstream
    propagation.
  - Exporter stalls the hot path. Mitigation: async batch processor, drop on
    overflow, export timeout, a drop counter, and a test with a blackholed
    endpoint.
  - Incomplete coverage presented as complete. Mitigation: the completeness
    counter, the `partial` span attribute, and no histogram observation
    without both boundaries.
  - Semantic drift in auth or lease. Mitigation: timing and tracing hooks only
    observe. The existing runloop, connector and worker suites run with
    tracing on and off and must stay identical.
  - Ownership conflict with `.github#55`. Mitigation: default off, PA-scoped
    sampler, provider in one replaceable package. Enabling on preview needs
    separate owner approval and a gitops PR (`otel.enabled: true`,
    `PA_TRACING_ENABLED`).
  - Account deletion: `trace_context` lives on `pa_jobs`, which is already
    covered by the `pa_account.go` delete and the `pa_convo.go` retention
    sweep. Exported traces and log lines follow backend retention, which is
    an enablement precondition (above).

## Verification tiers

Tests are split in tasks.md into two tiers. The rule: anything that protects
correctness, privacy and security, the unchanged run semantics or backward
compatibility is required before merge, because merging default-off code
must already be safe. Checks that need multi-process orchestration, fault
matrices across restarts and replicas, or operational confirmation are
required before the pilot GO, because no environment runs with tracing on
until then.

- Before merge: no untrusted inbound metadata and no downstream leakage;
  allowlisted attributes and redaction; missing duration never zero and the
  completeness classification; tracing failure, kill switch and Collector
  failure leave authorization, job results and delivery unchanged;
  default-off no-op; bounded labels; migration and mixed old/new
  worker-server compatibility; single-process duplicate observation.
- Before pilot GO: restart between enqueue and claim and after claim;
  split-replica claim and reply; the retry, fencing and lease-expiry matrix
  across processes; retention, RBAC and deletion confirmation (also the hard
  enablement precondition); dashboards coordinated with
  mctlhq/mctl-telegram#1446 and mctlhq/mctl-gitops#3004.
