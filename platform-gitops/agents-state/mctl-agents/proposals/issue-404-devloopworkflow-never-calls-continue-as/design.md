# Design: issue-404-devloopworkflow-never-calls-continue-as

## Current state

**The watch loop.** `DevLoopWorkflow.run` (`orchestrator/temporal/workflows/dev_loop.py:884-1130`)
runs investigate, a durable `wait_condition` on the approve signal, an
admission check, `find_proposal_slug`, the approve CWFT, the implement submit,
and then — behind `workflow.patched("merge-detection")` at line 1091 — calls
`self._watch_pr(target_repo, slug)`. Everything after that (deploy
observation at 1104-1109, incident watch at 1115-1121, the `DevLoopResult` at
1123-1130) consumes the watch's result.

`_watch_pr` (`dev_loop.py:2433-2721`) is the whole cost. Line 2441 computes
`deadline = workflow.now() + MERGE_WATCH_DEADLINE` as a local. The loop
(2516-2655) executes `get_pr_state` (2518), optionally `_track_ownership`
(2560), optionally a shepherd tick (2599-2628), then
`await workflow.sleep(cadence.poll_interval)` (2655). One poll is therefore
one `ACTIVITY_TASK_SCHEDULED`/`STARTED`/`COMPLETED` triple, one
`TIMER_STARTED`/`FIRED` pair, and the workflow tasks between them — the
~11.5 events/poll the issue measured. `grep -rn continue_as_new orchestrator/`
returns nothing: the whole watch lives in one history.

**What the loop decides once, at the top.** Lines 2451-2510 evaluate four
patch markers and store the results: `fast-shepherd-cadence` selects `CADENCE`
vs `LEGACY_CADENCE` (`_Cadence`, `dev_loop.py:325-368`), `shepherd-in-loop`
sets `self._shepherd_in_loop`, `concurrent-shepherd-tick` sets
`concurrent_ticks`, `lifecycle-ownership` sets `track_ownership`, and
`_proposal_ref`/`_policy_ref` are derived from service+slug. In-loop mutable
cursors are `poll_index`, `shepherd_ticks`, `polls_without_pr`, `last` and
`tick_task` — all locals.

**What outlives the loop.** Three `@workflow.query` handlers answer from
instance state: `implement_execution` (830), `shepherd_in_loop` (835) and
`lifecycle_claim` (848). `run_shepherd._dev_loop_owns_answer`
(`orchestrator/run_shepherd.py:211-312`) asks mctl-api, which queries
`shepherd_in_loop`, and stands the cron sweeper down when it answers True —
so this query is load-bearing for "who shepherds this PR". The lifecycle claim
state is a dozen `self._*` fields set in `__init__` (790-828) and mutated by
`_track_ownership` (1821+) and its helpers.

**Ownership identity.** `_ownership` (`dev_loop.py:1546-1618`) sends
`owner_id=info.workflow_id` and `temporal_workflow_id=info.workflow_id` (lines
1570, 1576) — not the run id. The workflow id is stable across
continue-as-new, so a hop does not change who the store thinks the owner is.
The epoch, however, lives only in `self._owner_epoch`, and the heartbeat is a
re-`acquire` that is idempotent for the same owner (docstring at 1830-1833).

**Bounds around the watch.** `MERGE_POLL_INTERVAL = timedelta(minutes=15)`
(179), `LEGACY_MERGE_POLL_INTERVAL` (180), `MERGE_WATCH_DEADLINE = 14 days`
(181). `start_dev_loop_workflow` (`orchestrator/temporal/start.py`) starts the
workflow with `IssueRef(issue_url=...)`, id `dev-loop-{owner}-{repo}-{issue}`
(`orchestrator/temporal/issue_ref.py:workflow_id_for`),
`ALLOW_DUPLICATE_FAILED_ONLY` + `USE_EXISTING`. Orphan detection uses
`ACTIVE_DEV_LOOPS_QUERY = "WorkflowType = 'DevLoopWorkflow' AND
ExecutionStatus = 'Running'"` (`orchestrator/temporal/activities/visibility.py:23`).

**SDK facts, read from the pinned version.** `pyproject.toml:33` pins
`temporalio==1.31.0`. In that version `is_continue_as_new_suggested` is a
**method on `Info`**, defined in `temporalio/workflow/_context.py:186`, beside
`get_current_history_length()` and `get_current_history_size()`. The issue's
sketch writes `workflow.info().is_continue_as_new_suggested` without the call
— that expression is a bound method, which is always truthy, so the sketch as
written would hop on the very first poll of every watch. The implementation
must call it.

