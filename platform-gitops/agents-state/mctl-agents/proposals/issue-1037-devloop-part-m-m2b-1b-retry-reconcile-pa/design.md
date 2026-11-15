# Design: issue-1037-devloop-part-m-m2b-1b-retry-reconcile-pa

## Current state

This design is carried over from the amended #1036 proposal (mctl-gitops#2453, amendment v2, digest
`sha256:86ad277e...e6b75c`) as #1037 requires. References are to `orchestrator/temporal/workflows/dev_loop.py` at
`bd3f51a` (the merge of PR #1030, the #1029 gap harness) and were re-checked in this run's clone at `95feb20`, where the
cited line numbers and symbols are unchanged and none of `merge-watch-terminal-reconcile`, `terminal_reconcile`,
`_terminal_claim` or `_apply_found_state` exists yet.

- **Markers.** Patch-marker constants sit at module level. The closest precedent is `PROPOSAL_TERMINAL_PATCH =
  "proposal-terminal-end"` (around line 483). Its comment documents the rule this slice follows: it is evaluated once
  in `_watch_pr`'s `resume is None` arm and carried in `MergeWatchResume.proposal_terminal_end`, with migration by
  attrition. `DEFERRED_RESUME_PATCH` follows the same carried-never-re-evaluated rule. It is evaluated in `run` (line
  ~4345), carried via `_carry_work_context` (line ~4415) and restored in `_resume_merge_watch` (line ~4571).
- **`MergeWatchResume`** (frozen dataclass, line ~1598). Every field is defaulted, so an old record decodes with the
  defaults. `deadline` is the first run's absolute ISO-Z deadline. The "decisions already taken" block carries
  `fast_cadence`, `shepherd_in_loop`, `concurrent_ticks`, `track_ownership`, `proposal_terminal_end` and
  `deferred_resume_contract`.
- **`_watch_pr`** (line 6348):
  - **Resume arm.** `deadline = _as_utc(resume.deadline)` and the flags come from `resume`.
  - **Fresh arm.** It computes `workflow.now() + MERGE_WATCH_DEADLINE` and evaluates `fast-shepherd-cadence`,
    `shepherd-in-loop`, `concurrent-shepherd-tick`, `lifecycle-ownership`, then `PROPOSAL_TERMINAL_PATCH`, in that
    order.
  - **Every run.** `hop_enabled` (`merge-watch-continue-as-new`) and `gate_enabled` (`MERGE_GATE_PATCH`) are
    evaluated on every run, fresh or resumed.
  - **Locals.** The poll state is plain locals: `last`, `polls_without_pr`, `saw_open_pr`, `terminal_status_polls`,
    `tick_task`, `gate_task`, `track_ownership`, `poll_index`, plus `shepherd_ticks`, `hops`, `polls_this_run`,
    `hopping`, `resume_record` and `watch_ended`.
  - **Found branch** (`if state.found:`). It sets `last`, `self._last_pr`, `polls_without_pr = 0`,
    `terminal_status_polls = 0`, and `saw_open_pr = True` if not MERGED/CLOSED. Then, under `track_ownership and
    state.repo and state.number is not None`, it runs `self._poll_index_for_heartbeat += 1` and `await
    self._track_ownership(state)`. Then, for MERGED/CLOSED, under `track_ownership and self._owned_entity_id`, it runs
    `await self._ownership("terminal", ...)` and `self._finish_claim("terminal", ...)`, and finally returns
    `_WatchOutcome(last=state)`. After that come the shepherd-tick and merge-gate blocks.
  - **Hop record and `finally`.** The hop record is built inline before `break`. The `finally` block reads `last`,
    `tick_task`, `gate_task`, `poll_index` and `track_ownership`.
- **`_resume_merge_watch`** (line 4504) rehydrates instance state from `resume` and calls `self._watch_pr(...,
  resume=resume)`. It contains `workflow.patched("deploy-observation")` later on, but no merge-watch decision marker.
- **Tests:**
  - `tests/test_patch_memoization.py::test_the_deferred_resume_marker_is_recorded_once_fresh_and_never_on_a_merge_watch_hop`
    is the template for the marker-count test. It runs a fresh loop and a `MergeWatchResume`-started loop and counts
    markers in each history.
  - `tests/test_workflow_replay.py` replays every fixture in `tests/fixtures/histories/` and asserts that certain
    markers are absent from the prepatch fixtures. No test asserts an exact marker set.
  - `dev_loop_resumed.json`, `dev_loop_delegated.json`, `dev_loop_issue_keyed.json`, `dev_loop_deferred_resume.json`
    and `dev_loop_issue_started_delegated.json` each contain a fresh merge watch: `get_pr_state` followed by two
    `lifecycle_ownership` activities (acquire, terminal). A command-order or dropped-command mutation in the found
    branch therefore fails replay.
  - `tests/test_merge_watch_worker_gap.py::test_resume_record_fields_reach_the_merge_watch_path` asserts `got == want`
    on a hand-built `MergeWatchResume`. A new field defaulted to False on both sides keeps that equality.
  - `tests/test_temporal_marker_scan.py` and `tools/temporal_marker_scan.py` scan only for `deferred-resume-contract`.
- **The new names are unused today.** Nothing in the clone mentions `merge-watch-terminal-reconcile`,
  `terminal_reconcile`, `_terminal_claim` or `_apply_found_state`.

Deployed state checked:
- This run (#1037): `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml` still shows `image.tag:
  "1.117.0"` and `replicaCount: 1`; `mctl-agents-worker-exec` and `mctl-agents-worker-implement` exist. The #1036
  proposal directory was read in full and its digest recomputed with `scripts/proposal-content-digest.py`
  (`sha256:86ad277e2303f68031c8071c6dd8708429e69d216aa9ce588612ad2429e6b75c`, matches #1037). Its `.status.yaml` shows
  `needs-triage`, `failure.code: no-commits`, run `mctl-agents-implement-5b5707bc`. No mctl MCP tool was called.
- Carried over from the #1036 investigation:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: the worker runs image tag `1.117.0` with
  `replicaCount: 1`. The sibling directories `mctl-agents-worker-exec` and `mctl-agents-worker-implement` exist. This
  slice changes none of them. The new marker reaches production only when a later, separately approved image bump
  ships this code.
- `agents-state/mctl-agents/proposals/issue-1021-devloop-part-m-m2b-feedback-tick-and-dea/{requirements,design,tasks}.md`
  were read as the specification: design section 1 "Marker", the `_apply_found_state` and `_terminal_claim`
  paragraphs, tasks 3, 4 and 9, and T-10/T-11.
- The mctl MCP tools were not called. Repository code and gitops files were sufficient, and no runtime state of the
  worker matters to a code-only, undeployed change.

## Proposed solution

### 1. Marker and carried field (#1021 task 3)

- **Constant.** Add the module constant `MERGE_WATCH_RECONCILE_PATCH = "merge-watch-terminal-reconcile"` beside
  `PROPOSAL_TERMINAL_PATCH`. Its comment states the rule: evaluated only in `_watch_pr`'s fresh-start arm, carried in
  `MergeWatchResume.terminal_reconcile`, never evaluated in `_resume_merge_watch`, and consumed by nothing until
  M2b-1d.
- **Resume field.** Add `terminal_reconcile: bool = False` to `MergeWatchResume`, in the "decisions already taken"
  block right after `proposal_terminal_end`. A pre-change record decodes as False.
- **Fresh-start arm.** Add `terminal_reconcile = workflow.patched(MERGE_WATCH_RECONCILE_PATCH)` immediately after the
  `proposal_terminal_end = workflow.patched(PROPOSAL_TERMINAL_PATCH)` line. It is the last marker of the arm. In
  new histories it appends one marker command after `proposal-terminal-end` and before the first `get_pr_state`. On
  replay of any existing history the marker is absent: `patched` returns False and emits no command, so the replay is
  deterministic.
- **Resume arm.** Add `terminal_reconcile = resume.terminal_reconcile`.
- **Hop record.** Add `terminal_reconcile=watch.terminal_reconcile` to the record. `deadline` stays
  `deadline.isoformat()...`, so the first run's absolute value is never recomputed. `_carry_work_context` uses
  `dataclasses.replace(resume, ...)`, so the field passes through `run`/`_resume_merge_watch` untouched.
- **Nothing reads it yet.** No branch reads `terminal_reconcile` in this slice.

### 2. Per-run watch record (#1021 task 4, part 1)

Add a private, mutable, never-serialized dataclass next to `_WatchOutcome`:

```python
@dataclass
class _MergeWatchRun:
    last: PRState | None
    polls_without_pr: int
    terminal_status_polls: int
    saw_open_pr: bool
    track_ownership: bool
    poll_index: int
    terminal_reconcile: bool
    tick_task: asyncio.Task[None] | None = None
    gate_task: asyncio.Task[ApprovalWaitResult | None] | None = None
```

`_watch_pr` builds one instance after both arms have resolved their values. Every former read or write of those
locals becomes `watch.<name>`. That covers the loop, the hop predicate call, `_finish_gate`/`_settle_gate` arguments,
the hop record, the `finally` block, and the returns `_WatchOutcome(last=watch.last, ...)`. Assignments keep their
positions, so no statement moves relative to an `await`. It is a plain attribute holder: no methods, no
`workflow.*` calls. Being a regular object, it cannot introduce nondeterminism.

### 3. Extracted helpers (#1021 task 4, part 2)

```python
async def _apply_found_state(self, state: PRState, watch: _MergeWatchRun) -> None:
    watch.last = state
    self._last_pr = state
    watch.polls_without_pr = 0
    watch.terminal_status_polls = 0
    if state.state not in ("MERGED", "CLOSED"):
        watch.saw_open_pr = True
    if watch.track_ownership and state.repo and state.number is not None:
        self._poll_index_for_heartbeat += 1
        await self._track_ownership(state)

async def _terminal_claim(self, state: PRState, watch: _MergeWatchRun) -> None:
    if watch.track_ownership and self._owned_entity_id:
        done = await self._ownership("terminal", repo=state.repo or "", number=state.number or 0,
                                     head_sha=state.head_sha or "",
                                     reason=f"pull request {(state.state or '').lower()}")
        self._finish_claim("terminal", done, state.repo or "", state.number or 0)
```

The found branch becomes the following. The existing comments move with the code.

```python
if state.found:
    await self._apply_found_state(state, watch)
    if state.state in ("MERGED", "CLOSED"):
        await self._terminal_claim(state, watch)
        return _WatchOutcome(last=state)
    watch.poll_index += 1
    ...  # shepherd tick and merge gate unchanged, using watch.tick_task / watch.gate_task
```

The statement order is identical to today's. Awaiting a coroutine method adds no command and no yield point beyond
the awaits it contains, so the sequence of scheduled activities and timers is unchanged. That covers the
`get_pr_state`, acquire/heartbeat and terminal `lifecycle_ownership` commands, the `fast-shepherd-cadence` sleeps,
tick tasks and gate tasks.

### 4. Evidence the implementer PR must carry

- **Tests first.** New tests are committed first and shown red against `bd3f51a`:
  - T1/T2 fail on a missing constant or field;
  - T3 fails on the missing helper;
  - T4 fails on the missing record.
  Then the implementation is shown green. One implementation commit is acceptable with reproducible commands
  (owner decision 2026-11-07).
- **Commands.** Every command runs under `timeout 300` and is reported per batch, for example `timeout 300 uv run
  pytest tests/test_patch_memoization.py -q`, `... tests/test_workflow_replay.py tests/test_pre_m1_compat.py
  tests/test_execution_request_replay.py -q`, `... tests/test_merge_watch_worker_gap.py -q`, and `...
  tests/test_dev_loop_workflow.py -q -k "watch or ownership or hop or merge or gate or tick"`. The rest of
  `tests/test_dev_loop_workflow.py` runs in batches that each fit 300 s.
- **Replay statement.** All existing fixtures in `tests/fixtures/histories/` and `tests/fixtures/histories/pre_m1/`
  replay green, with `git diff --stat tests/fixtures` empty. None of them contains `merge-watch-terminal-reconcile`;
  the PR shows a grep proving it.
- **Mutation proof.** Each mutation is applied locally, shown red, reverted, and kept out of the diff:
  - M-a: also evaluate `workflow.patched(MERGE_WATCH_RECONCILE_PATCH)` in `_resume_merge_watch`. Fails T1 (resumed run
    records 1 marker instead of 0).
  - M-b: on a hop, write `deadline=(workflow.now() + MERGE_WATCH_DEADLINE)` into the record. Fails T2's deadline
    assertion.
  - M-c: drop `terminal_reconcile=` from the hop record. Fails T2 (carried True arrives as False).
  - M-c2: in the resume arm, read `workflow.patched(...)` instead of `resume.terminal_reconcile`. Fails T1 (marker
    recorded on the resumed run) and T2.
  - M-d1: call `_terminal_claim` before `_apply_found_state` in the found branch. `_owned_entity_id` is still empty, so
    the terminal write is skipped. This fails replay of `dev_loop_resumed.json` (and siblings) with a nondeterminism
    error (one `lifecycle_ownership` missing) and the existing `ops[-1].op == "terminal"` assertions in
    `tests/test_dev_loop_workflow.py`.
  - M-d2: drop `await self._track_ownership(state)` from `_apply_found_state`. Fails the same replay fixtures and the
    ownership tests in `tests/test_dev_loop_workflow.py`.
  - M-e: in `_apply_found_state`, omit `watch.saw_open_pr = True`. Fails the existing #516 T8 family in
    `tests/test_dev_loop_workflow.py` (a once-open PR followed by a terminal status must not end the watch), and T3.
- **Gap harness.** `tests/test_merge_watch_worker_gap.py` passes, and `git diff` on it is empty.

## Alternatives

1. **Evaluate the marker on every run, like `hop_enabled`/`gate_enabled`.** Rejected. #1021 requires the decision to
   be carried. A re-evaluation on a fresh continue-as-new history answers True for a watch that started unpatched,
   and that would change its end-of-watch contract mid-watch once 1d consumes the flag. The issue also pins "zero
   times on a resumed run".
2. **Carry the flag on instance state via `_carry_work_context`/`_resume_merge_watch`, like
   `deferred_resume_contract`.** Rejected. That flag is decided in `run`, before the watch. This one is a watch
   decision, so it belongs with `proposal_terminal_end` in `_watch_pr`'s own arms and hop record. Routing it through
   `_resume_merge_watch` would also put a reader of it in the function the issue says must not touch it.
3. **Defer the refactor to 1d and land the marker alone.** Rejected. The issue scopes both tasks together. Landing
   the refactor separately, with no behaviour change, lets replay prove command identity before 1d adds behaviour on
   top. Mixing the two in 1d would make a replay failure ambiguous.
4. **Make the watch record a frozen dataclass rebuilt with `replace`.** Rejected. The found branch mutates five
   fields per poll and `_apply_found_state` must update them in place. A frozen record would force returning new
   records and widen the diff without benefit.

## Platform impact

- **Migrations.** None. `MergeWatchResume` gains one defaulted field. An old record (an in-flight hop written by
  image 1.117.0 or earlier) decodes as `terminal_reconcile=False`, which is also the behaviour the field will later
  gate (migration by attrition).
- **Backward compatibility and replay.** Existing histories have no `merge-watch-terminal-reconcile` marker. On replay,
  `patched` returns False without emitting a command, so in-flight executions replay deterministically on the new
  code. The refactor emits the identical command sequence.
- **Rollback consequence for B4 (#1007).** New marker name: `merge-watch-terminal-reconcile` (`core_patch` marker,
  `MERGE_WATCH_RECONCILE_PATCH`).
  - **Recording.** Once a worker image containing this code is deployed, every fresh merge watch records the marker.
    Resumed (hopped) runs never record it.
  - **Rolling back to an image without the marker.** A history that carries the marker replays on the older code,
    which never calls `patched` for it. The SDK tolerates an unrequested marker only when it was written by
    `deprecate_patch`. A non-deprecated marker that the old code does not request is expected to fail replay as
    non-deterministic. This is not verified here; B4 owns that check. B4 must therefore count histories carrying this
    marker, as `tools/temporal_marker_scan.py` does today for `deferred-resume-contract`. The decision is not made
    here.
  - **Not covered by the scanner.** `tools/temporal_marker_scan.py` scans only for `deferred-resume-contract`, so it
    will not see the new marker. Extending it is B4's call and not part of this slice.
  - **Hopped records.** A hopped run carries the flag only in its input, not as a marker. Observed during the
    amendment sweep (temporalio 1.34.0, the project's default data converter, baseline `bd3f51a` whose
    `MergeWatchResume` has no such field; script under the session scratchpad):
    - a payload carrying `"terminal_reconcile": true` decodes on the old class without an exception and the key is
      silently dropped, with the other fields intact; the same holds nested as `IssueRef.resume`, which is how the
      record travels across continue-as-new;
    - the reverse (an old payload decoded by the class with the new defaulted field) gives `terminal_reconcile ==
      False`;
    - the precedent `deferred_resume_contract` behaves identically (already pinned by
      `test_unsupported_direction_pre_m1_decoder_silently_drops_m1_fields`).
    So payload decoding is not a blocking B4 finding. Semantic consequence (reasoned from these observations, not run):
    an old worker that handles a hop re-encodes the record without the key, so the next new-code hop reads False, a
    safe-direction downgrade to the legacy behaviour. The B4 rollback notes should record it.
  - **Unverified.** An old worker replaying a history that already contains the new marker has not been reproduced with
    the SDK Replayer, because no history recorded from the new code exists yet. Forward-replay safety rests on the
    refactor being command-identical, which the mutation proofs must show. Rollback below the first build carrying the
    marker stays unsupported until a Replayer test with such a history is run.
  - **B4 coupling (from the B4 owner).** (i) The B4 marker classification MS-1 must classify
    `merge-watch-terminal-reconcile` (MARKER_PRESENT, MARKER_ABSENT or MARKER_UNKNOWN) before the first build carrying
    it ships. (ii) Under the forward-only baseline the rollback boundary moves up to that build: rolling back below it
    is unsafe for fresh watches, and the B4 scenario "the fixed worker does not start" must cover this marker. Worker
    Versioning does not block shipping this slice.
- **Resources.** One marker event per fresh watch. This is negligible against `MERGE_WATCH_HISTORY_FLOOR` and the hop
  predicate.
- **Release.** No image bump, no change under `services/admins/mctl-agents-worker*`, no flag. The implementer PR must
  be blocked by GitHub (code-owner hold, #1020); if it is not, stop. No merge, bypass or deployment.
- **Risks and mitigations.**
  - *A refactor that silently reorders an await.* Mitigated by replay of the five fixtures containing a fresh watch,
    and by M-d1/M-d2.
  - *An existing test needing an edit.* Exactly three edits in `tests/test_pre_m1_compat.py` are sanctioned (the pin
    table entries and the silent-drop sample, see requirements.md). Any other existing test or fixture needing an edit
    is a STOP condition: the implementer reports on #1037 instead of adapting the test. The amendment sweep found no
    other one in the whole suite.
  - *Test environment.* A worktree outside the workspace has no sibling `mctl-gitops` checkout, so `test_manifest.py`,
    `test_human_input_producer.py`, `test_human_input_e2e.py` and `test_b4_update_outage_e2e.py` fail on the untouched
    baseline too. Those reds are not regressions; the sweep ran them green with a symlink to the real checkout.
  - *The gap harness turning green by accident.* That would mean a final read was introduced. It is a STOP condition,
    and T5 asserts the harness file is unchanged and green, with scenario A still ending on `OPEN`.

## Open questions

- Base commit: see requirements.md Open questions (shallow clone at `95feb20`; code observed unchanged).

- **Forward/backward decode of an unknown `MergeWatchResume` key.** Answered by the amendment sweep: accepted, key
  dropped, no exception (see Platform impact, Hopped records). The implementer repeats the one-line check in the PR so
  the result is reproducible on the PR head, and states it for B4.
- The two `_terminal_claim` signatures in #1021 and the exact set of locals moved: see requirements.md Open questions.
