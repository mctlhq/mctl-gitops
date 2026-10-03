# Finish the implementation-admission slice: name the queued state, measure queue age at the source, and watch the admission queue

## Context

Issue #395 asks that implementation work be admitted in Temporal before it is
submitted to Argo, so that a burst of approvals queues as *Scheduled
activities* instead of as Argo workflows dying on a capacity-1 mutex. The
mechanism it specifies — a third task queue `mctl-dev-loop-implement`, served
by a one-replica `--role implementation` worker whose
`max_concurrent_activities` is the implementation capacity `N` — is largely on
`main` already, shipped through #396/#397 in 1.47.0 and 1.48.0:
`IMPLEMENTATION_TASK_QUEUE` and `implementation_max_concurrent_activities()`
(`orchestrator/temporal/constants.py:64,108`), the `implementation` role
(`orchestrator/temporal/worker.py:499-536`), the routing flip behind
`workflow.patched("implement-queue")` (`orchestrator/temporal/workflows/dev_loop.py:544`),
pre-start classification and bounded requeue
(`orchestrator/temporal/implement_outcome.py`, `dev_loop.py:1087-1166`), the
D7 amendment (`docs/adr/008-worker-queue-split-and-capacity.md:191-302`), and
the nine-approval regression test
(`tests/test_dev_loop_workflow.py::TestImplementationAdmission::test_a_burst_of_approvals_is_admitted_n_at_a_time`).

What is *not* on `main` is the observability half of the same issue, and it is
the half that decides whether an operator can tell a healthy capacity wait
from a silent hang. Three states of the four the issue defines are published
(`admitted`, `submitted`, `running` — `orchestrator/temporal/activities/argo.py:102-104`);
the first one, `queued`/`waiting` with `waiting_on: implementation_capacity`,
is named nowhere in code. `queue_age` is recorded nowhere: ADR-008 D7 says
the queue's schedule-to-start latency *is* the queue age, which is true as a
per-queue histogram in VictoriaMetrics but gives no per-attempt number for the
runtime projection #389 / mctl-api#331 renders. And because the implement
submit deliberately carries no `schedule_to_start_timeout`
(`dev_loop.py:103-107`), an implementation queue that no worker polls — a
failed rollout of mctl-gitops#1285, a crash-looping pod — is indistinguishable
from a full one: both are "activities sitting Scheduled forever", and nothing
in this repo looks.

This proposal closes those three gaps inside the boundary #395 drew: git stays
durable lifecycle state, Temporal and Argo stay durable runtime state, and no
new scheduler, service or control plane is introduced.

## User stories

- AS a platform operator I WANT a loop waiting for implementation capacity to
  report `waiting` with `waiting_on: implementation_capacity` and the instant
  it started waiting SO THAT a queued proposal is visibly queued rather than
  indistinguishable from a stalled one.
- AS a platform operator I WANT the admission wait of each implement submit
  recorded as its own number, separate from execution duration SO THAT I can
  tell "capacity is tight" from "the implementer is slow" without reading two
  dashboards and doing the subtraction by hand.
- AS a platform operator I WANT to be told when the admission queue has no
  poller, or more than one SO THAT a failed worker rollout or an unnoticed
  `replicaCount` change surfaces as a warning instead of as proposals that
  never start.
