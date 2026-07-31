# Tasks: issue-347-c2-production-quota-domain-gate-for-auto

- [ ] 1. Add `agent_profiles` columns (`max_msgs_per_hour`,
      `max_msgs_per_day`, `max_cost_usd_per_day`, `c2_kill_switch_tripped_at`,
      `c2_kill_switch_reason`, `c2_kill_switch_tripped_by`, `c2_enabled_at`,
      `c2_enabled_by`) and `agent_jobs.cost_usd`, via `addColumnIfMissing` in
      `internal/db/agent_schema.go`, plus the matching Postgres/SQLite
      CREATE TABLE defaults for fresh databases — DoD: `go test
      ./internal/db/...` passes on both dialects; a fresh DB and a
      pre-existing DB (SQLite fixture in `internal/db/agent_schema_test.go`
      style) both end up with identical column sets after `Migrate()`; every
      new column defaults to zero/empty/NULL.

- [ ] 2. Persist `total_cost_usd` from a completed job into
      `agent_jobs.cost_usd` at job-completion time (`internal/agentapi`'s
      complete-job handler and/or `internal/agentworker/worker.go`'s result
      handling) (depends on 1) — DoD: a completed job's `cost_usd` is
      queryable after `complete_agent_job`; existing job-completion tests
      extended to assert the persisted value; zero/absent cost from a
      failed or no-cost invocation stores as NULL, not a false zero that
      would look like a real free run.

- [ ] 3. Extend `db.Store` with a per-account, per-conversation, multi-window
      (hour/day) send-count check reusing `ReserveAgentActionSend`'s
      transaction-locked shape, plus a `c2_kill_switch_tripped_at IS NOT
      NULL` immediate-deny check inside the same transaction (depends on 1)
      — DoD: new/extended unit tests in `internal/db/agent_actions_test.go`-style
      cover: per-conversation hour ceiling denies at the boundary; per-
      conversation day ceiling denies at the boundary; per-account
      aggregate across two conversations denies once the account ceiling is
      hit even though no single conversation is over its own ceiling; a
      tripped C2 kill switch denies regardless of remaining ceiling
      headroom; concurrent reservations under Postgres `FOR UPDATE` do not
      double-admit past the ceiling (race test, following the existing
      `ReserveAgentActionSend` race-test precedent if one exists, or added
      here if not).