**Test and CI shape that constrains the change.** Workflow tests run under
`WorkflowEnvironment.start_time_skipping()` with the three-queue
`tests/temporal_harness.Worker`; `_fake_activities`
(`tests/test_dev_loop_workflow.py:153-534`) returns a 4-tuple and is also
consumed by `tests/replay_scenarios.py:_dev_loop_build`.
`tests/test_workflow_replay.py` replays
`tests/fixtures/histories/dev_loop_full.prepatch.json` against current code —
its measured capability table records that an *added or reordered activity* is
caught as `NondeterminismError` while an *extra argument* on the run method is
invisible to the replayer. `tools/diagram_facts.py:115` scrapes every
`workflow.patched("...")` id into `docs/diagrams/archify/facts.yaml`, and
`tests/test_diagram_facts.py:128` fails if the scrape comes up empty or a
regex rots. Branches that are only reachable while an activity is outstanding
cannot be driven under the time-skipping server; `TestTickSettling`
(`tests/test_dev_loop_workflow.py:3848-3986`) is the precedent for testing
those by calling methods on a bare `DevLoopWorkflow()` instance.

## Proposed solution

Add a resume-shaped second input to the workflow and make `_watch_pr` able to
*request* a hop instead of performing one.

**1. `MergeWatchResume`, a new frozen dataclass in `dev_loop.py`.** Every
field defaulted, flat scalars plus the two existing snapshot dataclasses, in
the style of `OwnershipRequest`
(`orchestrator/temporal/activities/lifecycle.py:45-68`) and
`ImplementExecutionState`. It carries exactly four groups:

- *Watch cursor*: `service`, `slug`, `deadline` (ISO-8601 Z string),
  `last_pr` (`PRState | None`), `polls_without_pr`, `poll_index`,
  `shepherd_ticks`.
- *Decisions already taken*: `fast_cadence: bool`, `shepherd_in_loop: bool`,
  `concurrent_ticks: bool`, `track_ownership: bool`. Carried rather than
  re-derived from patch markers, so a continued run cannot silently adopt a
  different cadence than the run it replaced.
- *Lifecycle claim*: `owned_entity_id`, `owner_epoch`, `owned_head_sha`,
  `poll_index_for_heartbeat`, `claim_refused`, `claim_refused_until_poll`,
  `refused_by_type`, `refused_by_id`, `refusals_observed`,
  `unknown_acquires`, `unknown_progress`, `unknown_heartbeats`,
  `proposal_ref`, `policy_ref`, `last_lifecycle_op`,
  `last_lifecycle_op_landed`, `claim_abandoned`.
- *Prior stage results and bookkeeping*: `investigate`, `implement`,
  `approve` (`WorkflowResult | None`), `implement_state`
  (`ImplementExecutionState`), `hops: int`.

All of it is small flat JSON — `PRState` and `WorkflowResult` are flat
dataclasses of strings, ints and bools — so the continue-as-new input stays
on the order of a kilobyte.

**2. `run` gains a defaulted second parameter.**

```python
async def run(self, issue: IssueRef, resume: MergeWatchResume | None = None) -> DevLoopResult:
```

External starts keep passing one payload (`start.py` is unchanged), which the
SDK accepts because the parameter has a default; the replayer treats an extra
run argument as invisible, so recorded histories keep replaying. When `resume`
is not None, `run` rehydrates `self._implement_state`, `self._shepherd_in_loop`
and every lifecycle field from it *before* awaiting anything — so the three
queries answer correctly from the first workflow task of the new run — then
goes straight to `_watch_pr`, skipping investigate, the approve wait, the
stale-issue admission check, `find_proposal_slug`, the approve CWFT and the
implement submit. The tail of `run` (deploy observation, incident watch,
`DevLoopResult`) is shared, and builds its result from the carried
`investigate`/`implement`/`approve` values.

**3. `_watch_pr` returns a decision, and never raises the hop.** Its return
type becomes a small `_WatchOutcome(last: PRState | None, resume:
MergeWatchResume | None)`. At the top of each poll it evaluates a hop
predicate; when it fires, it sets a `hopping` flag, breaks the loop, and
builds the resume record. `run` then calls
`workflow.continue_as_new(args=[issue, resume])` at the top level.

