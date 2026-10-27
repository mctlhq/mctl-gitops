# Design: issue-4-mctl-support-s1c-budgets-rate-limits-and

## Current state

The clone is at `8f8670d`, the merge of S1b, mctlhq/mctl-support#8.

- **Request path.** `app.py:create_app` wraps the inner executor in this order:
  1. `AdmissionMiddleware` (`admission.py`) runs whoami and the tenant
     allowlist. It produces a `Caller(principal_id, tenant, is_admin, bearer)`.
  2. `SupportRequestHandler.on_message_send` (`handler.py`) reserves
     `(principal, messageId)` and creates the `task_owners` row in one
     transaction (`idempotency.admit_message`).
  3. `LifecycleExecutor.execute` (`executors/lifecycle.py`) enqueues the new
     task, opens one WorkItemExecution, mints the `support` run token, runs
     the inner executor, then revokes the token and finishes the execution in
     `_close`. `TERMINAL` already contains `TASK_STATE_REJECTED`.
  4. `AgentExecutor.execute` (`agent/executor.py`) loads the context
     transcript and builds a `ToolRegistry` and a `Budget`. It calls
     `run_loop` and maps `LimitExceeded`, `AgentFailure`, `ProviderError` and
     MCP errors to `TASK_STATE_FAILED`.
- **Limits.** `agent/limits.py:Budget` is in-memory and created once per
  `execute()` call, so per A2A turn and not per task. `add_cost` runs after
  `provider.turn` returns (`agent/loop.py:41`) and raises once the sum
  exceeds `cost_cap_usd`. Unknown usage already fails closed. There are no
  tenant, workspace or principal limits.
- **Config.** `config.py:Config` holds `task_cost_cap_usd=2.0`, commented
  "provisional until S1c", and the prices `input_usd_per_mtok` and
  `output_usd_per_mtok`. `validate()` refuses non-finite or non-positive
  prices and caps.
- **Escalation stub.** `agent/registry.py` defines
  `ESCALATE = _t("escalate", ..., ["reason"])` in `LOCAL_TOOLS`. `dispatch`
  appends the reason to `registry.escalations` and answers "escalation is not
  wired until S1c". `validate_args` accepts only string arguments.
  `agent/result.py:parse` forces `escalation_id=None`, and `check_evidence`
  copies `escalation_requests`. The prompt (`agent/prompt.py`,
  `PROMPT_VERSION = "s1b-1"`) tells the model to call `escalate` with a
  reason.
- **mctl-api client.** `mctl_api.py:HttpMctlApi._call` fails closed on every
  non-2xx answer. It has no incident or usage calls. `FakeMctlApi` records
  calls for tests.
- **Store.** `store/schema.py` holds `contexts`, `task_owners`,
  `message_reservations`, `transcripts`, `model_transcripts` and
  `support_schema_migrations`. `migrate.py` uses `create_all` under an
  advisory lock with `CURRENT_VERSION = 2`.
- **Observability.** No metrics or tracing code exists. `opentelemetry-api`
  1.45.1 is in `uv.lock` only as a transitive dependency. There is no
  `prometheus_client`. `PUBLIC_PATHS` in `admission.py` covers the card and
  the health routes only.
- **Tests.** `tests/test_agent.py` uses the `stack` fixture and
  `tests/fakes.py` (`FakeMcpServer`, scripted turns with `Usage`).
  `test_t2_the_assertion_is_meaningful_when_the_allowlist_check_is_off`
  shows the existing "the test fails with the check removed" pattern. CI runs
  against Postgres 16 (`.github/workflows/ci.yml`).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-support/values.yaml`:
  - tenant `admins`, image `ghcr.io/mctlhq/mctl-support:0.1.1`,
    `replicaCount: 2`, `automountServiceAccountToken: false`;
  - env `SUPPORT_EXECUTOR: fake`, `SUPPORT_ALLOW_FAKE_IN_PRODUCTION: "true"`,
    `SUPPORT_ALLOWED_TENANTS: namax66`, `MCTL_API_URL: https://api.mctl.ai`;
  - `envFrom` `admins-mctl-support-db-creds` from Vault
    `teams/admins/mctl-support/database`;
  - ingress hosts `support.mctl.ai` and `admins-mctl-support.mctl.ai`;
  - no metrics port and no model or provider env.
