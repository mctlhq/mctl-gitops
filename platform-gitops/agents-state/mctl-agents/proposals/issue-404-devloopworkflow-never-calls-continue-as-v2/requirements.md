# Bound DevLoopWorkflow merge-watch history with continue_as_new (v2)

## Why this slug exists

This supersedes `issue-404-devloopworkflow-never-calls-continue-as`, whose
implementation PR (mctlhq/mctl-agents#437) was closed without merging: it was
written against `dev_loop.py` as it stood before mctlhq/mctl-agents#434
(released as 1.53.0), #434 rewrote the same regions, and the result conflicted.
The old proposal is kept as a historical artifact in `rejected` state and is
not edited. It cannot be revived in place — a closed-unmerged PR permanently
pins its slug to `rejected` (mctlhq/mctl-agents#438) — so the work continues
under a new slug with a new deterministic branch,
`feat/agents-issue-404-devloopworkflow-never-calls-continue-as-v2`.

Source issue is unchanged: mctlhq/mctl-agents#404.

## Context

`DevLoopWorkflow` watches an implementation PR by polling the `get_pr_state`
activity on a timer until the PR reaches a terminal state, bounded only by
`MERGE_WATCH_DEADLINE` (14 days, `orchestrator/temporal/workflows/dev_loop.py:201`).
Every poll appends an activity, a timer and a workflow task to one history —
about 11.5 events — and `continue_as_new` appears nowhere in `orchestrator/`,
so a full watch is a single history unbounded in event count. The issue
measured `dev-loop-mctlhq-mctl-gitops-1040` at 7,632 events over 665 polls at
the legacy 1800 s interval. Executions started after the
`fast-shepherd-cadence` marker poll at `MERGE_POLL_INTERVAL = 15 minutes`
(`dev_loop.py:199`), which doubles the poll count: a complete 14-day watch then
lands near 15,500 events, crossing Temporal's default `limit.historyCount.warn`
of 10,240. Nothing is terminated — the error limit of 51,200 stays far away and
size is ~2.4 MiB against a 10 MB warn limit — but the only thing holding the
count down is the deadline, and no mechanism in the workflow reacts to history
growth at all.

The fix is the server's own signal. `temporalio==1.31.0` (`pyproject.toml:33`)
exposes `workflow.info().is_continue_as_new_suggested()` — a **method**, not an
attribute (`temporalio/workflow/_context.py:186`) — plus
`workflow.info().get_current_history_length()`. The merge-watch loop is the
right shape for it: the carried state is small and the top of each poll is a
natural boundary.

## What #434 changed, and what it means here

Verified against current `main`, not against the superseded proposal's notes:

- **`run` is single-argument.** `DevLoopWorkflow.run(self, issue: IssueRef)`
  (`dev_loop.py:1008`), and `IssueRef` is a frozen dataclass with exactly one
  field, `issue_url` (`dev_loop.py:428-429`). There is no `resume` field and no
  second parameter on `main`.
- **A second signal now exists for the whole life of the execution.**
  `abandon` (`dev_loop.py:990-1005`) sets `_abandoned` / `_abandon_reason`, and
  the merge watch observes it directly: the loop condition is
  `while workflow.now() < deadline and not self._abandoned:` (`dev_loop.py:2703`)
  with an early exit at `dev_loop.py:2621`. The superseded proposal recorded
  "the only signal this workflow takes is `approve`, consumed long before the
  watch starts, so the exposure is nil" — that is now false, and signal loss
  across a continue-as-new boundary becomes a live concern rather than a note.
- **There are four query handlers, not three.** `implement_execution` (924),
  `shepherd_in_loop` (929), `lifecycle_claim` (942) and the new
  `abandon_state() -> AbandonState` (963). All four must answer identically
  after a hop.
- **`_cadence` is instance state.** `self._cadence` is set in `__init__`
  and bound for real in `_watch_pr`; it is not only a local.
- **Line numbers moved.** The watch is `_watch_pr` at `dev_loop.py:2613`
  (`(self, service: str, slug: str) -> PRState | None`), its `try` at 2697 and
  its `finally` at 2843; the four cadence/shepherd/ownership markers are now at
  2633-2674. The new marker `approval-watch` sits at 1048.

## User stories

- AS the platform operator I WANT a complete 14-day merge watch to stay well
  under Temporal's `limit.historyCount.warn` SO THAT the headroom does not
  depend on nobody ever shortening the poll interval or lengthening the watch
  again.
- AS a DevLoop execution I WANT to carry my absolute merge-watch deadline
  across a continue-as-new boundary SO THAT the watch stays bounded at 14 days
  from the first poll rather than restarting the clock on every hop.
- AS an operator who sent `abandon` I WANT the signal to take effect even if it
  races a hop SO THAT the escape hatch #434 added does not become unreliable
  exactly on long watches, which are the ones most likely to need it.
- AS the shepherd cron sweeper and the lifecycle reconciler I WANT a continued
  run to answer the same queries and hold the same ownership row as the run it
  replaced SO THAT a hop is invisible to everything that asks "who owns this PR".
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
- IF `self._abandoned` is true THEN THE SYSTEM SHALL NOT hop, and SHALL end the
  watch through the existing abandon path instead, so an `abandon` that arrived
  before the boundary is never traded for a continuation.
- WHEN a continued run starts THE SYSTEM SHALL carry `_abandoned` and
  `_abandon_reason` in its input and SHALL re-check them before its first sleep,
  so an `abandon` observed in the previous run still ends the watch.
- WHILE a continued run is executing THE SYSTEM SHALL use the absolute
  merge-watch deadline carried in its input and SHALL NOT recompute it from
  `workflow.now()`.
- IF the carried deadline has already passed when a continued run starts THEN
  THE SYSTEM SHALL end the watch immediately with the carried last observed
  `PRState`, exactly as the in-run deadline check does today.
- WHEN a continued run starts THE SYSTEM SHALL NOT re-run investigate, the
  approval park, the stale-issue admission check, `find_proposal_slug`, the
  approve CWFT or the implement submit.
- WHEN a continued run starts THE SYSTEM SHALL rehydrate `_implement_state`,
  `_shepherd_in_loop`, `_cadence`, the full lifecycle-claim state
  (`_owned_entity_id`, `_owner_epoch`, `_owned_head_sha`,
  `_poll_index_for_heartbeat`, `_claim_refused`, `_claim_refused_until_poll`,
  `_refused_by_type`, `_refused_by_id`, `_refusals_observed`,
  `_unknown_acquires`, `_unknown_progress`, `_unknown_heartbeats`,
  `_proposal_ref`, `_policy_ref`, `_last_lifecycle_op`,
  `_last_lifecycle_op_landed`, `_claim_abandoned`) and the abandon state from
  its input, so all FOUR `@workflow.query` handlers answer as the previous run
  would have.
- WHILE hopping THE SYSTEM SHALL NOT issue a lifecycle `release` or `terminal`
  write, and SHALL keep the claim (owner id is `workflow.info().workflow_id`,
  stable across continue-as-new) and the epoch it already holds.
- WHEN a continued run resumes THE SYSTEM SHALL keep the cadence, shepherd and
  ownership decisions of the original run as carried values rather than
  re-evaluating the `fast-shepherd-cadence`, `shepherd-in-loop`,
  `concurrent-shepherd-tick` and `lifecycle-ownership` markers
  (`dev_loop.py:2633-2674`).
- WHILE an in-loop shepherd tick task is still running THE SYSTEM SHALL defer
  the hop to a later poll rather than cancel the tick.
- WHEN a hop occurs THE SYSTEM SHALL carry the shepherd tick budget already
  spent, so `shepherd_ticks_max` stays a per-watch cap and not a per-run one.
- WHEN a hop occurs THE SYSTEM SHALL carry the consecutive `polls_without_pr`
  counter and the poll index, so the PR-lookup grace and the tick cadence keep
  their meaning across the boundary.
- WHEN the final run of a watch completes THE SYSTEM SHALL return a
  `DevLoopResult` whose `investigate`, `implement` and `approve` fields carry
  the results produced in the first run.
- IF fewer than one successful poll has completed in the current run THEN THE
  SYSTEM SHALL NOT hop, so a mis-set threshold cannot produce a
  continue-as-new storm.
- IF `MERGE_WATCH_MAX_HOPS` hops have already happened in this watch THEN THE
  SYSTEM SHALL log an error and keep watching in the current run until the
  deadline, never failing the workflow over the bound.
- WHEN an execution's history predates the `merge-watch-continue-as-new` marker
  THE SYSTEM SHALL keep polling in one run exactly as today (migration by
  attrition, as `tests/test_patch_memoization.py` pins).
- WHEN a hop occurs THE SYSTEM SHALL emit one `workflow.logger.info` line
  naming the service/slug, history length, polls completed, hop number and
  remaining time to the deadline.
- WHILE a watch has hopped THE SYSTEM SHALL remain a single Running execution
  under one workflow id, so `visibility.ACTIVE_DEV_LOOPS_QUERY`
  (`WorkflowType = 'DevLoopWorkflow' AND ExecutionStatus = 'Running'`) and
  `start_dev_loop_workflow`'s `USE_EXISTING` conflict policy behave unchanged.

## Out of scope

- Fixing the stale closed-PR preflight (mctlhq/mctl-agents#438). It is what
  forced this slug to exist, and it is deliberately a separate change.
- Changing `MERGE_POLL_INTERVAL`, `MERGE_WATCH_DEADLINE`, the shepherd tick
  cadence or any other `_Cadence` value.
- Replacing polling with a GitHub webhook or signal-driven merge detection.
- Editing `temporal-dynamic-config` in the cluster to raise
  `limit.historyCount.warn`.
- `continue_as_new` for `IncidentLoopWorkflow`, `ImplementSweepWorkflow` or
  `ReconcileWorkflow`.
- The lifecycle `handoff-start`/`handoff/complete` flip (#353).
- Reducing per-poll event cost.

## Open questions

- The exact value of `MERGE_WATCH_HISTORY_FLOOR`. Proceeding with 4,096 —
  Temporal's documented `limit.historyCount.suggestContinueAsNew` default,
  which makes the local floor agree with the server signal it backs up and
  yields roughly 4 hops across a full 14-day watch at 15-minute polls.
- Whether `resume` should be a defaulted second parameter on `run` or a
  defaulted field on `IssueRef`. Proceeding with a field on `IssueRef`, so
  `run` keeps arity 1 and the workflow's decoded argument list stays
  `[IssueRef]` on every path. See design.md — this is the point the superseded
  attempt got wrong in both directions and it is settled here against the real
  definition at `dev_loop.py:428`.
- Whether the time-skipping test server surfaces
  `is_continue_as_new_suggested()` at all. Proceeding by making the local
  history floor an overridable module constant so tests can force a hop
  deterministically.
