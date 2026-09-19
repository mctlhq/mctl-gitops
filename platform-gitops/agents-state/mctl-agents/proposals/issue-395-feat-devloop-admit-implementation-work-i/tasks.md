# Tasks: issue-395-feat-devloop-admit-implementation-work-i

Ordered so each numbered task is independently reviewable. Tasks 1-3 are the
durable queue age, 4 is capacity visibility, 5-6 are drift guards, 7-8 are the
diagrams, 9 is cleanup. Nothing here changes the admission mechanism itself,
which is already on `main`.

- [ ] 1. Return the admission instant from `submit_and_wait` — add
  `admitted_at: str | None = None` to `WorkflowResult`
  (`orchestrator/temporal/activities/argo.py:73-90`) and populate it at the
  terminal return (`:340-349`) from the `runtime` dict the activity already
  builds (`:186-192`), so no second source of truth appears. Document the
  `None` default as the pre-existing-history case, in the same terms as
  `implementer_ran` at `:79-86`. — DoD: a terminal result for an implement
  submit carries the same instant the heartbeat published; a `WorkflowResult`
  constructed without the field still builds; `uv run mypy` clean.

- [ ] 2. Widen `ImplementExecutionState` (depends on 1) — add `task_queue`,
  `waiting_on`, `queue_age_seconds: float | None` and
  `total_queue_age_seconds: float` to the dataclass at
  `orchestrator/temporal/workflows/dev_loop.py:766-785`, with comments stating
  that `task_queue`/`waiting_on` are static declarations and not liveness
  claims — whether the activity is still Scheduled stays
  `describe_workflow_execution`'s answer, per the existing docstring at
  `:768-774`. — DoD: the `implement_execution` query
  (`dev_loop.py:829-832`) returns the widened shape; existing callers and
  tests that read `stage`/`queued_at`/`prestart_requeues`/`outcome` are
  unchanged.

- [ ] 3. Compute and record the queue age in `_implement` (depends on 1, 2) —
  in `dev_loop._implement` (`:1087-1165`) set `task_queue=IMPLEMENTATION_TASK_QUEUE`
  and `waiting_on="implementation_capacity"` when the state is built
  (`:1113-1118`); after `_run_cwft` returns, fold `admitted_at - queued_at`
  into `queue_age_seconds` and add it to `total_queue_age_seconds` before
  classification. A requeue resets `queued_at` as today, so the per-attempt
  value describes the current attempt and the total survives the reset. Parse
  failures and a `None` `admitted_at` leave `queue_age_seconds` at `None` and
  add nothing — unknown is not zero, and the subtraction must never raise
  inside the workflow. Include both numbers in the step's completion log line
  and in the terminal `ApplicationError` message (`:1146-1164`). — DoD: after
  the implement step ends, `handle.query(DevLoopWorkflow.implement_execution)`
  reports a queue age that covers only scheduling-to-admission; no new
  `workflow.patched` marker is introduced; T5 passes.

- [ ] 4. Log the capacity the process imposes — extend the startup line at
  `orchestrator/temporal/worker.py:593-597` to name each plan's slot limit, and
  emit one further line when a plan serves `IMPLEMENTATION_TASK_QUEUE` stating
  `N`, that capacity is `replicas x N`, and that the deployment is pinned to one
  replica (mctl-gitops#1285). Read `N` off the already-built `WorkerPlan` —
  never by calling `implementation_max_concurrent_activities()` again, which
  would re-read the environment in every role and undo the lazy-plan isolation
  at `:495-505`. — DoD: `--role implementation` logs its `N`; `--role control`
  and `--role execution` log their limits and do not touch
  `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES`; T6 passes.

- [ ] 5. Teach the drift report about queues and capacity — extend
  `facts_from_code` (`tools/diagram_facts.py:110-182`) to read
  `orchestrator/temporal/constants.py` via the existing `_grep` helper and emit
  `facts["task_queues"]` (control / execution / implementation) and
  `facts["capacity"]` (`CONTROL_MAX_CONCURRENT_ACTIVITIES`,
  `EXECUTION_MAX_CONCURRENT_ACTIVITIES`,
  `DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES`,
  `IMPLEMENTATION_CAPACITY_ENV`). `_flatten` (`:183`) and `diff_facts` (`:192`)
  already handle nested dicts. — DoD: `tools/diagram_facts.py` run without
  `--update` reports drift when any of those five values is edited in
  `constants.py`.

- [ ] 6. Regenerate the recorded facts (depends on 5) — run
  `tools/diagram_facts.py --update` and commit the resulting
  `docs/diagrams/archify/facts.yaml` with the new `task_queues` and `capacity`
  blocks. — DoD: `tests/test_diagram_facts.py` passes; a fresh run reports no
  drift.

- [ ] 7. Correct the mermaid diagrams — `docs/diagrams/temporal-flow-overview.mmd:7`
  currently reads `queue=mctl-dev-loop`; change it to
  `queues=mctl-dev-loop / -exec / -implement`, matching
  `docs/temporal-flow.md:21`, and route the implement submit through the
  admission queue. In `docs/diagrams/temporal-flow-states.mmd` add
  `Approve -> Queued -> Admitted -> Implement` with a note that `Queued`
  consumes no execution deadline and that a `pre_start` outcome returns to
  `Queued` without counting an attempt. — DoD: no diagram in `docs/diagrams/`
  describes a single task queue; the states diagram shows admission as a state
  distinct from execution.

- [ ] 8. Add admission to the archify dev-loop diagram (depends on 7) — place an
  admission gate node between approval and the implementer submit in
  `docs/diagrams/archify/dev-loop.workflow.json`, which today contains no
  occurrence of "queue", "admit" or "capacity". — DoD:
  `.github/workflows/diagrams.yml` passes archify's composition checks (no
  crossing edges, no label collisions, readable at 1440px). If the node cannot
  be placed without a composition failure, split this task into its own PR and
  ship 1-7 without it — the substance is already in tasks 6 and 7.

