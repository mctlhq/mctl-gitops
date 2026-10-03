# Tasks: issue-404-devloopworkflow-never-calls-continue-as

- [ ] 1. Add the carried-state type and the two new constants to
  `orchestrator/temporal/workflows/dev_loop.py`: a frozen
  `MergeWatchResume` dataclass with every field defaulted (watch cursor,
  carried decisions, lifecycle claim fields, prior `WorkflowResult`s and
  `ImplementExecutionState`, `hops`), plus
  `MERGE_WATCH_HISTORY_FLOOR = 4096` and `MERGE_WATCH_MAX_HOPS = 16` as
  one-line module constants beside `MERGE_WATCH_DEADLINE` (line 181).
  — DoD: `uv run mypy` and `uv run ruff check orchestrator config tests tools`
  pass (line length 120); every field has a default and a comment saying why
  it must survive the boundary.

- [ ] 2. Add the hop predicate as a small private helper next to `_backed_off`
  (depends on 1) — `workflow.info().is_continue_as_new_suggested()` (a
  METHOD in temporalio 1.31.0; `temporalio/workflow/_context.py:186`) OR
  `workflow.info().get_current_history_length() >= MERGE_WATCH_HISTORY_FLOOR`,
  gated on polls-this-run, no in-flight tick, and the hop cap.
  — DoD: pure enough to unit-test by monkeypatching `dev_loop.workflow`, as
  `TestTickSettling` does (`tests/test_dev_loop_workflow.py:3831-3845`); a
  comment records that reading the suggestion without calling it is always
  truthy.

- [ ] 3. Evaluate `workflow.patched("merge-watch-continue-as-new")` once at
  the top of `_watch_pr`, beside the existing markers (`dev_loop.py:2451-2492`),
  and store it (depends on 2) — the marker gates a real branch, per the
  anti-pattern note at `dev_loop.py:2493-2501`.
  — DoD: an execution whose history lacks the marker takes today's exact
  command sequence; no new command is scheduled on the unpatched path.

- [ ] 4. Make `_watch_pr` hop-aware (depends on 3): accept an optional
  `resume: MergeWatchResume | None`, take `deadline` from it (parsed with
  `_as_utc`, `dev_loop.py:644`) instead of recomputing line 2441, rehydrate
  `poll_index`/`shepherd_ticks`/`polls_without_pr`/`last` and the carried
  decision booleans instead of re-reading `fast-shepherd-cadence`,
  `shepherd-in-loop`, `concurrent-shepherd-tick` and `lifecycle-ownership`,
  break the loop on a hop, and return a `_WatchOutcome(last, resume)`.
  — DoD: the deadline is never recomputed on a resumed run; `_Cadence`
  selection on a resumed run comes from carried data.

- [ ] 5. Make the `finally` block (`dev_loop.py:2656-2720`) skip the
  relinquishing `release`/`terminal` write and `_report_claim_abandonment`
  when the watch is hopping (depends on 4), while still draining a finished
  tick.
  — DoD: a hop produces zero `lifecycle_ownership` activity calls with
  `op in {"release", "terminal"}`; `_owned_entity_id` and `_owner_epoch` are
  carried into the resume record unchanged.

- [ ] 6. Add the resume parameter to `DevLoopWorkflow.run`
  (`async def run(self, issue: IssueRef, resume: MergeWatchResume | None = None)`),
  rehydrate `_implement_state`, `_shepherd_in_loop` and every lifecycle field
  from it before the first await, skip investigate/approve/slug/implement on a
  resumed run, and call `workflow.continue_as_new(args=[issue, resume])` at
  the top level when `_watch_pr` returns a hop request (depends on 4, 5).
  — DoD: `orchestrator/temporal/start.py` is unchanged and still starts with a
  single `IssueRef` payload; the final `DevLoopResult` carries the
  `investigate`/`implement`/`approve` results produced in the first run.

- [ ] 7. Log one line per hop (depends on 6): service/slug, history length,
  polls completed this run, hop number, and time left to the carried deadline.
  — DoD: `workflow.logger.info`, plain words, no emoji (CONTRIBUTING.md code
  style); asserted by T6 through the `caplog` pattern at
  `tests/test_dev_loop_workflow.py:1285-1304`.

- [ ] 8. Refresh the machine-checked docs (depends on 3): regenerate
  `docs/diagrams/archify/facts.yaml` with
  `python3 tools/diagram_facts.py --update` so the new
  `merge-watch-continue-as-new` id joins the scraped `patched_markers` list
  (`tools/diagram_facts.py:115`), and update the dev-loop diagram sublabels in
  `docs/diagrams/archify/dev-loop.workflow.json` (lines ~171 and ~221, which
  still say "poll 30 min").
  — DoD: `uv run pytest tests/test_diagram_facts.py` green; `python3
  tools/diagram_facts.py` reports no drift.