- `mctl_get_service_status(admins, mctl-support)`: ArgoCD Healthy/Synced,
  imageTag 0.1.1, `hasDatabase: true`.
- `mctl_list_incidents(limit=2)`: returned `count: 0`. The incident record
  shape (whether `source`, `type` and `fingerprint` exist) could not be
  observed and is recorded under Open questions in requirements.md.
- The ADR-012 usage-ledger producer endpoint and the mctl-api incident
  handler were not readable from this run. The contract below is a proposal
  for mctl-api to confirm.

Because production runs the fake executor, the model loop and therefore every
cap in this proposal take effect only after a later gitops change sets
`SUPPORT_EXECUTOR=agent`.

## Proposed solution

### 1. Spend ledger (`src/mctl_support/budget/ledger.py`, new)

New tables in `store/schema.py`. The migration moves to `CURRENT_VERSION = 3`;
`create_all` stays additive.

- `spend_periods(scope_kind, scope_key, period, committed_usd, reserved_usd, updated_at)`:
  - Primary key `(scope_kind, scope_key, period)`.
  - `scope_kind` is `workspace`, `tenant` or `task`. `scope_key` is `*`, the
    tenant name or the task id. `period` is `YYYY-MM` (UTC), or `-` for a
    task.
  - Amounts are `Numeric(12,6)`.
- `spend_turns(turn_id, task_id, tenant, period, reserved_usd, actual_usd, state, created_at, settled_at)`:
  - `state` is `reserved` or `settled`. One row per model turn.

`SpendLedger.reserve(task_id, tenant, amount, now)` runs one transaction:
- It upserts the three period rows, then takes `SELECT ... FOR UPDATE` on
  them in a fixed order (workspace, tenant, task) so it cannot deadlock.
- For each layer it checks `committed + reserved + amount <= cap`.
- On the first violation it raises `BudgetExhausted(layer, resets_at)`.
  Nothing is written.
- Otherwise it adds `amount` to each `reserved_usd` and inserts a
  `spend_turns` row.

`SpendLedger.settle(turn_id, usage)`:
- It moves the reservation to `committed` at the actual cost, priced with
  the existing `input_usd_per_mtok` and `output_usd_per_mtok`.
- If usage is missing, it commits the full reservation.
- It writes the usage outbox row (section 3) in the same transaction.

Stale `reserved` turns are released when a replica dies mid-turn. The
existing `RetentionLoop` (`retention.py`) settles any turn older than
`task_deadline_seconds + 60s` at its full reservation, never at zero.

The reservation is `SUPPORT_TURN_RESERVATION_USD`. Its default is computed
when the config is validated, as `MAX_TOKENS * output price` plus a
configured input-token allowance. It must be at most the task cap, so a task
always gets at least one turn.

Placement of the check:
- `agent/limits.py:Budget` keeps tool-call and time limits. It gains
  `async before_turn()` and `async after_turn(usage)`, which call the ledger.
- `agent/loop.py:run_loop` calls `await budget.before_turn()` immediately
  before `provider.turn(...)`. It replaces `budget.add_cost(turn.usage)` with
  `await budget.after_turn(turn.usage)`.
- The per-task layer is keyed by task id in Postgres, so a follow-up turn of
  the same task sees the earlier spend. Today the cap resets on every turn.

Admission-time check (rejection before any external call):
`LifecycleExecutor.execute`, after the new task is enqueued and before
`_open_execution`, calls `Gate.admit(caller, task_id, new_task)`
(`src/mctl_support/budget/gate.py`). The gate checks:
1. the workspace and tenant layers: `committed + reserved + one reservation <= cap`;
2. for a new task, the daily count in `task_starts`;
3. the concurrency lease.

A refusal emits `TASK_STATE_REJECTED` with the gate's message and returns.
`_close` then has no execution and no token to close. The message names the
layer and the reset time and never includes amounts of other tenants.

### 2. Rate limits per principal

