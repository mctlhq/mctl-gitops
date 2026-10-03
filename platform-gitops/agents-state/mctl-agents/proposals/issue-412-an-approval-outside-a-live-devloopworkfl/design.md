# Design: issue-412-an-approval-outside-a-live-devloopworkfl

## Current state

**The implement submit has exactly one caller.** In
`orchestrator/temporal/workflows/dev_loop.py`, after `wait_condition(self.
_approved)` the loop resolves the slug (`find_proposal_slug`), submits
`mctl-agents-approve` through `_run_cwft` (the `atomic_approve` branch),
resolves the implementer release, and only then calls `self._implement(...)`,
which submits `IMPLEMENTATION_OPERATION = "mctl-agents-implement"` with
`{"service": ..., "slug": ...}`. `_run_cwft` routes that one operation to
`IMPLEMENTATION_TASK_QUEUE` behind `workflow.patched("implement-queue")` —
the admission queue from ADR-008 D7 / #395, whose slot limit
(`constants.implementation_max_concurrent_activities()`, default 3) *is* the
number of implementer runs allowed to exist at once.

**The approve flip is a side effect of that step, not a trigger.** The CWFT
`mctl-agents-approve` performs only the `proposed -> accepted` write (see the
comments in `orchestrator/run_implementer.py` around line 2176 and in
`orchestrator/proposal_state.py`). Invoking it standalone via
`mctl_trigger_approve` produces the flip and nothing else.

**Nothing else promotes `accepted`.**

- `orchestrator/temporal/workflows/reconcile.py` submits exactly one
  operation, `APPLY_OPERATION = "mctl-agents-reconcile"`, and only when
  `discovery.projections` is non-empty. Its docstring states the contract:
  discovery is read-only, the write happens in Argo, no findings are passed.
- `orchestrator/temporal/activities/orphans.py` has the right idea and the
  wrong filter: `ACTIONABLE_STATUSES` includes `accepted`, but the loop does
  `pr = find_pr_for_proposal(...)` / `_detect_from_github` and then
  `if pr is None or pr.closed_unmerged or pr.merged: continue`. A stranded
  proposal has no PR *by definition*, so it is skipped before the
  active-workflow comparison ever runs. The result is not even logged.
- `orchestrator/temporal/worker.py:setup_schedules` registers three schedules
  and only three: `reconcile-mctl-agents-schedule` (15 min, offset 3),
  `issue-poll-mctl-agents-schedule` (15 min, offset 7),
  `incidents-mctl-agents-schedule` (1 h, offset 11). There is no implement
  schedule.
- `docs/agent-inventory.yaml` records the implementer's triggers as
  `cronworkflow-mctl-agents-implement (currently suspend: true)`,
  `mctl_trigger_implementer (MCP, admin-only)` and the shepherd's
  `--review-feedback` fork. `docs/diagrams/archify/facts.yaml` still carries
  that cron's old cadence (`*/5 * * * *`). So the pre-Temporal sweeper existed,
  was suspended during the migration, and was never replaced.

**The sweeper logic is present and correct.**
`run_implementer.find_accepted_proposals(state_dir, service_filter, slug_filter)`
globs `agents-state/*/proposals/*/.status.yaml`, defaults a missing file to
`proposed`, and returns `ProposalRef`s with `approval_ok =
human_approval_satisfied(data)`. `main()` calls it, `_max_proposals_error`
pins executable runs to one proposal, and `implement_one` takes an
`ExecutionClaim` plus the 130-minute `attempt` lease. That is exactly what the
hand-run `mctl_trigger_implementer` exercised on 2026-09-19.

