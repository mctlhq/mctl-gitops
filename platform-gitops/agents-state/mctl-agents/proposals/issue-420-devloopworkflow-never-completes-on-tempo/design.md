# Design: issue-420-devloopworkflow-never-completes-on-tempo

## Current state

### The loop and its bounds

`DevLoopWorkflow` lives in `orchestrator/temporal/workflows/dev_loop.py` (2721 lines).
`run()` (line 885) is a linear pipeline: resolve the investigator release, submit the
`mctl-agents-investigate` CWFT, park for approval, flip the proposal with
`mctl-agents-approve`, submit the implementer through `_implement` (line 1132), then
`_watch_pr` (line 2433), `_observe_deploy` (line 1276) and `_watch_incidents` (line 1213).

Every stage except one is bounded:

- CWFT submits go through `_run_cwft` (line 520) with `SDK_STEP_TIMEOUT = 2 h`
  (line 103) and `SDK_STEP_RETRY_POLICY` capped at 3 attempts.
- `_implement` requeues at most `MAX_PRESTART_REQUEUES = 3` (line 117) and otherwise
  raises a non-retryable `ApplicationError`, so the execution ends `Failed`.
- `_watch_pr` runs `while workflow.now() < deadline` with
  `MERGE_WATCH_DEADLINE = 14 days` (line 181), returns immediately when
  `state.state in ("MERGED", "CLOSED")` (line 2561), and gives up after
  `cadence.pr_lookup_grace_polls` consecutive unresolvable polls (line 2645).
- `_observe_deploy` is bounded by `DEPLOY_VERIFY_DEADLINE = 45 min` (line 389) and
  `_watch_incidents` by `INCIDENT_WATCH_WINDOW = 30 min` (line 403).

The one unbounded point is line 909:

```python
await workflow.wait_condition(lambda: self._approved)
```

`self._approved` is set only by the `approve` signal handler (line 869). No timeout, no
alternative predicate, no other writer. `activities/issue_state.py`'s own module docstring
states the property plainly: the workflow parks there "durably, with no upper bound".

### Why the observed execution is stuck

The `stale-issue-admission` gate (line 924) already reads `get_issue_state` and returns a
terminal `DevLoopResult` when the source issue is closed — but it runs *after* the wait
resolves. A loop that never receives the signal never reaches it.

