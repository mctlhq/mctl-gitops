# Bound DevLoopWorkflow merge-watch history with continue_as_new

## Context

`DevLoopWorkflow` watches an implementation PR by polling the `get_pr_state`
activity on a timer until the PR reaches a terminal state, bounded only by
`MERGE_WATCH_DEADLINE` (14 days, `orchestrator/temporal/workflows/dev_loop.py:181`).
Every poll appends an activity, a timer and a workflow task to one history —
about 11.5 events — and nothing in `orchestrator/` ever calls
`continue_as_new`, so a full watch is a single unbounded-in-count history. The
issue measured `dev-loop-mctlhq-mctl-gitops-1040` at 7,632 events over 665
polls at the legacy 1800 s interval. Executions started after the
`fast-shepherd-cadence` marker poll at `MERGE_POLL_INTERVAL = 15 minutes`
(`dev_loop.py:179`), which doubles the poll count: a complete 14-day watch
then lands near 15,500 events, crossing Temporal's default
`limit.historyCount.warn` of 10,240. Nothing is terminated — the error limit
of 51,200 stays far away and size is ~2.4 MiB against a 10 MB warn limit — but
the only thing holding the count down is the deadline, and no mechanism in the
workflow reacts to history growth at all.

The fix is the server's own signal. `temporalio==1.31.0`
(`pyproject.toml:33`) exposes `workflow.info().is_continue_as_new_suggested()`,
set from the same thresholds, plus `workflow.info().get_current_history_length()`.
The merge-watch loop is the right shape for it: the state to carry is small
and the top of each poll is a natural boundary. Two things make this a change
of its own rather than a drive-by. The absolute deadline (`dev_loop.py:2441`,
`deadline = workflow.now() + MERGE_WATCH_DEADLINE`) must become an input, or
each hop resets the 14 days and an intentionally bounded watch becomes
unbounded. And a continued run starts with a fresh history and fresh in-memory
state, so everything the three `@workflow.query` handlers answer
(`implement_execution`, `shepherd_in_loop`, `lifecycle_claim`,
`dev_loop.py:830-867`) — plus the lifecycle-ownership claim the loop holds —
has to survive the boundary. `run_shepherd._dev_loop_owns_answer` stands the
cron sweeper down on the strength of `shepherd_in_loop`, so a hop that
silently answered `False` would put two shepherds on one PR.

## User stories

- AS the platform operator I WANT a complete 14-day merge watch to stay well
  under Temporal's `limit.historyCount.warn` SO THAT the headroom does not
  depend on nobody ever shortening the poll interval or lengthening the watch
  again.
- AS a DevLoop execution I WANT to carry my absolute merge-watch deadline
  across a continue-as-new boundary SO THAT the watch stays bounded at 14 days
  from the first poll rather than restarting the clock on every hop.
- AS the shepherd cron sweeper and the lifecycle reconciler I WANT a
  continued run to answer the same queries and hold the same ownership row as
  the run it replaced SO THAT a hop is invisible to everything that asks "who
  owns this PR".
- AS an operator following an in-flight loop I WANT each hop logged with the
  history length, poll count and remaining deadline SO THAT a workflow that
  changed run ids is explainable without reading Temporal history by hand.

## Acceptance criteria (EARS)

- WHEN the merge-watch loop reaches the top of a poll AND
  `workflow.patched("merge-watch-continue-as-new")` is true AND the server
  suggests continue-as-new (`workflow.info().is_continue_as_new_suggested()`)
  THE SYSTEM SHALL end the current run with `workflow.continue_as_new` and
  resume the watch in a new run.
- WHEN the server suggestion is unavailable or disabled BUT
  `workflow.info().get_current_history_length()` has reached
  `MERGE_WATCH_HISTORY_FLOOR` THE SYSTEM SHALL treat the hop as suggested, so
  the bound does not depend on cluster dynamic config.
- WHILE a continued run is executing THE SYSTEM SHALL use the absolute
  merge-watch deadline carried in its input and SHALL NOT recompute it from
  `workflow.now()`.
- IF the carried deadline has already passed when a continued run starts THEN
  THE SYSTEM SHALL end the watch immediately with the carried last observed
  `PRState`, exactly as the in-run deadline check does today.
- WHEN a continued run starts THE SYSTEM SHALL NOT re-run investigate,
  the stale-issue admission check, `find_proposal_slug`, the approve CWFT or
  the implement submit.
- WHEN a continued run starts THE SYSTEM SHALL rehydrate `_implement_state`,
  `_shepherd_in_loop` and the full lifecycle-claim state
  (`_owned_entity_id`, `_owner_epoch`, `_owned_head_sha`,
  `_poll_index_for_heartbeat`, the refusal and unknown-write counters,
  `_proposal_ref`, `_policy_ref`, `_last_lifecycle_op`,
  `_last_lifecycle_op_landed`, `_claim_abandoned`) from its input, so every
  `@workflow.query` answers as the previous run would have.
