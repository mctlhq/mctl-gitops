# Design: issue-395-feat-devloop-admit-implementation-work-i

## Current state

### What already exists on `main` (1.48.0)

The admission mechanism #395 specifies is implemented. Read in the clone:

- **The queue and its capacity.** `orchestrator/temporal/constants.py:64`
  defines `IMPLEMENTATION_TASK_QUEUE = "mctl-dev-loop-implement"`, `:68`
  defines `IMPLEMENTATION_OPERATION = "mctl-agents-implement"`, and
  `:104-109` reads `N` lazily from
  `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` (default 3) through
  `implementation_max_concurrent_activities()` — lazily on purpose, so a bad
  value only refuses the role that serves the queue.
- **The worker role.** `orchestrator/temporal/worker.py:360` lists
  `ROLES = ("all", "control", "execution", "implementation")`; `:499-536`
  builds the implementation plan with `activities=[submit_and_wait]` and
  `max_concurrent_activities=implementation_max_concurrent_activities()`, and
  `--role all` keeps that limit so the documented rollback target does not
  silently remove the capacity it exists to impose.
- **The routing.** `orchestrator/temporal/workflows/dev_loop.py:544-552`
  routes only `operation == IMPLEMENTATION_OPERATION`, behind
  `workflow.patched("implement-queue")`, to the admission queue; everything
  else falls through to the `exec-queue` branch at `:553`.
- **The two clocks.** `dev_loop.py:103-107` states the deliberate absence of
  `schedule_to_start_timeout` and `schedule_to_close_timeout`, and
  `tests/test_workflow_replay.py:288-340` asserts it from recorded history,
  tolerating the server's ten-year "unset" cap and rejecting any bound a run
  could actually hit.
- **Pre-start semantics.** `orchestrator/temporal/implement_outcome.py`
  classifies an implement result as `pre_start | execution | finalization |
  success` from Argo's node graph, reading "ran" from `hostNodeName`, an exit
  code or a Succeeded phase — never from `startedAt`, which Argo stamps while
  a node is still Pending on a mutex (`_pod_ran`, `:65-77`).
  `dev_loop._implement` (`:1087-1166`) requeues `pre_start` up to
  `MAX_PRESTART_REQUEUES = 3` with a `PRESTART_REQUEUE_BACKOFF` of 2 minutes,
  and raises typed `ApplicationError`s otherwise.
- **Three of four runtime phases.** `orchestrator/temporal/activities/argo.py:102-104`
  defines `PHASE_ADMITTED`, `PHASE_SUBMITTED`, `PHASE_RUNNING` and publishes
  them as the second heartbeat detail (`:187-192`, `:245-247`, `:324-337`),
  with the first detail reserved as the resume key. `:201-210` restores the
  prior projection on a retry and filters to known keys.
- **The orchestrator's half of the state.** `dev_loop.py:766-784` defines
  `ImplementExecutionState(stage, queued_at, prestart_requeues, outcome)`,
  exposed by the `implement_execution` query (`:829-832`) and rewritten on
  every submit and requeue (`:1114-1131`).
- **The written decision.** `docs/adr/008-worker-queue-split-and-capacity.md:191-302`
  is D7, amended 2026-09-19, and states the rollout order, the "not a
  distributed semaphore" limit, and that the projection surface is the
  heartbeat plus the `implement_execution` query.
- **The DoD as a test.** `tests/test_dev_loop_workflow.py` class
  `TestImplementationAdmission` holds the nine-approval burst
  (`test_a_burst_of_approvals_is_admitted_n_at_a_time`, asserting
  `gate.entered_total == n` while the pool is full), the routing test, the
  requeue tests and the typed-failure tests.
  `tests/temporal_harness.py` gives every workflow test a worker on all three
  queues with production's `N`.

### The three gaps this proposal closes

