# Tasks: issue-334-c2-gate-isolate-production-communication

## Reconciliation with the code and the gate plan (2026-11-04)

The tasks below were written on 2026-07-26 for a dedicated Claude credential.
The worker has since moved to the OpenAI runner on GLM-5.1 through Nebius, and
much of the code landed under other names. The current work plan is steps W1 to
W10 of `docs/plans/gate-334-quota-isolation.md` (mctlhq/mctl-telegram#1121). The
text of the tasks is kept as written; this table is what counts for status.
Evidence was read on mctl-telegram `origin/main` on 2026-11-04.

This section records status only. It accepts nothing, and `.status.yaml` is not
changed by it.

| Task | Status | Evidence or plan step |
|---|---|---|
| 1 | done, other names | `mctl_agent_credential_domain`, `mctl_agent_job_cost_usd_total`, `mctl_agent_claude_result_errors_total{class}` in `internal/metrics/metrics.go` |
| 2 | done | `requireEnv("AGENT_CREDENTIAL_DOMAIN_ID")` in `cmd/agent-worker/main.go`, tested in `main_test.go` |
| 3 | done, other shape | `recordCost` shared through `recordRunCost` in `internal/agentworker/finishrun.go` |
| 4 | done, other shape | `isUsageLimitSubtype` in `internal/agentworker/worker.go`, including `error_provider_429`; no new error type |
| 5 | done, other name | `MctlAgentClaudeUsageLimit`. Budget and rate alerts: W2, mctlhq/mctl-gitops#2396 and mctlhq/mctl-telegram#1123, open |
| 6 | open | W3, mctlhq/mctl-telegram#1122, retargeted to the Nebius key and the AI Gateway token |
| 7 | open | W10, mctlhq/mctl-telegram#1122 |
| 8 | open | W10, mctlhq/mctl-telegram#1122 |
| 9 | open, changed | No production credential exists. W4, W5 and W6; "separate domain" now means a Nebius project and quota scope, still unread |
| 10 | open, changed | W9, deferred until after 2026-11-11 and only on owner command (D7) |
| T1 to T5, T7 | superseded | Covered by the tests of the merged code and by CI; the names above replace the proposed ones |
| T6 | open | W8, needs owner approval (D5) |

Claude-only wording in the tasks does not apply to the managed worker. The
Rollback section still names `AGENT_KILL_SWITCH`, `autopilot_paused` and zero
replicas; the current stop procedure is "Managed runtime rollback" in
`docs/runbook.md`. A Gantt review asked that the approvals contract be verified
before this proposal moves on: that is not done here.

- [ ] 1. Add `AgentWorkerCredentialDomainInfo`, `AgentWorkerJobCostUSD`, and
      `AgentWorkerQuotaExhaustedTotal` metrics to `internal/metrics/metrics.go`
      (following the existing `AgentDeadLetterTotal`/`AgentActionsExecutingStuck`
      registration pattern, all labeled `credential_domain` where applicable) —
      DoD: metrics registered and exported on `/metrics`, unit test in
      `internal/metrics` (or wherever existing agent metrics are tested)
      confirms they appear with the right names/labels/types.

- [ ] 2. Add `AGENT_CREDENTIAL_DOMAIN_ID` env var to `cmd/agent-worker/main.go`
      (depends on 1) — DoD: `run()` reads it via `requireEnv` when
      `AGENT_ENABLED`-equivalent startup path is taken, sets
      `AgentWorkerCredentialDomainInfo{credential_domain=<value>}=1` once at
      startup, value is included in the `/livez`/`/healthz` JSON body
      (`cmd/agent-worker/health_server.go`), documented in
      `docs/agent-worker.md`'s configuration table, and a missing value
      produces the same fail-fast behavior as a missing `AGENT_API_TOKEN`.

- [ ] 3. Record `TotalCostUSD` into `AgentWorkerJobCostUSD` inside
      `ClaudeInvoker.Run` (`internal/agentworker/claudeinvoker.go`), right
      after `ParseClaudeResult` succeeds and before `CheckResult` (depends on
      1) — DoD: `claudeinvoker_test.go`'s fake-CLI-script harness asserts the
      metric increments by the fixture's `total_cost_usd` value on both a
      successful and a failed (`is_error: true`) result.

- [ ] 4. Add quota/usage-limit error detection to
      `internal/agentworker/worker.go`'s `CheckResult`: a new
      `ErrAgentCredentialQuotaExhausted` (wrapping `ErrClaudeReportedError`)
      returned when the result's error shape matches the documented
      usage-limit condition from `docs/plans/communication-agent.md`'s
      Appendix, incrementing `AgentWorkerQuotaExhaustedTotal` (depends on 1)
      — DoD: table-driven unit test in `worker_test.go` covers the
      usage-limit fixture string, a generic unrelated `is_error` case (must
      NOT match), and confirms `worker.Loop`'s existing retry/backoff and
      dead-letter path is unchanged for both.

- [ ] 5. Add `MctlAgentWorkerQuotaExhausted` alert rule to
      `deploy/alerts/mctl-telegram.rules.yaml`, mirroring the existing
      `MctlAgentDeadLetter` rule's structure (depends on 4) — DoD: rule
      validates with the repo's existing Prometheus rule validation
      (referenced in `docs/reports/communication-agent-c1.md`'s evidence
      entries), and is documented in `docs/runbook.md`'s "Agent alert
      response" subsection with a response procedure (check
      `mctl_agent_worker_credential_domain`, confirm interactive/
      `claude-review.yml` are unaffected, escalate to the provider console).