- [ ] 4. Add `C2KillSwitchTripped bool` (and any needed ceiling-derived
      fields) to `policy.Input` in `internal/agent/policy/policy.go` and
      wire a cheap first-pass deny, mirroring the existing `GlobalKill`
      check order (depends on 1) — DoD: `internal/agent/policy/policy_test.go`
      table-driven cases cover a tripped C2 kill switch denying before any
      other check runs; existing table-driven cases unaffected (field
      defaults to false/zero on every case that doesn't set it).

- [ ] 5. Wire `executor.send()` in `internal/agent/executor/executor.go` to
      load the account's C2 state alongside the existing profile/conversation
      loads, pass it into both the `policy.Evaluate` call and the extended
      reservation call from task 3, and deny-and-terminalize the action on a
      C2 ceiling/kill-switch rejection using the same
      `UpdateAgentActionStatus(... ActionDenied)` pattern already used for
      every other send-time denial (depends on 3, 4) — DoD: an
      `internal/agent/executor/executor_test.go`-style test proves an
      approved guarded-mode action is denied (not silently dropped, not
      retried forever) when the account's hour ceiling is already consumed,
      and when the C2 kill switch is tripped mid-flight between approval and
      send (matching the existing "kill switch flip mid-flow must block
      execution" invariant from the canonical plan's Part 1 verification
      section).

- [ ] 6. Implement the periodic C2 anomaly sweep (new function, e.g.
      `Executor.SweepC2Anomalies` or a small `internal/agent/quota` package)
      that trips the kill switch on repeated-denial rate, send-velocity
      multiple, or cost-ceiling breach, using the idempotent first-trip-wins
      UPDATE described in design.md, called from a ticker goroutine in
      `cmd/server/main.go` alongside the existing `RecoverStuck` ticker
      (depends on 1, 2, 3) — DoD: unit tests cover each of the three trip
      conditions independently trip the switch exactly once (a second sweep
      tick over an already-tripped account is a no-op, verified by
      `c2_kill_switch_tripped_by`/`_reason`/`_at` staying unchanged); each
      trip calls `LogToolCall` with the `agent.c2_kill_switch.auto_trip`
      tool name.

- [ ] 7. Add the admin-only manual clear endpoint
      (`admin.agent_c2_kill_switch.clear`) requiring account id and actor,
      auditing via `LogToolCall`, and refusing to clear an account that
      isn't currently tripped (depends on 1) — DoD: `internal/agentapi`
      handler test proves a non-admin caller (wrong `aud`/scope, following
      the existing `TestHandleAutopilotPause_TogglesBothWays`-style
      convention) is rejected; clearing an untripped account 4xxs instead of
      silently succeeding; a successful clear is auditable and leaves
      `c2_kill_switch_tripped_at` NULL.

- [ ] 8. Add the dedicated C2 opt-in admin path enforcing "ceilings must
      already be non-zero" and "kill switch must not currently be tripped"
      before allowing `mode=guarded && autopilot_paused=false`
      simultaneously, writing `c2_enabled_at`/`c2_enabled_by` and the
      `admin.agent_c2.enable` audit event, in
      `internal/agentapi/profilehandler.go` (depends on 1, 7) — DoD: handler
      tests prove: opting in with a zero ceiling is rejected; opting in
      while tripped is rejected; a successful opt-in is distinguishable in
      the audit log from a routine `admin.agent_profile.upsert`; the
      existing generic profile-upsert path still works unchanged for every
      edit that does not cross the guarded+unpaused boundary
      simultaneously (regression test against
      `internal/agentapi/profilehandler_test.go`'s existing cases,
      especially `TestAdminAgentProfileHandler_DoesNotClobberConcurrentAutopilotPause`).

- [ ] 9. Add `AgentC2KillSwitchTrippedTotal`, `AgentC2SpendRatioMax`,
      `AgentC2RateRatioMax` collectors to `internal/metrics/metrics.go`,
      populated by the task-6 sweep (depends on 6) — DoD:
      `internal/metrics/metrics_test.go`-style registration test passes (no
      duplicate-registration panic); the sweep updates the gauges every
      tick, verified by a unit test asserting the gauge value after a
      synthetic sweep run.

- [ ] 10. Add `MctlAgentC2CeilingApproaching`, `MctlAgentC2CeilingBreached`,
      and `MctlAgentC2KillSwitchTripped` alert rules to the existing
      `mctl-telegram-agent` group in `deploy/alerts/mctl-telegram.rules.yaml`,
      following the file's existing two-tier warning/critical pattern
      (depends on 9) — DoD: the PrometheusRule YAML passes whatever manifest/
      lint validation this repo's CI already runs on that file (same gate
      the plan doc references as "Prometheus rule validation" in the C1
      evidence log); `runbook_url` entries point at a real anchor added to
      `docs/runbook.md`'s Communication Agent operations section.

- [ ] 11. Update `docs/runbook.md`'s "Communication Agent operations"
      section and its Configuration reference table with the new C2 kill
      switch, the new ceilings, the opt-in procedure, and the alert
      runbook anchors referenced in task 10 (depends on 6, 7, 8, 10) — DoD:
      the table lists every new env/config knob with default and
      operational meaning, matching the existing row format; a new
      subsection documents the C2 opt-in procedure and the manual-clear
      procedure, cross-referenced from `docs/plans/communication-agent.md`'s
      "Rollout gates" item 2 so the plan doc's "production quota domain
      provisioned" checkbox has a concrete implementation to point at.

