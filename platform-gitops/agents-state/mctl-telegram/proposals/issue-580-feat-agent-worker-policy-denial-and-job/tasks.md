# Tasks: issue-580-feat-agent-worker-policy-denial-and-job

- [ ] 1. Add `DenyCode` to `internal/agent/policy/policy.go`: the type, the 17
      code constants plus `DenyUnknown`, a `Code DenyCode` field on `Result`,
      and a `Result.DenyCode()` accessor that returns `DenyUnknown` for an empty
      code. Change `deny(reasons ...string)` (`policy.go:61`) to
      `deny(code DenyCode, reasons ...string)` and pass the matching code at all
      17 call sites (lines 287, 298, 303, 305, 308, 323, 325, 327, 329, 332,
      338, 343, 346, 350, 367, 370, 373) — DoD: `go build ./...` passes,
      existing policy tests pass unchanged, `Evaluate` still imports nothing new
      and performs no I/O, and reason strings are byte-identical to today.

- [ ] 2. Register the new families in `internal/metrics/metrics.go` next to the
      existing agent block (`:279-307` region) and in the `MustRegister` list:
      `AgentPolicyDenialsTotal` (`mctl_agent_policy_denials_total`,
      `{reason, surface}`), `AgentJobCostUSDTotal`
      (`mctl_agent_job_cost_usd_total`, `{result}`),
      `AgentClaudeResultErrorsTotal` (`mctl_agent_claude_result_errors_total`,
      `{class}`), `AgentCredentialDomain` (`mctl_agent_credential_domain`,
      `{domain_id}`, info-gauge modelled on `TelegramReplicaID`). Add the
      `PolicySurface*` constants and the `CountPolicyDenial(reason, surface)`
      helper — DoD: each collector has a Help string naming why its label set
      is bounded, and `internal/metrics/metrics_test.go`'s
      `expectedMetricNames` is extended with all four names.

- [ ] 3. Increment the denial counter at the four consumption sites (depends on
      1, 2): `internal/agentapi/actions.go:207` (`propose_reply`),
      `internal/agentapi/actions.go:429` (`owner_notify`),
      `internal/agent/executor/executor.go:283` (`executor_send`),
      `internal/agent/executor/executor.go:561` (`executor_recover`), each
      guarded by `result.Decision == policy.Deny` and nil-safe on the registry —
      DoD: `grep -n "AgentPolicyDenialsTotal\|CountPolicyDenial"
      internal/agent/policy/` returns nothing, and in `recoverOne` the
      `requireApprovalBypassesUnreviewedAllow` escalation does NOT increment.

- [ ] 4. Change `ClaudeResult.TotalCostUSD` to `*float64`
      (`internal/agentworker/worker.go:177`) and update `worker_test.go:270` —
      DoD: `ParseClaudeResult` on a payload with no `total_cost_usd` key yields
      `nil`, on `"total_cost_usd": null` yields `nil`, and on
      `"total_cost_usd": 0` yields a non-nil pointer to `0`.

- [ ] 5. Add `ErrClaudeUsageLimit` (declared as
      `fmt.Errorf("%w: ...", ErrClaudeReportedError)`), `usageLimitSubtypes`
      and `isUsageLimitSubtype`, and branch `CheckResult`
      (`worker.go:212`) onto the right sentinel keeping the message format
      identical (depends on 4) — DoD: `CheckResult` still performs no I/O and
      never references `res.Result` beyond `len()`.

- [ ] 6. Add the persistence layer: `cost_usd` in both `agent_jobs`
      `CREATE TABLE` statements (`internal/db/agent_schema.go:424` SQLite
      `REAL`, `:635` Postgres `DOUBLE PRECISION`), an `addColumnIfMissing(ctx,
      dbConn, pg, "agent_jobs", "cost_usd", "DOUBLE PRECISION", "REAL")` pass
      with no DEFAULT in the same block as the existing ones (`:137-160`
      region), `CostUSD sql.NullFloat64` on `db.AgentJob`
      (`internal/db/agent_jobs.go:44`) with every scan site updated, and
      `Store.RecordAgentJobCost(ctx, userID, jobID, attempt, cost)` fenced on
      `attempts = $attempt` returning `ErrAgentJobNotFound` on zero rows — DoD:
      `go test ./internal/db/...` passes and no scan site reads `cost_usd` into
      a bare `float64`.