This is the load-bearing structural decision. `workflow.continue_as_new`
raises, and the watch loop sits inside a `try/finally` (2515-2720) whose
`finally` issues a lifecycle `release`/`terminal` **activity** and calls
`_finish_claim`/`_report_claim_abandonment`. Raising the hop from inside the
loop would unwind through that `finally`, release the ownership row on every
hop, and record `"merge watch ended without a terminal pull-request state"`
for a watch that is simply continuing — all while awaiting an activity during
a continue-as-new unwind. Returning the decision keeps the hop a plain control
flow that the `finally` can be made aware of: on `hopping`, it skips the
relinquishing write entirely and keeps the claim, whose owner id
(`workflow_id`) and epoch both remain valid in the new run.

**4. The hop predicate.** Evaluated at the top of a poll, all of:

- `workflow.patched("merge-watch-continue-as-new")`, evaluated **once** at
  watch start next to the other markers (2451-2492) and stored. Per
  `tests/test_patch_memoization.py`, this makes migration by attrition:
  in-flight executions memoize False and keep their single-history behaviour
  for the rest of their lives, which is exactly the retirement path the issue
  asks for.
- `workflow.info().is_continue_as_new_suggested()` **or**
  `workflow.info().get_current_history_length() >= MERGE_WATCH_HISTORY_FLOOR`
  (new constant, 4096 — Temporal's documented
  `limit.historyCount.suggestContinueAsNew` default, so the local floor agrees
  with the server signal it backs up). The floor exists because the cluster's
  `temporal-dynamic-config` is empty and a future edit to it must not be able
  to silently switch the bound off, and because it is the only handle a test
  has: it is a module constant a test can lower.
- `polls_this_run >= 1` — at least one completed poll in the current run, so a
  misconfigured threshold cannot produce a continue-as-new storm.
- `tick_task is None or tick_task.done()` — never hop with an in-loop shepherd
  tick in flight. Deferring costs one poll and avoids cancelling a tick that
  may have spawned an implementer run; the suggestion stays true once crossed,
  so the hop simply happens at the next clean boundary.
- `hops < MERGE_WATCH_MAX_HOPS` (new constant, 16 — four times the ~4 hops a
  full 14-day watch needs at a 4096-event floor). Past it the loop logs an
  error and keeps watching in the current run; the watch is observational and
  must never fail over its own bound.

**5. Cadence and constants.** `MERGE_POLL_INTERVAL`, `_Cadence`, the tick
budget and `MERGE_WATCH_DEADLINE` are untouched. `MERGE_WATCH_HISTORY_FLOOR`
and `MERGE_WATCH_MAX_HOPS` are new one-line `NAME = value` constants so
`tools/diagram_facts.py`'s anchored regexes can be extended to them if
`docs/diagrams/archify/facts.yaml` should track them; the new patch marker
lands in the scraped `patched_markers` list either way, so facts.yaml is
regenerated as part of the change.

**Arithmetic.** At a 4096-event floor and ~11.5 events/poll, a hop lands about
every 356 polls, i.e. ~3.7 days at the 15-minute interval: about 4 hops across
a complete 14-day watch, each run's history around 4.2k events — comfortably
under `suggestContinueAsNew`'s successor threshold of `warn` 10,240 and three
orders of magnitude from `error` 51,200. Cost per hop is one extra
`WorkflowExecutionContinuedAsNew`/`Started` pair plus a ~1 KiB input payload.

## Alternatives

