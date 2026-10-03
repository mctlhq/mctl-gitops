# Tasks: issue-420-devloopworkflow-never-completes-on-tempo

- [ ] 1. Add the `abandon` signal and the `_abandoned` / `_abandon_reason` state to
      `DevLoopWorkflow` (`orchestrator/temporal/workflows/dev_loop.py`): initialise both in
      `__init__` (line 790), add `@workflow.signal def abandon(self, *args: object)` beside
      `approve` (line 869) using the same defensive `*args` parse that never raises, and add
      an `abandoned`/`abandon_reason` view to the existing `lifecycle_claim` or a new
      `abandon_state` query so an operator can read it back.
      — DoD: signalling `abandon` on a running execution sets the flag; the handler raises on
      no input shape; no `workflow.patched` marker is introduced by this task.

- [ ] 2. Make both long waits observe `_abandoned` (depends on 1). Broaden line 909's
      predicate to `lambda: self._approved or self._abandoned` in **both** the new and the
      legacy branch, and return a terminal `DevLoopResult` with `ended="abandoned: <reason>"`
      immediately after the wait — **before** the `workflow.patched("stale-issue-admission")`
      block at line 924, so no patched branch is entered on the abandon path. Add
      `and not self._abandoned` to `_watch_pr`'s `while workflow.now() < deadline` at
      line 2516 so the `finally` at line 2656 still runs its ownership release.
      — DoD: an execution parked at approval and one mid-merge-watch both complete (not fail,
      not terminate) after an `abandon` signal; the merge-watch case still issues its
      `_ownership("release", ...)` write; no new command appears in either path.

- [ ] 3. Add `DevLoopResult.ended: str = ""` (dataclass at line 486) with the documenting
      comment the sibling fields carry, and populate it on every non-pipeline exit: the
      investigate-failure return (line 903), the `stale-issue-admission` return (line 948),
      the failed-approve-flip return (line 1038), and the new abandon/closed/expired returns.
      — DoD: `DevLoopResult` deserialises unchanged from `tests/fixtures/histories/dev_loop_full.*.json`
      results; every terminal return in `run()` sets `ended` or is the full-pipeline return.

- [ ] 4. Measure `workflow.patched` behaviour against a history parked at the approval wait,
      **before** writing task 5 (depends on 3). Add a scenario/fixture whose recorded history
      ends at `wait_condition` (no approve signal), then assert: (a) `Replayer` replays it
      clean against today's definitions, and (b) an execution resumed from it under the new
      code takes the polling branch rather than the legacy one. Register the new fixture in
      `tests/replay_scenarios.py::SCENARIOS` (line 228) or in
      `tests/test_workflow_replay.py::_STANDALONE_FIXTURES` (line 398), which
      `test_every_recorded_fixture_belongs_to_a_scenario` (line 401) enforces. Record with
      `python -m tools.record_workflow_history --kind patched` only; the existing `prepatch`
      fixtures are evidence and must never be regenerated.
      — DoD: a written, measured answer to design.md's open question "does the marker reach an
      already-parked execution?" — and if the answer is no, task 5's scope is amended to
      "new executions only" and the `abandon` signal is documented as the recovery path for
      the twelve existing ones.