**The pieces a scheduled sweep needs already exist too.**
`activities/gitops_state.list_proposal_refs()` reads every `.status.yaml` from
gitops `main` over the API (no clone — the worker has none by design);
`activities/visibility.VisibilityActivities.list_active_dev_loop_ids` answers
`WorkflowType = 'DevLoopWorkflow' AND ExecutionStatus = 'Running'`;
`orphans._expected_workflow_id(slug, repo, service)` derives
`dev-loop-{owner}-{service}-{issue}` from an `issue-<N>-` slug and returns
`None` for slugs that never had a loop (`incident-*`, pre-Temporal).
`proposal_state.human_approval_satisfied` / `unrunnable_reason` name the one
permanently unrunnable combination (#349).

## Proposed solution

Add a fourth scheduled Temporal workflow that turns `accepted` back into an
actionable queue, plus the reporting that makes the condition visible. All of
it lives in `mctl-agents`; no sibling repository has to change for the fix to
work.

### 1. A stranding predicate, in one place

New `orchestrator/temporal/activities/stranded.py`:

```python
@dataclass(frozen=True)
class StrandedProposal:
    service: str
    slug: str
    updated_at: str
    reason: str          # "accepted, no PR, no live DevLoopWorkflow"

@dataclass(frozen=True)
class StrandedScanResult:
    total_accepted: int
    stranded: list[StrandedProposal]
    skipped: list[tuple[str, str]]     # (service/slug, why it was skipped)
    skipped_reason: str | None = None  # the whole scan declined

@activity.defn
async def find_stranded_accepted(
    active_workflow_ids: list[str], grace_minutes: int
) -> StrandedScanResult: ...
```

It calls `list_proposal_refs()` and keeps `status == "accepted"`, then drops a
proposal when any of the following holds, recording which one:

1. `pr_url` is set — that is `detect_orphans`' and the shepherd's case.
2. `attempt` is present and not expired — an implementer run holds it
   (`run_implementer`'s 130-minute lease).
3. `unrunnable_reason(data) is not None`, or a `blocked` marker is set — a
   submit could only refuse (#349).
4. `updated_at` is newer than `grace_minutes` — a live loop may be between its
   approve flip and its implement submit.
5. `expected_dev_loop_id(...)` is in `active_workflow_ids` — a DevLoopWorkflow
   owns it.

Filters 2-4 need three fields `ProposalStateRef` does not carry today.
`gitops_state._parse_status_yaml` returns `(status, pr_url)`; it gains
`updated_at`, `attempt_expires_at` and `unrunnable`/`blocked` booleans, all
**defaulted on the dataclass** — the same rule `PRSnapshot.head_sha` follows,
so an activity result recorded before this change still deserializes. The
approval check reuses `proposal_state.human_approval_satisfied`; no second copy
of that predicate is written.

`orphans._expected_workflow_id` is promoted to a public
`expected_dev_loop_id` (still in `orphans.py`, re-exported) so both sweeps
derive the id the same way. Note the deliberate consequence: an `incident-*`
slug yields `None`, i.e. "never had a loop", so the incident responder's
auto-accepted proposals — which today reach the implementer only when a human
runs `mctl_trigger_implementer` — become sweepable.

### 2. `ImplementSweepWorkflow` and a child per proposal

New `orchestrator/temporal/workflows/implement_sweep.py`:

```
list_active_dev_loop_ids        (control queue, 5 min timeout, 3 attempts)
   |  on failure after retries -> return skipped_reason, submit NOTHING
find_stranded_accepted(ids, grace)
   |
for each stranded proposal, up to MAX_SUBMITS_PER_TICK:
   start_child_workflow(
       SweptImplementWorkflow,
       id=f"implement-sweep-{service}-{slug}",
       id_reuse_policy=ALLOW_DUPLICATE,
       id_conflict_policy=USE_EXISTING,
       parent_close_policy=ABANDON,
   )
```

The child is deliberately tiny: it submits `mctl-agents-implement` with
`{"service", "slug"}` on `IMPLEMENTATION_TASK_QUEUE` (`SDK_STEP_TIMEOUT`-class
start-to-close, 2-minute heartbeat, `maximum_attempts=3`, same shape as every
other CWFT submit) and records the outcome.

Three properties come out of that structure rather than out of new code:

- **Dedup without a lock.** The child's workflow id is the entity id, and
  `USE_EXISTING` makes a second start for a proposal already being swept a
  no-op — the same mechanism `start.py` uses to guarantee one DevLoop per
  issue. `ALLOW_DUPLICATE` (not `ALLOW_DUPLICATE_FAILED_ONLY`) keeps a
  proposal re-sweepable after a completed-but-ineffective run; the filters
  above, not the reuse policy, are what stop a pointless resubmit.
- **The tick stays short.** An implement run can occupy its activity for
  hours. With `ABANDON` the parent returns in seconds, so `overlap=SKIP` on
  the schedule costs nothing — unlike reconcile, whose 35-minute apply step
  can swallow two fires.
- **Capacity is still ADR-008's.** Every submit lands on the admission queue;
  with no free slot the activity stays `Scheduled` in Temporal and no Argo
  workflow is created. The per-tick cap only bounds how many children one tick
  mints after an outage.

Failure stance, stated because it is the opposite of reconcile's: reconcile
keeps writing projections when the visibility query fails, because projecting a
merged PR is harmless without the active set. Here the active set *is* the
safety argument, so an unknown active set means **submit nothing this tick**.
Recovery latency of 15 minutes is the correct price for never double-running
the implementer.

### 3. Registration, schedule, and making the state visible

- `worker.py`: add `SweptImplementWorkflow` and `ImplementSweepWorkflow` to the
  `workflows` list in `worker_plans` (control queue only, like every other
  workflow) and `find_stranded_accepted` to `short_activities` — it is a
  bounded set of GitHub reads, the same shape as `detect_orphans`.
- `worker.py:setup_schedules`: register
  `IMPLEMENT_SWEEP_SCHEDULE_ID = "implement-sweep-mctl-agents-schedule"` with
  `every=15 min, offset=12 min` and `overlap=SKIP`. That fires at
  :12/:27/:42/:57 — clear of reconcile (:03/:18/:33/:48), issue-poll
  (:07/:22/:37/:52), incidents (:11) and of the Argo cron minutes {0, 15, 30}
  that `tests/test_worker_schedules.py::test_no_schedule_lands_on_an_argo_cron_minute`
  pins. 15 minutes matches the cadence the issue asks for and the one
  reconcile/shepherd already use; it is not the old Argo `*/5`, which would put
  a sweep on :15 and :30.
- Every candidate — submitted or skipped — is logged as one
  `STRANDED service=... slug=... reason=...` line, mirroring `detect_orphans`'
  `ORPHAN` lines, and the counts are returned in `ImplementSweepResult`. This
  is the half of the issue that is about *invisibility*: even with the sweep
  paused, the tick's result says how many proposals are stranded.
- Docs the repo's own tests treat as code: `docs/temporal-flow.md` §4 and
  `docs/diagrams/temporal-flow-schedules.mmd` gain the fourth schedule;
  `docs/diagrams/archify/facts.yaml` is regenerated with
  `tools/diagram_facts.py --update` (`facts["schedules"]` and
  `facts["workflows"]` are scraped from `worker.py`, so `tests/
  test_diagram_facts.py` fails otherwise); `docs/agent-inventory.yaml` gains
  the new trigger under the implementer's `triggeredBy`; `README.md`'s Tier 2
  section states that `accepted` is swept.

### 4. Explicitly not changed

`cronworkflow-mctl-agents-implement` stays suspended, `run_implementer.py`
keeps its one-proposal-per-run policy, and `ReconcileWorkflow` is untouched.
The cross-repo guard (mctl-api: have `mctl_trigger_approve` consult
`mctl_get_dev_loop` and say so when no loop exists) is recorded as a follow-up
issue with the interface named, not attempted from here.

## Alternatives

**A. Un-suspend the Argo `cronworkflow-mctl-agents-implement` (`*/5`).**
The smallest diff, and the issue's option (2) read literally. Dropped: it
submits the implementer *outside* Temporal, so it bypasses the admission queue
that exists precisely because nine simultaneous approvals reached Argo at once
on 2026-09-19 and six died on a capacity-1 mutex (`constants.py`,
`IMPLEMENTATION_TASK_QUEUE`); it is the bypass `mctl-gitops#1283` already
files against `mctl_trigger_implementer`; it has no view of running
DevLoopWorkflows, so it would race a live loop's own implement step; it fires
on :00/:15/:30, minutes `test_no_schedule_lands_on_an_argo_cron_minute`
identifies as contended on the gitops write mutex; and with
`--max-proposals 1` it drains one proposal per tick while paying for a clone
every five minutes.

**B. Let `ReconcileWorkflow._apply` promote (the issue's option 3).**
Dropped on three counts. `_apply` submits one operation and passes no findings
on purpose — the CWFT re-reads state in the pod that holds the clone — so
promotion would need a second operation and a findings payload, breaking that
stance. Discovery is read-only by contract, and the reconcile tick already
carries a 35-minute mutex-bound step under `overlap=SKIP`; adding implement
submits would let a slow implement starve drift correction. And the reconcile
result would then mix "what I observed" with "what I caused", which is the
distinction ADR-005 keeps.

**C. Guard-only: make the standalone approve refuse when no loop exists (the
issue's option 1).** Correct and worth doing, but not sufficient and not
available here. It stops new strandings and recovers none of the existing
ones; it lives in `mctl-api`/`mctl-gitops`, outside this repository's implement
scope; and it does nothing for the incident responder, which writes
`status: accepted` with no approval step at all
(`run_incident_responder.py`) and has been relying on the suspended cron ever
since the migration.

**D. Have the approve path start a DevLoopWorkflow when none exists.**
Superficially the tidiest — one owner for every proposal. Dropped:
`DevLoopWorkflow.run` begins at `resolve("issue-investigator")` and
`mctl-agents-investigate`, so it would re-investigate a proposal that already
exists and, on a renamed issue, mint a second `issue-<N>-*` directory that
`find_proposal_slug` then refuses as ambiguous (the hazard #246 closed). And
`incident-*` proposals have no issue URL to key a loop on.

## Platform impact

**Migrations.** None. No schema, no gitops state format change. New
`ProposalStateRef` fields are defaulted so results recorded by the running
worker still deserialize. New workflow types mean new histories, so no
`workflow.patched` marker is needed for the sweep itself; `ReconcileWorkflow`
and `DevLoopWorkflow` histories are untouched, and
`tests/test_workflow_replay.py` keeps passing against the existing fixtures.

**Backward compatibility.** `mctl_trigger_implementer`, the shepherd's
`--review-feedback` fork and the DevLoop path all keep working unchanged. A
proposal a live DevLoop owns is never touched by the sweep.

**Resource impact.** One extra Temporal schedule and one workflow execution
every 15 minutes. Cost per tick: one visibility query, one git-tree read plus
about 200 blob reads against gitops (`list_proposal_refs`, concurrency-capped
at `_FETCH_CONCURRENCY = 8`) — the same read the reconcile tick already
performs, nine minutes earlier on the clock, so the two bursts do not share
the GitHub token at the same instant. Implementer runs are unchanged in cost
and are capped by the admission queue, not by this workflow.

**Risks and mitigations.**

- *Double implementation.* Four independent bounds: the running-DevLoop
  visibility check, the `USE_EXISTING` child id, the proposal's `attempt`
  lease, and `implement_one`'s `ExecutionClaim`. Plus fail-closed on an
  unknown active set.
- *Submit storm after an outage.* Per-tick cap (5, env-tunable) and the
  admission queue's slot limit (default 3). Excess candidates are logged, not
  dropped silently — the repo's stated rule about silent caps.
- *Stale visibility.* Temporal advanced visibility is eventually consistent;
  the 20-minute grace on `updated_at` covers the window, chosen above
  `APPROVE_STEP_TIMEOUT` (15 min) so a loop that flipped but has not submitted
  yet is always inside it.
- *Sweeping a proposal that can never run.* `unrunnable_reason` /
  `human_approval_satisfied` are consulted before submitting, so a
  `requires_human_approval` proposal with no approver (#349) is reported, not
  run.
- *A schedule that is registered but wrong.* `_ensure_schedule` converges spec
  and overlap policy on every boot and preserves `state`, so a pause survives
  redeploys — which is also the rollback.
- *Cross-repo drift.* If `cwft-mctl-agents-implement.yaml` ever drops the
  `slug` parameter, the sweep silently reverts to service-scoped runs — the
  same exposure `dev_loop.py` already documents for its own implement params.
  The follow-up issue for the mctl-api guard names it.
