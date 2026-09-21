# Tasks: issue-404-devloopworkflow-never-calls-continue-as-v2

> Rebased onto `main` at 1.53.0 (post mctlhq/mctl-agents#434). Every line
> number below was read from current `main`. Do NOT restore the structure of
> the superseded attempt (PR mctlhq/mctl-agents#437, closed unmerged) — build
> on the `approval-watch` / `abandon` behaviour that is on `main` today.

- [ ] 0. Confirm the starting point before writing code: `git log --oneline -1`
  on `main` includes #434, `dev_loop.py` has `abandon` (`:990`),
  `abandon_state` (`:963`) and `IssueRef` with a single `issue_url` field
  (`:428`), and `continue_as_new` appears nowhere in `orchestrator/`.
  — DoD: if any of these is false, stop and re-read design.md's "Current
  state" rather than adapting the plan silently.

- [ ] 1. Add the carried-state type and the two new constants to
  `orchestrator/temporal/workflows/dev_loop.py`: a frozen `MergeWatchResume`
  dataclass with every field defaulted (watch cursor, carried decisions,
  lifecycle claim fields, **abandon state**, prior `WorkflowResult`s,
  `ImplementExecutionState`, `approver`, `hops`), plus
  `MERGE_WATCH_HISTORY_FLOOR = 4096` and `MERGE_WATCH_MAX_HOPS = 16` as
  one-line module constants beside `MERGE_WATCH_DEADLINE` (`:201`).
  — DoD: `uv run mypy` and `uv run ruff check orchestrator config tests tools`
  pass (line length 120); every field has a default and a comment saying why it
  must survive the boundary; `claim_abandoned` and `abandoned` are separate
  fields with a comment pointing at `AbandonState`'s docstring (`:507-515`).

- [ ] 2. Add `resume: MergeWatchResume | None = None` as a defaulted field on
  `IssueRef` (`:427-429`) (depends on 1). Do NOT add a second parameter to
  `run`.
  — DoD: `DevLoopWorkflow`'s decoded argument list stays `[IssueRef]`
  (assertable via `temporalio.workflow._Definition.from_class`);
  `orchestrator/temporal/start.py` is unchanged; `IssueRef(issue_url=...)`
  still constructs with one argument everywhere it is built today.

- [ ] 3. Add the hop predicate as a small private helper (depends on 1) —
  `workflow.info().is_continue_as_new_suggested()` (a METHOD in temporalio
  1.31.0, `temporalio/workflow/_context.py:186`) OR
  `workflow.info().get_current_history_length() >= MERGE_WATCH_HISTORY_FLOOR`,
  gated on `not self._abandoned`, polls-this-run, no in-flight tick, and the
  hop cap.
  — DoD: pure enough to unit-test by monkeypatching `dev_loop.workflow`, as
  `TestTickSettling` does; a comment records that reading the suggestion
  without calling it is always truthy.

- [ ] 4. Evaluate `workflow.patched("merge-watch-continue-as-new")` once at the
  top of `_watch_pr`, beside the existing markers (`:2633-2674`), and store it
  (depends on 3).
  — DoD: an execution whose history lacks the marker takes today's exact
  command sequence; no new command is scheduled on the unpatched path.

- [ ] 5. Make `_watch_pr` (`:2613`) hop-aware (depends on 4): accept an
  optional `resume`, take `deadline` from it (parsed with `_as_utc`) instead of
  recomputing it, rehydrate `poll_index`/`shepherd_ticks`/`polls_without_pr`/
  `last` and the carried decision booleans instead of re-reading the four
  markers, break the loop on a hop, and return
  `_WatchOutcome(last, resume)` instead of `PRState | None`.
  — DoD: the deadline is never recomputed on a resumed run; `_Cadence`
  selection on a resumed run comes from carried data; the
  `while ... and not self._abandoned` condition (`:2703`) is preserved
  verbatim.

- [ ] 5a. Make the abandon guard resume-aware (depends on 5). `if self._abandoned:
  return None` at `:2621-2622` runs BEFORE the deadline is computed at `:2623`;
  on the resume path it must return the carried `last_pr` instead of `None`, so a
  carried abandon does not erase the PR state earlier runs observed. The
  unpatched/non-resume path keeps returning `None` unchanged.
  — DoD: covered by T5; no behaviour change for an execution without a resume
  record.

- [ ] 6. Make the `finally` block (`:2843`) skip the relinquishing
  `release`/`terminal` write and `_report_claim_abandonment` (`:2905-2907`)
  when the watch is hopping (depends on 5), while still draining a finished
  tick.
  — DoD: a hop produces zero `lifecycle_ownership` activity calls with
  `op in {"release", "terminal"}`; `_owned_entity_id` and `_owner_epoch` are
  carried into the resume record unchanged.

- [ ] 7. Rehydrate and continue in `run` (`:1008`) (depends on 2, 5, 6):
  when `issue.resume` is not None restore `_implement_state`,
  `_shepherd_in_loop`, `_cadence`, `_approved`/`_approver`, every lifecycle
  field and `_abandoned`/`_abandon_reason` before the first await; skip
  investigate, the approval park (`:1048`), admission, slug lookup, approve and
  implement; and call
  `workflow.continue_as_new(IssueRef(issue_url=..., resume=resume))` at the top
  level when `_watch_pr` returns a hop request.
  — DoD: the final `DevLoopResult` carries the `investigate`/`implement`/
  `approve` results produced in the first run; a resumed run schedules no
  investigate/approve/implement command.

- [ ] 8. Re-check the abandon state at the start of a continued run (depends on
  7), before the first sleep, so an `abandon` observed pre-hop still ends the
  watch.
  — DoD: covered by T5; the early-exit path at `:2621` is reached without an
  intervening poll sleep.

- [ ] 8a. Keep `DevLoopResult.ended` correct across a hop (depends on 7). The
  field (`:544-550`) is written at seven return sites; `:1309`
  (`ended=f"abandoned: {self._abandon_reason}" if self._abandoned else ""`) is
  the only record of a merge-watch abandon and is what `cli.py status` prints on
  a COMPLETED execution. The final run of a hopped watch must populate it exactly
  as an unhopped watch would.
  — DoD: asserted by T5b; no return site loses its `ended=` argument.

- [ ] 9. Log one line per hop (depends on 7): service/slug, history length,
  polls completed this run, hop number, and time left to the carried deadline.
  — DoD: `workflow.logger.info`, plain words, no emoji (CONTRIBUTING.md code
  style); asserted through the `caplog` pattern already used in
  `tests/test_dev_loop_workflow.py`.

- [ ] 10. Refresh the machine-checked docs (depends on 4): regenerate
  `docs/diagrams/archify/facts.yaml` with
  `python3 tools/diagram_facts.py --update` so `merge-watch-continue-as-new`
  joins the scraped `patched_markers` list, and update the dev-loop diagram
  sublabels in `docs/diagrams/archify/dev-loop.workflow.json` if they still say
  "poll 30 min". #434 is the precedent for how wide this goes: it also touched
  `docs/temporal-flow.md`, `docs/diagrams/temporal-flow-states.mmd` and
  `docs/diagrams/temporal-flow-devloop-sequence.mmd`. A change that adds a run
  boundary to the state machine should expect the same set.
  — DoD: `uv run pytest tests/test_diagram_facts.py` green;
  `python3 tools/diagram_facts.py` reports no drift.

- [ ] 11. Record the mechanism in
  `docs/adr/006-dev-loop-merge-deploy-monitor.md` (depends on 7): why the watch
  hops, why the deadline is an input, why the claim is not released on a hop,
  how `abandon` is kept safe across the boundary, and the narrowing of the
  attrition property.
  — DoD: a reader of ADR-006 can explain why a DevLoop workflow id has more
  than one run without reading `dev_loop.py`.

## Tests

- [ ] T1. `MergeWatchResume` survives the payload converter: a round-trip test
  in the style of `tests/test_stranded_skipped_roundtrip.py` (a tiny workflow
  receiving a fully populated instance, including a non-None `last_pr` and
  three `WorkflowResult`s) — the converter, not an `ActivityEnvironment` fake.
- [ ] T2. `IssueRef` still decodes as a single argument: assert
  `_Definition.from_class(DevLoopWorkflow)` reports one argument type, and that
  `IssueRef(issue_url=...)` (no `resume`) round-trips. This pins the exact
  claim the superseded attempt got wrong.
- [ ] T3. Forced hop, end to end: monkeypatch
  `dev_loop.MERGE_WATCH_HISTORY_FLOOR` low, drive the existing merge-watch
  setup (`_fake_activities(released=True, pr_states=[open_pr, ..., MERGED_PR])`),
  and assert the watch still returns the MERGED state and a `DevLoopResult`
  whose `investigate`/`implement`/`approve` are populated.
- [ ] T4. The deadline does not reset: after at least one forced hop the watch
  still ends at the original absolute deadline (drive it with an always-OPEN
  `PRState` under the time-skipping env, as
  `test_merge_detection_deadline_returns_last_open_state` does) and the final
  result is `state == "OPEN"`.
- [ ] T5. **Abandon beats the hop** (new): signal `abandon` while the hop
  predicate would otherwise fire, and assert the watch ends with the abandon
  path rather than continuing; and after a forced hop, assert `abandon_state`
  in the continued run still reports the carried `abandoned`/`reason`.
- [ ] T5a. **A carried abandon does not erase the PR state**: force a hop, then
  signal `abandon`, and assert the final result carries the last observed
  `PRState` rather than `None` — i.e. the guard at `:2621-2622` took the resume
  path (task 5a).
- [ ] T5b. **`ended` survives the hop**: after a forced hop the final
  `DevLoopResult.ended` is `""` for a normal terminal state and
  `abandoned: <reason>` when the watch ended on a carried abandon, matching what
  `:1309` produces today.
- [ ] T6. Queries survive the boundary: after a forced hop, `shepherd_in_loop`
  still answers True, `implement_execution` still reports `stage="implementer"`
  with the pre-hop `outcome`, `lifecycle_claim` still names the same
  `entity_id` and `epoch`, and `abandon_state` answers as before.
- [ ] T7. No ownership churn on a hop: the captured `ownership_ops` list
  contains no `release`/`terminal` op before the PR reaches a terminal state,
  and the epoch carried after the hop equals the one acquired before it.
- [ ] T8. Hop safety rails, as direct unit tests on a bare `DevLoopWorkflow()`
  with a monkeypatched `dev_loop.workflow` (the `TestTickSettling` pattern):
  no hop before one completed poll, no hop with an unfinished `tick_task`, no
  hop past `MERGE_WATCH_MAX_HOPS`, no hop while `_abandoned`, and a hop when
  only `is_continue_as_new_suggested()` is true.
- [ ] T9. Attrition holds: `uv run pytest tests/test_workflow_replay.py` stays
  green, plus a new content guard asserting `"merge-watch-continue-as-new"` is
  absent from the prepatch history's patch ids — mirror
  `test_prepatch_history_predates_the_approval_watch`
  (`tests/test_workflow_replay.py:218`), which #434 added for exactly this
  purpose. Note `_STANDALONE_FIXTURES` (`:473`) and the parked-history replay
  `test_parked_history_replays_against_current_definitions` (`:244`, over the
  new `tests/fixtures/histories/dev_loop_parked.json`) impose the same fixture
  discipline on any new marker.

- [ ] T9a. **#434's suites stay green unmodified.** These pin the behaviour this
  change builds on; if any needs editing, the change is wrong:
  `tests/test_dev_loop_workflow.py` —
  `test_abandon_signal_ends_a_parked_loop` (:630),
  `test_parked_loop_ends_when_the_source_issue_closes` (:669),
  `test_parked_loop_expires_at_the_approval_deadline` (:711),
  `test_issue_state_failure_while_parked_keeps_waiting` (:737),
  `test_parked_closed_issue_not_resurrected_by_late_approve` (:830),
  `test_abandon_signal_cuts_short_a_merge_watch_and_releases_ownership` (:1598)
  — **the most likely casualty**, since it pins that an abandon RELEASES the
  ownership row while task 6 makes a HOP skip that release —
  and `test_abandon_signal_before_pr_watch_terminates_cleanly` (:1659);
  `tests/test_temporal_cli.py` :53, :70, :80; and
  `tests/test_run_implementer_approval.py:337`.
  Caution: the lifecycle-claim suite at `tests/test_dev_loop_workflow.py:2188-2310`
  exercises `_claim_abandoned` (the ownership row), NOT `_abandoned` (the
  operator signal). Similar names, different attributes — do not conflate them.
- [ ] T10. Re-record only the patched fixture:
  `uv run python tools/record_workflow_history.py --kind patched dev_loop_full`,
  commit the diff, and confirm the existing patched-history assertions still
  pass. Do not re-record `*.prepatch.json`.
- [ ] T11. Full gate: `uv run pytest -q`, `uv run ruff check orchestrator
  config tests tools`, `uv run mypy` — the three commands
  `.github/workflows/pr-validation.yml` runs. The tests job has a 10-minute
  cap, so new tests must rely on time skipping and never wall-clock waits.

## Rollback

Rolling back is two steps, not one, because a hop leaves executions whose next
run carries a `resume` payload.

1. **Disable hopping, keep resume.** Ship a one-line change making the hop
   predicate return False (or set `MERGE_WATCH_MAX_HOPS = 0`). New watches stay
   in a single history immediately; executions that already hopped keep
   resuming correctly, because the resume field and its rehydration are still
   there. This is the emergency lever and it is safe at any moment.
2. **Remove the resume path only after the hopping executions drain.** They are
   bounded by `MERGE_WATCH_DEADLINE`, so 14 days after step 1 no execution can
   still carry a `MergeWatchResume`. Revert the rest then.

Reverting in one step while a continued run is alive would leave that run's
next continuation decoding an `IssueRef` whose `resume` field no longer exists.
Because `resume` is a dataclass field rather than a positional argument, the
likely outcome is a decode error on that one execution rather than a silent
restart from investigate — still bad, still avoided by the two-step order. If
it has already happened, the recovery is to terminate the affected `dev-loop-*`
executions: the watch is observational, the implement and merge have already
occurred, and `run_shepherd`'s cron sweeper resumes shepherding as soon as the
`shepherd_in_loop` query stops answering True. Nothing in gitops, mctl-api or
the lifecycle store needs to be undone — the only lifecycle row involved is
released by the reconciler's liveness bound once the execution is gone
(ADR-010 §5).
