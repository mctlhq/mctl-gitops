# Design: issue-1046-devloop-part-m-m2b-1d-1-typed-result-cli

## Current state

All paths are in the `mctlhq/mctl-agents` clone at `e6b70a3` (the merge of PR #1042, M2b-1c).
`orchestrator/temporal/workflows/dev_loop.py` is 6983 lines.

### Result types (`orchestrator/temporal/workflows/dev_loop.py`)

- `DevLoopResult` (line 1169, `@dataclass(frozen=True)`): `investigate`, `implement`, then defaulted `approve`, `pr`
  (line ~1181; its comment says `state="OPEN"` "means the watch deadline expired with the PR still open"), `deploy`,
  `incidents`, `human_input`, `ended` (#420), `outcome` (#702, `"approval_refused"`, `"approval_failed"` or `""`) and
  `security` (#809). Every field after `implement` is defaulted "so results recorded before this field existed still
  deserialize".
- `_WatchOutcome` (line 1788, frozen): `last: PRState | None`, `resume: MergeWatchResume | None = None`,
  `ended: str = ""`. Its docstring states it is "a plain return value, never serialized". So only `DevLoopResult`
  crosses a wire.
- `PRState` (`orchestrator/temporal/activities/pr_state.py:54`): `found`, `pr_url`, `repo`, `number`, `state`, `merged`,
  `merge_commit`, `merged_at`, head SHA; all defaulted except `found`.

### Result tail

`_finish_after_watch` (line 4640) is called from `run` (line 4419) and `_resume_merge_watch` (line 4631). It takes
`pr_state = outcome.last`, then runs deploy observation under
`workflow.patched("deploy-observation") and pr_state is not None and pr_state.merged`, the security record under
`workflow.patched("security-record-landed") and ... merged and merge_commit`, and the incident watch under
`workflow.patched("incident-watch") and deploy ...`. The `patched` call is the first operand each time, so it is
evaluated on every path. The result sets
`ended=(f"{ABANDONED_ENDED_PREFIX}{self._abandon_reason}" if self._abandoned else outcome.ended)`
(`ABANDONED_ENDED_PREFIX = "abandoned: "`, line 1148). `outcome` is not set (stays `""`).

### Markers and activities already on main

- `MERGE_WATCH_RECONCILE_PATCH = "merge-watch-terminal-reconcile"` (line 489), evaluated once in `_watch_pr`'s fresh
  arm (line 6544), carried by `MergeWatchResume.terminal_reconcile: bool = False` (line 1646) and read from `resume` on
  the resume arm (line 6485). Its comment: "Consumed by nothing until M2b-1d".
- `record_merge_watch_reconcile` and `confirm_no_pr` are registered in `orchestrator/temporal/worker.py` (lines 703 and
  733, comments "registered but unscheduled until M2b-1d"). Nothing in `dev_loop.py` schedules either.

### Deliveries

`_deliver` (line 2887): returns `unsupported` without `EXECUTION_REQUEST_RESUME_PATCH`; lands an `opened.pending_phase`
directly; polls `_poll_delivery_bind` until bound, with one `DELIVERY_EXIT_GRACE` poll under `_exiting` and
`request-not-fulfilled` if that poll finds nothing; ends an unbound/stranded delivery with the bind's outcome; records
the `ExecutionRef`; fails an `accepted_after_gates` delivery with `feedback-not-ready`; then
`await workflow.wait_condition(lambda: self._abandoned or self._is_approved() or self._gates_passed or self._exiting or self._hopping)`,
computes `decided`, carries an undecided delivery across a hop, and lands `Succeeded if decided else Failed` with
refusal `""`. `_land_delivery` (line 2978) retries the advance and keeps a `pending_phase` across hops.
`RESUME_DEFERRAL_REASONS` (line 505) is the validator's closed vocabulary. Instance state is initialised in `__init__`
around lines 1968-1995 (`_abandoned`, `_gates_passed`, `_exiting`, `_hopping`).

### Readers of `DevLoopResult`

- `orchestrator/temporal/cli.py` `status` (lines 69-139): prints `ended`, the stage phases, then
  `pr: <state> (<url>)` / `pr: unresolvable ...` when `result.pr` is set, else
  `pr: not watched (pre-merge-detection history, or no PR link appeared)` when implement succeeded. It acquires an
  untyped handle with `client.get_workflow_handle(workflow_id)` (see Open questions Q1).
- `orchestrator/temporal/start.py` `restart_if_restartable` (around line 109-140): typed
  `get_workflow_handle_for(DevLoopWorkflow.run, ...)`, decides on `ended` prefixes and `implement` only.
- mctl-api `restartIfAbandoned` decodes `ended` and `implement` only (per the #1021 design; not re-read here).
- No other module in `orchestrator/` references `DevLoopResult` (grep: only `cli.py`, `dev_loop.py`, and
  `tests/test_dev_loop_workflow.py`). The shepherd and dispatcher read `.status.yaml` and workflow state, not this result.

### Tests that pin compatibility

- `tests/test_pre_m1_compat.py`: `_M1_CLASSES`/`M1_ADDED` cover `ResumeDelivery`, `OpenDelivery`, `MergeWatchResume`,
  `IssueRef`. `DevLoopResult` is not in the table, so adding fields to it needs no pin-table edit.
  `test_unsupported_direction_pre_m1_decoder_silently_drops_m1_fields` pins that Temporal's converter ignores unknown
  keys; the same mechanism governs R4.
- `tests/test_execution_request_resume.py` drives `_deliver` end to end on a time-skipping env with a fake mctl-api
  (`api`, `env`, `_worker`, `_dispatcher`, `_row`, `_wait_for`), e.g.
  `test_a_delivery_accepted_after_the_gates_fails_closed_in_deliver` (line 626) starts from a `MergeWatchResume` with an
  `OpenDelivery` and asserts the landed phase.
- `tests/test_execution_request_replay.py:646` shows the established way to alter a loop for a test: a subclass
  `@workflow.defn(name="DevLoopWorkflow", sandboxed=False) class _ReleasedStrandedLoop(DevLoopWorkflow)`.
- `tests/test_temporal_cli.py` stubs `connect()` with a `SimpleNamespace` handle (`_stub_client`).
- `tests/test_merge_watch_worker_gap.py` (M2b-1a'): the deadline-gap harness; its scenario A documents the defect that
  1d-2 fixes. Untouched here.

### Deployed state checked

- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: `image.tag: "1.117.0"` (hand-bumped). The worker
  runs a release that predates M1/M2; nothing in this slice is deployed, and no env var or CWFT change is needed.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/issue-1021-devloop-part-m-m2b-feedback-tick-and-dea/`
  (`design.md`, `requirements.md`, `tasks.md`): read as the specification (sections 5 and 2, R6, R11, R15, R16, T-12,
  T-13, task 7, mutations (m) and (an)).
- mctl MCP tools: not called. This slice changes no runtime configuration and its behaviour is inert in production, so
  no live state is relied on. mctl-api's `restartIfAbandoned` was not re-read in this run; the claim that it decodes
  only `ended` and `implement` is taken from the #1021 design (recorded under Open questions).

## Proposed solution

Four additive edits in two production files, plus one new test file. No existing test file is edited.

### 1. Types (`dev_loop.py`)

- `_WatchOutcome`: add `watch_end: str = ""` and `reconcile_record: str = ""` after `ended`, with a comment listing the
  values (`final-read`, `reconcile-required`, `no-pr-confirmed`, `abandoned-unverified`, `""`) and stating that nothing
  in this slice sets them.
- Module constants near `ABANDONED_ENDED_PREFIX`: `WATCH_END_RECONCILE_REQUIRED = "reconcile-required"`,
  `WATCH_END_NO_PR_CONFIRMED = "no-pr-confirmed"`, `WATCH_END_ABANDONED_UNVERIFIED = "abandoned-unverified"`,
  `WATCH_END_FINAL_READ = "final-read"`, `MERGE_WATCH_RECONCILE_REQUIRED_OUTCOME = "merge_watch_reconcile_required"`,
  `MERGE_WATCH_RECONCILE_ENDED_FALLBACK = "merge watch: pull-request state not established; reconciliation required"`.
  `cli.py` imports the `WATCH_END_*` constants so the two sides cannot drift.
- `DevLoopResult`: append, after `security`, `watch_end: str = ""`, `last_observed_pr: PRState | None = None`,
  `reconcile_record: str = ""`, each with a "defaulted so results recorded before this field existed still
  deserialize" comment. Appending keeps the positional order of every existing field (nothing constructs it
  positionally beyond `investigate`/`implement`, but appending removes the question).

### 2. `_finish_after_watch`

```python
reconcile = outcome.watch_end == WATCH_END_RECONCILE_REQUIRED
pr_state = None if reconcile else outcome.last
... existing three stages unchanged, gated on pr_state ...
if reconcile:
    ended = outcome.ended or MERGE_WATCH_RECONCILE_ENDED_FALLBACK
    workflow.logger.warning("MERGE_WATCH_RECONCILE_REQUIRED repo=%s workflow=%s ended=%s record=%s", ...)
else:
    ended = f"{ABANDONED_ENDED_PREFIX}{self._abandon_reason}" if self._abandoned else outcome.ended
return DevLoopResult(..., pr=pr_state, ended=ended,
                     outcome=MERGE_WATCH_RECONCILE_REQUIRED_OUTCOME if reconcile else "",
                     watch_end=outcome.watch_end,
                     last_observed_pr=outcome.last if reconcile else None,
                     reconcile_record=outcome.reconcile_record if reconcile else "")
```

Gating through `pr_state = None` instead of an early return keeps all three `workflow.patched(...)` calls evaluated in
their current order on every path (R7), so even when a later slice produces reconcile-required, the marker set of the
tail does not depend on the watch end. `workflow.logger` schedules no command. On every existing path
`outcome.watch_end == ""`, so `pr`, `ended`, `outcome` and the stages are byte-for-byte today's, and the only
difference in the returned value is three keys at their defaults.

Docstrings: `DevLoopResult.pr` says None also on reconcile-required (see `last_observed_pr`), that an OPEN state is the
last observed state, and that on `abandoned-unverified` it is not verified current state. `_watch_pr`'s docstring
drops the claim that the fail-open return is a final answer and points at `watch_end` for later slices.

### 3. Delivery refusal (`dev_loop.py`)

- `MERGE_WATCH_RECONCILE_REFUSAL = "merge-watch-reconcile-required"` defined next to the delivery constants
  (`DELIVERY_ACCEPTED`, ~line 497), with a comment that it is a delivery landing refusal and deliberately not in
  `RESUME_DEFERRAL_REASONS` (a validator vocabulary).
- `__init__`: `self._reconcile_required = False`, commented as plain instance state, set by nothing until 1d-3, not
  carried across a hop (the decision point cannot coincide with a hop: the hop is decided only inside the watch loop).
- `_deliver`, check 1: immediately after the `accepted_after_gates` block and before `wait_condition`:
  `if self._reconcile_required: await self._land_delivery(opened, "Failed", MERGE_WATCH_RECONCILE_REFUSAL, engine_ref); return`.
  Placing it after `accepted_after_gates` keeps `feedback-not-ready` for that case (R15); placing it after the bind and
  `ExecutionRef` bookkeeping means only a bound delivery is refused, while an unbound one keeps
  `request-not-fulfilled`; the `pending_phase` early return above is untouched.
- `_deliver`, check 2: immediately after `wait_condition` returns and before `decided`/hop carry:
  the same landing. `wait_condition` suspends the task even when its predicate is already true, so a flag set in the
  activation that resolves the wait is seen only here.
- The `wait_condition` predicate is not changed (Q3), so with the flag False every statement runs as today.

### 4. CLI (`orchestrator/temporal/cli.py`)

The `pr:` block becomes:

```python
if result.watch_end == WATCH_END_RECONCILE_REQUIRED:
    print(f"  pr:          reconcile required ({result.reconcile_record or 'no record'})")
elif result.pr is not None:
    ... existing found / unresolvable lines, with
    " (last observed before abandon, not verified current)" appended when watch_end == WATCH_END_ABANDONED_UNVERIFIED
elif result.watch_end == WATCH_END_NO_PR_CONFIRMED:
    print("  pr:          none (confirmed)")
elif result.implement and result.implement.succeeded:
    ... existing not watched line
```

With `watch_end == ""` the output is identical to today's.

### 5. Tests

A new file `tests/test_merge_watch_typed_result.py` holds every test of this slice (T1-T7 in `tasks.md`), so no
existing test file changes. Delivery tests reuse the fixtures of `tests/test_execution_request_resume.py` by import and
a test-only subclass `@workflow.defn(name="DevLoopWorkflow", sandboxed=False) class _FlaggedLoop(DevLoopWorkflow)`
that redefines `@workflow.run` (calling `super().run`, else class creation fails) and adds two signals: `flag` (sets
`self._reconcile_required = True`) and `flag_and_pass` (sets it and `self._gates_passed = True` in one handler). Only the
combined handler resolves `wait_condition` in the same activation that sets the flag, because the predicate is
unchanged and a flag-only signal never wakes it; this was measured by the independent review of this proposal. The
`pending_phase` case needs the flag set before `_deliver` runs (`start_signal`). The production class gains no signal. Result-shape tests
call `_finish_after_watch` from a probe workflow (`@workflow.defn(name="FinishAfterWatchProbe", sandboxed=False)`,
like `PatchMemoProbe` in `tests/test_patch_memoization.py`) so `workflow.patched`/`workflow.now` run in a real workflow
context; the reconcile-required and OPEN cases schedule no activity.

## Alternatives

1. **Early `return` in `_finish_after_watch` on reconcile-required.** Dropped: it would skip the three
   `workflow.patched` calls on that path, so the tail's marker set would depend on the watch end, a replay hazard for
   1d-3 histories. Gating via `pr_state = None` costs nothing.
2. **Add `_reconcile_required` to the `wait_condition` predicate (one check instead of two).** Dropped: #1021 specifies
   two checks; the predicate change makes the first check unobservable by mutation, and the post-wait check is still
   needed for the same-activation case. Recorded as Q3.
3. **Put the refusal in `RESUME_DEFERRAL_REASONS`.** Dropped by the spec: that set is the validator's closed deferral
   vocabulary normalised by the dispatcher; a landing refusal is a different contract.
4. **Unit-test `_deliver` by calling it outside a workflow with monkeypatched `workflow.*`.** Dropped: it would not
   exercise the activation semantics T-12 is about; the existing time-skipping harness already drives `_deliver`.
5. **Fix the untyped CLI handle at the same time.** Dropped: not in the slice's task list; recorded as Q1.

## Platform impact

- **Replay.** No `workflow.patched`, no activity, no timer, no command and no command-order change. `_reconcile_required`
  is never True, `watch_end` is always `""`, so every recorded history (`tests/fixtures/histories/*.json`, `pre_m1/`,
  the `*.prepatch` fixtures) schedules the same commands with the same inputs; they are not re-recorded.
- **Marker and activities accounted for.** `merge-watch-terminal-reconcile` keeps its single evaluation site and its
  carry; `record_merge_watch_reconcile` and `confirm_no_pr` stay registered with no caller. Restated from the 08.11
  result, not re-measured here: an old worker replaying a history recorded by a marker-bearing worker fails with a
  nondeterminism error, so rollback below `883b3a1bf` is unsafe for watches whose first run recorded the marker. This
  slice adds nothing to that and decides nothing for B4 (#1007, owned elsewhere).
- **Payload compatibility, both directions.** Old `DevLoopResult` payload into the new class: defaults (T3). New payload
  into the old class: decodes without error and drops the three keys (T4). Rollback consequence: reverting this slice
  alone loses nothing, because every result it can produce carries only defaults in the new keys. After 1d-3 lands, a
  rollback below this slice would make a reader print a reconcile-required result as `pr: not watched` and lose
  `last_observed_pr`/`reconcile_record` silently; `ended` and `outcome` survive (existing fields), and
  `restart_if_restartable`/mctl-api `restartIfAbandoned` decide on `ended`/`implement` only, so their answers do not
  change. That is part of what #1022 must cover before any release carrying 1d-3.
- **#1022.** Not satisfied and not needed for this slice: it creates none of the reconcile-required, failed-to-record or
  cancelled-while-deciding states. 1d-3 does. Green tests here are never grounds for lifting the release hold.
- **Resource impact.** None at runtime.
- **Risks.**
  - A future producer sets `watch_end` without `ended`: mitigated by the fallback text (R6) and a test.
  - A check placed before `accepted_after_gates` or before `pending_phase` would change those outcomes once a flag is
    set: pinned by T-12 cases and mutations (aag) and (pend).
  - CLI drift between producer strings and the CLI: mitigated by importing the `WATCH_END_*` constants.
- **Merge governance.** The PR must be verified as blocked by GitHub (code-owner hold, #1020); if not blocked, stop. A
  HEAD change after review needs re-verification and a fresh review. No autonomous merge, admin bypass, release or
  deployment. B4 stays FAIL, release hold ON.