- AS the runtime-projection consumer (mctl-agents#389 → mctl-api#331 →
  mctlhq/.github#95) I WANT one normative, versioned description of the
  runtime phase vocabulary and where each field comes from SO THAT the
  projection is read off a written contract rather than reverse-engineered
  from a dict literal in an activity.
- AS a reader arriving from the ADR-010 claim/fencing thread I WANT ADR-010 to
  say that worker-slot admission is the current, softer backpressure and where
  the hard count belongs SO THAT the two threads are not read as competing.

## Acceptance criteria (EARS)

Runtime states and the projection contract

- THE SYSTEM SHALL define the implementation runtime phase vocabulary —
  `waiting`, `admitted`, `submitted`, `running` — in exactly one module,
  imported by `orchestrator/temporal/activities/argo.py` and by the workflow,
  with no second spelling of any phase string anywhere in the repo.
- WHEN `submit_and_wait` publishes its runtime heartbeat detail THE SYSTEM
  SHALL include a schema version field, and SHALL keep the detail's existing
  keys (`phase`, `admitted_at`, `submitted_at`, `implementer_started_at`) and
  their meanings unchanged.
- WHEN a heartbeat detail written by a newer schema version is read back by an
  older attempt THE SYSTEM SHALL ignore keys it does not define rather than
  fail, preserving the current filtering behaviour at `argo.py:201-210`.
- WHILE an implement `submit_and_wait` activity is scheduled on
  `mctl-dev-loop-implement` and has not started THE SYSTEM SHALL make that
  state derivable as `phase=waiting, waiting_on=implementation_capacity` from
  the DevLoopWorkflow `implement_execution` query plus
  `describe_workflow_execution`'s pending-activity block, and the derivation
  rule SHALL be written down in this repository's docs.
- THE SYSTEM SHALL expose `waiting_on` on `ImplementExecutionState` as a
  constant describing what the current implement submit waits for, and SHALL
  NOT have the workflow assert whether the activity has started — that remains
  Temporal's knowledge.

Queue age

- WHEN an implement `submit_and_wait` attempt starts THE SYSTEM SHALL compute
  its admission wait from `activity.info().scheduled_time` and
  `activity.info().started_time` (both present in temporalio 1.31.0,
  `temporalio/activity.py:110-118`) and publish it as `queue_age_seconds`
  alongside `queued_at` in the runtime heartbeat detail.
- WHILE an activity is retried THE SYSTEM SHALL keep the first attempt's
  `admitted_at`, `queued_at` and `queue_age_seconds` in the restored
  projection, so that queue age never absorbs a previous attempt's execution
  time.
- WHEN an implement submit is admitted THE SYSTEM SHALL log the admission with
  the operation, the Argo-bound workflow reference once known, and the queue
  age, at INFO, in the plain-word style CONTRIBUTING.md requires.
- THE SYSTEM SHALL NOT add `schedule_to_start_timeout` or
  `schedule_to_close_timeout` to the implement submit; the admission wait
  stays unbounded by design (ADR-008 D7, `dev_loop.py:103-107`).

Admission-queue health

- WHEN `ReconcileWorkflow` runs a tick THE SYSTEM SHALL read the admission
  queue's poller count and backlog through
  `WorkflowService.DescribeTaskQueue` (`report_pollers`, `report_stats`) in an
  activity, never in workflow code.
- IF the admission queue reports zero pollers THEN THE SYSTEM SHALL log an
  error naming the queue and the backlog, and carry the observation in the
  reconcile result.
- IF the admission queue reports more than one poller THEN THE SYSTEM SHALL
  log a warning stating that capacity is `replicas x N` and that
  `replicaCount: 1` is an architectural invariant of this phase.
- IF the DescribeTaskQueue read fails THEN THE SYSTEM SHALL log the failure
  and continue the reconcile tick unchanged — admission health is an
  observation, never a gate.
- THE SYSTEM SHALL NOT fail, retry, cancel or resubmit any implementation work
  on the basis of this observation.

Documentation and regression

- THE SYSTEM SHALL add an amendment section to
  `docs/adr/010-lifecycle-ownership-contract.md` recording that worker-slot
  admission (ADR-008 D7) is this phase's backpressure, that it is not a
  distributed lease, and that the hard count across crashes and replicas
  belongs to ADR-010's server-side claims (mctl-api#337).
- WHEN nine loops are approved simultaneously with `N = 3` THE SYSTEM SHALL
  start exactly three implement submits, leave six durably scheduled with no
  submit call made for them, and drain the remaining six as slots free, with
  no manual retry — the existing regression test SHALL keep passing unchanged.
- WHEN the projection is asserted in tests THE SYSTEM SHALL show a queued loop
  reported as `waiting` and an admitted one reported with a `queue_age_seconds`
  that excludes execution time.

## Out of scope

- Per-service capacity `M` — it needs a distributed counter, which this phase
  exists to avoid.
- Lowering `EXECUTION_MAX_CONCURRENT_ACTIVITIES` from 40.
- Removing or narrowing the Argo mutex `mctl-agents-proposal-claims`
  (mctl-gitops#1283).
- The implementation worker Deployment, its `replicaCount: 1` CI guard, the
  VMRules and dashboards — mctl-gitops#1285. This proposal adds the in-cluster
  *observation* of the same invariant, not its enforcement.
- The mctl-api projection endpoint and its UI (mctl-api#331, mctlhq/.github#95).
  This proposal produces and documents the data they read.
- ADR-010 server-side claims and fencing (mctl-api#337); `ClaimClient` stays at
  rollout `off`.
- A second reconciler or any recovery behaviour (#353, mctl-api#294).
- Any change to the issue poller's cadence.

## Open questions

- The issue uses two words for the first state: `queued` in the scope list and
  `phase: waiting, waiting_on: implementation_capacity` in the projection
  sample. Proceeding with `waiting` as the wire value (it matches the concrete
  sample the consumer was specified against) and `queued_at` as the timestamp
  field name already in `ImplementExecutionState`, with both spellings recorded
  in the docs contract. If mctl-api#331 has already shipped `queued`, the alias
  is a one-line change in the vocabulary module.
- Whether mctl-api#331 reads the workflow query, the activity heartbeat, or
  both. Proceeding by publishing both and documenting precedence: the heartbeat
  detail wins wherever the two overlap, because it is written by the process
  that observes Argo.
- Whether `queue_age_seconds` should also be a Prometheus metric emitted by the
  implementation worker. Proceeding without one: the SDK already exports
  `temporal_activity_schedule_to_start_latency` labelled
  `task_queue="mctl-dev-loop-implement"`, which is the same quantity in
  aggregate, and a second exporter would be a second surface.
- Whether admission health belongs on the reconcile tick (every 15 min,
  `offset=3`) or on its own schedule. Proceeding with reconcile: it already
  holds a Temporal-client-bound activity class
  (`orchestrator/temporal/activities/visibility.py`) and adding a schedule
  would be a new moving part for one read.
- Whether zero pollers should also raise an incident rather than only log.
  Proceeding with log plus reconcile-result field; alerting on the metric is
  mctl-gitops#1285's half.
