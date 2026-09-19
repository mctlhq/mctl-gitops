# Close out Temporal admission of implementation work: durable queue age, capacity visibility, and drift guards

## Context

Issue #395 asks that implementation work be admitted in Temporal before it
reaches Argo: a dedicated task queue whose slot limit *is* the implementation
capacity `N`, so that a burst of approvals queues as Scheduled activities in
Temporal rather than as nine Argo workflows racing a capacity-1 mutex and dying
of a workflow-level `activeDeadlineSeconds`.

Most of that mechanism is already on `main` in this clone. `IMPLEMENTATION_TASK_QUEUE`
(`orchestrator/temporal/constants.py:64`), the `--role implementation` worker plan
(`orchestrator/temporal/worker.py:497-505`), the routing branch behind
`workflow.patched("implement-queue")` (`orchestrator/temporal/workflows/dev_loop.py:544-552`),
the `admitted`/`submitted`/`running` runtime projection in
`orchestrator/temporal/activities/argo.py:102-104`, the `pre_start` classifier
(`orchestrator/temporal/implement_outcome.py`), the requeue loop
(`dev_loop.py:1087-1165`) and the nine-approval regression test
(`tests/test_dev_loop_workflow.py:4013-4051`) all exist. ADR-008 carries D7 and
ADR-010 carries the matching amendment in its Non-goals section.

What is *not* done is the part of #395's scope that survives the run. Scope item 5
says "`queue_age` recorded separately from execution duration": today the admission
wait is observable only twice, and both are perishable. Live, it is a join of
`DevLoopWorkflow.implement_execution`'s `queued_at` (`dev_loop.py:781`) with the
pending activity's heartbeat; in aggregate, it is the SDK's
`temporal_activity_schedule_to_start_latency` histogram keyed on `task_queue`.
Neither gives a per-attempt number once the step ends: `WorkflowResult`
(`argo.py:73-90`) carries no `admitted_at`, `ExecutionRecord`
(`orchestrator/temporal/activities/state.py:29-43`) carries no timing at all, and
the activity's heartbeat details are gone the moment it completes. So the very
question the 2026-09-19 incident review will be asked — "how long did these
proposals wait for capacity, and was any of that charged to the execution budget"
— cannot be answered after the fact from anything this repo writes down.

Three smaller residues sit beside it. `N` is the one number that defines admission
and it is absent from the worker's startup log (`worker.py:593-597` logs role and
queue names only). `tools/diagram_facts.py`'s `facts_from_code` reads `worker.py`
for schedules and workflow classes but records neither the task-queue names nor
the capacity default, so `docs/diagrams/archify/facts.yaml` cannot report drift if
someone changes `DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES`. And the
diagrams still describe a single queue: `docs/diagrams/temporal-flow-overview.mmd:7`
reads `queue=mctl-dev-loop` while `docs/temporal-flow.md:21` was already updated to
`queues=mctl-dev-loop / -exec / -implement`, and `docs/diagrams/archify/dev-loop.workflow.json`
contains no admission node at all.

## User stories

- AS a platform operator reviewing an implementation incident I WANT the admission
  wait of each implement attempt recorded durably SO THAT I can prove, after the
  run has ended, that waiting for capacity did not consume the execution budget.
- AS an on-call engineer reading a worker's logs I WANT the implementation capacity
  `N` stated at startup SO THAT I can tell what capacity that process actually
  imposed without reading the environment of a pod that may already be gone.
