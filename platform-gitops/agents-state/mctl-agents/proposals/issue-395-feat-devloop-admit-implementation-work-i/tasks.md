# Tasks: issue-395-feat-devloop-admit-implementation-work-i

- [ ] 1. Add `orchestrator/temporal/runtime_projection.py`: `PROJECTION_VERSION`,
      `PHASE_WAITING/ADMITTED/SUBMITTED/RUNNING`,
      `WAITING_ON_IMPLEMENTATION_CAPACITY`, the frozen `RuntimeProjection`
      dataclass, `to_detail()` and `restore(detail, *, fallback)` —
      DoD: pure module, no Temporal or httpx imports, `uv run mypy` clean, and
      `restore()` reproduces today's behaviour at
      `activities/argo.py:201-210` (unknown keys dropped, missing detail falls
      back, resume floors the phase at `submitted`).
- [ ] 2. Move the phase strings in `orchestrator/temporal/activities/argo.py`
      to imports from the new module, keeping `PHASE_ADMITTED`,
      `PHASE_SUBMITTED`, `PHASE_RUNNING` as re-exports for one release
      (depends on 1) — DoD: no phase string literal remains in `argo.py`;
      `grep -rn '"admitted"\|"submitted"\|"running"' orchestrator/` returns
      only the vocabulary module.
- [ ] 3. Measure queue age in `submit_and_wait` from
      `activity.info().scheduled_time` and `.started_time`, publish
      `queued_at`, `queue_age_seconds` and `version` in the runtime detail, and
      log `info: admitted <operation> after <n>s in queue` (depends on 1, 2) —
      DoD: a first attempt publishes a queue age equal to start minus schedule;
      a resumed attempt republishes the ORIGINAL `queued_at`, `admitted_at` and
      `queue_age_seconds` from the restored detail; detail `[0]` is still the
      workflow name.
- [ ] 4. Add `waiting_on` to `ImplementExecutionState`
      (`workflows/dev_loop.py:766-784`), set to
      `WAITING_ON_IMPLEMENTATION_CAPACITY` whenever `stage == "implementer"`,
      defaulted to `""` (depends on 1) — DoD: the `implement_execution` query
      returns it; the workflow still makes no claim about whether the activity
      started; no patch marker needed (queries are not replayed).
- [ ] 5. Write `docs/runtime-state.md`: the four-state vocabulary, the field
      table (which value comes from the query, which from the heartbeat, which
      from `describe_workflow_execution`), the precedence rule (heartbeat wins),
      the `queued`/`waiting` alias note, and the derivation rule for
      `phase=waiting, waiting_on=implementation_capacity` (depends on 1, 3, 4)
      — DoD: a reader of mctl-api#331 can implement the projection from this
      page alone; linked from ADR-008 D7.
- [ ] 6. Add `AdmissionQueueHealth` and
      `VisibilityActivities.describe_admission_queue` in
      `orchestrator/temporal/activities/visibility.py`, using
      `client.workflow_service.describe_task_queue` with `report_pollers=True`
      and `report_stats=True` against `IMPLEMENTATION_TASK_QUEUE` — DoD:
      returns pollers, backlog, `N` and a `healthy` flag; logs `error:` at zero
      pollers, `warn:` above one with the `replicas x N` explanation, `info:`
      otherwise; raises nothing the caller cannot catch.
- [ ] 7. Register the activity on the control plan in
      `orchestrator/temporal/worker.py` `short_activities` and call it once per
      `ReconcileWorkflow` tick behind `workflow.patched("admission-health")`,
      inside try/except, carrying the result on `ReconcileWorkflowResult`
      (depends on 6) — DoD: a raising or slow read leaves the tick's behaviour
      and result otherwise unchanged; the observation gates nothing.
- [ ] 8. Update `docs/diagrams/archify/facts.yaml` via
      `uv run python tools/diagram_facts.py --update` for the new patch marker
      (depends on 7) — DoD: `uv run pytest tests/test_diagram_facts.py` green.