- [ ] 5. Bound and instrument the approval park behind `workflow.patched("approval-watch")`
      (depends on 2, 4). Add `APPROVAL_POLL_INTERVAL = timedelta(hours=6)` and
      `APPROVAL_WAIT_DEADLINE = timedelta(days=14)` to the constants block with the
      cost/derivation comment the surrounding constants all carry. Replace line 909 with the
      patched poll loop from design.md; keep the unpatched `else` branch byte-identical to
      today's call apart from the broadened predicate. Add a `_read_issue_state` helper
      wrapping the existing `get_issue_state` activity (already imported at line 69, already
      registered in `worker.py`'s `short_activities` at line 514) with the same fail-open
      `ActivityError` handling as the gate at line 936.
      — DoD: a parked execution whose issue is observed `closed` completes with
      `ended="source issue closed while parked (...)"` and `calls == ["mctl-agents-investigate"]`;
      a parked execution with an open issue completes at the deadline with
      `ended="approval wait expired"`; a signalled execution's command sequence past the wait
      is unchanged.

- [ ] 6. Add the `abandon` subcommand to `orchestrator/temporal/cli.py` (depends on 1):
      mirror `approve` (line 30) with a required, undefaulted `--reason` for the same reason
      `--approver` is required (line 101), and extend `status` (line 37) to print
      `result.ended` when non-empty.
      — DoD: `build_parser()` parses `abandon <workflow_id> --reason "..."`; the existing
      parser test that pins the approve command's shape still passes; `status` on an abandoned
      execution prints the reason.

- [ ] 7. Update the documentation the change invalidates (depends on 5).
      `docs/diagrams/temporal-flow-states.mmd`'s `AwaitApproval` note currently says the wait
      is unbounded; `docs/temporal-flow.md` says the same at lines 103 and 139. Regenerate
      `docs/diagrams/archify/facts.yaml` via `tools/diagram_facts.py` (line 115 extracts
      `workflow.patched("...")` markers) — note that committed snapshot is already stale
      (it lists 14 markers and is missing `stale-issue-admission`), so this task fixes that
      drift too. Add a short ADR-006 addendum, or a note in the dev_loop module docstring
      (line 1), recording that the approval park is now bounded and why.
      — DoD: no committed doc still states the approval wait is unbounded;
      `tests/test_diagram_facts.py` passes against the regenerated snapshot.

- [ ] 8. File the cross-repo follow-ups (depends on 6). (a) `mctl-api`: expose
      `POST /api/v1/agents/dev-loop/{workflow_id}/abandon` and an `mctl_abandon_dev_loop` MCP
      tool calling the signal from task 1 — this is what fully satisfies the issue's stretch
      criterion, since the CLI still needs Temporal frontend network access. (b) `mctl-api`:
      the `mctl_get_dev_loop` tool description asserts "wait_condition has no timeout, so the
      loop then waits forever", which becomes false on merge. (c) optional: a stale-`Running`
      sweeper built on `VisibilityActivities.list_active_dev_loop_ids`
      (`activities/visibility.py:109`), noting the `expected_dev_loop_id` service-vs-repo
      id-derivation quirk at `activities/orphans.py:82`.
      — DoD: three linked issues exist and are referenced from this PR's description.

- [ ] 9. Operator runbook step, executed after deploy (depends on 5, 6). Re-check the twelve
      `Running` executions in the `mctl-agents` namespace; for each whose source issue is
      already closed, confirm it self-terminated (if task 4 measured the marker as
      retroactive) or run `cli.py abandon` against it. Record the outcome on issue #420.
      — DoD: `mctl_get_dev_loop(workflow_id="dev-loop-mctlhq-portfolio-98")` no longer returns
      `status: "Running"`, and the `Running` list contains only executions whose issue/PR is
      genuinely live.

## Tests

All Temporal tests go in `tests/test_dev_loop_workflow.py`, using the module's existing
`env` fixture (line 147, `WorkflowEnvironment.start_time_skipping()`), the
`tests.temporal_harness.Worker` (imported at line 50), and `_fake_activities(...)`
(line 153) whose activity list at line 521 must keep covering every activity the new paths
reach. The `anyio.fail_after(10) / await investigate_ran.wait()` pair (line 556) is the
established way to know the workflow has actually parked at the wait before acting on it.

- [ ] T1. `test_abandon_signal_ends_a_parked_loop` — start, wait for `investigate_ran`,
      `await handle.signal(DevLoopWorkflow.abandon, "operator cleanup")`, assert
      `handle.result()` returns with `implement is None`, `approve is None`,
      `ended.startswith("abandoned:")`, and `calls == ["mctl-agents-investigate"]`.
      Closes acceptance criterion 4 in requirements.md.

- [ ] T2. `test_abandon_signal_cuts_short_a_merge_watch_and_releases_ownership` — drive to the
      merge watch with `pr_states` that stay `OPEN`, signal `abandon`, assert the execution
      completes and that `ownership_ops` (the 4th element of `_fake_activities`) records the
      `release` write from `_watch_pr`'s `finally`. This is the test that would turn red if
      someone "simplified" the fix to a Temporal `terminate`.

- [ ] T3. `test_parked_loop_ends_when_the_source_issue_closes` — `_fake_activities` with a
      `get_issue_state` fake that returns `IssueState(state="open")` on the first read and
      `IssueState(state="closed", state_reason="completed")` afterwards; never signal
      `approve`; let the time-skipping env advance past `APPROVAL_POLL_INTERVAL`. Assert the
      result carries `ended="source issue closed while parked (completed)"`,
      `calls == ["mctl-agents-investigate"]`, and that the execution status is terminal.
      This is the direct regression for `dev-loop-mctlhq-portfolio-98` and is the test the
      issue's "a test covers this transition" criterion asks for.

- [ ] T4. `test_parked_loop_expires_at_the_approval_deadline` — issue stays `open`, no signal,
      advance past `APPROVAL_WAIT_DEADLINE`; assert completion with
      `ended="approval wait expired"`. Note there is currently **no** test in the module that
      parks the workflow and never signals — both existing no-signal tests
      (`test_failed_investigate_never_implements` line 686,
      `test_a_release_without_an_image_is_fatal` line 715) short-circuit before the wait — so
      T3/T4 are new ground and should be written against the time-skipping clock deliberately.

- [ ] T5. `test_issue_state_failure_while_parked_keeps_waiting` — `issue_state_raises=True`
      for the parked reads, then signal `approve`; assert the workflow still reaches
      `mctl-agents-approve` and `mctl-agents-implement`. Pins the fail-open rule and mirrors
      the existing `test_get_issue_state_failure_fails_open` (line 597).

- [ ] T6. `test_merged_pr_ends_the_watch_within_one_poll` — a regression guard for the
      behaviour that already works: `pr_states` returning `OPEN` then `MERGED`; assert
      `_watch_pr` returns on the `MERGED` read and the execution completes. Covers
      acceptance criteria 1 and 2 from the issue for the loop that drives its own implement.
      Pair it with a `CLOSED`-without-merge variant.

- [ ] T7. `test_prepatch_history_predates_the_approval_watch` in
      `tests/test_workflow_replay.py`, in the shape of
      `test_dev_loop_prepatch_history_predates_the_stale_issue_gate` (line 192): assert
      `"approval-watch" not in _patch_ids(_events(history))` for both `dev_loop_full`
      fixtures, and that `test_recorded_history_replays_against_current_definitions`
      (line 142) still passes. Read that module's docstring table first — a divergence
      confined to the **last** recorded workflow task is invisible to `Replayer`, which is
      exactly where a parked history ends, so T7 must be paired with task 4's resumed-execution
      assertion rather than relied on alone.

- [ ] T8. `test_cli_parses_the_abandon_command` in the existing CLI parser test, asserting
      `--reason` is required (a bare `abandon <id>` exits non-zero).

## Rollback

The change is a single deploy of the `mctl-agents` worker image; there is no migration,
no gitops state change and no new credential, so rollback is a redeploy of the previous
image tag.

What survives a rollback, and what it means:

- Executions that already completed through a new path stay completed. Correct — they were
  finished work.
- Executions that recorded the `approval-watch` marker and are still parked will, under the
  old image, hit the marker at a position their history now contains and take the **legacy**
  unbounded branch. They revert to waiting forever, which is today's behaviour: the
  rollback is not worse than the status quo, but it does not undo the marker. A second
  roll-forward puts them back on the polling branch.
- The `abandon` signal handler disappears with the old image, so a signal sent to a
  rolled-back worker is rejected/ignored rather than acted on. Operators must stop using
  `cli.py abandon` for the duration of a rollback.
- `DevLoopResult.ended` is additive and defaulted, so results written by the new code
  deserialize under the old code.

If only the approval-park behaviour is wrong (e.g. the deadline is too aggressive and is
ending live work), prefer a **constant change** over a rollback: raising
`APPROVAL_WAIT_DEADLINE` or `APPROVAL_POLL_INTERVAL` is a one-line, marker-free edit that
takes effect for every running execution on the next worker deploy, whereas a rollback
leaves the marker recorded.
