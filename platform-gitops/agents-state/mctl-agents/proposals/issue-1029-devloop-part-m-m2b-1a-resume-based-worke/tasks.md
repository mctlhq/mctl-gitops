# Tasks: issue-1029-devloop-part-m-m2b-1a-resume-based-worke

- [ ] 1. Create `tests/test_merge_watch_worker_gap.py` with:
  - a time-skipping environment fixture;
  - a switchable `get_pr_state` fake (a holder with `state`, `calls` and
    `merged_returns`), which replaces the factory fake by activity name;
  - the remaining activities from `tests.test_dev_loop_workflow._fake_activities(released=True, ...)`,
    including the healthy lifecycle-ownership fakes;
  - `tests.temporal_harness.Worker`.

  DoD: the module imports and collects. The diff touches nothing under
  `orchestrator/`, `agents/` or `config/`.
- [ ] 2. (depends on 1) Add a `_resume_record(t0, offset)` builder for
  `MergeWatchResume`. It sets:
  - the absolute `deadline` string with a `Z` suffix;
  - `last_pr=OPEN_PR` and `saw_open_pr=True`;
  - `poll_index=0`;
  - `fast_cadence`, `shepherd_in_loop`, `concurrent_ticks` and
    `track_ownership` True, with `owned_entity_id`/`owner_epoch`;
  - `proposal_terminal_end` and `deferred_resume_contract` True;
  - `merge_gate_settled_head=OPEN_PR.head_sha`;
  - Succeeded stage results and `hops=0`.

  DoD: any flag forced False because the factory lacks a fake is listed in
  the docstring mapping.
- [ ] 3. (depends on 2) Add a `_run_with_gap(env, deadline_offset)` helper:
  1. Start `DevLoopWorkflow.run` with `IssueRef(issue_url, resume=record)`
     under worker 1 (`identity="gap-worker-1"`, `max_cached_workflows=0`).
  2. Poll `fetch_history()` with real-time sleeps until the `get_pr_state`
     result, the `TimerStarted` and the following `WorkflowTaskCompleted`
     are recorded, then stop worker 1.
  3. Switch the fake to `MERGED` and record `gap_start`.
  4. Call `env.sleep(12 min)` and record `gap_end`.
  5. Start worker 2 (`identity="gap-worker-2"`) and await the result.
  6. Return the result, the history, the run ids and the gap bounds.

  DoD: the helper never calls a workflow method directly.
- [ ] 4. (depends on 3) Add the scenario A test (deadline at +10 min). It
  asserts:
  - exactly one `get_pr_state` `ActivityTaskScheduled`;
  - `merged_returns == 0` and `result.pr.state == "OPEN"`;
  - the first post-gap `WorkflowTaskStarted.event_time >= deadline`.

  DoD: green on the baseline.
- [ ] 5. (depends on 3) Add the scenario B control test (deadline at +20
  min). It asserts a second `get_pr_state` schedule after `gap_end` and
  `result.pr.state == "MERGED"`. DoD: green.
- [ ] 6. (depends on 4, 5) Add shared interruption assertions used by A and
  B:
  - worker-1 identities only before the gap, worker-2 identities only after
    it, and the two identities differ;
  - no `WorkflowTaskScheduled`/`WorkflowTaskStarted` event and no
    `get_pr_state` schedule inside [gap_start, gap_end];
  - the same workflow id and run id, `first_execution_run_id` unchanged, and
    no `ContinuedAsNew` event;
  - the decoded `resume.deadline` unchanged.

  DoD: they fail when worker 1 is kept running through the gap.
- [ ] 7. (depends on 2) Add a separate resume-record verification test. It
  decodes the `WorkflowExecutionStarted` input and compares every field the
  test set. It also asserts:
  - no investigate/submit activity was scheduled;
  - the poll timer's duration equals `MERGE_POLL_INTERVAL`.

  DoD: green, and every field set in task 2 is named in an assertion.
- [ ] 8. Write the mapping of the executed `_watch_pr` statements against an
  ordinary production merge watch into the module docstring. It covers:
  - the deadline source;
  - the flag source (patched or resume);
  - the shepherd tick not reached;
  - the gate suppressed;
  - the worker cache setting;
  - 12 virtual minutes against 14 days;
  - the limit that the A pin holds even without the gap.

  It also states that the test is not equivalent to a 14-day outage. DoD:
  the docstring and the PR body agree.
- [ ] 9. Collect the evidence:
  - one single run;
  - 20 consecutive repeats in batches under 300 s each, with every batch
    output reported;
  - the four mutations (a final read at the deadline exit, worker 1 kept
    running, an A deadline after the timer, no fake switch), each shown
    failing, reverted, and absent from the diff.

  DoD: 20/20 passes. Otherwise stop, report a negative result on #1029, and
  open no PR that presents as success.
- [ ] 10. Open the PR as a single implementation commit, with the evidence
  in the body. Verify that GitHub reports it as blocked by the #1020
  code-owner hold, and stop if it is not. DoD: no merge, bypass, release,
  deployment or flag change.

## Tests

- [ ] T1. `test_deadline_in_gap_ends_watch_without_reading_merged` (scenario
  A pin plus the interruption assertions).
- [ ] T2. `test_deadline_after_poll_timer_reads_merged_after_gap` (scenario
  B control plus the interruption assertions).
- [ ] T3. `test_resume_record_fields_reach_the_merge_watch_path`
  (resume-record verification).
- [ ] T4. A local-only mutation run of the four mutations, documented in the
  PR and not committed.
- [ ] T5. `uv run pytest tests/test_execution_request_resume.py
  tests/test_dev_loop_workflow.py -q` still green (no shared-fixture
  regressions).

## Rollback

Revert the single commit, or delete
`tests/test_merge_watch_worker_gap.py`. No production code, configuration,
patch marker or deployed state changes, so nothing else needs to be undone.
