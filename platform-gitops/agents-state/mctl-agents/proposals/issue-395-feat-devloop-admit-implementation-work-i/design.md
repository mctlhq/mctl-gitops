# Design: issue-395-feat-devloop-admit-implementation-work-i

## Current state

### The admission mechanism is already on `main`

This clone is at `c6b7df7` (merge of PR #398). Everything #395 describes as "the
mechanism" exists:

- **The queue.** `orchestrator/temporal/constants.py:64` defines
  `IMPLEMENTATION_TASK_QUEUE = "mctl-dev-loop-implement"`, with
  `IMPLEMENTATION_OPERATION = "mctl-agents-implement"` at `:68`, and capacity read
  from the environment at `:104-109`:
  `IMPLEMENTATION_CAPACITY_ENV = "IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES"`,
  `DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES = 3`,
  `implementation_max_concurrent_activities()`. `_int_env` (`:71-87`) turns a
  malformed or sub-1 value into a `SystemExit` rather than a worker that admits
  nothing.
- **The worker.** `orchestrator/temporal/worker.py:360` has
  `ROLES = ("all", "control", "execution", "implementation")`. `worker_plans`
  (`:434-536`) builds the implementation plan lazily (`:495-505`) so a bad `N`
  only refuses the role that needs it, and `all` keeps the limit (`:523-536`) so
  collapsing the deployments is not a silent removal of capacity.
- **The routing.** `orchestrator/temporal/workflows/dev_loop.py:544-552` routes the
  implement submit to the admission queue behind `workflow.patched("implement-queue")`,
  nested inside the `exec-queue` funnel at `:553-561`. Migration is by attrition.
- **The two clocks.** `_run_cwft` schedules `submit_and_wait` with
  `start_to_close_timeout` only. `dev_loop.py:104-107` records why there is
  deliberately no `schedule_to_start_timeout`: on this queue the schedule-to-start
  wait *is* the admission queue, and bounding it would turn waiting for capacity
  into a failure.
- **The runtime phases.** `orchestrator/temporal/activities/argo.py:102-104` defines
  `PHASE_ADMITTED` / `PHASE_SUBMITTED` / `PHASE_RUNNING`, published as the second
  heartbeat detail (`:246`, `:281`) with `admitted_at` taken from
  `activity.info().started_time` (`:186-192`) and `running` set only when a pod is
  observed to have run (`:324-337`). A resumed attempt restores the prior
  projection rather than rebuilding it (`:193-210`).
- **Attempt semantics.** `orchestrator/temporal/implement_outcome.py` classifies
  `pre_start` / `execution` / `finalization` / `success`, with unknown deliberately
  mapping to `execution` (`:164-167`). `dev_loop._implement` (`:1087-1165`) requeues
  `pre_start` up to `MAX_PRESTART_REQUEUES = 3` with a `PRESTART_REQUEUE_BACKOFF` of
  two minutes, and raises a typed non-retryable `ApplicationError` otherwise.
- **The DoD test.** `tests/test_dev_loop_workflow.py:4013-4051` approves nine loops
  at `N = 3` and asserts exactly three submits ever enter the activity function,
  `gate.peak == n`, and all nine drain unaided. It is real slot enforcement because
  `tests/temporal_harness.py:90-103` builds an actual SDK worker on
  `IMPLEMENTATION_TASK_QUEUE` with the production `max_concurrent_activities`.
- **The decision record.** ADR-008 carries D7 (`docs/adr/008-worker-queue-split-and-capacity.md:191-256`)
  and ADR-010 carries the matching Non-goals amendment (`:557-568`).

### What is missing

**1. Queue age does not survive the run.** ADR-008 D7 asserts that "the
schedule-to-start latency on this queue is, by construction, the queue age" — true,
but that is a Prometheus histogram, an aggregate keyed on `task_queue`, not a
per-attempt fact. Per attempt the wait is observable only while the step is live,
as a join of two perishable surfaces: `ImplementExecutionState.queued_at`
(`dev_loop.py:781`) from the workflow query, and `admitted_at` from
`heartbeat_details[1]`, which Temporal discards when the activity completes.
`WorkflowResult` (`argo.py:73-90`) returns `started_at`/`finished_at` for the *Argo*
workflow but no admission instant, and `ExecutionRecord`
(`orchestrator/temporal/activities/state.py:29-43`) carries no timing at all. So
scope item 5 — "`queue_age` recorded separately from execution duration" — is
satisfied live and in aggregate, and not at all after the fact. `queue_age` and
`waiting_on` appear zero times in `orchestrator/` and `tests/`.

**2. `N` is invisible in logs.** `worker.py:593-597` logs
`worker starting: role=%s task_queues=%s`. The one number that defines admission
is never printed, so reconstructing what capacity a since-deleted pod imposed means
reading a gitops values file at the right commit.

**3. Capacity and queue names are not drift-checked.** `tools/diagram_facts.py`'s
`facts_from_code` (`:110-182`) reads `worker.py` for `facts["schedules"]` and
`facts["workflows"]`, and `dev_loop.py` for timeouts and patched markers — but
reads `constants.py` not at all. `docs/diagrams/archify/facts.yaml` therefore has
no `task_queues` and no capacity entry, and changing
`DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` produces no drift report.

**4. The diagrams still show one queue.** `docs/temporal-flow.md:21` already reads
`queues=mctl-dev-loop / -exec / -implement`, but `docs/diagrams/temporal-flow-overview.mmd:7`
still reads `queue=mctl-dev-loop`, and `docs/diagrams/archify/dev-loop.workflow.json`
contains no occurrence of "queue", "admit", "capacity" or "mutex" at all. The
picture of the dev loop goes straight from approval to the implementer.

**5. A stale test docstring.** `tests/test_worker_roles.py:89-91` says control and
execution run unbounded under `all`; `worker.py:528-536` reuses the same
`execution_plan` object, which carries `max_concurrent_activities=40`. Only control
is unbounded. No assertion depends on the false half, so it is documentation rot
rather than a defect — but it is documentation rot about capacity, in the file that
is meant to pin capacity.

## Proposed solution

Four changes, each independently releasable, none introducing a component.

### A. Return the admission instant, derive the queue age in the workflow

Add one optional field to `WorkflowResult` in `argo.py`:

```python
    # When a worker slot took this activity — activity.info().started_time,
    # the instant schedule-to-start ended. None on results recorded before
    # this field existed, exactly like implementer_ran above.
    admitted_at: str | None = None
```

It is populated from the `runtime` dict the activity already builds
(`argo.py:189`), so no new source of truth appears; the value returned at
`argo.py:340-349` is the same one the heartbeat has been publishing. Because the
dataclass is deserialised from history on replay, an older recorded result simply
defaults to `None` — the same compatibility shape `implementer_ran` uses and the
reason its comment at `argo.py:80-82` exists.

`ImplementExecutionState` (`dev_loop.py:766-785`) then gains three fields:

```python
    # The queue this step's submit is routed to, and what it waits on there.
    # Static declarations, not liveness: whether the activity is STILL
    # Scheduled stays Temporal's answer via describe_workflow_execution.
    task_queue: str = ""
    waiting_on: str = ""
    # Admission wait of the CURRENT attempt, and of every attempt so far.
    # Disjoint from execution duration by construction: both ends of the
    # span are before the activity started.
    queue_age_seconds: float | None = None
    total_queue_age_seconds: float = 0.0
```

`_implement` (`dev_loop.py:1112-1120`) sets `task_queue` and `waiting_on` when it
builds the state, and after `_run_cwft` returns it folds
`admitted_at - queued_at` into `queue_age_seconds` and adds it to the running total
before classification. A requeue resets `queued_at` as it does today, so
`queue_age_seconds` always describes the current attempt while
`total_queue_age_seconds` survives the reset. An absent or unparseable
`admitted_at` leaves `queue_age_seconds` at `None` and adds nothing to the total:
unknown is not zero.

Both numbers are then in Temporal history for as long as the namespace retains it,
readable by `handle.query(DevLoopWorkflow.implement_execution)` after the step has
ended — which is the thing that does not exist today. The same numbers go into the
step's completion log line and into the terminal `ApplicationError` message
(`dev_loop.py:1146-1164`), so an implementation that failed after a long wait says
so in the text a human reads first.

This is the minimal honest reading of scope item 5. It does not move runtime state
into git, it does not add a metric exporter of our own, and it does not require
mctl-api to change.

### B. Log the capacity the process actually imposed

In `main()` (`worker.py:593-597`), extend the startup line to name each plan's slot
limit, and emit one additional line when a plan serves `IMPLEMENTATION_TASK_QUEUE`
stating `N`, that capacity is `replicas x N`, and that the deployment is pinned to
one replica (mctl-gitops#1285). Read `N` off the already-built `WorkerPlan`, never
by calling `implementation_max_concurrent_activities()` again — calling it in
`main` would re-read the environment in every role and reintroduce exactly the
cross-role startup refusal the lazy plan at `worker.py:495-505` exists to prevent.

### C. Make capacity and queue names drift-checked

Extend `facts_from_code` (`tools/diagram_facts.py:110`) to read
`orchestrator/temporal/constants.py` through the existing `_grep` helper and record:

```yaml
task_queues:
  control: mctl-dev-loop
  execution: mctl-dev-loop-exec
  implementation: mctl-dev-loop-implement
capacity:
  control_max_concurrent_activities: '100'
  execution_max_concurrent_activities: '40'
  implementation_max_concurrent_activities_default: '3'
  implementation_capacity_env: IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES
```

then regenerate `docs/diagrams/archify/facts.yaml` with
`tools/diagram_facts.py --update`. The flattening and diff machinery
(`_flatten` at `:183`, `diff_facts` at `:192`) already handles nested dicts, so no
change is needed there. After this, moving `N` or renaming a queue without
regenerating facts is reported as drift by the same check that already guards
timeouts and patched markers.

This is the closest mctl-agents can get to scope item 2's "`replicaCount: 1`
enforced": the replica count lives in another repo and only that repo's CI can fail
on it, but the number it multiplies becomes auditable here.

### D. Bring the diagrams up to the three-queue reality

- `docs/diagrams/temporal-flow-overview.mmd:7`: change the subgraph label to
  `queues=mctl-dev-loop / -exec / -implement`, matching `docs/temporal-flow.md:21`,
  and show the implement submit entering through the admission queue.
- `docs/diagrams/temporal-flow-states.mmd`: add `Approve -> Queued -> Admitted ->
  Implement`, with a note that `Queued` consumes no execution deadline and that a
  `pre_start` outcome returns to `Queued` without counting an attempt.
- `docs/diagrams/archify/dev-loop.workflow.json`: add an admission node between
  approval and the implementer submit. This file is validated by
  `.github/workflows/diagrams.yml` against archify's composition checks, so the
  node placement must keep the lane layout free of crossing edges and label
  collisions; if it cannot, the overview and states diagrams still carry the change
  and the archify update becomes its own PR.

### E. Small correctness repairs found on the way

- `tests/test_worker_roles.py:89-91`: correct the docstring — under `all`, control
  is unbounded and execution keeps 40.
- `tests/test_dev_loop_workflow.py:4023-4024`: the burst test asserts
  `implementation_max_concurrent_activities() == 3` against the ambient
  environment. A developer with `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` exported
  fails the DoD test for a reason that has nothing to do with the DoD. Pin `N = 3`
  for the test explicitly (monkeypatched env, before the harness builds its
  workers) and keep the assertion as a guard that the pin took.

## Alternatives

**1. Put `queue_age_seconds` on `ExecutionRecord` and POST it to mctl-api.**
This is where the number arguably belongs: `record_execution`
(`activities/state.py:48`) already writes the per-step audit trail that
`mctl_list_recent_agent_runs` reads, and queue age beside `argo_workflow_name` and
`phase` would answer the incident question directly from the platform API. Dropped
as the first move because it needs an mctl-api schema and endpoint change, which
makes an otherwise self-contained change cross-repo and couples it to mctl-api#331's
release. The workflow-query form lands now and does not preclude it; the field name
is chosen to be liftable verbatim. Recorded as a follow-up, not as a rejection.

**2. Publish a custom Prometheus metric from the orchestrator.** A histogram of
admission wait per service, exported from the worker, would make queue age a
dashboard rather than a query. Dropped: the repo has no custom metrics today (only
the SDK's, per `worker.py:399-431`), and the aggregate answer already exists as
`temporal_activity_schedule_to_start_latency{task_queue="mctl-dev-loop-implement"}`.
Adding a parallel exporter would give two numbers that can disagree, for a question
the existing one already answers in aggregate. What is missing is the *per-attempt,
after-the-fact* number, and a histogram is the wrong shape for that.

**3. Have the workflow itself decide whether the activity is still waiting, and
expose a `phase: waiting` from the query.** This would give #389 a single surface
to read instead of a join. Dropped because `ImplementExecutionState`'s docstring
(`dev_loop.py:768-774`) rules it out for a good reason: the workflow cannot observe
its own activity's dispatch, so any `waiting` it reported would be a guess that
drifts from `describe_workflow_execution`'s pending-activity truth, and two
runtime-state surfaces that disagree are worse than one that is incomplete. The
design takes the narrower step — declare *what* the step waits on
(`waiting_on = "implementation_capacity"`, `task_queue = IMPLEMENTATION_TASK_QUEUE`)
and let Temporal keep answering *whether* it still is.

**4. Add `schedule_to_start_timeout` so a starved queue surfaces as a failure.**
Rejected upstream by ADR-008 D7 (`:225-231`) and by `dev_loop.py:104-107`, and
restated here only to record that it was considered: bounding the admission wait
converts backpressure back into the loss mode of 2026-09-19. The alert belongs on
the schedule-to-start histogram in mctl-gitops, not on the activity.

## Platform impact

**Migrations.** None. No schema, no gitops file, no CWFT. `WorkflowResult` and
`ImplementExecutionState` gain optional fields with defaults.

**Backward compatibility.** Two replay surfaces are touched and both are additive:

- `WorkflowResult.admitted_at` defaults to `None`, so an activity result recorded
  before this change deserialises cleanly. This is the pattern already proven by
  `implementer_ran` / `implementer_phase` / `finalization_phase`
  (`argo.py:79-86`).
- `ImplementExecutionState` is a query return type, not a history record; a running
  workflow on old code answers the old shape and a caller must tolerate missing
  fields. That is already true of every field added to it.
- No new `workflow.patched` marker is needed: nothing in this change alters the
  sequence, arity or ordering of commands the workflow issues. The queue-age
  computation is pure arithmetic on values the workflow already holds, executed
  between two existing commands. This is the one claim in this design that must be
  verified rather than assumed — see the replay test in `tasks.md`.

**Resource impact.** Negligible. Two floats and two strings per workflow, one extra
log line per worker start, four extra facts in the drift report.

**Risks and mitigations.**

- *Replay divergence.* The whole risk of touching `dev_loop.py`. Mitigated by
  running `tests/test_workflow_replay.py` against the recorded histories in
  `tests/replay_scenarios.py` and `tests/fixtures/`, and by adding no command to
  the workflow. If replay does diverge, the computation moves behind a new
  `implement-queue-age` marker — cheap, and the attrition cost is one loop
  lifetime.
- *Timestamp parsing.* `queued_at` is written by `workflow.now().isoformat()` with
  `+00:00` replaced by `Z` (`dev_loop.py:1116`), `admitted_at` by `argo._iso`
  (`:157-169`), which produces the same spelling for exactly this reason. The
  subtraction must still fail soft to `None` rather than raise inside the workflow,
  where an unhandled `ValueError` would fail the loop over a cosmetic field.
- *Drift facts becoming noisy.* Recording the *default* `N` rather than the
  deployed `N` means the fact is stable while production capacity is tuned in
  mctl-gitops. That is deliberate: this repo can only speak for its own defaults,
  and a fact that tracked a value it cannot see would report drift it cannot
  explain. Called out in `requirements.md`'s open questions.
- *Archify composition failure.* `.github/workflows/diagrams.yml` validates
  `docs/diagrams/archify/**` on PR. If the admission node cannot be placed without
  a crossing edge, the archify change is split out rather than forced; the mermaid
  diagrams and `docs/temporal-flow.md` already carry the substance.
- *What this still does not guarantee.* Unchanged from ADR-008 D7 and restated so
  no reader infers otherwise: `N` is a per-process limit, capacity is
  `replicas x N`, and a worker that dies after submitting leaves Argo running while
  the slot is released. The contract stays "under normal worker operation no more
  than `N` implementation submissions are actively supervised, and queued DevLoops
  submit no Argo work at all". The hard count belongs to ADR-010's server-side
  claims (mctl-api#337), and the Argo mutex stays until every production submit path
  goes through admission.