- [ ] 6. Extend `docs/runbook.md`'s "Credential rotation" subsection with a
      domain-aware Claude-credential rotation/revocation procedure (scale to
      zero, revoke at the provisioned domain's console, replace the
      Vault-sourced secret, start one replica, verify old credential fails,
      verify the domain-identity metric updates) — DoD: procedure reviewed
      and matches the mechanism actually provisioned in task 9; no
      credential value appears in the doc.

- [ ] 7. Create `docs/reports/communication-agent-c2.md` mirroring
      `docs/reports/communication-agent-c1.md`'s structure, scoped to this
      issue's acceptance criteria (depends on 2, 5, 6) — DoD: file contains
      Scope/acceptance, an Evidence section with the credential domain's
      non-secret identifier, a description of its budget/rate-limit controls
      and reference to tested-alert evidence, the rotation-drill result, the
      controlled-invocation-during-outage drill result, a Remaining checklist
      for anything outstanding, and an explicit `Go/no-go: <go|no-go>` line
      referencing issue #334. No credential values, raw console screenshots,
      or Telegram content in the file.

- [ ] 8. Update `docs/plans/communication-agent.md`'s Rollout gates item 2
      and `docs/reports/communication-agent-c1.md`'s remaining checklist to
      link the new C2 report instead of only asserting the prerequisite in
      prose (depends on 7) — DoD: both files point at
      `docs/reports/communication-agent-c2.md`; no contradiction between the
      plan's gate wording and the new report's scope.

- [ ] 9. **Coordination task (not implemented in this repo)**: provision the
      production billing/quota domain (separate org/account or metered API
      credential per the Open questions in requirements.md), store it only
      in Vault, mount it only into the worker pod via a `mctl-gitops` PR
      (e.g. `platform-gitops/services/labs/communication-agent-worker-preview/
      values.yaml` or its eventual production equivalent), configure the
      domain's own monthly budget and rate-limit alerts, and set the
      matching `AGENT_CREDENTIAL_DOMAIN_ID` value in that values file
      (depends on 2) — DoD: tracked as an explicit follow-up issue/PR in
      `mctl-gitops`; this repo's proposal does not merge task 2 as a hard
      requirement for the worker Deployment until this is ready, per
      "Never auto-merge `mctl-gitops`."