- [ ] 9. Amend `docs/adr/010-lifecycle-ownership-contract.md` with a section
      after §13: admission lives in ADR-008 D7; worker slots are backpressure,
      not a lease; the hard count across crashes and replicas is ADR-010's
      server-side claim (mctl-api#337), whose `ClaimClient`
      (`orchestrator/lifecycle/claim.py`) targets endpoints mctl-api does not
      serve yet, so rollout is `off` — DoD: no decision is restated in two
      ADRs; D7 gains the reciprocal link.
- [ ] 10. Update ADR-008 D7's projection paragraph (`:295-302`) to name
      `queue_age_seconds`, `waiting_on` and `docs/runtime-state.md` (depends on
      3, 4, 5) — DoD: D7 and the code agree on the field list.

## Tests

- [ ] T1. `tests/test_runtime_projection.py`: `to_detail()`/`restore()`
      round trip; an unknown key from a future version is dropped; the legacy
      name-only heartbeat shape still resumes; `restore()` floors a resumed
      projection at `submitted`.
- [ ] T2. `tests/test_temporal_activities.py`: a first attempt of
      `submit_and_wait` publishes `queue_age_seconds` equal to
      `started_time - scheduled_time`; extend the existing resume test at
      `:318-340` to assert `queued_at`, `admitted_at` and `queue_age_seconds`
      survive the retry unchanged — i.e. queue age never absorbs the previous
      attempt's execution time.
- [ ] T3. `tests/test_dev_loop_workflow.py`: with the admission pool held full,
      a queued loop's `implement_execution` query reports
      `stage="implementer"`, a `queued_at`, and
      `waiting_on="implementation_capacity"`; after the gate opens the same
      loop reports `outcome="success"`.
- [ ] T4. `tests/test_dev_loop_workflow.py::TestImplementationAdmission::test_a_burst_of_approvals_is_admitted_n_at_a_time`
      passes UNMODIFIED — nine approvals, `N = 3`, three submits, six with no
      submit call, all nine draining with no intervention. Any edit to this
      test means the change overstepped.
- [ ] T5. `tests/test_workflow_replay.py` unchanged and green: the implement
      submit still carries no `scheduleToStartTimeout` and no
      `scheduleToCloseTimeout`, and is still the only submit on the admission
      queue.
- [ ] T6. `tests/test_visibility_admission.py`: a faked `workflow_service`
      returning zero / one / three pollers produces the error / info / warning
      classification, the backlog is carried through, and a raising stub is
      surfaced as a caught failure rather than an exception escaping the tick.
- [ ] T7. `tests/test_reconcile_workflow.py`: an unpatched history replays
      without the health read; a patched tick records the health result; a
      failing health activity leaves the tick's other results identical.
- [ ] T8. `uv run pytest tests/`, `uv run ruff check orchestrator config tests`
      and `uv run mypy` all green (pr-validation.yml runs the three).

## Rollback

Nothing here changes routing, capacity, timeouts or retry policy, so rollback
is layered and cheap:

1. **The admission-health read** — revert task 7 (or ship a follow-up that
   deletes the call site). Executions that recorded `admission-health` replay
   the marker as present, so the branch must survive until those ticks end;
   reconcile ticks are minutes long, so attrition is same-day. The activity
   gates nothing, so leaving it registered and uncalled is also a valid stop.
2. **The queue-age and projection fields** — revert tasks 1-3. The only
   external reader is mctl-api#331; older keys are unchanged, so a consumer
   written against them keeps working, and a consumer written against
   `queue_age_seconds` degrades to computing it from `describe`'s
   `scheduled_time`/`last_started_time`. In-flight activities whose restored
   detail carries unknown keys have those keys dropped by the existing filter.
3. **`waiting_on`** — revert task 4. A defaulted dataclass field; no history,
   no replay, no marker.
4. **Docs** — tasks 5, 9, 10 are text; revert freely.

If the underlying admission mechanism itself must be rolled back — which this
proposal does not touch — the documented target is unchanged: set
`WORKER_ROLE=all` (one process polling all three queues, capacity `N` still
applied on the admission queue, `worker.py:524-536`) or move `N` via
`IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` in the values file. Reverting the
`implement-queue` routing in code is NOT a rollback for executions that already
recorded the marker; those keep their routing for life by attrition.