- [ ] 9. Record the mechanism in `docs/adr/006-dev-loop-merge-deploy-monitor.md`
  (depends on 6): why the watch hops, why the deadline is an input, why the
  claim is not released on a hop, and the narrowing of the attrition property
  (a continued run executes the currently deployed code).
  — DoD: a reader of ADR-006 can explain why a DevLoop workflow id has more
  than one run without reading `dev_loop.py`.

## Tests

- [ ] T1. `MergeWatchResume` survives the payload converter: a round-trip test
  in the style of `tests/test_stranded_skipped_roundtrip.py` (a tiny workflow
  that receives a fully populated instance, including a non-None `last_pr` and
  three `WorkflowResult`s) — the converter, not an `ActivityEnvironment` fake,
  must be exercised.
- [ ] T2. Forced hop, end to end: monkeypatch `dev_loop.MERGE_WATCH_HISTORY_FLOOR`
  low, drive the existing merge-watch setup (`_fake_activities(released=True,
  pr_states=[open_pr, ..., MERGED_PR])`, `tests/test_dev_loop_workflow.py:153`),
  and assert the watch still returns the MERGED state and a `DevLoopResult`
  whose `investigate`/`implement`/`approve` are populated.
- [ ] T3. The deadline does not reset: after at least one forced hop, the watch
  still ends at the original absolute deadline (drive it with an always-OPEN
  `PRState` under the time-skipping env, as
  `test_merge_detection_deadline_returns_last_open_state`
  (`tests/test_dev_loop_workflow.py:3029-3062`) does) and the final result is
  `state == "OPEN"`.
- [ ] T4. Queries survive the boundary: after a forced hop, `shepherd_in_loop`
  still answers True, `implement_execution` still reports
  `stage="implementer"` with the pre-hop `outcome`, and `lifecycle_claim`
  still names the same `entity_id` and `epoch`.
- [ ] T5. No ownership churn on a hop: the captured `ownership_ops` list from
  `_run_ownership_loop` (`tests/test_dev_loop_workflow.py:1340`) contains no
  `release`/`terminal` op before the PR reaches a terminal state, and the
  epoch carried after the hop equals the one acquired before it.
- [ ] T6. Hop safety rails, as direct unit tests on a bare `DevLoopWorkflow()`
  with a monkeypatched `dev_loop.workflow` (the `TestTickSettling` pattern,
  `tests/test_dev_loop_workflow.py:3848-3986`, since a tick in flight stops
  the time-skipping clock): no hop before one completed poll, no hop with an
  unfinished `tick_task`, no hop past `MERGE_WATCH_MAX_HOPS`, and a hop when
  only `is_continue_as_new_suggested()` is true.
- [ ] T7. Attrition holds: `uv run pytest tests/test_workflow_replay.py` stays
  green against `tests/fixtures/histories/dev_loop_full.prepatch.json`, plus a
  new content guard mirroring
  `test_dev_loop_prepatch_history_predates_the_stale_issue_gate`
  (`tests/test_workflow_replay.py:192-215`) asserting
  `"merge-watch-continue-as-new"` is absent from the prepatch history's patch
  ids.
- [ ] T8. Re-record only the patched fixture:
  `uv run python tools/record_workflow_history.py --kind patched dev_loop_full`,
  commit the diff, and confirm
  `test_patched_histories_show_submit_and_wait_on_the_execution_queue` and
  `test_every_history_actually_reaches_submit_and_wait` still pass. Do not
  re-record `*.prepatch.json`.
- [ ] T9. Full gate: `uv run pytest -q`, `uv run ruff check orchestrator
  config tests tools`, `uv run mypy` — the three commands
  `.github/workflows/pr-validation.yml` runs. The tests job has a 10-minute
  cap, so the new tests must rely on time skipping and never wall-clock waits.

## Rollback

Rolling back is two steps, not one, because a hop leaves executions whose next
run was started with two payloads.

1. **Disable hopping, keep resume.** Ship a one-line change making the hop
   predicate return False (or set `MERGE_WATCH_MAX_HOPS = 0`). New watches
   stay in a single history immediately; executions that already hopped keep
   resuming correctly, because the resume path and the run signature are still
   there. This is the emergency lever and it is safe at any moment.
2. **Remove the resume path only after the hopping executions drain.** They
   are bounded by `MERGE_WATCH_DEADLINE`, so 14 days after step 1 no execution
   can still be carrying a `MergeWatchResume`. Revert the rest then.

Reverting the whole change in one step while a continued run is alive would
leave that run's next hop calling a one-parameter `run` with two payloads:
best case the extra argument is dropped and the workflow restarts from
investigate — re-running the investigator and re-submitting an approve flip
for an issue that is already implemented. If that has already happened, the
recovery is to terminate the affected `dev-loop-*` executions by hand: the
watch is observational, the implement and merge have already occurred, and
`run_shepherd`'s cron sweeper resumes shepherding as soon as the
`shepherd_in_loop` query stops answering True. Nothing in gitops, mctl-api or
the lifecycle store needs to be undone — the only lifecycle row involved is
released by the reconciler's liveness bound once the execution is gone
(ADR-010 §5).