1. **`waiting` is unnamed.** The four-state definition of scope item 4 is
   three states in code. `ImplementExecutionState`'s docstring
   (`dev_loop.py:768-775`) deliberately declines to guess whether the activity
   is Scheduled or running — correct, that is Temporal's knowledge — but the
   consequence is that nothing states the join rule, and the consumer
   (#389 → mctl-api#331 → mctlhq/.github#95) has to invent it. There is also
   no `waiting_on`, so a projection cannot say *what* the loop waits for
   without hard-coding the answer on the reader's side.
2. **`queue_age` is recorded nowhere.** D7's "schedule-to-start latency is, by
   construction, the queue age" holds for the per-queue histogram, not for a
   single proposal. The heartbeat publishes `admitted_at` (`argo.py:189`, from
   `info.started_time`) but not the schedule instant, and the workflow's
   `queued_at` is workflow time from a different clock, so a consumer holding
   either one alone cannot compute the wait. Meanwhile `activity.info()`
   already carries both ends of it: `scheduled_time`,
   `current_attempt_scheduled_time` and `started_time` are all fields of
   `ActivityInfo` in the pinned temporalio 1.31.0
   (`temporalio/activity.py:110-118`).
3. **Nobody watches the admission queue.** The two limits #395 states honestly
   both rest on the implementation deployment being exactly one healthy
   replica. mctl-gitops#1285 guards the manifest in CI; nothing observes the
   live cluster. The worst failure this design can have is the silent one: an
   admission queue with no poller looks exactly like a full one, forever,
   because there is no `schedule_to_start_timeout` by design.

## Proposed solution

Three changes, each small, none introducing a component.

### 1. One runtime vocabulary module, versioned

New `orchestrator/temporal/runtime_projection.py`:

```text
PROJECTION_VERSION = 1
PHASE_WAITING  = "waiting"     # activity Scheduled, no slot yet
PHASE_ADMITTED = "admitted"    # a worker slot took it
PHASE_SUBMITTED = "submitted"  # Argo accepted the workflow
PHASE_RUNNING  = "running"     # a run-implementer pod is executing
WAITING_ON_IMPLEMENTATION_CAPACITY = "implementation_capacity"

@dataclass(frozen=True)
class RuntimeProjection:
    version: int
    phase: str
    queued_at: str | None
    admitted_at: str | None
    queue_age_seconds: float | None
    submitted_at: str | None
    implementer_started_at: str | None

    def to_detail(self) -> dict[str, object]
    @classmethod
    def restore(cls, detail: object, *, fallback: RuntimeProjection) -> RuntimeProjection
```

`argo.py` imports `PHASE_*` from here instead of defining them (the existing
names stay as re-exports for one release so nothing outside breaks), and
builds/updates a `RuntimeProjection` instead of a bare dict. `restore()` keeps
today's behaviour exactly: unknown keys are dropped, a missing detail falls
back, and a resume floors the phase at `submitted` because the resume key only
exists if a POST already succeeded. `PHASE_WAITING` is never *written* by the
activity — by definition the activity has not started — it exists so the
vocabulary has one home and the consumer has one source for the string.

Why a module rather than more constants in `argo.py`: the workflow, the
activity, the docs contract and the tests all need to spell the same four
words, and `argo.py` is an activity implementation that the workflow must not
import broadly (`dev_loop.py:78-84` already imports only narrow names under
`TYPE_CHECKING`/`unsafe.imports_passed_through`).

### 2. Queue age measured at admission, by the process that knows it

In `submit_and_wait`, at the top, from one clock:

```text
info = activity.info()
queued_at = _iso(info.scheduled_time)
queue_age_seconds = (info.started_time - info.scheduled_time).total_seconds()
```

`scheduled_time` is the activity's schedule instant and `started_time` this
attempt's start, so their difference is precisely the schedule-to-start wait
the admission queue *is*. Both are server-assigned, so there is no clock skew
between them and no join across surfaces.

Retries are handled by the mechanism already there: `restore()` takes
`queued_at`, `admitted_at` and `queue_age_seconds` from the prior detail when
one exists, so a retry after a heartbeat timeout reports the original
admission, not its own. That is the same reasoning `argo.py:193-210` already
applies to `admitted_at`, made explicit for the new fields. A *requeued*
pre-start submit is a new activity and legitimately gets a fresh queue age;
`dev_loop._implement` already resets `queued_at` per iteration
(`dev_loop.py:1114-1118`) and `prestart_requeues` distinguishes the rounds.

`ImplementExecutionState` gains one field, `waiting_on`, set to
`WAITING_ON_IMPLEMENTATION_CAPACITY` whenever `stage == "implementer"`. It is a
constant, not an inference: the workflow still does not claim to know whether
the activity started. Adding a defaulted field to a dataclass returned by a
query is backward compatible for consumers and for replay (queries are not
recorded in history).

The derivation rule the consumer needs is written into
`docs/runtime-state.md` (new, short) and cross-linked from ADR-008 D7:

```text
pending activity absent            -> the step is not in flight
pending activity, no heartbeat     -> phase = waiting,
  and last_started_time unset         waiting_on = implementation_capacity,
                                      queued_at from the query
pending activity with a detail     -> the detail's phase wins, with its
                                      timestamps and queue_age_seconds
```

Plus one INFO log line at admission (`info: admitted mctl-agents-implement
after 132.4s in queue`) so the number is visible in Loki without a dashboard.

### 3. An admission-health read on the reconcile tick

`VisibilityActivities` (`orchestrator/temporal/activities/visibility.py`)
already holds the connected `Client` for exactly this class of question. Add:

```text
@activity.defn
async def describe_admission_queue(self) -> AdmissionQueueHealth
```

implemented with the raw service stub —
`self._client.workflow_service.describe_task_queue(DescribeTaskQueueRequest(
namespace=..., task_queue=TaskQueue(name=IMPLEMENTATION_TASK_QUEUE),
task_queue_type=ACTIVITY, report_pollers=True, report_stats=True))` — which
exists in the pinned SDK (`temporalio/api/workflowservice/v1`,
`DescribeTaskQueueRequest` fields `report_pollers`, `report_stats`). It returns
`AdmissionQueueHealth(pollers, backlog, capacity_n, healthy, detail)` and logs:

- `pollers == 0` → `error:` naming the queue and the backlog. This is the
  silent-hang case; with no `schedule_to_start_timeout` nothing else will ever
  say it.
- `pollers > 1` → `warn:` that capacity is `replicas x N` and that
  `replicaCount: 1` is an architectural invariant of this phase (transient
  during a rolling restart, which is why it is a warning and not a failure).
- otherwise `info:` with backlog and `N`.

`ReconcileWorkflow` calls it once per tick behind
`workflow.patched("admission-health")`, wraps it in try/except like every other
non-essential read in that workflow (`reconcile.py:89-122` is the existing
shape), and carries the result on `ReconcileWorkflowResult`. It gates nothing:
a failed read leaves the tick byte-identical to today.

### 4. ADR-010 amendment

A short section in `docs/adr/010-lifecycle-ownership-contract.md`, after §13,
recording that ADR-008 D7 is where implementation admission is decided, that
worker slots are backpressure and not a lease, and that the hard count across
crashes and replicas is ADR-010's server-side claim work (mctl-api#337) — with
the note that `ClaimClient` (`orchestrator/lifecycle/claim.py`) targets
`POST /api/v1/lifecycle/claims/*`, which mctl-api does not serve yet, so the
rollout is `off`. The substantive write-down stays in D7, where capacity is
the subject; ADR-010 gets the cross-reference the issue's "where this is
written down" section is really asking for, without duplicating a decision in
two ADRs that can then drift.

## Alternatives

**Publish a `waiting` heartbeat from the workflow side.** Have
`DevLoopWorkflow` start a timer at schedule time and mark the state `waiting`
until the activity completes. Dropped: the workflow cannot observe an
activity's *start*, only its completion, so "waiting" would be indistinguishable
from "running for three hours" — the exact conflation this issue exists to
remove — and it would make the query a second, guessing runtime-state surface,
which `dev_loop.py:768-775` and D7 both explicitly refuse.

**Give the implement submit a long `schedule_to_start_timeout` so a dead
admission queue eventually fails loudly.** Dropped: it is one of the three
things D7 says the design must not do. A bound on the queue wait turns
"waiting for capacity" back into a failure, one layer earlier than the 2026-09-19
bug. The dead-queue case is a *deployment* fault and is caught by observing
pollers, not by failing work that is correctly waiting.

**Emit `queue_age` as its own Prometheus metric from the implementation
worker.** Dropped: `temporal_activity_schedule_to_start_latency_{bucket,count,sum}`
labelled `task_queue="mctl-dev-loop-implement"` is already exported by the SDK
runtime wired up in `worker.telemetry_config()` (ADR-008 D5, `#252`), and it is
the same quantity. A second exporter would mean two numbers that can disagree.
The per-attempt value is published where a per-attempt value belongs — in the
projection.

**Compute queue age in the consumer (mctl-api#331) from `describe`'s
`scheduled_time`/`last_started_time`.** Dropped as the *only* mechanism: it is
correct but leaves the number unavailable to anything that reads the heartbeat
alone (logs, tests, a future recovery path), and it pushes an arithmetic rule
into another repository and another language, which is how the four-state
vocabulary got three states in the first place. The consumer can still compute
it; the activity publishing it makes the two agree by construction.

**A dedicated Temporal schedule for admission health.** Dropped: one read every
15 minutes does not need a schedule, a workflow and an overlap policy of its
own, and `worker.setup_schedules` already documents how easily a fourth
schedule collides with the shared `mctl-gitops-main-writes` mutex windows.

## Platform impact

**Migrations.** None. No database, no gitops schema, no `.status.yaml` change —
the issue's boundary ("git is durable lifecycle and result state") is preserved
exactly.

**Backward compatibility.**
- The heartbeat detail gains keys; readers already filter to known keys
  (`argo.py:201-210`), and the new `restore()` keeps that. An older worker
  resuming an activity heartbeated by a newer one drops `version`,
  `queued_at`, `queue_age_seconds` and behaves as today.
- `ImplementExecutionState` gains a defaulted field: existing consumers of the
  `implement_execution` query keep working; queries are not part of replay.
- The `admission-health` patch marker follows the repo's convention
  (`workflow.patched`, attrition migration) and must be added to
  `docs/diagrams/archify/facts.yaml` — `tests/test_diagram_facts.py` fails
  otherwise. Note that `facts.yaml` currently lists markers under `dev_loop`;
  a reconcile-side marker needs either the same list or a new key, decided by
  what `tools/diagram_facts.py --update` produces.
- No routing, capacity, timeout or retry policy changes. The nine-approval
  regression test must pass unmodified; if it needs an edit, the change has
  overstepped.

**Resource impact.** One extra gRPC call per reconcile tick (96/day), one extra
log line per implement admission, a few dozen bytes per heartbeat. Nothing
measurable against the Argo pods.

**Risks and mitigations.**
- *A projection change breaks an in-flight resume.* Mitigated by keeping detail
  `[0]` (the workflow name resume key) untouched and by round-trip tests for
  `restore()` against today's dict shape, including the older name-only shape
  already covered at `tests/test_temporal_activities.py:318-340`.
- *`DescribeTaskQueue` is not available or is rate-limited on this Temporal
  deployment.* Mitigated by try/except at both the activity and the workflow
  call site, and by the observation gating nothing. Worst case it logs a
  failure once every 15 minutes, which is itself a finding.
- *`pollers > 1` fires on every rolling restart and is learned to be ignored.*
  Mitigated by wording the log as a rollout-aware warning and by leaving the
  alert threshold (sustained, not instantaneous) to mctl-gitops#1285, which owns
  alerting.
- *Two words for one state (`queued` vs `waiting`) leak into the consumer.*
  Mitigated by a single vocabulary module and by writing both spellings into
  `docs/runtime-state.md`; changing the wire value later is a one-line change
  in one file.
- *Scope creep toward a second reconciler.* Explicitly bounded: the health read
  returns data and logs. It cannot cancel, resubmit or reassign anything, and
  the acceptance criteria say so.