- `task_starts(task_id PK, principal_id, tenant, started_at)` is inserted by
  the gate when a new task passes. The daily check counts rows with
  `started_at > now - 24h`. Rejected tasks are not inserted. Retention
  deletes rows older than 2 days.
- `principal_leases(principal_id PK, task_id, lease_until)` is acquired with
  `INSERT ... ON CONFLICT (principal_id) DO UPDATE ... WHERE principal_leases.lease_until < :now OR principal_leases.task_id = :task_id`.
  - Zero affected rows means another live task holds the lease: rejected.
  - `lease_until = now + task_deadline_seconds + 60`. No turn outlives its
    deadline (`Budget.guard`), so no heartbeat is needed.
  - The lease is released in `LifecycleExecutor._close`.
  - An input-required task does not hold the lease.
- Concurrency is checked for follow-up turns too. The daily count applies
  only to new tasks.
- Config: `SUPPORT_CONCURRENT_TASKS_PER_PRINCIPAL` (fixed at 1 in S1c;
  validated `== 1` because the lease table holds one row per principal) and
  `SUPPORT_TASKS_PER_DAY` (default 20, `>= 1`).

### 3. Usage records (ADR-012 producer)

- `usage_outbox(id PK, turn_id UNIQUE, payload JSON, attempts, next_attempt_at, delivered_at)`.
- The payload includes:
  - `producer: "mctl-support"`, `agent: "mctl-support"`;
  - `execution_kind: "support"` (the non-DevLoop marker, so no
    `devloop_stage`);
  - `tenant`, `execution_id` (WorkItemExecution), `run_id` (task id) and
    `turn_id`;
  - `provider`, `model`, `input_tokens`, `output_tokens`, `calculated_cost`
    and `outcome`.
- A `UsageShipper` loop, started next to `RetentionLoop` in the app
  lifespan, posts pending rows with `Authorization: Bearer <usage-writer>`
  and `Idempotency-Key: <turn_id>`. It backs off exponentially and marks rows
  delivered on 2xx.
- Delivery failures are logged and counted. They never change the local
  ledger, which is the enforcement source.
- The client lives in `mctl_api.py` as `post_usage_record`. Its path and
  field names are behind one function, so confirming ADR-012 is a one-place
  change.

### 4. `escalate` local tool (`src/mctl_support/agent/escalation.py`, new)

The tool definition replaces the `reason` schema in `registry.py`:
- `kind`: an enum of the four types.
- `summary`: a string of at most 2000 characters.
- `evidence`: an array of 1 to 10 strings, each matching a `tool:`/`skill:`
  source of this task.
- `signature`: an optional string of at most 300 characters, the error
  signature.
- `tenant`: optional; only checked.

`ToolDef` gains an explicit JSON schema for this one tool. `validate_args`
gains array and enum checks for it. The read tools are unchanged.

`ToolRegistry.dispatch` routes `escalate` to `Escalator.escalate(call)`. The
`Escalator` is built per task with the bound tenant, the task id, the caller
principal and the registry's evidence sources. It runs these steps in order,
and steps 1-3 are purely local:

1. Schema validation. A failure is a tool error result.
2. If `tenant` is present and differs from the bound tenant, it returns
   `{"error": "escalation refused: tenant does not match this task"}`,
   counts `support_tool_calls_total{tool="escalate",status="refused"}` and
   makes no network call. `support_escalations_total{kind}` counts only
   incidents created or reused.
3. Evidence references must be in `registry.evidence_sources()`. Unknown
   references are refused.
4. Fingerprint:
   - `normalize(signature or summary, tenant)` lowercases the text and
     replaces the bound tenant name with `<tenant>`. It replaces UUIDs,
     hex runs of 7 or more, IPs, ISO timestamps and digit runs with
     placeholders, collapses whitespace and truncates to 300 characters.
   - `fingerprint = "support:" + kind + ":" + sha256(normalized)[:32]`.
   - The fingerprint holds no tenant data, so it doubles as mctl-api's
     `normalized_fingerprint`.
