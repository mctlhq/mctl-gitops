# Tasks: issue-4-mctl-support-s1c-budgets-rate-limits-and

- [ ] 1. Add the config fields to `src/mctl_support/config.py`.
  - Work:
    - `workspace_monthly_cap_usd` (50), `tenant_monthly_cap_usd` (10) and
      `task_cost_cap_usd`, whose default changes 2.0 -> 0.50.
    - `turn_reservation_usd`, defaulted from `MAX_TOKENS` times the output
      price plus an input allowance.
    - `tasks_per_day` (20), `concurrent_tasks_per_principal` (1),
      `escalations_per_task` (1), `escalations_per_tenant_per_day` (5) and
      `escalation_dedupe_hours` (24).
    - `usage_writer_token` and `incident_producer_token` (`Secret`), and
      `metrics_port` (9090).
  - Validation:
    - finite and above 0;
    - task cap <= tenant cap <= workspace cap;
    - reservation <= task cap;
    - concurrency == 1;
    - both tokens required when `executor == "agent"`.
  - DoD: `tests/test_config.py` covers every refusal; README config table
    updated.
- [ ] 2. Add the new tables to `src/mctl_support/store/schema.py` and bump
  `CURRENT_VERSION` to 3 in `migrate.py` (depends on 1).
  - Tables: `spend_periods`, `spend_turns`, `task_starts`,
    `principal_leases`, `usage_outbox` and `escalations`.
  - DoD: the migration is idempotent on Postgres and SQLite; an existing v2
    database upgrades.
- [ ] 3. Add `src/mctl_support/budget/ledger.py` with `SpendLedger.reserve`,
  `settle` and `release_stale` (depends on 2).
  - Lock order: workspace, tenant, task. Use `FOR UPDATE` on Postgres.
  - `BudgetExhausted(layer, resets_at)`.
  - `settle` writes the `usage_outbox` row in the same transaction.
  - Missing usage commits the full reservation.
  - DoD: unit tests for each layer and the month rollover; a concurrent
    reserve test on Postgres shows no overshoot beyond one reservation.
- [ ] 4. Wire the ledger into `agent/limits.py` and `agent/loop.py`
  (depends on 3).
  - Add `Budget.before_turn()` and `Budget.after_turn(usage)`.
  - `run_loop` calls `before_turn` immediately before `provider.turn`.
  - `AgentExecutor` builds the budget with the task id and the tenant.
  - A refusal mid-task raises `LimitExceeded` with the layer message, so the
    task ends failed.
  - DoD: the per-task cap persists across follow-up turns of one task.
- [ ] 5. Add `src/mctl_support/budget/gate.py` with `Gate.admit` (depends on
  3).
  - Checks: workspace and tenant headroom, the daily `task_starts` count for
    new tasks, and the `principal_leases` acquire.
  - Call it in `LifecycleExecutor.execute` before `_open_execution`. A
    refusal emits `TASK_STATE_REJECTED` with a clear message.
  - Release the lease in `_close`.
  - `RetentionLoop` prunes `task_starts` older than 2 days and calls
    `release_stale`.
  - DoD: a rejected task created no execution, minted no token and made no
    provider call.
- [ ] 6. Ship usage records (depends on 3).
  - Add `HttpMctlApi.post_usage_records(token, records)` for the existing
    `POST /api/v1/usage/records` and a `FakeMctlApi` counterpart that derives
    ids from content and answers `accepted`/`deduped` like mctl-api.
  - Add a `UsageShipper` loop in the app lifespan with backoff; it does not
    start when `SUPPORT_USAGE_WRITER_TOKEN` is unset.
  - Record fields as in design.md section 3: `session_id` = task id,
    `result_uuid` = turn id, `agent` = `mctl-support`, no `devloop_stage`,
    `execution_id`, `work_item_id`, provider, model, tokens, cost, outcome.
    No `id`, no tenant, no `Idempotency-Key`.
  - DoD: a re-delivered turn is `deduped` and marked delivered; a failed
    delivery leaves the row pending; a 400 parks the named row only.
- [ ] 7. Implement `escalate` (depends on 2).
  - Add `agent/escalation.py`. The new `ESCALATE` schema is `kind` (enum),
    `summary`, `evidence[]`, optional `signature` and optional `tenant`.
  - Extend `validate_args` for array and enum arguments of this tool only.
  - Add `normalize()` and `fingerprint()`.
  - Do tenant-mismatch refusal, evidence-reference checks, the per-task and
    per-tenant rate limits, and the `(tenant, fingerprint)` dedupe in the
    `escalations` table.
  - Add `HttpMctlApi.create_support_incident` using only the producer
    credential on the existing `POST /api/v1/incidents`, with `id` set to
    the escalation id; `409` on that id and a dedupe hit both mean the
    incident exists. Task id, caller principal and evidence references go
    into `evidence[]` (design.md section 4, step 6).
  - Pass `escalation_id` into `check_evidence` and `SupportResult`.
  - Bump the prompt to `PROMPT_VERSION = "s1c-1"` with the new arguments.
  - Update the `agent/agent.yaml` description.
  - DoD: the stub text "not wired until S1c" is gone; tests T6-T10 pass.