- [ ] 10. **Coordination task (not implemented in this repo)**: exercise the
      controlled drill — point the worker's Claude credential at its
      dedicated domain while the interactive/`claude-review.yml` pool is
      deliberately exhausted or rate-limited (or capture a real occurrence),
      confirm a job still completes successfully, and record the result in
      the C2 report (depends on 7, 9) — DoD: result recorded in
      `docs/reports/communication-agent-c2.md` per task 7's DoD.

## Tests

- [ ] T1. `internal/metrics` (or agent-metrics-adjacent test file): new
      metrics register without panic/collision and expose the expected
      names/labels.
- [ ] T2. `internal/agentworker/claudeinvoker_test.go`: cost metric records
      `total_cost_usd` from the fake CLI script's JSON result on both
      success and `is_error: true` paths.
- [ ] T3. `internal/agentworker/worker_test.go`: `CheckResult` returns
      `ErrAgentCredentialQuotaExhausted` only for the documented usage-limit
      error shape, increments `AgentWorkerQuotaExhaustedTotal` exactly once,
      and leaves unrelated `is_error` handling unchanged.
- [ ] T4. `cmd/agent-worker/main_test.go` and/or `health_server_test.go`:
      missing `AGENT_CREDENTIAL_DOMAIN_ID` fails startup the same way a
      missing `AGENT_API_TOKEN` does; present value appears in the
      `/livez`/`/healthz` JSON body.
- [ ] T5. Prometheus rule validation (existing tooling referenced in the C1
      report) passes with the new `MctlAgentWorkerQuotaExhausted` rule added
      to `deploy/alerts/mctl-telegram.rules.yaml`.
- [ ] T6. Manual/drill: the rotation procedure in `docs/runbook.md` is
      exercised once end-to-end (task 6/10) and the result — including that
      the old credential now fails — is recorded in the C2 report, not just
      asserted from the written steps.
- [ ] T7. `go test ./...`, `go vet ./...`, and `golangci-lint` all pass
      repo-wide after the code changes, matching this repo's existing
      per-PR verification pattern (see `docs/plans/communication-agent.md`'s
      Verification section).

## Rollback

All code changes in this proposal are additive (new metrics, one new
env var, one new alert rule, new/updated docs) and independently
revertible:

1. If `AGENT_CREDENTIAL_DOMAIN_ID` being required breaks an existing
   deployment unexpectedly, the fastest rollback is reverting the
   `cmd/agent-worker/main.go` commit (task 2) that makes it required —
   this restores the previous startup behavior immediately; the metrics
   and alert additions (tasks 1, 3, 4, 5) can remain since they are inert
   without the env var and do not change job-processing control flow.
2. If the quota-exhaustion detection (task 4) ever misclassifies a normal
   failure as quota exhaustion (or vice versa), disable the new alert rule
   (task 5) first — it is the only user-facing effect with page/ticket
   consequences — then fix or revert the detection logic; job
   retry/dead-letter behavior is unchanged either way, so no data-safety
   issue is created by leaving it enabled briefly.
3. Documentation changes (tasks 6, 7, 8) carry no runtime risk; revert by
   reverting the commit.
4. The coordination tasks (9, 10) are operational, not code: if the newly
   provisioned domain itself needs to be rolled back (e.g. a
   misconfigured metered key), follow the existing "Credential rotation"
   procedure in `docs/runbook.md` (scale worker to zero, revoke/replace,
   verify) — this predates and is unaffected by this proposal.
5. In all cases, C2/guarded autopilot remains blocked
   (`AGENT_KILL_SWITCH=true`, `autopilot_paused=true`, worker replicas
   zero) until the full task list and the C2 report's go/no-go line are
   both in place — a partial or rolled-back state here never by itself
   promotes anything to production.
