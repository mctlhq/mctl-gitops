# Agent-worker policy-denial and job-cost observability

## Context

The communication agent (M6) is instrumented for queue flow but not for the two
axes that decide whether guarded autopilot can ever be enabled: what a job costs
and how often policy refuses an action. `internal/metrics/metrics.go` registers
six `mctl_agent_*` families (`AgentEventsReceivedTotal`, `AgentJobsTotal`,
`AgentDeadLetterTotal`, `AgentActionsExecutingStuck`,
`AgentApprovalLatencySeconds`, `AgentExecutorRestartsTotal`) and none of them
counts a policy denial, even though `policy.Evaluate`
(`internal/agent/policy/policy.go:285`) already produces a reason string at every
one of its 17 `deny(...)` sites. Spend is worse than unalerted: it is parsed and
discarded — `ClaudeResult.TotalCostUSD` (`internal/agentworker/worker.go:177`) is
populated by `ParseClaudeResult` and never read, and `agent_jobs`
(`internal/db/agent_schema.go:424` SQLite, `:635` Postgres) has no cost column.
`AGENT_MAX_BUDGET_USD` is a per-job ceiling handed to the `claude` CLI
(`internal/agentworker/claudeinvoker.go:157`); nothing aggregates across jobs.

Two further gaps follow from the same root cause. Nothing records which
credential domain a worker ran against, so a claim of quota isolation between
deployments has no machine-checkable counterpart. And `CheckResult`
(`internal/agentworker/worker.go:212`) collapses every `is_error` result into one
undifferentiated error, so a run that stopped because the account hit a usage
limit is indistinguishable from one that hit `error_max_turns`. This proposal
adds measurements only. Alert rules in
`deploy/alerts/mctl-telegram.rules.yaml`'s `mctl-telegram-agent` group are a
deliberate follow-up, because a rule cannot reference a series that does not
exist yet.

## User stories

- AS a platform operator I WANT a counter of policy denials broken down by
  denial cause SO THAT repeated refused attempts — the primary anomaly signal
  named by the C2 safety work — become measurable and, later, alertable.
- AS a platform operator I WANT to distinguish a denial that happened when the
  model proposed an action from one that happened when an already-approved
  action was about to be sent SO THAT I can tell an ordinary policy refusal from
  the far more alarming case of a send being stopped at execution time.
- AS a service owner I WANT per-job Claude spend exported as a metric and
  persisted on the job row SO THAT I can see daily and monthly cost without
  reading logs, and correlate spend to individual jobs.
- AS a service owner I WANT spend recorded even when the job subsequently fails
  SO THAT money burned by failing jobs is not invisible.
- AS a service owner I WANT a worker to refuse to start without a declared
  credential-domain identifier SO THAT no worker can ever run unattributably
  against an unknown quota pool.
- AS an on-call engineer I WANT a usage-limit result counted separately from a
  generic `is_error` result SO THAT "we ran out of quota" is distinguishable
  from "the model misbehaved" at a glance.
- AS a privacy reviewer I WANT to confirm no new metric label or log line
  carries a Telegram id, username, peer, message body or credential value SO
  THAT the observability work does not become a data-exposure path.

## Acceptance criteria (EARS)

### Policy denials

- WHEN `policy.Evaluate` returns a `Deny` decision AND that decision is consumed
  by `internal/agentapi.handleProposeReply`
  (`internal/agentapi/actions.go:207`), `internal/agentapi`'s owner-notification
  path (`internal/agentapi/actions.go:429`), `executor.send`
  (`internal/agent/executor/executor.go:283`), or `executor.recoverOne`
  (`internal/agent/executor/executor.go:561`), THE SYSTEM SHALL increment a
  counter named `mctl_agent_policy_denials_total` by 1.
- WHILE the counter exists THE SYSTEM SHALL label it with exactly two
  dimensions: `reason` (a stable, closed-set denial code) and `surface` (the
  call site that consumed the decision, one of `propose_reply`, `owner_notify`,
  `executor_send`, `executor_recover`).
- WHILE denial reasons are being turned into label values THE SYSTEM SHALL use a
  code drawn from a compile-time-fixed set, never the free-text reason string,
  because three existing reasons interpolate a runtime value via `strconv.Quote`
  (`policy.go:305`, `:329`, `:338`) and would otherwise make label cardinality
  unbounded.
