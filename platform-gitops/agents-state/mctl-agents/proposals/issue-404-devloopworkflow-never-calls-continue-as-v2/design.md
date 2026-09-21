# Design: issue-404-devloopworkflow-never-calls-continue-as-v2

> Supersedes `issue-404-devloopworkflow-never-calls-continue-as`. Same source
> issue (mctlhq/mctl-agents#404), same shape of solution, rebased onto `main`
> at 1.53.0 (post mctlhq/mctl-agents#434). All line numbers below were read
> from current `main`, not carried over from the superseded document.

## Current state

**The watch loop.** `DevLoopWorkflow.run` (`dev_loop.py:1008`) runs
investigate, the approval park (now behind `workflow.patched("approval-watch")`
at `dev_loop.py:1048`, whose `wait_condition` observes
`self._approved or self._abandoned`, `dev_loop.py:1056`), an admission check,
`find_proposal_slug`, the approve CWFT, the implement submit, and then — behind
`workflow.patched("merge-detection")` at 1266 — calls `self._watch_pr(...)`.
Everything after that (deploy observation at 1280, incident watch at 1291, the
`DevLoopResult` at 1307) consumes the watch's result.

`_watch_pr` (`dev_loop.py:2613`, signature
`(self, service: str, slug: str) -> PRState | None`) is the whole cost. The
loop condition is `while workflow.now() < deadline and not self._abandoned:`
(2703) inside a `try` at 2697 with a `finally` at 2843. One poll is one
`ACTIVITY_TASK_SCHEDULED`/`STARTED`/`COMPLETED` triple, one
`TIMER_STARTED`/`FIRED` pair, and the workflow tasks between them — the
~11.5 events/poll the issue measured. `grep -n continue_as_new` over
`dev_loop.py` returns only prose in comments: the whole watch lives in one
history.

**What the loop decides once, at the top.** `dev_loop.py:2633-2674` evaluates
four patch markers and stores the results: `fast-shepherd-cadence` selects
`CADENCE` vs `LEGACY_CADENCE` (2633), `shepherd-in-loop` sets
`self._shepherd_in_loop` (2635), `concurrent-shepherd-tick` sets
`concurrent_ticks` (2669), `lifecycle-ownership` sets `track_ownership` (2674).
`_proposal_ref`/`_policy_ref` are derived from service+slug. In-loop mutable
cursors are `poll_index`, `shepherd_ticks`, `polls_without_pr`, `last` and
`tick_task` — all locals.

**What outlives the loop.** FOUR `@workflow.query` handlers answer from
instance state: `implement_execution` (924), `shepherd_in_loop` (929),
`lifecycle_claim` (942) and `abandon_state` (963), the last added by #434.
`run_shepherd._dev_loop_owns_answer` asks mctl-api, which queries
`shepherd_in_loop`, and stands the cron sweeper down when it answers True — so
that query is load-bearing for "who shepherds this PR". `abandon_state` is what
lets `cli.py status` distinguish "still parked" from "an operator ended this",
per its own docstring.

**Instance state on `main`**, from `__init__`: `_implement_state`, `_cadence`,
`_approved`, `_approver`, `_shepherd_in_loop`, `_owned_entity_id`,
`_owner_epoch`, `_owned_head_sha`, `_poll_index_for_heartbeat`,
`_claim_refused`, `_claim_refused_until_poll`, `_refused_by_type`,
`_refused_by_id`, `_refusals_observed`, `_unknown_acquires`,
`_unknown_progress`, `_unknown_heartbeats`, `_proposal_ref`, `_policy_ref`,
`_last_lifecycle_op`, `_last_lifecycle_op_landed`, `_claim_abandoned`,
`_abandoned`, `_abandon_reason`. Note `_claim_abandoned` and `_abandoned` are
deliberately different questions — `AbandonState`'s docstring
(`dev_loop.py:507-515`) says so explicitly — and a resume record must keep them
apart for the same reason.

**Ownership identity.** `_ownership` sends `owner_id=info.workflow_id` and
`temporal_workflow_id=info.workflow_id`, not the run id. The workflow id is
stable across continue-as-new, so a hop does not change who the store thinks
the owner is. The epoch lives only in `self._owner_epoch`, and the heartbeat is
a re-`acquire` that is idempotent for the same owner.

**Bounds.** `MERGE_POLL_INTERVAL = timedelta(minutes=15)` (199),
`LEGACY_MERGE_POLL_INTERVAL` (200), `MERGE_WATCH_DEADLINE = timedelta(days=14)`
(201). `start_dev_loop_workflow` starts the workflow with
`IssueRef(issue_url=...)`, id `dev-loop-{owner}-{repo}-{issue}`
(`orchestrator/temporal/issue_ref.py:workflow_id_for`), `USE_EXISTING`. Orphan
detection uses `ACTIVE_DEV_LOOPS_QUERY`.

**SDK facts, read from the pinned version.** `pyproject.toml:33` pins
`temporalio==1.31.0`. There `is_continue_as_new_suggested` is a **method on
`Info`** (`temporalio/workflow/_context.py:186`), beside
`get_current_history_length()`. The issue's sketch writes
`workflow.info().is_continue_as_new_suggested` without the call — a bound
method, always truthy — which would hop on the first poll of every watch. The
implementation must call it.

## The argument-shape decision (settled here)

The superseded attempt burned a full implementer run on this point, so it is
recorded explicitly.

On `main`, `run` takes exactly one argument and `IssueRef` has exactly one
field:

```python
# dev_loop.py:427-429
@dataclass(frozen=True)
class IssueRef:
    issue_url: str

# dev_loop.py:1008
async def run(self, issue: IssueRef) -> DevLoopResult:
```

**Decision: carry the resume record as a defaulted field on `IssueRef`**, not
as a second parameter on `run`:

```python
@dataclass(frozen=True)
class IssueRef:
    issue_url: str
    resume: MergeWatchResume | None = None
```

Rationale. Temporal decodes a workflow's arguments positionally against the
run method's type hints, so argument *count* is part of the wire contract while
a dataclass field is not: with a field, every start — external or continued —
passes exactly one payload and the decoded argument list is always
`[IssueRef]`. A defaulted second parameter also works, but it makes external
starts and continued runs differ in arity, which is the seam the previous
attempt tripped over. `start.py` is unchanged either way, because the new field
is defaulted.

## Proposed solution

**1. `MergeWatchResume`, a new frozen dataclass in `dev_loop.py`.** Every field
defaulted; flat scalars plus the existing snapshot dataclasses. It carries five
groups:

- *Watch cursor*: `service`, `slug`, `deadline` (ISO-8601 Z string), `last_pr`
  (`PRState | None`), `polls_without_pr`, `poll_index`, `shepherd_ticks`.
- *Decisions already taken*: `fast_cadence: bool`, `shepherd_in_loop: bool`,
  `concurrent_ticks: bool`, `track_ownership: bool` — carried rather than
  re-derived from patch markers, so a continued run cannot adopt a different
  cadence than the run it replaced.
- *Lifecycle claim*: `owned_entity_id`, `owner_epoch`, `owned_head_sha`,
  `poll_index_for_heartbeat`, `claim_refused`, `claim_refused_until_poll`,
  `refused_by_type`, `refused_by_id`, `refusals_observed`, `unknown_acquires`,
  `unknown_progress`, `unknown_heartbeats`, `proposal_ref`, `policy_ref`,
  `last_lifecycle_op`, `last_lifecycle_op_landed`, `claim_abandoned`.
- *Abandon state* (new versus the superseded design): `abandoned: bool`,
  `abandon_reason: str`. Without these a hop silently resets the `abandon`
  signal #434 added, and `abandon_state` would answer False in the continued
  run while an operator believes the execution is ending.
- *Prior stage results and bookkeeping*: `investigate`, `implement`, `approve`
  (`WorkflowResult | None`), `implement_state` (`ImplementExecutionState`),
  `approver: str | None`, `hops: int`.

All flat JSON on the order of a kilobyte.

**2. `run` rehydrates before its first await.** When `issue.resume` is not
None, `run` restores `_implement_state`, `_shepherd_in_loop`, `_cadence`,
`_approved`/`_approver`, every lifecycle field and `_abandoned`/
`_abandon_reason` *before* awaiting anything — so all four queries answer
correctly from the first workflow task of the continued run — then goes
straight to `_watch_pr`, skipping investigate, the approval park, the
stale-issue admission check, `find_proposal_slug`, the approve CWFT and the
implement submit. The tail of `run` (deploy observation, incident watch,
`DevLoopResult`) is shared and builds its result from the carried
`investigate`/`implement`/`approve` values.

**3. `_watch_pr` returns a decision and never raises the hop.** Its return type
becomes `_WatchOutcome(last: PRState | None, resume: MergeWatchResume | None)`.
At the top of each poll it evaluates a hop predicate; when it fires it sets a
`hopping` flag, breaks the loop, and builds the resume record. `run` then calls
`workflow.continue_as_new(IssueRef(issue_url=..., resume=resume))` at the top
level.

This is the load-bearing structural decision, and #434 strengthened the reason
for it. `workflow.continue_as_new` raises, and the loop sits inside a
`try`/`finally` (2697/2843) whose `finally` issues a lifecycle
`release`/`terminal` **activity** and calls `_finish_claim` /
`_report_claim_abandonment` (2905-2907). Raising the hop from inside would
unwind through that `finally`, release the ownership row on every hop, and
record "merge watch ended without a terminal pull-request state" for a watch
that is simply continuing — all while awaiting an activity during a
continue-as-new unwind. Returning the decision keeps the hop plain control flow
the `finally` can be made aware of: on `hopping` it skips the relinquishing
write and keeps the claim, whose owner id (`workflow_id`) and epoch both stay
valid.

**4. The hop predicate.** Evaluated at the top of a poll, all of:

- `workflow.patched("merge-watch-continue-as-new")`, evaluated **once** at
  watch start beside the existing markers (2633-2674) and stored. Per
  `tests/test_patch_memoization.py` this makes migration by attrition:
  in-flight executions memoize False and keep single-history behaviour for the
  rest of their lives.
- `workflow.info().is_continue_as_new_suggested()` **or**
  `workflow.info().get_current_history_length() >= MERGE_WATCH_HISTORY_FLOOR`
  (new constant, 4096). The floor exists because the cluster's
  `temporal-dynamic-config` is empty and a future edit must not silently switch
  the bound off, and because it is the only handle a test has.
- **`not self._abandoned`** — new versus the superseded design. An `abandon`
  already observed must end the watch, never be traded for a continuation.
- `polls_this_run >= 1` — at least one completed poll in the current run.
- `tick_task is None or tick_task.done()` — never hop with an in-loop shepherd
  tick in flight; the suggestion stays true once crossed, so the hop happens at
  the next clean boundary.
- `hops < MERGE_WATCH_MAX_HOPS` (new constant, 16). Past it the loop logs an
  error and keeps watching; the watch is observational and must never fail over
  its own bound.

**5. Signal safety across the boundary.** Temporal can lose a signal that
races a continue-as-new. Before #434 this was a non-issue for this workflow;
now `abandon` is live for the entire watch. Mitigations, in order: the hop
predicate refuses to hop while `_abandoned` is set; `_abandoned` and
`_abandon_reason` are carried in the resume record; and the continued run
re-checks them before its first sleep, so the state survives even though a
signal delivered exactly at the boundary may not. The residual exposure is a
single `abandon` delivered in the instant between the hop decision and the
continuation — it costs one poll interval (15 minutes), because the operator's
signal can simply be re-sent and the next poll observes it. That trade is
recorded here rather than left implicit.

**6. Cadence and constants.** `MERGE_POLL_INTERVAL`, `_Cadence`, the tick
budget and `MERGE_WATCH_DEADLINE` are untouched. `MERGE_WATCH_HISTORY_FLOOR`
and `MERGE_WATCH_MAX_HOPS` are new one-line module constants beside line 201;
the new patch marker lands in `tools/diagram_facts.py`'s scraped
`patched_markers` list, so `docs/diagrams/archify/facts.yaml` is regenerated as
part of the change.

**Arithmetic.** At a 4096-event floor and ~11.5 events/poll a hop lands about
every 356 polls, ~3.7 days at the 15-minute interval: about 4 hops across a
complete 14-day watch, each run's history around 4.2k events — under
`warn` 10,240 and three orders of magnitude from `error` 51,200. Cost per hop
is one extra `WorkflowExecutionContinuedAsNew`/`Started` pair plus a ~1 KiB
input.

## Alternatives

**Raise `continue_as_new` inline at the top of the loop (the issue's sketch).**
Smallest diff, wrong for a reason specific to this function: the `finally` at
2843 performs a lifecycle `release`/`terminal` activity and the
claim-abandonment metric. A hop raised inside it relinquishes the ownership row
on every hop and re-acquires with a new epoch in the next run — a repeated
few-second window with no owner, in which the cron sweeper can take the entity.
Dropped in favour of returning a decision. (Its second defect — reading
`is_continue_as_new_suggested` as an attribute — is a plain bug fixed by
calling it.)

**A separate `MergeWatchWorkflow` child, restarted per window.** Dropped: it
multiplies surface for no extra safety. `shepherd_in_loop`, `lifecycle_claim`
and now `abandon_state` are asked of the DevLoop workflow id by mctl-api and
`run_shepherd`, `ACTIVE_DEV_LOOPS_QUERY` filters on
`WorkflowType = 'DevLoopWorkflow'`, and the worker would need a new workflow
type registered plus test-harness plan updates.

**Reviving the superseded slug instead of forking it.** Not possible:
`_preflight_existing_result` matches the closed PR #437 by `headRefName`
forever and rewrites the proposal to `rejected` (mctlhq/mctl-agents#438). The
fork is a workaround for that bug, not a design preference.

**Make a poll cheaper instead of bounding the run.** Folding the ownership
heartbeat into `get_pr_state`, a longer interval, or raising
`limit.historyCount.warn` in `temporal-dynamic-config`. All trade the symptom
and none give the workflow a mechanism that reacts to history growth.

## Platform impact

**Migrations.** None. No schema, no gitops state, no mctl-api contract change.
The only new persisted artifact is the continue-as-new input payload inside
Temporal history.

**Backward compatibility.** In-flight executions memoize
`merge-watch-continue-as-new` as False and finish in one history exactly as
today, retiring by attrition at `MERGE_WATCH_DEADLINE`. `start.py` and
`workflow_id_for` are unchanged; because `resume` is a defaulted field rather
than a second parameter, external starts keep sending the same single payload
and recorded replay fixtures keep decoding. `USE_EXISTING` still attaches to
the latest run of a hopping watch and `handle.result()` follows the
continuation chain. `ACTIVE_DEV_LOOPS_QUERY` still sees exactly one Running
execution per workflow id: the server marks the previous run `ContinuedAsNew`
and starts the successor in the same transaction.

**Resource impact.** Strictly negative on storage and workflow-task payload
size: each run's history is bounded near the floor instead of growing to ~15.5k
events. Four extra workflow executions per long watch, each with a ~1 KiB
input. No new activity, so no worker registration and no queue-routing change.

**Risks and mitigations.**

- *An `abandon` is lost or ignored across a hop.* The sharpest new failure mode
  after #434, and the one the superseded design did not have. Mitigated by the
  `not self._abandoned` term in the hop predicate, by carrying the abandon
  state, by re-checking it before the first sleep of a continued run, and by a
  test that signals `abandon` immediately before a forced hop and asserts the
  watch ends rather than continues.
- *A continued run answers a query differently and the cron sweeper
  double-shepherds the PR.* Mitigated by rehydrating all four query handlers'
  state before the first await, and by a test that queries all four after a
  forced hop.
- *The deadline resets and the watch becomes unbounded.* Mitigated by carrying
  an absolute ISO timestamp (parsed with the existing `_as_utc`), never
  recomputing it, and by a test asserting a hopped watch still ends 14 days
  after its first poll.
- *A continue-as-new storm.* Mitigated by the one-poll floor, the hop cap, and
  the cap degrading to "keep watching" rather than to a failure.
- *Mid-watch deploys now reach a continued run.* Today an in-flight watch is
  frozen against code changes by patch memoization; after this change a hop
  re-enters the current image. Mitigated by carrying cadence, shepherd and
  ownership decisions as data rather than re-deriving them from markers. It
  remains a real, accepted narrowing of the attrition property and belongs in
  the PR description.
- *Rollback while continued runs exist.* Mitigated by the two-step rollback in
  tasks.md: disable the hop predicate first, keep the resume path until the
  hopping executions drain.