**Raise `continue_as_new` inline at the top of the loop (the issue's sketch).**
Smallest diff, and wrong here for a reason specific to this function: the loop
is wrapped in a `try/finally` that performs a lifecycle `release` or `terminal`
activity and the claim-abandonment metric. A hop raised inside it relinquishes
the ownership row on every hop and then re-acquires with a new epoch in the
next run — a repeated few-second window in which the entity has no owner and
the cron sweeper can take it, precisely the zero-owner gap
`dev_loop.py:2658-2688` documents. Dropped in favour of returning a decision
and making the `finally` hop-aware. (Its second defect — reading
`is_continue_as_new_suggested` as an attribute — is a plain bug fixed by
calling it.)

**A separate `MergeWatchWorkflow` child, restarted per window.** Clean
separation of the long-running part, and each child's history is naturally
bounded. Dropped: it multiplies the surface for no extra safety. The
`shepherd_in_loop` and `lifecycle_claim` queries are asked of the DevLoop
workflow id by mctl-api and `run_shepherd`, `visibility.ACTIVE_DEV_LOOPS_QUERY`
filters on `WorkflowType = 'DevLoopWorkflow'`, and the worker would need a new
workflow type registered in `orchestrator/temporal/worker.py` plus test-harness
plan updates (`tests/test_worker_roles.py`). Every one of those is a place the
change could be wrong, to solve a problem `continue_as_new` solves in the same
file.

**Make a poll cheaper instead of bounding the run.** Fold the ownership
heartbeat into `get_pr_state`, or drop back to a 30-minute interval, or raise
`limit.historyCount.warn` in `temporal-dynamic-config`. All three trade the
symptom: the interval was deliberately halved with the `fast-shepherd-cadence`
marker (`dev_loop.py:174-218`) and re-lengthening it undoes a decision made
for review latency; folding activities buys one factor and leaves the growth
unbounded; and the dynamic-config edit lives in mctl-gitops, would apply to
every workflow type in the namespace, and makes the ceiling invisible rather
than removing it. None of them give the workflow a mechanism that reacts to
history growth, which is what the issue is actually about.

## Platform impact

**Migrations.** None. No schema, no gitops state, no mctl-api contract change.
The only new persisted artifact is the continue-as-new input payload, which
exists only inside Temporal history.

**Backward compatibility.** In-flight executions memoize
`merge-watch-continue-as-new` as False and finish in one history exactly as
today; they retire by attrition at `MERGE_WATCH_DEADLINE`, which the issue
names as the intended path. `start.py` and `workflow_id_for` are unchanged, so
`USE_EXISTING` still attaches to the latest run of a hopping watch and
`handle.result()` follows the continuation chain. `visibility.ACTIVE_DEV_LOOPS_QUERY`
still sees exactly one Running execution per workflow id: the server marks the
previous run `ContinuedAsNew` and starts the successor in the same
transaction, so orphan detection neither double-counts nor sees a gap.
Recorded replay fixtures stay valid — an added run parameter is invisible to
the replayer, and every new command sits behind the new marker.

**Resource impact.** Strictly negative on storage and workflow-task payload
size: each run's history is bounded near the floor instead of growing to
~15.5k events. Four extra workflow executions per long watch, each with a
~1 KiB input. No new activity, so no worker registration, no queue routing and
no change to slot accounting under ADR-008.

**Risks and mitigations.**

- *A continued run answers a query differently and the cron sweeper
  double-shepherds the PR.* This is the sharpest failure mode:
  `run_shepherd._dev_loop_owns_answer` stands down on `shepherd_in_loop=True`,
  and a hop that forgot to rehydrate it would put a cron shepherd and an
  in-loop shepherd on one `.status.yaml`. Mitigated by rehydrating query state
  before the first await of the continued run, and by a test that queries all
  three handlers after a forced hop.
- *The deadline resets and the watch becomes unbounded.* Mitigated by carrying
  an absolute ISO timestamp (parsed with the existing `_as_utc`,
  `dev_loop.py:644`), never recomputing it, and by a test that asserts a
  hopped watch still ends 14 days after its first poll.
- *A continue-as-new storm.* Mitigated by the one-poll floor, the hop counter
  cap, and the fact that the cap degrades to "keep watching" rather than to a
  failure.
- *Mid-watch deploys now reach a continued run.* Today an in-flight watch is
  frozen against code changes by patch memoization; after this change a hop
  re-enters the current image. Mitigated by carrying cadence, shepherd and
  ownership decisions as data rather than re-deriving them from markers, so a
  new image cannot change the shape of a watch already running. It remains a
  real, accepted narrowing of the attrition property, and belongs in the
  change's PR description.
- *Rollback while continued runs exist.* A straight revert leaves executions
  whose next run was started with two payloads facing a one-parameter `run`
  that would restart from investigate. Mitigated by the two-step rollback in
  tasks.md: disable the hop predicate first, keep the resume path until the
  hopping executions drain.
- *A signal lost across the boundary.* Temporal can drop a signal that races a
  continue-as-new. The only signal this workflow takes is `approve`, which is
  consumed long before the watch starts, so the exposure is nil today — worth
  restating if a signal is ever added to the watch phase.