That is the shape of `dev-loop-mctlhq-portfolio-98`. The proposal was approved out of band
(the standalone `mctl-agents-approve` operation flips `.status.yaml` directly — the
`mctl_approve_dev_loop` tool documentation calls out exactly this hazard: "a hand-edited
`.status.yaml` is invisible to a workflow already parked on the approve signal"), the cron
implementer picked the accepted proposal up, `portfolio#99` merged, `portfolio#98` closed.
The workflow heard none of it and is still at line 909 seven days later.

The issue's acceptance criteria phrase this as "a DevLoopWorkflow whose PR merges". Worth
being precise: for a loop that *drove* its own implement, `_watch_pr` already ends on
`MERGED`/`CLOSED` and the AC holds today. The failure is the loop that never got past
approval and therefore has no PR of its own to watch.

### The stuck loop is not inert — it suppresses recovery

`VisibilityActivities.list_active_dev_loop_ids` (`orchestrator/temporal/activities/visibility.py:109`)
runs `ACTIVE_DEV_LOOPS_QUERY = "WorkflowType = 'DevLoopWorkflow' AND ExecutionStatus = 'Running'"`
(`visibility.py:23`) and feeds the result to two sweepers:

- `find_stranded_accepted` (`activities/stranded.py:182`), called by `ImplementSweepWorkflow`
  (`workflows/implement_sweep.py:297`), skips any proposal whose
  `expected_dev_loop_id(...)` is in `active_workflow_ids` (`stranded.py:160`).
- `detect_orphans` (`activities/orphans.py:141`), called by `ReconcileWorkflow`
  (`workflows/reconcile.py:148`), applies the same exclusion (`orphans.py:124`).

So a wedged `Running` execution silences both sweepers for its own proposal indefinitely.
The leak is not only an operational-visibility problem; it is a hole in the repair path.

### There is no way out today

`orchestrator/temporal/cli.py` exposes exactly `start`, `approve`, `status`
(`build_parser`, line 89). `start_dev_loop_workflow` (`orchestrator/temporal/start.py:30`)
uses `WorkflowIDConflictPolicy.USE_EXISTING`, so re-triggering the issue silently returns
the same stuck handle. mctl-api exposes an approve endpoint and a read-only
`GET /api/v1/agents/dev-loop/{workflow_id}`. Nothing in this repository can end an
execution.

### Conventions the change must respect

- **Patch markers.** Every command-shape change to `DevLoopWorkflow` is gated by
  `workflow.patched(...)`: `stale-issue-admission` (line 924), `atomic-approve` (990),
  `slug-scoped-implement` (995), `merge-detection` (1091), `deploy-observation` (1104),
  `incident-watch` (1116), `fast-shepherd-cadence` (2451), `shepherd-in-loop` (2453),
  `concurrent-shepherd-tick` (2487), `lifecycle-ownership` (2492), `implement-outcome`
  (1167), `exec-queue`/`implement-queue` (545/554).
- **Replay coverage.** `tests/test_workflow_replay.py` replays
  `tests/fixtures/histories/dev_loop_full.{prepatch,patched}.json` recorded by
  `tools/record_workflow_history.py` from `tests/replay_scenarios.py`. Its own docstring
  records the measured limits: an added/removed/reordered activity is caught; a divergence
  in the *last* recorded workflow task is invisible.
- **New activity plumbing.** Import inside the `workflow.unsafe.imports_passed_through()`
  block (line 48); register in `short_activities` in `worker_plans`
  (`orchestrator/temporal/worker.py:514`).
- **`DevLoopResult` fields are additive and defaulted** so results recorded before a field
  existed still deserialize (see the comments at line 486).

## Proposed solution

Three changes in `mctl-agents`, in dependency order.

### 1. An `abandon` signal, observed by both long waits (no patch marker)

Add beside `approve` (line 869):

```python
@workflow.signal
def abandon(self, *args: object) -> None:
    # Same defensive parse as approve(): signals must never raise.
    self._abandon_reason = _first_string(args) or "abandoned by operator"
    self._abandoned = True
```

and broaden the approval predicate to
`lambda: self._approved or self._abandoned`, followed immediately — **before** any
`workflow.patched(...)` branch — by:

```python
if self._abandoned:
    return DevLoopResult(
        investigate=investigate_result, implement=None, approve=None,
        ended=f"abandoned: {self._abandon_reason}",
    )
```

This is deliberately the first change, because it is the only part that works on the
executions stuck **right now**. A signal handler is not a workflow command, so adding one
needs no patch marker and changes no recorded history. Broadening the predicate adds no
command either: a parked execution has no history events after the wait, so returning at
that point is a clean completion. `_watch_pr`'s loop condition gains the same check
(`while workflow.now() < deadline and not self._abandoned`), which also lets an operator
cut short a 14-day merge watch; that path runs the existing `finally` block, so the
lifecycle-ownership row is released rather than left active.

Why a signal rather than Temporal `terminate`: `terminate` kills the execution without
running `_watch_pr`'s `finally` (line 2656), which is where `_ownership("release"/"terminal")`
and `_report_claim_abandonment` run. A terminated loop would abandon a live ADR-010
ownership row — precisely the abandonment the `lifecycle_claim` query exists to make
visible. Cancellation has a milder version of the same problem (activities scheduled in a
cancelled scope need a detached scope to run). The signal keeps cleanup on the normal path.

### 2. A bounded, observant approval park (patch marker `approval-watch`)

Replace the single wait with a poll loop, gated so old histories are untouched:

```python
if workflow.patched("approval-watch"):
    deadline = workflow.now() + APPROVAL_WAIT_DEADLINE
    while workflow.now() < deadline:
        if await workflow.wait_condition(
            lambda: self._approved or self._abandoned,
            timeout=APPROVAL_POLL_INTERVAL,
        ):
            break                      # signalled — fall through to the gate below
        parked_state = await self._read_issue_state(issue)   # fail-open, returns None
        if parked_state is not None and parked_state.state == "closed":
            return DevLoopResult(..., ended=f"source issue closed while parked "
                                            f"({parked_state.state_reason or 'completed'})")
    else:
        return DevLoopResult(..., ended="approval wait expired")
else:
    await workflow.wait_condition(lambda: self._approved or self._abandoned)
```

New constants next to the existing cadence block:

- `APPROVAL_POLL_INTERVAL = timedelta(hours=6)`
- `APPROVAL_WAIT_DEADLINE = timedelta(days=14)` — matched to `MERGE_WATCH_DEADLINE` so the
  worst-case lifetime of an execution is two bounded fortnights, not infinity.
  56 polls over the deadline is a negligible history footprint against Temporal's 50k
  event limit (compare the ~1344 polls `_watch_pr` already budgets for).

`_read_issue_state` is a small helper wrapping the **existing** `get_issue_state` activity
with the **existing** fail-open rule the `stale-issue-admission` gate uses (line 936): an
`ActivityError` after retries logs a warning and returns `None`, so a GitHub blip delays
the check by one interval instead of wedging or failing the loop. No new activity, no new
worker registration, no new credentials.

The signalled path still falls through to the existing `stale-issue-admission` gate
unchanged, so an approval that arrives after the issue closed is still refused there.

Note the marker's reach. `workflow.patched` returns `False` during replay of a position
whose history holds no marker, and `True` once the execution is past the end of its
recorded history. For an execution **parked at line 909**, this call site sits after its
last history event — so the marker should evaluate `True`, record itself, and the parked
execution should adopt the new polling behaviour on the next worker deploy. That would
make the automatic fix retroactive for the currently-wedged executions, not just new ones.
This is the design's one load-bearing assertion about SDK semantics rather than about this
repo's code, so T4 measures it against `Replayer` before the change is trusted; the
`abandon` signal is the fallback that works either way.

### 3. `cli.py abandon`, and the mctl-api follow-up

Add a fourth subcommand mirroring `approve` (`cli.py:30`):

```
python -m orchestrator.temporal.cli abandon <workflow_id> --reason "<why>"
```

`--reason` required and undefaulted, for the same reason `--approver` is (line 101): a
recorded reason of `"unknown"` is worse than no affordance. `status` (line 37) gains a
line printing `result.ended` when set, so the outcome is legible from the same command an
operator already runs.

The MCP-visible version (`POST /api/v1/agents/dev-loop/{workflow_id}/abandon`, tool
`mctl_abandon_dev_loop`) belongs in the sibling `mctl-api` repo and cannot be implemented
from here. This proposal ships the signal it would send and files the follow-up issue; the
CLI is the interim affordance and is what satisfies the issue's stretch criterion in this
repository. Worth saying explicitly: the CLI still needs cluster network access to the
Temporal frontend, so the stretch criterion is only fully met once mctl-api exposes it.

### Result shape

`DevLoopResult` gains one field:

```python
# Why this execution ended, when it ended for a reason other than running
# the pipeline to the end: "abandoned: ...", "source issue closed while
# parked (...)", "approval wait expired". Empty on every other path, and
# defaulted so results recorded before this field existed still deserialize.
ended: str = ""
```

The existing early returns (investigate failure at line 903, `stale-issue-admission` at
948, failed approve flip at 1038) are also given `ended` strings, so `cli.py status` and
any future mctl-api reader can explain a `Completed` execution that produced no PR.

## Alternatives

**A sweeper that detects and signals stale Running executions.** `VisibilityActivities`
already lists Running `DevLoopWorkflow` ids, and `ReconcileWorkflow` already runs every
15 minutes — a new activity could cross-reference each id's issue against GitHub and
signal `abandon`. Dropped as the *primary* fix: it requires the workflow to be signal-aware
anyway (change 1), it adds a second actor that can end a loop the loop itself should end,
and it inherits `expected_dev_loop_id`'s known id-derivation quirk (`orphans.py:82` builds
the id from the gitops *service* directory while `issue_ref.workflow_id_for` builds it from
the issue URL's *repo* — they agree only when those names match). Better as a follow-up
once self-termination exists, and then it is a safety net rather than the mechanism.

**A `workflow.wait_condition(..., timeout=APPROVAL_WAIT_DEADLINE)` and nothing else.** One
line, no poll loop, satisfies the "bounded" half of the ACs. Dropped because it gives a
14-day-late answer to a question GitHub could answer in six hours, and it does nothing for
the actual incident: `portfolio#98` closed on day 0 and the loop would still have sat there
until day 14. The bound is the backstop; the issue-state poll is the fix.

**Have the approve path (`mctl-agents-approve` / the implementer) signal the workflow.**
Close the loop at the source: whatever flips `.status.yaml` out of band also signals the
parked execution. Dropped because the flip runs inside an Argo CWFT in `mctl-gitops` with
no Temporal client, deriving the workflow id from a proposal slug would re-introduce the
`expected_dev_loop_id` mismatch above, and it only covers the out-of-band-approval cause —
a loop parked on an issue that was simply closed and forgotten stays stuck. It is a good
*additional* change, not a substitute for a self-bounding workflow.

**Temporal `terminate` exposed directly.** Rejected for the cleanup reason in §1: it skips
`_watch_pr`'s `finally` and abandons the lifecycle-ownership row.

## Platform impact

**Migrations.** None. No schema, no gitops layout change, no new secret, no new activity
registration.

**Backward compatibility.** Guarded by `approval-watch`. Executions past the approval wait
replay their recorded command sequence unchanged (the marker evaluates `False` during
replay of a position that lacks it). Executions parked at the wait are expected to adopt
the new branch — the intended, and beneficial, behaviour — which T4 verifies. `DevLoopResult.ended`
is defaulted, so old recorded results still deserialize; readers outside this repo
(`cli.py status`, mctl-api's dev-loop GET) must treat it as optional.

**Resource impact.** One `get_issue_state` activity per parked execution per 6 h. With 12
concurrent parks that is 48 GitHub reads a day against a token that already serves
`get_pr_state` at one read per 15 min per watching loop. History growth per parked
execution over the full deadline is ~56 timer/activity pairs — two orders of magnitude
below what `_watch_pr` already records.

**Risks and mitigations.**

- *A patched branch that wedges in-flight loops.* This is the repo's recurring hazard (see
  the comments at lines 971-978 and 984-989). Mitigated by the marker, by the existing
  `dev_loop_full.{prepatch,patched}.json` replay fixtures, and by a new fixture recorded
  from a history parked at approval (T4). Note the measured limitation in
  `test_workflow_replay.py`'s docstring: a divergence confined to the *last* recorded
  workflow task is invisible to `Replayer` — which is exactly where a parked history ends,
  so T4 must assert on the *resumed* execution's behaviour, not only on a clean replay.
- *A GitHub outage ending loops early.* Cannot happen: `_read_issue_state` fails open and a
  `None` read is never treated as "closed". Only a successful `closed` read ends the park.
- *An issue closed and reopened during the park.* The loop ends on the closed read and does
  not resume. Recovery is the existing one: re-add the intake label, which starts a fresh
  execution — `ALLOW_DUPLICATE_FAILED_ONLY` permits it because this execution ends
  `Completed`... which it does **not**. This is a real edge: `USE_EXISTING` +
  `ALLOW_DUPLICATE_FAILED_ONLY` in `start.py:30` means a *Completed* id cannot be restarted
  (`WorkflowAlreadyStartedError`). It is the same constraint every other terminal path in
  this workflow already has (the `stale-issue-admission` gate at line 948 completes
  identically), so this change does not make it worse — but it should be stated in the PR
  and is a candidate follow-up.
- *An operator abandons a loop that was actually working.* The reason string is required
  and lands in the result; `_watch_pr`'s `finally` releases the ownership row so the cron
  sweeper picks the proposal back up. Recoverable.
- *Cross-repo drift.* mctl-api's dev-loop GET and the `mctl_get_dev_loop` tool description
  both assume the unbounded park ("wait_condition has no timeout, so the loop then waits
  forever"). That text becomes stale on merge; the follow-up issue should carry it.
