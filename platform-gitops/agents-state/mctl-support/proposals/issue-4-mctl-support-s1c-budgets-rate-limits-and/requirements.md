# mctl-support S1c: budgets, rate limits and per-tenant escalation

## Context

Phase S1c of the tenant support agent epic (mctlhq/.github#243) makes the
pilot safe and observable. S1b (mctlhq/mctl-support#3) shipped the read-only
model loop. It has only a per-call, in-memory cost cap: `Budget.add_cost` in
`src/mctl_support/agent/limits.py` checks the cap after a call and resets on
every `execute()`. It has no per-tenant or workspace spend control and no rate
limit per principal. `escalate` is a stub: `ToolRegistry.dispatch` in
`src/mctl_support/agent/registry.py` records the reason and answers
"escalation is not wired until S1c". There are no metrics and no traces.

This proposal adds the following:
- Spend caps that refuse before a model call: a provider workspace cap of
  $50/month, $10 per tenant per month and $0.50 per task.
- Rate limits per principal: 1 concurrent task and 20 tasks per day.
- Usage records per model turn through the ADR-012 producer contract.
- A real `escalate` local tool. It creates one support incident per tenant in
  mctl-api through a narrow producer identity and is rate-limited.
- Prometheus metrics and OpenTelemetry traces.

The incident-type extension and the admin-only cross-tenant aggregation must
be implemented in mctl-api. This proposal specifies their contract and lists
them as a companion change.

## User stories

- AS the platform owner I WANT model spend capped per workspace, tenant and task, checked before every model call, SO THAT a pilot cannot overrun the budget.
- AS the platform owner I WANT each principal limited to 1 concurrent task and 20 tasks a day SO THAT one caller cannot exhaust the shared budget.
- AS a tenant member I WANT a refused task to say clearly which limit refused it SO THAT I know whether to wait or ask the owner.
- AS the platform owner I WANT the support agent to escalate platform problems as incidents bound to the asking tenant SO THAT I see real platform defects without tenants' data being mixed.
- AS the platform owner I WANT an admin-only view `normalized_fingerprint -> affected_tenants, count` SO THAT I see when several customers hit the same problem.
- AS an operator I WANT metrics, traces and per-turn usage records SO THAT I can see cost, failures and latency of the pilot.

## Acceptance criteria (EARS)

Budgets
- WHEN a model turn is about to start THE SYSTEM SHALL check the per-task cap, the per-tenant monthly cap and the workspace monthly cap against the Postgres spend ledger before the provider is called.
- IF admitting the per-turn reservation would exceed any of the three caps THEN THE SYSTEM SHALL NOT call the provider.
- IF a cap check refuses the first turn of a new task THEN THE SYSTEM SHALL end the task in `TASK_STATE_REJECTED` with a message naming the exhausted layer (for example "tenant monthly support budget exhausted; resets on 2026-11-01").
- IF a cap check refuses the first turn of a new task THEN THE SYSTEM SHALL NOT create a WorkItemExecution, mint a run token or call the provider for it.
- IF a cap check refuses a later turn of a task that is already running THEN THE SYSTEM SHALL end the task `TASK_STATE_FAILED` with the same message.
- WHEN a model turn returns THE SYSTEM SHALL settle the turn's reservation with the actual cost priced from the reported usage.
- IF the usage was not reported THEN THE SYSTEM SHALL charge the full reservation and fail the task, as `Budget.add_cost` does today.
- WHILE several replicas run tasks THE SYSTEM SHALL serialise check-and-reserve per tenant and per workspace in Postgres, so that concurrent turns cannot together overshoot a cap by more than one reservation's misestimate.
- THE SYSTEM SHALL read every cap and the per-turn reservation from configuration: `SUPPORT_WORKSPACE_MONTHLY_CAP_USD` (default 50), `SUPPORT_TENANT_MONTHLY_CAP_USD` (default 10), `SUPPORT_TASK_COST_CAP_USD` (default 0.50) and `SUPPORT_TURN_RESERVATION_USD`.
- IF any of these values is non-finite or not above 0 THEN THE SYSTEM SHALL refuse to start.
- IF the task cap exceeds the tenant cap, or the tenant cap exceeds the workspace cap, THEN THE SYSTEM SHALL refuse to start.

Rate limits
- WHEN a new task would start for a principal that already holds a live turn lease THE SYSTEM SHALL end the new task `TASK_STATE_REJECTED` ("one support task at a time") before creating an execution.
- WHEN a new task would start for a principal that has started `SUPPORT_TASKS_PER_DAY` (default 20) tasks in the last 24 hours THE SYSTEM SHALL end the new task `TASK_STATE_REJECTED` before creating an execution.
- THE SYSTEM SHALL count only tasks that were started, not rejected ones, toward the daily limit.
- WHILE a turn runs THE SYSTEM SHALL hold the principal's lease in Postgres and release it when the turn ends.
- IF the replica holding the lease dies THEN THE SYSTEM SHALL let the lease expire after the task deadline plus a margin.

Usage records
- WHEN a model turn returns THE SYSTEM SHALL write a usage record to a durable outbox in the same transaction that settles the ledger. The record carries task id, turn id, execution id, provider, model, input/output tokens, calculated cost and the non-DevLoop marker (`agent: mctl-support`, no `devloop_stage`); the tenant stays in the local ledger.
- THE SYSTEM SHALL deliver outbox records to the mctl-api usage ledger (ADR-012 producer contract) with the usage-writer credential, retrying until accepted.
- IF delivery fails THEN THE SYSTEM SHALL keep the record and SHALL NOT treat the failure as zero usage.

Escalation
- WHEN the model calls `escalate(kind, summary, evidence[], signature?, tenant?)` THE SYSTEM SHALL validate it locally before any network call. `kind` must be one of `platform_defect`, `quota_request`, `policy_exception` or `needs_owner`. `summary` must be a bounded string. Every evidence entry must be a `tool:<id>` or `skill:<name>` source of this task.
- IF `tenant` is given and differs from the task's bound tenant THEN THE SYSTEM SHALL refuse the escalation and SHALL NOT call mctl-api.
- WHEN an escalation is valid and within rate limits THE SYSTEM SHALL `POST` one incident with the incident-producer credential. The incident carries `source=support`, the task's bound tenant, `type=<kind>`, a fingerprint, the summary, the evidence references, the support task id and the caller principal.
- THE SYSTEM SHALL compute the fingerprint as `support:<kind>:` plus the hash of a normalised signature. Normalisation removes the tenant name, ids, hex, numbers and timestamps, so the same problem in two tenants yields the same fingerprint.
- THE SYSTEM SHALL NOT use the run token or the caller's bearer to create the incident.
- THE SYSTEM SHALL NOT use the producer credential for anything other than creating support incidents.
- IF the same tenant and fingerprint were already escalated within the dedupe window THEN THE SYSTEM SHALL return the existing incident id and SHALL NOT post again.
- IF a task has reached `SUPPORT_ESCALATIONS_PER_TASK` (default 1) or a tenant has reached `SUPPORT_ESCALATIONS_PER_TENANT_PER_DAY` (default 5) THEN THE SYSTEM SHALL refuse further escalations with a tool result saying so.
- WHEN an escalation creates or reuses an incident THE SYSTEM SHALL put its id in the result's `escalation_id`.
- IF the incident post fails THEN THE SYSTEM SHALL return an explicit tool error and leave `escalation_id` null, never a fabricated id.

mctl-api companion (contract)
- WHEN two tenants escalate the same signature THE SYSTEM (mctl-api) SHALL hold two incidents, deduplicated on `tenant + fingerprint`, and SHALL never merge them across tenants.
- WHEN an admin reads the support incident aggregation THE SYSTEM (mctl-api) SHALL return rows `normalized_fingerprint, affected_tenants, count`. For the same signature in two tenants that is one row with count 2.
- IF a non-admin reads the aggregation THEN THE SYSTEM (mctl-api) SHALL answer 403.
- IF a request with the support incident-producer identity is anything other than `POST` of a `source=support` incident THEN THE SYSTEM (mctl-api) SHALL refuse it.

Observability
- THE SYSTEM SHALL export these metrics on a separate port (default 9090) that is not routed by the ingress:
  - `support_tasks_total{state}`
  - `support_task_duration_seconds`
  - `support_tool_calls_total{tool,status}`
  - `support_model_tokens_total{direction}`
  - `support_model_cost_usd_total`
  - `support_budget_rejections_total{reason}`
  - `support_escalations_total{kind}`
  - `support_agent_scope_denials_total`
- THE SYSTEM SHALL use a tenant label only on `support_tasks_total`, `support_model_cost_usd_total` and `support_budget_rejections_total`, and only for tenants in `SUPPORT_ALLOWED_TENANTS`. Every other tenant is labelled `other`.
- THE SYSTEM SHALL NOT put secret values, principal ids or raw log text in any label.
- WHEN an A2A request is served THE SYSTEM SHALL produce one trace with these spans: A2A request, support task, model turn, tool call and mctl-api request. The trace carries `support.task_id` and `support.work_item_execution_id`, and `traceparent` is propagated on calls to mctl-api.
- IF no OTLP endpoint is configured THEN THE SYSTEM SHALL run with a no-op tracer.

## Out of scope

- A pricing or billing model. The caps are pilot safety limits only.
- Reading Anthropic's own spend API. The local ledger is the enforcement point; the Anthropic console limit stays as a separate backstop that operators set by hand.
- Editing, resolving or commenting on incidents from mctl-support.
- Notification delivery (Telegram and similar) of support incidents. That is mctl-api's existing incident pipeline.
- Switching production from `SUPPORT_EXECUTOR=fake` to `agent`. That is a separate mctl-gitops change after this lands.
- Streaming and push notifications.

## Resolved by the owner (2026-10-27)

- ADR-012: `POST /api/v1/usage/records` exists with server-derived ids (no
  `Idempotency-Key`) and no tenant field. mctl-support reuses the existing
  route-restricted usage-writer principal (`SUPPORT_USAGE_WRITER_TOKEN`) and
  marks its rows with `agent: mctl-support` and no `devloop_stage`. See
  design.md section 3.
- Incidents: `POST /api/v1/incidents` already accepts `source`, `type`,
  `tenant`, `fingerprint` and `evidence[]`, requires a caller-chosen `id`, and
  dedupes on `(tenant, fingerprint)` among open incidents without merging
  across tenants. Only the narrow producer principal and the admin
  aggregation are new, in mctlhq/mctl-api#830.
- Credentials: both tokens reach the pod through a Vault-synced secret, like
  `admins-mctl-support-db-creds`, in the step 12 gitops PR. Rotation follows
  the mctl-api token rules (at least 32 characters, never shared with
  another principal).
- `base-service` has `metrics.enabled`/`metrics.port` (a named `metrics`
  container and service port) and a ServiceMonitor template that
  `metrics.serviceMonitor: false` turns off in favour of a native
  VMServiceScrape. Tracing reads the standard `OTEL_EXPORTER_OTLP_*`
  environment and is off when no endpoint is set; the endpoint value is set
  in the step 12 gitops PR.

## Open questions (as investigated; the remaining two are accepted as designed)

- "20 tasks per day": the design uses a rolling 24 hours, not a UTC calendar day. "Month" is the UTC calendar month.
- Whether a follow-up message on an existing task counts as a task for the daily limit. The design says no: only new tasks count. Follow-up turns are still covered by the spend caps and the concurrency lease.