- [ ] 7. Add `POST /jobs/{id}/cost` to `internal/agentapi`: handler modelled on
      `handleJobComplete` (`events.go`) using `identity`, `decodeStrict`,
      `GetAgentJob`, mapping `ErrAgentJobNotFound` to 409; register it in
      `server.go`'s route block next to `/jobs/{id}/complete` (`:125`)
      (depends on 6) — DoD: the route is absent from `allowedTools`
      (`internal/agentworker/claudeinvoker.go:49`) and from `NewMCPServer`, and
      a test asserts the MCP tool list still has exactly the 11 existing tools.

- [ ] 8. Add `Client.ReportJobCost(ctx, jobID, attempt, cost)` to
      `internal/agentworker/client.go` following `CompleteJob`'s shape
      (depends on 7) — DoD: it sends `{"attempt":N,"cost_usd":X}` and surfaces
      an `*APIError` for non-2xx.

- [ ] 9. Wire the worker-side recording: add `Metrics *metrics.Registry` to
      `ClaudeInvoker`, and in `Run` insert `c.recordCost(...)` between
      `ParseClaudeResult` (`claudeinvoker.go:182`) and `CheckResult` (`:186`),
      and `c.countResultError(err)` inside the `CheckResult` error branch
      (depends on 2, 4, 5, 8) — DoD: both helpers are nil-safe on a nil
      registry, `recordCost` is a no-op when `TotalCostUSD == nil`, a failing
      `ReportJobCost` only logs a warning and never changes `Run`'s return
      value, and the log line carries `job_id` but no event id, peer or content.

- [ ] 10. Require and validate `AGENT_CREDENTIAL_DOMAIN_ID` in
      `cmd/agent-worker/main.go` `run()` via `requireEnv` alongside
      `AGENT_API_TOKEN` (`:68`), plus `validateDomainID` rejecting characters
      outside `[A-Za-z0-9._:/-]` or length > 128; construct `metrics.New()` in
      `run()`, set `AgentCredentialDomain.WithLabelValues(id).Set(1)`, and pass
      the registry into `ClaudeInvoker.Metrics` (depends on 2, 9) — DoD:
      `runMCPServe()` is untouched (the MCP-serve subprocess must not require
      the var), and an unset value exits non-zero with
      `AGENT_CREDENTIAL_DOMAIN_ID is required`.

- [ ] 11. Extend `cmd/agent-worker/health_server.go`: `newHealthServer` takes
      the registry, the domain id and an optional `AGENT_METRICS_ALLOW_CIDR`;
      add a `/metrics` route via `promhttp.HandlerFor` wrapped by a CIDR guard
      modelled on `cmd/server/main.go:619`; `writeProbeResult` appends
      `credential_domain_id=<value>` as a second line while keeping the first
      line `ok`/`not ok` and the existing status codes (depends on 10) — DoD:
      `cmd/agent-worker/health_server_test.go`'s existing assertions still pass
      and Content-Type is unchanged.