- [ ] 9. Two small repairs found while reading — (a) correct the stale docstring
  at `tests/test_worker_roles.py:89-91`, which says control and execution run
  unbounded under `all`; `worker.py:528-536` reuses `execution_plan`, so
  execution keeps 40 and only control is unbounded. (b) In
  `tests/test_dev_loop_workflow.py:4023-4024` the DoD test asserts
  `implementation_max_concurrent_activities() == 3` against the ambient
  environment, so a developer with `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES`
  exported fails the DoD test for an unrelated reason. Pin `N = 3` explicitly
  (monkeypatched env, set before `tests/temporal_harness.py` builds its
  workers at `:90-103`) and keep the assertion as a guard that the pin took. —
  DoD: the burst test passes with an arbitrary `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES`
  exported in the shell; no docstring in `tests/test_worker_roles.py` claims an
  unbounded execution plan.

## Tests

- [ ] T1. `submit_and_wait` returns `admitted_at` equal to
  `activity.info().started_time`, in the same `Z`-suffixed spelling `_iso`
  produces — extends `tests/test_temporal_activities.py`, beside the existing
  projection tests at `:317-345`.

- [ ] T2. A `WorkflowResult` deserialised without `admitted_at` (an older
  recorded shape) defaults it to `None` and the workflow then reports
  `queue_age_seconds is None` — not `0.0`.

- [ ] T3. Queue age is disjoint from execution duration: with a fake
  `submit_and_wait` that is admitted after a measurable delay and then runs for
  a measurably longer one, `queue_age_seconds` covers only the first span.

- [ ] T4. A pre-start requeue resets the per-attempt wait and accumulates the
  total: after one requeue, `queue_age_seconds` measures only the second wait
  while `total_queue_age_seconds` covers both. Extends
  `test_a_pre_start_failure_is_requeued_without_an_attempt`
  (`tests/test_dev_loop_workflow.py:4053-4074`), which already asserts
  `prestart_requeues == 1`.

- [ ] T5. `tests/test_workflow_replay.py` replays every history in
  `tests/replay_scenarios.py` and `tests/fixtures/` against the changed
  `dev_loop.py` with no non-determinism error. This is the gate on the design's
  one unverified claim — that no new `workflow.patched` marker is needed. If it
  fails, the queue-age computation goes behind an `implement-queue-age` marker
  and T5 is re-run.

- [ ] T6. A worker started with `--role implementation` logs its `N`; a worker
  started with `--role control` logs its limits and never reads
  `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` (assert via a poisoned env value
  that would `SystemExit` if read) — extends `tests/test_worker_roles.py`,
  beside `test_implementation_capacity_is_read_from_the_environment` at `:132`.

- [ ] T7. The existing DoD regression stays green and stays meaningful:
  `test_a_burst_of_approvals_is_admitted_n_at_a_time`
  (`tests/test_dev_loop_workflow.py:4013-4051`) — nine approvals at `N = 3`,
  exactly three submits entered, `gate.peak == n`, all nine drain unaided, and
  `seen["mctl-agents-implement"] == [IMPLEMENTATION_TASK_QUEUE] * 9`. With task
  9(b) applied it must also pass with a conflicting value exported.

- [ ] T8. Drift: editing `DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` or
  a task-queue name in `constants.py` without regenerating
  `docs/diagrams/archify/facts.yaml` is reported by
  `tests/test_diagram_facts.py`.

- [ ] T9. Whole suite and static checks, per `CONTRIBUTING.md`:
  `uv run pytest tests/`, `uv run ruff check orchestrator config tests tools`,
  `uv run mypy`.

## Rollback

Each task reverts independently; nothing here is one-way.

- **Tasks 1-3 (queue age).** Revert the commit. `admitted_at` and the four
  `ImplementExecutionState` fields are additive with defaults, no new patched
  marker is introduced, and no command sequence changes — so a revert is
  replay-safe in both directions and a workflow mid-flight at the revert simply
  stops recording the numbers. Any consumer reading the query must already
  tolerate missing fields. If T5 forces an `implement-queue-age` marker instead,
  the revert becomes attrition-bound like every other marker in
  `dev_loop.py`: histories that recorded it keep the branch until they end, at
  most one `MERGE_WATCH_DEADLINE`.
- **Task 4 (logging).** Revert; log-only, no behaviour.
- **Tasks 5-6 (drift facts).** Revert `tools/diagram_facts.py` and re-run
  `--update`. The facts file is a record, not a control — a stale one reports
  drift, it does not block a deploy.
- **Tasks 7-8 (diagrams).** Revert the files. `.github/workflows/diagrams.yml`
  renders from `main`; no PNG or HTML is committed, so there is nothing to
  clean up.
- **Task 9 (test repairs).** Revert.

Nothing in this proposal touches the admission mechanism, the Argo mutex
`mctl-agents-proposal-claims`, `EXECUTION_MAX_CONCURRENT_ACTIVITIES`, the
`implement-queue` or `implement-outcome` markers, or the mctl-gitops deployment.
A full revert of every task leaves admission working exactly as it does on
`c6b7df7` today — it only removes the after-the-fact evidence of how long
anything waited.