- [ ] 8. Add metrics in `observability/metrics.py` (depends on 4, 5, 7).
  - Pin `prometheus-client` exactly in its own commit.
  - Serve the dedicated registry on a separate listener started by
    `__main__.py`.
  - Emit all eight metrics at the points named in design section 6, through
    `tenant_label()`.
  - DoD: a test scrapes the listener and finds every metric name; no label
    value equals a principal id, a token or a log line.
- [ ] 9. Add traces in `observability/tracing.py` (depends on 4).
  - Pin `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-http`
    exactly.
  - Spans: A2A request, support task, model turn, tool call and mctl-api
    request.
  - Attributes `support.task_id` and `support.work_item_execution_id`.
  - Inject `traceparent` in `HttpMctlApi._call` and `McpClient._rpc`.
  - The tracer is a no-op without `OTEL_EXPORTER_OTLP_ENDPOINT`.
  - DoD: an in-memory exporter test sees the span chain with one trace id
    and the `traceparent` header on the fake mctl-api request.
- [ ] 10. mctl-api companion: mctlhq/mctl-api#830 (its own DevLoop; **not
  part of this repository's implementation**, required before step 12).
  - The `support-incident-producer` principal, limited to `POST
    /api/v1/incidents` with `source=support`.
  - Admin-only `GET /api/v1/incidents/support/aggregation`.
  - The incident fields, the per-tenant dedupe and the usage writer already
    exist and are not part of it.
- [ ] 11. Update the README.
  - Replace "Escalation is a stub until S1c".
  - Document the limits, the metrics port and the credentials.
  - DoD: `ruff check`, `ruff format --check` and `pytest` are green in CI.
- [ ] 12. (Not part of this repository's implementation.) Change mctl-gitops `services/admins/mctl-support/values.yaml`
  (follow-up PR, after 10 is released).
  - Add the ExternalSecret for the two producer tokens.
  - Add the metrics port and scrape configuration.
  - Add the OTLP endpoint.
  - DoD: the service starts with `SUPPORT_EXECUTOR=agent` only once these
    are present; this proposal does not flip the executor.

## Tests

- [ ] T1. Workspace layer: seed `spend_periods` so the workspace month is
  exhausted, then send a new task.
  - Expected: `TASK_STATE_REJECTED` with a workspace message, zero provider
    calls, no `create_execution` and no mint.
  - Companion test: with `Gate.admit` and `before_turn` monkeypatched to
    no-ops, the same assertion fails (the provider was called).
- [ ] T2. Tenant layer: the same as T1 for the tenant month. Another tenant
  is still admitted.
- [ ] T3. Task layer: a task with $0.50 cap and a reservation such that the
  second turn would exceed the cap.
  - Expected: the provider is called once, and the task fails with the task
    budget message before the second call.
  - Companion "check removed" test, as in T1.
- [ ] T4. Concurrency: while principal A's task is blocked in a scripted
  slow turn, a second new task from A is `REJECTED`. A task from principal B
  runs. After A's first task ends, A can start again. An expired lease is
  taken over.
- [ ] T5. Daily limit: the 21st new task within 24h from one principal is
  `REJECTED`. Rejected tasks do not count, and follow-ups on an existing task
  do not count.
- [ ] T6. `escalate` with `tenant` set to a tenant other than the task's
  bound tenant.
  - Expected: a refusal tool result, zero `create_support_incident` calls,
    and `support_tool_calls_total{tool="escalate",status="refused"}`
    incremented.
- [ ] T7. `escalate` with evidence not from this task, an unknown `kind` or
  an over-long summary is refused locally with no network call.
- [ ] T8. Two tasks in tenants `t-a` and `t-b` escalate the same signature
  with different ids and numbers.
  - Expected: the same fingerprint, and two `create_support_incident` calls,
    each with its own bound tenant.
  - Repeating in `t-a` within the dedupe window reuses the incident id
    without a second call.
- [ ] T9. Escalation rate limit: a second `escalate` in one task and the
  sixth in one tenant per day are refused, so an injected log line repeated
  N times creates at most one incident.
- [ ] T10. An incident post failure gives an explicit tool error and a null
  `escalation_id`. The producer token is the only credential sent, never the
  run token or the bearer.
- [ ] T11. Usage outbox: each settled turn creates one outbox row with the
  non-DevLoop marker and the tenant. The shipper retries after a 503 and
  delivers once with the same idempotency key.
- [ ] T12. Metrics and traces as in tasks 8 and 9. A failed MCP call
  increments `support_agent_scope_denials_total` on `McpDenied`.
- [ ] T13. Two-replica test (`tests/test_replicas.py` pattern): concurrent
  reserves on two app instances sharing Postgres never exceed the tenant cap
  by more than one reservation.

## Rollback

- mctl-support: redeploy the previous image tag (0.1.1, or the last S1b tag)
  via `values.yaml`.
  - The v3 tables are additive and ignored by older images; no down-migration
    is needed.
  - Production currently runs `SUPPORT_EXECUTOR=fake`, so no model spend
    depends on this release until a deliberate executor switch.
- To disable escalation without a rollback, unset
  `SUPPORT_INCIDENT_PRODUCER_TOKEN` and the executor. Validation will refuse
  `agent`, so also set the executor back to `fake`. Alternatively, revoke the
  producer principal in mctl-api; `escalate` then returns explicit errors.
- Created support incidents remain in mctl-api and are resolved by the owner
  as usual.
- Pending `usage_outbox` rows can be shipped later or dropped. The local
  ledger stays the record.
