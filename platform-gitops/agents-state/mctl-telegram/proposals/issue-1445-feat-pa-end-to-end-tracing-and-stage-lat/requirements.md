# PA end-to-end correlation and stage latency across webhook, queue, model, MCP dispatch and reply

## Revision 2026-11-27

This revision applies the review amendment register (https://github.com/mctlhq/mctl-telegram/issues/1445#issuecomment-7229399030) and its correction (https://github.com/mctlhq/mctl-telegram/issues/1445#issuecomment-7229485586). Implementation HOLD stays in force; this revision is not an approval and needs a fresh review and digest.

- Observations are classified as complete, partial or missing, with bounded labels. A missing duration is never zero, and the in-memory `runTimer` is no longer described as cross-replica coverage.
- Root and attempt span ids, span ownership, terminal timestamps, retry siblings and dedup across replica changes, restarts, cancellation and fencing are now defined (design.md). No new event table.
- Tracing failure, the kill switch and Collector failure are no-ops for authorization, job results and delivery. No trace context reaches downstream MCP servers, the model provider or Telegram.
- Retention, RBAC, deletion/expiry and access isolation for `job_id` -> `trace_id` -> Loki/Tempo are a hard precondition for enabling tracing, but not for merge.
- Verification is split into "required before merge" and "required before pilot GO" tiers (tasks.md). Gates referenced: ADR 0011 and mctlhq/mctl-telegram#1319 (mctlhq/mctl-telegram#1317 is closed and met).

## Context

Issue #1445 (part of #1312, supports Phase 3 telemetry #1324) asks for one
trusted, server-generated correlation context that follows a Personal
Assistant (PA) run through every stage: webhook acceptance and dedup,
enqueue, claim and attempt, model calls, MCP tool dispatch when used, reply
delivery to Telegram, and the terminal outcome. It also asks for separate,
queryable durations for each stage. Today one sample (preview, job 13) took
about 14 s from the Telegram message to the reply. Nothing correlates that
run stage by stage. The issue states that one sample is not an SLO.

The code already measures part of this. `internal/pa/timing.go` feeds
`mctl_pa_run_phase_seconds{phase=queue|model|tool|run|total}` and logs
`pa run timing`. It only covers runs that one replica saw from start to end,
and only runs that got a reply. It drops failed, cancelled and fenced runs
(`runTimer.drop`). It has no Telegram delivery stage and no worker-side
model-call timing. It shares no correlation id with the worker's
`pa worker: job finished` log. mctl-telegram has no OpenTelemetry tracer
installed: `internal/mcp/audit_span.go` only writes to a span that already
exists. This proposal extends what exists, avoids duplicate series, and adds
traces behind a default-off switch. It does not change authorization, lease
or fencing behaviour. The issue is under an implementation HOLD: this is a
plan only.

## User stories

- AS a platform operator I WANT to open one PA run by its job id or trace id and see each stage's duration SO THAT I can tell where a slow reply spent its time without reading message content.
- AS an on-call engineer I WANT p50/p95/p99 per stage, plus failure, cancellation and fencing outcomes SO THAT I can tell queue starvation from model latency, tool latency or Telegram delivery latency.
- AS the PA owner I WANT the telemetry to carry no message text, prompts, tool arguments or results, Telegram chat or user ids, or credentials SO THAT ADR 0011 and the threat model stay intact.
- AS a reviewer I WANT CI to prove context propagation, redaction, bounded cardinality and unchanged lease and authorization semantics SO THAT turning tracing on cannot change what a run is allowed to do.

## Acceptance criteria (EARS)

- WHEN the PA webhook accepts a new update and enqueues a job THE SYSTEM SHALL generate a W3C trace context on the server with a cryptographically random trace id and store it durably with the job (`pa_jobs.trace_context`).
- WHEN the PA webhook receives a request THE SYSTEM SHALL ignore any `traceparent`, `tracestate` or `baggage` header on it. The stored context is always created by the server.
- WHEN a worker calls a run-loop route (`/api/pa/v1/jobs/claim|turn|tool|reply|draft`) THE SYSTEM SHALL take the run's trace context from the job row named by the verified pa-job token (principal, job, attempt, digest). It SHALL never take it from request headers or the request body.
- WHEN a job is claimed THE SYSTEM SHALL return an attempt-scoped `trace_parent` in the claim response. The worker SHALL use it only as the parent of its own model-call and tool-call spans.
- WHEN a job is retried, backed off, released or reclaimed THE SYSTEM SHALL keep the same trace id for every attempt and record the attempt number as an attribute, so all attempts of one job form one trace.
- WHEN a reply or other job-level outbox row is delivered or fails THE SYSTEM SHALL record a delivery span and a `delivery` phase duration linked to the job's trace context through `OutboxItem.JobID`.
- WHEN a run ends without a reply (failed, cancelled or lease-expired) THE SYSTEM SHALL observe its claim-to-end duration in `mctl_pa_run_unanswered_seconds{outcome}` and end its spans with that outcome. A fenced request is a late action of a superseded attempt, not the end of the run: it ends only its own refused span (`pa.reply`/`pa.tool.dispatch` result `fenced`) and records no unanswered observation, because the job's own outcome is recorded by the winning terminal transition. It SHALL not discard the run's timing silently as `runTimer.drop` does today.
- WHEN the worker makes a model call, a tool call or a reply post THE SYSTEM SHALL observe the duration in `mctl_pa_worker_stage_seconds{stage,result}` on the worker's existing `/metrics` registry.
- IF a stage did not happen in a run (no tool call, no delivery yet, unknown creation time) THEN THE SYSTEM SHALL record no observation, no span and no log field for that stage. It SHALL never record zero.
- WHEN a run reaches a terminal state THE SYSTEM SHALL classify its observation as `complete` (every stage boundary seen or read from a durable field), `partial` (some boundary unknown) or `missing` (no correlation context or no observation possible), and count it in `mctl_pa_run_observations_total{completeness,reason}` with closed label sets. A partial or missing duration SHALL never be observed as zero.
- WHERE a stage boundary has a durable timestamp or context (for example `created_at_ms` or the stored trace context) THE SYSTEM SHALL use it. WHERE a boundary exists only in the in-memory `runTimer` of another replica or of a process that restarted, THE SYSTEM SHALL mark the observation `partial` and SHALL NOT observe that duration. It SHALL NOT present `runTimer` figures as cross-replica coverage.
- WHEN more than one replica, attempt or webhook delivery could observe the same transition THE SYSTEM SHALL record the terminal observation and end the `pa.job` span exactly once, from the component whose conditional state transition won. A fenced or stale request SHALL record only its own refused span, never a terminal observation.
- WHILE tracing is disabled (the default, or turned off with the kill switch `PA_TRACING_ENABLED=false` / chart `otel.enabled: false`) THE SYSTEM SHALL install a no-op tracer provider and behave exactly as it does today, apart from the additive column, the new phase label, the new histograms and the observation counter.
- WHILE any span, metric or log line for a PA run is produced THE SYSTEM SHALL include only allowlisted attribute keys. It SHALL exclude message text, prompts, tool arguments or results, model output, Telegram principal, chat or user ids, @handles, OAuth tokens, pa-job tokens and API credentials.
- WHILE metrics are produced THE SYSTEM SHALL use only closed label sets (phase, stage, result, outcome). Job ids, trace ids, attempts and tool names SHALL appear only in spans and logs, never as metric labels.
- WHEN a PA log line is written inside a run that has a trace context THE SYSTEM SHALL add `trace_id` (and `span_id` where one exists), so Loki and Tempo can be joined on one id.
- IF the trace exporter or Collector is unreachable, slow or blackholed THEN THE SYSTEM SHALL drop spans from a bounded queue, count the drops on a bounded counter, and not block or fail the webhook, claim, turn, tool, reply or outbox path.
- IF any tracing operation fails (setup, span creation, context parsing or export) THEN THE SYSTEM SHALL leave authorization decisions, job results, lease and fencing outcomes and Telegram delivery unchanged.
- THE SYSTEM SHALL NOT send trace context, trace ids, span ids or job ids to downstream MCP servers, the model provider or the Telegram Bot API.
- IF retention, RBAC and deletion/expiry rules for the `job_id` -> `trace_id` -> Loki/Tempo path, and access isolation of that data, have not been confirmed and documented THEN tracing SHALL NOT be enabled in any environment. This is a precondition for enablement, not for merging the default-off code.
- WHILE two or more jobs for different principals run at the same time (worker `WithConcurrency` > 1) THE SYSTEM SHALL keep each job's spans under that job's own trace context, with no context leaking across jobs.

## Out of scope

- Queue depth, oldest-job age and the polling design (#1430).
- Model accounting: tokens, cost and pricing (sibling issue; `pa_usage` and `mctl_agent_*` cost series stay as they are).
- Installing a platform-wide tracer policy for the non-PA parts of mctl-telegram, such as MCP tool calls in `internal/mcp` (owned by `mctlhq/.github#55`). This proposal only touches the PA path.
- Any change to authorization, consent, catalog pin, egress, lease, fencing, budget or rate semantics (ADR 0011 and mctlhq/mctl-telegram#1319 gates).
- A new table for per-stage timestamps or events. This revision uses the durable fields that already exist.
- Enabling tracing on preview or production, setting the gitops `otel.enabled` flag, or any deployment. Preview validation needs its own owner approval.
- An SLO or alert thresholds. The histograms make p50/p95/p99 queryable; choosing targets is separate.
- Dashboards. They are coordinated with mctlhq/mctl-telegram#1446 and mctlhq/mctl-gitops#3004 before the pilot GO, not built here.

## Open questions

- Ownership of the tracer provider: `docs/runbook.md` says the provider, exporter, propagator and sampling policy belong to `mctlhq/.github#55`. Does #55 accept a PA-scoped provider in mctl-telegram, behind a default-off switch and following the mctl-agents conventions (Collector to the permanent Tempo in `tracing`, `otel.enabled` chart flag)? Or must this wait for a shared Go helper from #55? This proposal assumes the scoped provider, isolated in one package that can be swapped out.
- Sampling: the default here is head-based sampling decided once at enqueue and stored in the traceparent flags, with ratio 1.0 on preview and configurable via `PA_TRACE_SAMPLE_RATIO`. Should production use a lower ratio, or always sample failures (which requires tail sampling in the Collector)?
- Retention: Tempo and Loki retention for the `labs` tenant were not observable from this run. Retention, RBAC, deletion/expiry and access isolation must be confirmed before tracing is enabled anywhere (see the acceptance criteria). Is a shorter retention needed for PA traces, since they carry job ids?
- Whether `job_id` in traces and logs counts as "restricted" enough, given that Tempo access is platform-admin only. The issue allows IDs in restricted traces and logs. This proposal keeps them out of metrics only.
- Whether the existing `pa run timing` log line is being emitted on preview. A 72h read of `labs/mctl-telegram-preview` logs returned only startup lines, so this was not observed either way. The inventory task should confirm it before treating it as a baseline.
- Whether "MCP dispatch" in the issue means only the server-side connector dispatch (`internal/pa/connector.Executor.Execute`) or also the downstream HTTP call to the MCP server. This proposal times both: the downstream call as a child span, without propagating trace context to the third-party MCP server.
