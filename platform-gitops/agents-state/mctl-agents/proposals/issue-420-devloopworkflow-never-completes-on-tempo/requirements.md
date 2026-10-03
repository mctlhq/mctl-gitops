# Bound the DevLoopWorkflow approval park so every execution reaches a terminal Temporal status

## Context

`DevLoopWorkflow` (`orchestrator/temporal/workflows/dev_loop.py`) parks at a single
unbounded durable wait — `await workflow.wait_condition(lambda: self._approved)` at
line 909 — until an `approve` signal arrives. Nothing else can release that wait: not
the source issue closing, not the proposal being approved out of band through the
standalone `mctl-agents-approve` operation, not the implementer running and its PR
merging via the cron path. Every other stage of the loop is already bounded
(`SDK_STEP_TIMEOUT` 2 h per CWFT submit, `MERGE_WATCH_DEADLINE` 14 days for the PR
watch, `DEPLOY_VERIFY_DEADLINE`, `INCIDENT_WATCH_WINDOW`), and `_watch_pr` already
returns the moment a PR reads `MERGED` or `CLOSED`. The approval park is the one place
an execution can live forever, and it is where `dev-loop-mctlhq-portfolio-98` is sitting:
its proposal was approved and implemented through the gitops path, `portfolio#99` merged
on 2026-09-13, `portfolio#98` closed the same day, and seven days later the execution
still reports `Running`.

This matters because a never-terminal execution is a silent leak. It never alerts, it
keeps answering the `shepherd_in_loop` query the cron sweeper consults, and it forces an
operator scanning the `Running` list to cross-reference each execution against GitHub by
hand to tell live work from finished work. There is also no way to end one without direct
Temporal CLI or `kubectl` access: `orchestrator/temporal/cli.py` exposes only
`start`, `approve` and `status`, and mctl-api exposes only the approve endpoint. This
proposal bounds the park, makes it observant of the facts that make an approval moot, and
adds a graceful operator-driven end that works on executions already stuck today.

## User stories

- AS a platform operator I WANT every `DevLoopWorkflow` execution to reach a terminal
  Temporal status on its own SO THAT the `Running` list is a list of live work and not a
  mix of live work and abandoned parks.
- AS a platform operator I WANT a `DevLoopWorkflow` whose source issue has closed to end
  itself SO THAT I do not have to cross-reference each execution against GitHub state.
- AS a platform operator I WANT a documented, cluster-access-free way to end one specific
  stuck execution SO THAT recovering from a leak does not require Temporal CLI or
  `kubectl`.
- AS a mctl-agents maintainer I WANT the change gated by a patch marker and covered by a
  replay fixture SO THAT in-flight executions are not wedged by a nondeterministic edit.

## Acceptance criteria (EARS)

- WHILE parked at the approval wait THE SYSTEM SHALL re-read the source issue's state on a
  bounded poll cadence rather than waiting only on the `approve` signal.
- WHEN the source issue is observed `closed` while the workflow is parked at the approval
  wait THE SYSTEM SHALL stop waiting and return a `DevLoopResult` that records why it
  ended, without submitting the `mctl-agents-approve` CWFT and without submitting the
  implementer.
- IF the approval park reaches `APPROVAL_WAIT_DEADLINE` with no signal and an open issue
  THEN THE SYSTEM SHALL end the execution with a `DevLoopResult` recording the expiry,
  rather than continuing to wait.
- WHEN an `abandon` signal is delivered to a `DevLoopWorkflow` THE SYSTEM SHALL leave the
  approval wait (or cut short the merge watch) at its next observation point, run its
  existing lifecycle-ownership cleanup, and complete with the abandonment recorded in the
  result.
- WHEN the watched PR is observed `MERGED` or `CLOSED` THE SYSTEM SHALL end the merge
  watch within one `MERGE_POLL_INTERVAL` of that observation (already true in `_watch_pr`;
  this proposal pins it with a regression test rather than changing it).
- WHILE the `get_issue_state` activity is failing THE SYSTEM SHALL keep waiting for the
  approval signal and retry on the next poll boundary rather than failing the workflow,
  matching the fail-open rule the existing `stale-issue-admission` gate applies.
- IF an execution's history predates the new patch marker AND that execution has already
  passed the approval wait THEN THE SYSTEM SHALL replay its recorded command sequence
  unchanged.
- WHEN an operator runs the new CLI subcommand against a workflow id THE SYSTEM SHALL
  deliver the `abandon` signal and report the result, without requiring a Temporal
  `terminate` capability.
- WHEN an execution ends through any of the new paths THE SYSTEM SHALL record a reason
  string in `DevLoopResult` that `cli.py status` prints.

## Out of scope

- Changing `MERGE_WATCH_DEADLINE`, the shepherd tick cadence, or any other existing bound
  in `_Cadence`. The merge watch already terminates correctly.
- Retro-terminating the currently stuck executions as part of this change. The `abandon`
  signal plus the CLI subcommand is the tool; running it against the live namespace is an
  operator step, tracked separately.
- The mctl-api / MCP surface (`POST /api/v1/agents/dev-loop/{workflow_id}/abandon`, a
  `mctl_abandon_dev_loop` tool). That lives in the sibling `mctl-api` repo and cannot be
  implemented here; this proposal ships the signal and CLI it would call, and files the
  follow-up.
- Alerting on long-lived `Running` executions (a Temporal/VictoriaMetrics concern).
- Any change to `run_shepherd.py`'s `_dev_loop_owns` sweeper logic.
- Hard Temporal `terminate`. The graceful `abandon` signal is preferred precisely because
  `terminate` skips the `finally` block in `_watch_pr` that releases the lifecycle
  ownership row.

## Open questions

- **Deadline value.** The issue says "bounded time" without a number.
  `APPROVAL_WAIT_DEADLINE` is proposed at 14 days to match `MERGE_WATCH_DEADLINE`, and
  `APPROVAL_POLL_INTERVAL` at 6 h (≈56 polls over the deadline, negligible against
  Temporal's 50k event limit). A reviewer who wants an approval park to expire sooner
  should say so here; the constants are one-line changes.
- **Does the patch marker reach an already-parked execution?** The intent is that
  `workflow.patched("approval-watch")`, evaluated at a position that sits after the last
  recorded history event of a parked execution, returns `True` and records the marker —
  which would make the automatic fix retroactive for the 12 `Running` executions rather
  than applying only to new ones. This is asserted from Temporal's replay semantics, not
  yet measured against this repo's `Replayer` harness. Task T4 exists to measure it; if it
  returns `False` instead, the automatic path covers only new executions and the `abandon`
  signal (which needs no marker) is the recovery tool for the existing ones. Either way
  the proposal is complete — the reviewer should know which one they are getting.
- **Closed-as-`not_planned` vs closed-as-`completed`.** `IssueState` carries
  `state_reason`, and the existing `stale-issue-admission` gate ignores it, treating any
  `closed` as a stop. This proposal keeps that rule for consistency but records the reason
  in the result so the two cases are distinguishable after the fact.
- **Should the parked loop also watch for an out-of-band merged PR?** Reading the issue
  state alone already covers the observed incident (`portfolio#98` closed when its PR
  merged). Adding a `find_proposal_slug` + `get_pr_state` probe to every park poll would
  also catch a merged PR whose issue was never closed, at the cost of two more activities
  per poll. Proposed answer: no, not in this change — issue state is the cheaper and
  sufficient signal, and the deadline backstops the rest.