- WHILE hopping THE SYSTEM SHALL NOT issue a lifecycle `release` or
  `terminal` write, and SHALL keep the claim (owner id is
  `workflow.info().workflow_id`, which is stable across continue-as-new) and
  the epoch it already holds.
- WHEN a continued run resumes THE SYSTEM SHALL keep the cadence, shepherd and
  ownership decisions of the original run (`_Cadence`, `shepherd_in_loop`,
  concurrent ticks, `track_ownership`) as carried values rather than
  re-evaluating the `fast-shepherd-cadence`, `shepherd-in-loop`,
  `concurrent-shepherd-tick` and `lifecycle-ownership` patch markers.
- WHILE an in-loop shepherd tick task is still running THE SYSTEM SHALL defer
  the hop to a later poll rather than cancel the tick.
- WHEN a hop occurs THE SYSTEM SHALL carry the shepherd tick budget already
  spent, so `shepherd_ticks_max` stays a per-watch cap and not a per-run one.
- WHEN a hop occurs THE SYSTEM SHALL carry the consecutive
  `polls_without_pr` counter and the poll index, so the PR-lookup grace and
  the tick cadence keep their meaning across the boundary.
- WHEN the final run of a watch completes THE SYSTEM SHALL return a
  `DevLoopResult` whose `investigate`, `implement` and `approve` fields carry
  the results produced in the first run.
- IF fewer than one successful poll has completed in the current run THEN THE
  SYSTEM SHALL NOT hop, so a mis-set threshold cannot produce a
  continue-as-new storm.
- IF `MERGE_WATCH_MAX_HOPS` hops have already happened in this watch THEN THE
  SYSTEM SHALL log an error and keep watching in the current run until the
  deadline, never failing the workflow over the bound.
- WHEN an execution's history predates the `merge-watch-continue-as-new`
  marker THE SYSTEM SHALL keep polling in one run exactly as today (migration
  by attrition, as `tests/test_patch_memoization.py` pins).
- WHEN a hop occurs THE SYSTEM SHALL emit one `workflow.logger.info` line
  naming the service/slug, history length, polls completed, hop number and
  remaining time to the deadline.
- WHILE a watch has hopped THE SYSTEM SHALL remain a single Running execution
  under one workflow id, so `visibility.ACTIVE_DEV_LOOPS_QUERY`
  (`WorkflowType = 'DevLoopWorkflow' AND ExecutionStatus = 'Running'`) and
  `start_dev_loop_workflow`'s `USE_EXISTING` conflict policy behave unchanged.

## Out of scope

- Changing `MERGE_POLL_INTERVAL`, `MERGE_WATCH_DEADLINE`, the shepherd tick
  cadence or any other `_Cadence` value. This proposal makes the count safe at
  the current numbers; it does not re-tune them.
- Replacing polling with a GitHub webhook or a Temporal signal-driven merge
  detection (a new ingress/HMAC surface in mctl-api, explicitly deferred in
  `activities/pr_state.py`'s module docstring).
- Editing `temporal-dynamic-config` in the cluster to raise
  `limit.historyCount.warn`. That is a mctl-gitops change and it hides growth
  instead of bounding it.
- `continue_as_new` for the other long-lived workflows (`IncidentLoopWorkflow`,
  `ImplementSweepWorkflow`, `ReconcileWorkflow`). Their histories are not near
  any threshold and each would need its own carried state.
- The lifecycle `handoff-start`/`handoff/complete` flip (#353). The watch-end
  write stays a bare `release`.
- Reducing per-poll event cost (folding the ownership heartbeat into
  `get_pr_state`, or dropping the timer for a longer sleep).

## Open questions

- The exact value of `MERGE_WATCH_HISTORY_FLOOR`. The reasonable default is
  4,096 — Temporal's documented `limit.historyCount.suggestContinueAsNew`
  default, which makes the local floor agree with the server signal it backs
  up, and yields roughly 4 hops across a full 14-day watch at 15-minute polls.
  Proceeding with 4,096.
- Whether the `investigate`/`implement`/`approve` `WorkflowResult`s should be
  carried verbatim in the continue-as-new input or summarised. Proceeding with
  verbatim: they are small flat dataclasses
  (`activities/argo.py:74-90`), and anything less makes the final
  `DevLoopResult` lie about what the loop did.
- Whether a mid-watch deploy reaching a continued run is acceptable. A hop
  makes the continued run execute the CURRENTLY deployed code, which weakens
  the "migration is by attrition" property this codebase leans on. Proceeding
  by carrying every cadence/shepherd/ownership decision explicitly in the
  input, so a new image cannot silently change a watch already in flight; this
  is called out in design.md as a residual risk.
- Whether the time-skipping test server surfaces
  `is_continue_as_new_suggested()` at all. Proceeding by making the local
  history floor an overridable module constant so tests can force a hop
  deterministically without depending on server dynamic config.