## Tests

- [ ] T1. Policy unit tests (`internal/agent/policy/policy_test.go`): C2
      kill switch tripped denies before any other reason accumulates;
      existing table-driven cases pass unchanged.
- [ ] T2. Store unit/race tests (`internal/db/agent_actions_test.go`):
      per-conversation hour/day ceilings; per-account aggregate ceiling
      across multiple conversations; concurrent reservation race under
      Postgres locking does not over-admit.
- [ ] T3. Executor tests (`internal/agent/executor/executor_test.go`):
      ceiling-exhausted action denies and terminalizes (not stuck, not
      silently dropped); kill switch tripped between approval and send
      blocks execution, matching the existing kill-switch-flip-mid-flow
      invariant.
- [ ] T4. Anomaly sweep tests: each of the three trip conditions
      (denial-rate, velocity, cost) independently verified; idempotent
      second sweep on an already-tripped account is a no-op; audit entry
      recorded on trip.
- [ ] T5. Admin API tests (`internal/agentapi`): opt-in rejected without
      ceilings configured; opt-in rejected while tripped; manual clear
      rejected for a non-admin caller and for an untripped account;
      generic profile-upsert path unaffected (regression against existing
      `profilehandler_test.go` cases).
- [ ] T6. Metrics registration test: no duplicate-registration panic with
      the new collectors added.
- [ ] T7. End-to-end / staging drill (before this gate is considered
      "provisioned" per the plan's rollout gate 2): opt an account into C2
      in the preview environment with deliberately low ceilings, drive
      synthetic traffic past the hour ceiling and confirm denial, past the
      cost ceiling and confirm automatic trip, verify the AlertManager
      warning fires before the breach alert, and verify the manual-clear
      procedure restores traffic — recorded in
      `docs/reports/communication-agent-c1.md` or a new C2-specific report
      alongside the existing evidence-log convention.
- [ ] T8. `go vet ./...`, `golangci-lint`, and `govulncheck ./...` clean, per
      CONTRIBUTING.md conventions, on every PR in this sequence.

## Rollback

Every change in this proposal is additive and gated behind state
(`mode=guarded && autopilot_paused=false`) that, per the C1 report, no
production account has reached yet — so the lowest-risk rollback for any
single PR is simply reverting that PR; no account-visible behavior changes
for `observe`/`off` accounts at any point in this sequence.

If a problem surfaces after an account has been opted into C2 in
production:

1. Immediate stop for the affected account: flip `AGENT_KILL_SWITCH=true`
   (global, existing, fastest) or `autopilot_paused=true` for the specific
   account via the existing `/autopilot/pause`/admin path — both continue
   to work exactly as today and do not depend on any code in this proposal.
2. If the new C2 kill switch itself is misbehaving (e.g. false-positive
   trips or, worse, failing to trip when it should), the account can still
   be fully stopped through step 1's pre-existing, unmodified controls —
   the new gate is additive, never a replacement, so its removal or a bug
   in it cannot reopen a hole that the existing four containment controls
   don't already independently close.
3. Schema rollback is not required for a code revert: every new column is
   additive with safe defaults, so reverting the enforcement code while
   leaving the columns in place is safe (unused columns, no behavior
   change). Do not write a down-migration that drops columns — this
   codebase's migration style (`internal/db/agent_schema.go`) is
   forward-only additive, matching the existing precedent (e.g. the
   `job_leads.job_id` ALTER in #310 was never reverted, only fixed
   forward).
4. If the anomaly sweep (task 6) is the source of a false-positive storm,
   it can be disabled independently of the rest of the gate by removing its
   ticker registration in `cmd/server/main.go` (one-line revert) while
   leaving the manual kill switch, opt-in gate, and rate ceilings fully
   active — the sweep is the only automatic-trip path; every other control
   in this proposal is either static configuration or manually operated.