- IF a denial arrives carrying no recognised code THEN THE SYSTEM SHALL record
  it under the single fallback label value `unknown` rather than inventing a new
  label value.
- WHILE denials are being counted THE SYSTEM SHALL keep `policy.Evaluate` free
  of side effects: it performs no metric increment, no logging and no I/O, and
  remains callable in a unit test with no registry.
- WHILE the counter is exposed THE SYSTEM SHALL NOT label it by account,
  user id, conversation id, peer id or username.

### Job cost

- WHEN `ParseClaudeResult` succeeds inside `ClaudeInvoker.Run`
  (`internal/agentworker/claudeinvoker.go:182`) THE SYSTEM SHALL record the
  parsed cost as a metric before calling `CheckResult` (`:186`), so that a job
  which then fails `CheckResult` still reports what it spent.
- WHEN a cost is recorded THE SYSTEM SHALL increment
  `mctl_agent_job_cost_usd_total` by exactly the parsed `total_cost_usd`,
  labelled `result="success"` when `is_error` is false and `result="error"` when
  it is true.
- WHEN a cost is recorded THE SYSTEM SHALL also report it to the agent API so it
  is persisted on the corresponding `agent_jobs` row's `cost_usd` column.
- IF the `claude` result JSON has no `total_cost_usd` key, or its value is JSON
  `null`, THEN THE SYSTEM SHALL record no metric sample and persist SQL NULL —
  never `0` — because a false zero is indistinguishable from a genuinely free
  run and would understate spend.
- IF the `claude` result JSON cannot be parsed at all THEN THE SYSTEM SHALL
  leave `agent_jobs.cost_usd` NULL and return the existing parse error
  unchanged.
- IF reporting the cost to the API fails THEN THE SYSTEM SHALL log a warning and
  continue, and SHALL NOT convert an otherwise-successful job into a failure.
- WHEN `internal/db.Migrate` runs against a fresh database THE SYSTEM SHALL
  create `agent_jobs.cost_usd` as a nullable floating-point column in both the
  SQLite and Postgres schema paths.
- WHEN `internal/db.Migrate` runs against a database whose `agent_jobs` table
  already exists without the column THE SYSTEM SHALL add it via
  `addColumnIfMissing` with no DEFAULT, leaving every pre-existing row NULL.
- WHILE a cost report is being applied THE SYSTEM SHALL fence it on the job's
  claim attempt, so a stale worker whose claim was requeued cannot overwrite a
  newer attempt's recorded cost.
- WHILE the cost-report endpoint exists THE SYSTEM SHALL NOT expose it as an MCP
  tool: it is absent from `allowedTools`
  (`internal/agentworker/claudeinvoker.go:49`) and from `NewMCPServer`, so the
  model can never assert its own spend.

### Credential-domain identity

- WHEN the agent worker starts in poll-loop mode (`cmd/agent-worker/main.go`
  `run()`) THE SYSTEM SHALL read `AGENT_CREDENTIAL_DOMAIN_ID` through
  `requireEnv` and SHALL exit non-zero with a clear error when it is unset or
  empty.
- IF `AGENT_CREDENTIAL_DOMAIN_ID` contains characters outside
  `[A-Za-z0-9._:/-]`, or exceeds 128 characters, THEN THE SYSTEM SHALL refuse to
  start, so a pasted credential or a free-text blob cannot become a metric label
  value.
- WHEN the worker has started THE SYSTEM SHALL expose an info-style gauge
  `mctl_agent_credential_domain`, constant value 1, labelled `domain_id` with
  the configured value, following the `mctl_telegram_replica_id` precedent
  (`internal/metrics/metrics.go`).
- WHEN `/livez` or `/healthz` is requested on the worker
  (`cmd/agent-worker/health_server.go`) THE SYSTEM SHALL include the credential
  domain id in the response body while preserving the existing first-line
  `ok` / `not ok` contract and the existing status codes.
- WHILE the value is being handled THE SYSTEM SHALL treat it as a non-secret
  identifier (a Vault path or account label) and SHALL NOT accept, log or
  expose the credential itself.
- WHEN `docs/agent-worker.md` is rendered THE SYSTEM SHALL list
  `AGENT_CREDENTIAL_DOMAIN_ID` in the environment-variable table
  (`docs/agent-worker.md:75-82`) marked required.

### Quota exhaustion

