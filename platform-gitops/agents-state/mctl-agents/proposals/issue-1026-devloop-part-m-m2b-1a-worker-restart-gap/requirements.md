# DevLoop Part M M2b-1a: worker-restart gap harness feasibility

## Context

Issue mctlhq/mctl-agents#1026 is the first sequential child of #1021. Before any
production change is written, it asks one question: can the existing Temporal
test harness run a real `DevLoopWorkflow` into its merge watch (`_watch_pr`),
stop the only worker on its task queue, let the absolute merge-watch deadline
(`MERGE_WATCH_DEADLINE`, 14 days) pass while no worker polls, change the PR
state while the worker is down, then restart a second worker on the same queue?
And does that show that the current baseline misses the `MERGED` transition?
The parent's implementer stopped with no commits, partly because it could not
confirm this. Every later slice of #1021 depends on the answer.

The deliverable is test-only: one new test module with two scenarios. Scenario
A puts the deadline inside the gap and pins the current defective behaviour.
Scenario B is a control with a gap shorter than the deadline. The PR also
carries reproducibility evidence (20 of 20 passes) and mutation proof. A
negative result is a valid outcome, and it must be reported as one, never
presented as success.

## User stories

- AS the #1021 slice author I WANT a reproducible Temporal-level test of a worker stop spanning the merge-watch deadline SO THAT later slices can invert a pin that already exists, instead of arguing about whether the gap is expressible.
- AS a reviewer I WANT history-based evidence that the interruption was real and the deadline was absolute SO THAT the pin cannot pass for a reason other than the defect.
- AS the platform owner I WANT this slice to touch no production code SO THAT it carries no release, deployment or replay risk.

## Acceptance criteria (EARS)

- WHEN `uv run --locked pytest tests/test_merge_watch_gap_harness.py -q` is run THE SYSTEM SHALL execute scenario A and scenario B through a real `WorkflowEnvironment.start_time_skipping()` server and a real `DevLoopWorkflow` registered on `tests.temporal_harness.Worker`, with fakes only at the activity boundary.
- WHEN scenario A runs THE SYSTEM SHALL start worker 1, drive the workflow into `_watch_pr` with `get_pr_state` answering `OPEN`, wait for at least one recorded read, exit worker 1, switch the fake to `MERGED`, advance time with `env.sleep` past watch start plus `MERGE_WATCH_DEADLINE`, then start worker 2 on the same task queue and await the result.
- WHEN scenario A completes THE SYSTEM SHALL assert, from the workflow history, that no `WorkflowTaskStarted` event falls inside the gap, that the `WorkflowTaskStarted` identities before and after the gap differ, and that the `get_pr_state` call count did not change during the gap.
- WHEN scenario A completes THE SYSTEM SHALL assert the same run id before and after the restart, and no `WorkflowExecutionContinuedAsNew` event in the history.
- WHEN scenario A completes THE SYSTEM SHALL assert, from history timestamps, that the watch start plus `MERGE_WATCH_DEADLINE` is earlier than the first `WorkflowTaskStarted` after the restart, and that no timer started after the restart has a duration that re-arms a new 14-day watch.
- WHEN scenario A completes on the current baseline THE SYSTEM SHALL assert that no `get_pr_state` was called after the restart, that `result.pr.state == "OPEN"`, and that `result.pr.merged is False`, while the fake answers `MERGED`.
- WHEN scenario B runs with a gap shorter than `MERGE_WATCH_DEADLINE` THE SYSTEM SHALL assert that worker 2 performs at least one `get_pr_state` read that returns `MERGED` and that `result.pr.state == "MERGED"`.
- WHILE either scenario runs THE SYSTEM SHALL NOT call workflow methods directly, mock Temporal workflow execution, or patch `orchestrator/` code.
- WHILE this change is in review THE SYSTEM SHALL keep `git diff origin/main -- orchestrator agents config` empty.
- IF a reusable helper cannot live in the test module THEN THE SYSTEM SHALL place it in `tests/temporal_harness.py` and nowhere else.
- IF fewer than 20 of 20 consecutive repeats pass, or the time-skipping server does not deliver the workflow task to worker 2, or the baseline does read the PR after the restart, or a production change appears necessary THEN THE SYSTEM SHALL stop, report the negative finding on #1026, and open no PR that presents the result as success.
- WHEN the PR is opened THE SYSTEM SHALL include the single-run command output, every batch of the 20 repeats, green runs of the existing merge-watch tests in `tests/test_dev_loop_workflow.py` and of `tests/test_worker_teardown_eviction.py`, and the five mutation results (mutation, failing test, failure message), with every mutation reverted and absent from the diff.

## Out of scope

- Any change under `orchestrator/`, `agents/` or `config/`: no workflow fix, no patch marker, no new activity, no typed outcome, no fixture migration.
- Inverting the scenario A pin. That belongs to a later slice of #1021, with its own proposal, digest and approval.
- Restarting or reusing #1021's DevLoop or its consumed approval, and any change to umbrella #993.
- Merge, release, deployment or flag changes. B4 stays FAIL, and the release hold, #1003 and gitops#2394 are untouched.
- Autonomous merge or admin bypass. The first PR must be verified as blocked by GitHub (the code-owner hold from #1020).

## Open questions

- Sticky queue behaviour during the gap. Worker 1 owns a sticky queue. Whether the time-skipping server times out the sticky schedule-to-start (and moves the task to the normal queue) once `env.sleep` advances time, or whether SDK shutdown clears stickiness, is not observable from the clone. The design allows either history shape (`WorkflowTaskTimedOut` and rescheduling are permitted inside the gap, `WorkflowTaskStarted` is not). If worker 2 never receives the task, that is a STOP condition, not something to work around.
- Worker identity. Both workers run in one process, so the SDK default identity (pid@host) is identical for both. The design passes an explicit `identity=` through `Worker(**kwargs)`. This is assumed to be acceptable as test configuration, not a harness change.
- The issue's budget section quotes the parent's spend as "/bin/zsh.17". This is read as a shell-expansion artefact of "$0.17". It has no bearing on the design.