5. Rate limit and dedupe in Postgres, in one transaction:
   - `escalations(id PK, task_id, principal_id, tenant, kind, fingerprint, summary, evidence JSON, incident_id, state, created_at)`.
   - Unique `(tenant, fingerprint)` among rows created within
     `SUPPORT_ESCALATION_DEDUPE_HOURS` (default 24). This is enforced as a
     select-then-insert under a per-tenant advisory lock.
   - Limits: `SUPPORT_ESCALATIONS_PER_TASK` (default 1) and
     `SUPPORT_ESCALATIONS_PER_TENANT_PER_DAY` (default 5).
   - A dedupe hit with an `incident_id` returns that id.
6. It calls `MctlApi.create_support_incident(...)` with the producer
   credential (`SUPPORT_INCIDENT_PRODUCER_TOKEN`, a `Secret`) and
   `Idempotency-Key: <escalation id>`. The body is:
   `{source: "support", tenant, type: kind, fingerprint, summary, evidence: [refs], support_task_id, caller_principal, severity: "warning"}`.
   It stores the returned `incident_id`.
   - On failure the row stays `pending`, so a retry in the same task reuses
     the key, and the tool returns an explicit error.

`ToolRegistry.escalation_id` holds the last created or reused incident id.
`check_evidence` takes it and sets `SupportResult.escalation_id`. `parse`
still ignores any id the model writes. The prompt moves to `s1c-1` and
describes the new arguments.

The run token never reaches the escalator. The producer credential is used
only by `create_support_incident`; no other method of `HttpMctlApi` accepts
it.

### 5. mctl-api companion change (separate PR in mctlhq/mctl-api)

- The incidents API accepts `source=support` with `type` in the four kinds.
  It requires `tenant`, and dedupes on `(tenant, fingerprint)` without ever
  merging across tenants. It stores `support_task_id`, `caller_principal`
  and the evidence references.
- A narrow `support-incident-producer` service principal is allowed only
  `POST` of `source=support` incidents. Editing, resolving or listing is 403.
- A `usage-writer` principal for mctl-support exists per ADR-012.
- `GET /api/v1/incidents/support/aggregation` is admin-only (non-admin gets
  403). It returns
  `[{normalized_fingerprint, kind, affected_tenants: [..], count}]` grouped
  over active `source=support` incidents.
- mctl-support tests run against `FakeMctlApi` extensions that mirror this
  contract. The mctl-api tests own the two-tenant aggregation and the
  non-admin criteria.

### 6. Metrics (`src/mctl_support/observability/metrics.py`, new)

- Pin `prometheus-client` exactly, in its own dependency bump commit.
- A dedicated registry is served by a second Starlette/uvicorn listener on
  `SUPPORT_METRICS_PORT` (default 9090), started from `__main__.py`. It is
  not on the A2A app, so it is never behind the public ingress and never
  through admission.
- The issue's metrics are emitted at these points:

  | Metric | Emitted in |
  |---|---|
  | tasks total and duration | `LifecycleExecutor` final state |
  | tool calls | `ToolRegistry.dispatch`; status is `ok`, `denied`, `error` or `refused` |
  | tokens and cost | `SpendLedger.settle` |
  | budget rejections | `Gate`, `before_turn` |
  | escalations | `Escalator` |
  | scope denials | `McpDenied` in `dispatch` |

- The tenant label goes through `tenant_label(t)`, which returns `t` if it
  is in `SUPPORT_ALLOWED_TENANTS` and otherwise `other`. Tool labels come
  from the closed allowlist, and any unknown name is `unknown`.

### 7. Traces (`src/mctl_support/observability/tracing.py`, new)

- Pin `opentelemetry-api`, `opentelemetry-sdk` and
  `opentelemetry-exporter-otlp-proto-http` exactly.
- With `OTEL_EXPORTER_OTLP_ENDPOINT` unset, only the no-op API tracer is
  used.
- Spans and where they start:

  | Span | Started in |
  |---|---|
  | `a2a.request` | middleware |
  | `support.task` | `LifecycleExecutor.execute`, with attrs `support.task_id`, `support.context_id`, `support.work_item_execution_id` and `support.tenant` |
  | `model.turn` | `run_loop`, with provider, model and tokens |
  | `tool.call` | `dispatch` |
  | `mctl_api.request` | `HttpMctlApi._call` and `McpClient._rpc` |