- WHEN `CheckResult` is given a result whose `is_error` is true and whose
  `subtype` identifies a usage-limit or quota condition THE SYSTEM SHALL return
  an error that satisfies `errors.Is(err, ErrClaudeUsageLimit)`.
- WHILE that error is returned THE SYSTEM SHALL keep it satisfying
  `errors.Is(err, ErrClaudeReportedError)` as well, so every existing caller
  that tests the general case keeps working unchanged.
- IF `is_error` is true but the subtype is unrelated (for example
  `error_max_turns` or `error_during_execution`) THEN THE SYSTEM SHALL NOT
  return an error matching `ErrClaudeUsageLimit`.
- WHEN a `CheckResult` error is consumed in `ClaudeInvoker.Run` THE SYSTEM SHALL
  increment `mctl_agent_claude_result_errors_total` labelled
  `class="usage_limit"` or `class="other"`.
- WHILE both error classes exist THE SYSTEM SHALL leave `Worker.Loop`'s
  retry, backoff and dead-letter behaviour byte-for-byte identical for each: no
  new early return, no changed backoff, no re-routing, and the server-side
  `queue.Retry` / `RequeueStale` paths untouched.

### Privacy and naming

- WHILE any new series is exposed THE SYSTEM SHALL prefix it `mctl_agent_` to
  match the existing block and avoid collisions with other exporters.
- WHILE any new label value is produced THE SYSTEM SHALL guarantee it carries no
  Telegram id, username, peer, message body, error text or credential value.
- WHEN any new structured log attribute is introduced THE SYSTEM SHALL either
  carry a non-sensitive value or be registered in
  `internal/audit/redact.go`'s `sensitiveKeys`.

## Out of scope

- Any change to `deploy/alerts/mctl-telegram.rules.yaml`. Alert rules are a
  separate follow-up once these series exist and have been observed.
- Any ceiling, cap, gate or enforcement: per-hour or per-day send limits, cost
  ceilings, an anomaly-tripped kill switch. This proposal measures only.
- Changing `AGENT_MAX_BUDGET_USD`'s existing per-job semantics or its
  `--max-budget-usd` plumbing.
- Aggregating spend into a monthly budget object, a billing table, or any
  rollup beyond the counter and the per-job column.
- Grafana dashboard changes (`deploy/grafana/mctl-telegram-beta.json`).
- Backfilling cost for jobs already completed before this change ships.

## Open questions

- The exact `subtype` string the `claude` CLI emits on a usage-limit or quota
  stop is not evidenced anywhere in this clone — the only subtypes present in
  test fixtures are `success`, `error_max_turns` and `error_during_execution`
  (`internal/agentworker/claudeinvoker_test.go:203`,
  `internal/agentworker/worker_test.go:305`). Proceeding with a
  substring match over a documented token set (`usage_limit`, `rate_limit`,
  `quota`, `credit_balance`, `insufficient_credits`) against a lowercased
  subtype, and deliberately NOT inspecting `res.Result` (which can carry
  model-derived Telegram content and is prompt-injectable). If a real capture
  later shows the signal lives only in the result text, that is a follow-up with
  a real fixture attached.
- `agent_jobs.cost_usd` for a job retried across attempts: proceeding with
  last-reported-attempt-wins (a plain SET fenced on `attempts`), not a running
  sum, because that keeps the report idempotent under an HTTP retry. True
  cumulative spend across retries is available from
  `mctl_agent_job_cost_usd_total`. Revisit if per-job total-across-retries turns
  out to be the question operators actually ask.
- Making `AGENT_CREDENTIAL_DOMAIN_ID` required is a breaking configuration
  change: any already-running worker deployment will crash-loop on upgrade until
  the value is set. The issue explicitly asks for `requireEnv` semantics
  ("fails fast rather than starting an unattributable worker"), so proceeding as
  specified, with an ordered rollout note in the design (set the value in the
  gitops values first, then roll the image).
- The worker binary currently has no `/metrics` endpoint at all — only
  `/livez`, `/healthz`, `/readyz` on `AGENT_HEALTH_ADDR`
  (`cmd/agent-worker/health_server.go`). Adding one is unavoidable for cost and
  credential-domain series and is proposed on the same port, guarded by an
  optional `AGENT_METRICS_ALLOW_CIDR` mirroring `cmd/server/main.go:619`'s
  `metricsHandler`. Whether the platform's scrape config needs a matching
  change in `mctl-gitops` is outside this repo and flagged for the reviewer.