- AS the runtime-projection consumer (mctl-agents#389 to mctl-api#331) I WANT the
  orchestrator to declare which queue the implement step waits on and why SO THAT
  I can render `phase: waiting, waiting_on: implementation_capacity` without
  hard-coding a reason string or inventing a second runtime-state surface.
- AS a reviewer of a future change to capacity or queue naming I WANT the diagram
  drift report to fail SO THAT `N` and the queue split cannot move silently.
- AS a reader of the architecture diagrams I WANT the three task queues and the
  admission gate drawn SO THAT the pictures agree with `docs/temporal-flow.md` and
  ADR-008 D7.

## Acceptance criteria (EARS)

### Durable queue age

- WHEN `submit_and_wait` returns a terminal `WorkflowResult` THE SYSTEM SHALL
  include `admitted_at`, the ISO-8601 UTC instant at which a worker slot took the
  activity, spelled through the existing `_iso` helper (`argo.py:157-169`).
- WHEN a `WorkflowResult` is deserialised from a history recorded before
  `admitted_at` existed THE SYSTEM SHALL default it to `None` and SHALL NOT fail
  replay, in the same manner as `implementer_ran` (`argo.py:83`).
- WHEN the implement step's submit returns THE SYSTEM SHALL compute
  `queue_age_seconds` as `admitted_at - queued_at` and record it on
  `ImplementExecutionState` alongside the existing `queued_at` and
  `prestart_requeues`.
- WHEN a pre-start requeue resets `queued_at` (`dev_loop.py:1113-1118`) THE SYSTEM
  SHALL keep a running `total_queue_age_seconds` across every attempt of the step,
  so the reset does not erase the waiting already observed.
- WHILE an implement attempt is executing THE SYSTEM SHALL keep `queue_age_seconds`
  disjoint from execution duration: the recorded value SHALL cover only the span
  from scheduling to admission and SHALL NOT include any time after the activity
  started.
- IF `admitted_at` is absent or unparseable THEN THE SYSTEM SHALL leave
  `queue_age_seconds` as `None` and SHALL NOT substitute zero, because an unknown
  wait and a zero wait are different answers.
- WHEN the implement step completes or fails THE SYSTEM SHALL emit one log line
  naming the Argo workflow, the outcome, `queue_age_seconds` and
  `prestart_requeues`, and the terminal `ApplicationError` message for a non-success
  outcome SHALL carry the queue age.

### Capacity visibility

- WHEN a worker starts with a plan that serves `IMPLEMENTATION_TASK_QUEUE` THE
  SYSTEM SHALL log the queue name and its `max_concurrent_activities`, together
  with a statement that capacity is `replicas x N` and that the deployment is
  pinned to one replica.
- WHILE a worker serves no implementation plan THE SYSTEM SHALL NOT read
  `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES`, preserving the existing rule that a
  malformed value only refuses the role that needs it
  (`worker.py:496-505`, `constants.py:96-101`).
- WHEN the orchestrator declares the implement step's waiting surface THE SYSTEM
  SHALL expose, on `ImplementExecutionState`, the task queue the submit is routed
  to and a static `waiting_on` reason of `implementation_capacity`.
- WHILE the implement submit has not yet been admitted THE SYSTEM SHALL NOT assert
  liveness from the workflow query: whether the activity is still Scheduled remains
  Temporal's answer via `describe_workflow_execution`, and the query SHALL only say
  what the step waits on, never whether it is still waiting.

### Drift guards and diagrams

- WHEN `tools/diagram_facts.py` builds facts from code THE SYSTEM SHALL record the
  three task-queue names, the execution slot limit, and the implementation capacity
  default from `orchestrator/temporal/constants.py`.
- IF a change alters a task-queue name or `DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES`
  without regenerating `docs/diagrams/archify/facts.yaml` THEN the diagram drift
  check SHALL report it.
- WHEN the overview diagram is read THE SYSTEM SHALL name all three queues, matching
  `docs/temporal-flow.md:21`.
- WHEN `docs/diagrams/archify/dev-loop.workflow.json` is read THE SYSTEM SHALL show
  admission between approval and Argo submission, and SHALL continue to pass the
  archify composition checks run by `.github/workflows/diagrams.yml`.

### Regression coverage

- WHEN nine DevLoops are approved simultaneously with `N = 3` THE SYSTEM SHALL start
  exactly three implement activities, SHALL leave six durably Scheduled with no
  submit call made for them, and SHALL drain the remaining six with no intervention
  as slots free — the existing
  `test_a_burst_of_approvals_is_admitted_n_at_a_time` contract, which SHALL continue
  to pass.
- WHEN that burst test runs THE SYSTEM SHALL pin `N = 3` explicitly for the test
  rather than asserting that the ambient environment happens to leave the default in
  place (`tests/test_dev_loop_workflow.py:4023-4024`).
- WHEN a pre-start requeue occurs THE SYSTEM SHALL show, in a test, that the second
  attempt's `queue_age_seconds` measures only the second wait while
  `total_queue_age_seconds` covers both.
- WHEN an existing recorded history is replayed against the changed workflow code
  THE SYSTEM SHALL replay without a non-determinism error
  (`tests/test_workflow_replay.py`, `tests/replay_scenarios.py`).

## Out of scope

- Per-service capacity `M`. It needs a distributed counter, which is the thing this
  phase exists to avoid (ADR-008 Non-goals; #395 states it explicitly).
- Lowering `EXECUTION_MAX_CONCURRENT_ACTIVITIES` from 40. Investigate, reconcile and
  incidents stay independent of implementation capacity.
- Removing the Argo mutex `mctl-agents-proposal-claims`. The admin-only direct
  `mctl_trigger_implementer` path and the `cronworkflow-mctl-agents-implement`
  five-minute cron (`docs/diagrams/archify/facts.yaml:25`) both bypass Temporal
  admission, so the mutex still guards a real path.
- Adding `schedule_to_start_timeout` or `schedule_to_close_timeout` to the implement
  submit. Bounding the admission wait would turn waiting for capacity into a failure
  — the shape of the bug being fixed (`dev_loop.py:104-107`).
- The mctl-gitops deployment, `replicaCount: 1` CI guard, queue-age alert and
  dashboards. Those are mctlhq/mctl-gitops#1285 and #1287; this repo can make `N`
  auditable and loggable but cannot fail another repo's CI.
- The mctl-api side of the runtime projection (mctl-api#331) and the schema in
  mctlhq/.github#95. This proposal only makes the producer side complete.
- ADR-010's server-side claim and fencing (mctl-api#337). `ClaimClient`
  (`orchestrator/lifecycle/claim.py`) stays at rollout `off`.
- A second reconciler, and any change to `commit-and-push` or to what reaches git
  mid-attempt. Git remains durable lifecycle state; Temporal and Argo remain durable
  runtime state.
- Writing a new ADR. ADR-008 D7 and the ADR-010 Non-goals amendment already record
  this decision; this proposal amends wording only where a new field needs naming.

## Open questions

- **Where the durable queue age should ultimately live.** This proposal keeps it in
  Temporal (workflow query state plus the activity's return value), which is
  self-contained and needs no cross-repo change. Extending `ExecutionRecord`
  (`activities/state.py:29-43`) with `queue_age_seconds` would put it in mctl-api's
  execution audit trail where `mctl_list_recent_agent_runs` could read it, but that
  needs an mctl-api schema change. Proceeding with the in-repo form and recording
  the mctl-api extension as a follow-up.
- **Whether `waiting_on` belongs on the query at all.** `ImplementExecutionState`'s
  docstring (`dev_loop.py:768-774`) deliberately refuses to model liveness. This
  proposal reads that as a prohibition on *guessing whether* the step is waiting,
  not on *declaring what* it waits on, and adds only the static reason and the queue
  name. If a reviewer disagrees, drop that one field; nothing else depends on it.
- **The archify diagram's shape.** `dev-loop.workflow.json` has no queue concept
  today, so where the admission gate sits in its lane layout is an authoring choice
  that must still satisfy the composition checks (no crossing edges, no label
  collisions). Proceeding with a gate node between approval and the implement
  submit; the renderer decides whether that survives.
- **Whether N is still 3 in production.** `DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES = 3`
  is the code default, but the live value comes from the mctl-gitops values file,
  which is not in this clone. The drift fact records the default, not the deployed
  value.