- `traceparent` is injected into the outgoing httpx headers. Arguments, tool
  output and bearer values are never span attributes.

### 8. Config and README

`Config` gains these fields, all validated finite and above 0, and all
`Secret` where they are credentials:
- `workspace_monthly_cap_usd`, `tenant_monthly_cap_usd` and
  `turn_reservation_usd`; `task_cost_cap_usd` defaults to 0.50;
- `tasks_per_day`, `escalations_per_task`, `escalations_per_tenant_per_day`
  and `escalation_dedupe_hours`;
- `usage_writer_token` and `incident_producer_token`;
- `metrics_port`.

`validate()` also checks that the task cap is at most the tenant cap, which
is at most the workspace cap, and that the reservation is at most the task
cap. With `executor == "agent"`, both producer tokens are required: missing
tokens refuse start, like a missing model key. The README configuration table
and the "Escalation is a stub" line are updated, and `agent/agent.yaml`
describes `escalate`.

## Alternatives

- **Pre-call check against an in-memory or per-replica counter** (extending
  today's `Budget`). Dropped: two replicas share tenants and the workspace
  (`replicaCount: 2`), so per-replica counters overshoot by up to a factor of
  2. They also reset on restart, which is fail-open.
- **Query Anthropic's usage/cost API, or rely only on the console workspace
  limit.** Dropped as the enforcement point: the data is delayed, cannot be
  attributed per tenant or task, and a console limit fails mid-task rather
  than rejecting before the call. The console limit remains a manual
  backstop.
- **Check caps only after the call, as `Budget.add_cost` does.** Dropped: the
  issue requires refusal before any model call. A post-check lets a capped
  tenant spend one more turn per task forever.
- **Let the model's run token carry an incident-create permission.**
  Rejected by the issue: escalation must be a service-interpreted local tool.
  A token permission would let injected text drive incident creation without
  the tenant, schema and rate checks.
- **Use mctl-api's usage ledger as the cap source.** Dropped for now: it adds
  a network dependency to every pre-call check, and its producer coverage is
  incomplete (mctl-agents#507). The local ledger enforces, and mctl-api
  receives copies.

## Platform impact

- **Migrations.** These tables are additive, created by `create_all`:
  - `spend_periods`
  - `spend_turns`
  - `task_starts`
  - `principal_leases`
  - `usage_outbox`
  - `escalations`

  `CURRENT_VERSION` becomes 3. There are no changes to existing tables.
  Running an old image after the migration is safe, because it ignores the
  new tables.
- **Backward compatibility.**
  - The `escalate` tool schema changes. Stored S1b transcripts may contain
    `escalate` calls with `reason`; they replay as history only and are
    never re-dispatched.
  - The default task cap drops from 2.00 to 0.50, which is intended.
  - `SupportResult.escalation_id` can now be non-null. A2A clients already
    see the field.
- **Credentials.** Two new narrow service credentials come from Vault via a
  new ExternalSecret, through a gitops change in mctl-gitops. Neither is an
  admin token. The pod still mounts no ServiceAccount token.
- **Resources.**
  - One extra listener and a background shipper. CPU and memory stay within
    the current 200m/256Mi requests.
  - Each model turn adds one short Postgres transaction with row locks on at
    most three rows. Workspace-row contention is bounded by the pilot's
    volume: one concurrent task per principal and one allowlisted tenant.
- **Rollout dependency.** Escalation and the aggregation need the mctl-api
  companion release, and usage shipping needs the ADR-012 endpoint. Without
  them, `escalate` returns an explicit tool error and outbox rows accumulate.
  Neither reports success falsely.
- **Risks and mitigations.**
  - A wrong price config could undercharge. Mitigation: prices are validated
    above 0, and a missing usage report charges the full reservation.
  - A reservation that is too small could overshoot a cap by one turn's
    excess. Mitigation: the default is the worst-case output cost, and
    overshoot is visible in `support_model_cost_usd_total`.
  - Advisory-lock or row-lock deadlocks. Mitigation: a fixed lock order.
  - A metrics port exposed publicly. Mitigation: a separate listener, and
    the ingress has no route to it.