- [ ] 12. Documentation (depends on 10, 11): add the
      `AGENT_CREDENTIAL_DOMAIN_ID` row (required, "non-secret identifier such
      as a Vault path or account label — never the credential itself") and an
      `AGENT_METRICS_ALLOW_CIDR` row to `docs/agent-worker.md:75-82`; document
      the new `/metrics` route on `AGENT_HEALTH_ADDR` and the rollout ordering
      (set the env var in gitops values BEFORE rolling the image, else the pod
      crash-loops) — DoD: `go test ./docs/...` passes.

- [ ] 13. Add the deliberate-absence comment in `internal/audit/redact.go` next
      to the `device_pubkey` precedent recording that `credential_domain_id`
      and `cost_usd` are intentionally NOT in `sensitiveKeys` because both are
      non-secret by construction and redacting them would defeat the purpose
      (depends on 10) — DoD: no new key is added to `sensitiveKeys` and the
      reasoning is written down.

- [ ] 14. Confirm `deploy/alerts/mctl-telegram.rules.yaml` and
      `deploy/grafana/mctl-telegram-beta.json` are unchanged in the final diff —
      DoD: `git diff --stat` lists neither file.

## Tests

- [ ] T1. `internal/metrics/metrics_test.go`: extend `expectedMetricNames` and
      the "force each metric to be used" block so `Gather()` returns families
      for `mctl_agent_policy_denials_total`, `mctl_agent_job_cost_usd_total`,
      `mctl_agent_claude_result_errors_total` and
      `mctl_agent_credential_domain`, asserting the expected type (COUNTER /
      COUNTER / COUNTER / GAUGE) and the exact label-name sets
      (`reason,surface` / `result` / `class` / `domain_id`).
      Mutation check: deleting one name from the `MustRegister` block, or
      renaming a label, must fail this test.

- [ ] T2. `internal/agent/policy/policy_test.go`: a table asserting every
      `deny(...)` path returns the expected `DenyCode`, and that the set of
      codes returned across the table equals the exported constant set minus
      `DenyUnknown`; plus an assertion that `Evaluate` returns the same
      `Result` twice for the same `Input` and touches no registry.
      Mutation check: swapping any two codes at their `deny` sites must fail.

- [ ] T3. `internal/agentapi` and `internal/agent/executor` tests: a denied
      `propose_reply` increments
      `AgentPolicyDenialsTotal{reason,surface="propose_reply"}` by 1 (via
      `testutil.ToFloat64`, the pattern already used at
      `internal/agent/queue/queue_test.go:51`), and a denied executor send
      increments `surface="executor_send"`. Also assert an `Allow` and a
      `RequireApproval` increment nothing.
      Mutation check: removing the increment, or dropping the
      `Decision == Deny` guard, must fail.

- [ ] T4. `internal/agentworker/worker_test.go`: `ParseClaudeResult` on a
      fixture that **omits `total_cost_usd` entirely** yields `nil`; on
      `"total_cost_usd": null` yields `nil`; on `"total_cost_usd": 0` yields a
      non-nil `0`. This is the explicit "exercised with a payload that actually
      lacks the field, not merely a zero value" requirement.
      Mutation check: reverting the field to `float64` must fail.

- [ ] T5. `internal/agentworker/claudeinvoker_test.go`: with a stub `claude`
      binary (the pattern already used at `claudeinvoker_test.go:75`) and a
      metrics registry attached, `mctl_agent_job_cost_usd_total{result="success"}`
      increases by the fixture's `total_cost_usd` on a successful result, and
      `{result="error"}` increases by the fixture's cost on an
      `is_error=true` result **that then fails `CheckResult`** — proving the
      recording happens before the check.
      Mutation check: moving `recordCost` after `CheckResult` must fail the
      second case.

- [ ] T6. `internal/agentworker/worker_test.go`: a usage-limit subtype fixture
      produces an error where both `errors.Is(err, ErrClaudeUsageLimit)` and
      `errors.Is(err, ErrClaudeReportedError)` hold; the existing
      `error_max_turns` and `error_during_execution` fixtures produce an error
      where `errors.Is(err, ErrClaudeReportedError)` holds and
      `errors.Is(err, ErrClaudeUsageLimit)` is false. Plus a re-run of the
      existing "result text never appears in the error"
      assertion (`worker_test.go:302`) against the usage-limit path.
      Mutation check: widening the match to any `is_error` must fail the
      unrelated-fixture case.

- [ ] T7. `internal/agentworker/worker_test.go`: a `Loop` test with a stub
      `Runner` returning, in turn, a usage-limit error and a generic
      `ErrClaudeReportedError`, asserting identical behaviour for both — the
      loop continues, polls again, applies no extra sleep, returns nil on ctx
      cancel, does not return `ErrFatalAuth`, and health state is unchanged.
      This is the "retry/backoff and dead-letter behaviour is unchanged, and a
      test proves it" criterion.
      Mutation check: adding any early return or extra backoff for the
      usage-limit class must fail.

- [ ] T8. `internal/db/agent_schema_test.go`: modelled on
      `TestMigrate_UpgradesPreExistingConversationsWithoutPeerAccessHash`
      (`:139`) — hand-create `agent_jobs` in its pre-#580 shape with a seeded
      row, run `Migrate`, assert `cost_usd` exists, that the pre-existing row's
      value is SQL NULL (not 0), and that the real `GetAgentJob` path still
      works against the upgraded table.
      Mutation check: adding `DEFAULT 0` to the `addColumnIfMissing` call, or
      removing the call entirely, must fail.

- [ ] T9. `internal/db/agent_jobs_test.go`: `RecordAgentJobCost` sets the value
      for the matching attempt; a call with a stale attempt returns
      `ErrAgentJobNotFound` and leaves the stored value untouched; a job never
      reported on keeps `CostUSD.Valid == false`.
      Mutation check: dropping the `attempts = $attempt` predicate must fail
      the stale-attempt case.

- [ ] T10. `cmd/agent-worker/main_test.go`: `run()` fails with a clear error
      when `AGENT_CREDENTIAL_DOMAIN_ID` is unset, when it is empty, and when it
      contains a disallowed character or exceeds 128 chars; `runMCPServe()` is
      unaffected by its absence.

- [ ] T11. `cmd/agent-worker/health_server_test.go`: `/livez` and `/healthz`
      bodies still start with `ok` / `not ok` with unchanged status codes and
      now also contain `credential_domain_id=<value>`; `/metrics` serves the
      exposition format and contains `mctl_agent_credential_domain{domain_id=...} 1`;
      with `AGENT_METRICS_ALLOW_CIDR` set to a non-matching CIDR, `/metrics` is
      refused while the probe routes still answer.

- [ ] T12. A privacy assertion test in `internal/agentworker`: scrape the
      worker registry's exposition output after running a job against a fixture
      whose event id, peer handle and message body are known synthetic values
      (reuse an existing persona — Alice / Bob / Carol / Dana — per
      `.claude/CLAUDE.md`), and assert none of those strings appears anywhere in
      the output.

## Rollback

The change is additive and rolls back cleanly in three independent layers.

1. **Worker.** `mctl_rollback_service` to the previous agent-worker image tag.
   The old binary does not read `AGENT_CREDENTIAL_DOMAIN_ID` (an extra env var
   is harmless), never calls `POST /jobs/{id}/cost`, and exposes no `/metrics` —
   probes are unchanged, so Kubernetes readiness is unaffected. This alone
   reverts every worker-side behaviour.
2. **API.** Roll the mctl-telegram server image back. `POST /jobs/{id}/cost`
   disappears; a still-new worker's cost report gets a 404, which is
   best-effort-logged and never fails a job — no operational impact. The
   policy-denial counter simply stops being emitted; no alert rule depends on it
   because this proposal adds none.
3. **Schema.** `agent_jobs.cost_usd` is left in place. It is nullable with no
   DEFAULT and no code path outside `RecordAgentJobCost` writes it, so an older
   binary ignores it entirely. Dropping the column is neither required nor
   recommended; if it must go, `ALTER TABLE agent_jobs DROP COLUMN cost_usd`
   is safe once no binary at or after this change is running.

The one failure mode requiring care is the forward direction, not the backward
one: rolling the new worker image before `AGENT_CREDENTIAL_DOMAIN_ID` is present
in the gitops values crash-loops the pod. The fix is to add the value and sync,
or roll back per step 1; jobs are durable in `agent_jobs` and are requeued by
`queue.RequeueStale` once a worker returns, so no work is lost.
