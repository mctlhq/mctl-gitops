# Tasks: issue-418-fix-devloop-implementer-deadline-counts

- [ ] 1. Mirror the CWFT lock facts in `orchestrator/temporal/constants.py`: add
      `ARGO_IMPLEMENT_MUTEX_NAME = "mctl-agents-proposal-claims"`,
      `ARGO_IMPLEMENT_MUTEX_TEMPLATE = "run-implementer"`,
      `ARGO_IMPLEMENT_MUTEX_WIDTH = 1`, and `argo_admission_width()` returning the
      width while the mirror names `implement_outcome.IMPLEMENTER_TEMPLATE` and
      `None` otherwise — DoD: comments state that these mirror
      `cwft-mctl-agents-implement.yaml` in mctl-gitops and that task 3's check is
      what keeps the mirror honest; `uv run ruff check orchestrator` and
      `uv run mypy` pass; no import cycle introduced (`constants.py` may import
      `implement_outcome`, which imports nothing from `constants`).

- [ ] 2. Bind N to the ceiling (depends on 1): make
      `implementation_max_concurrent_activities()` raise `SystemExit` when N
      exceeds `argo_admission_width()`, naming N, the mutex, the guarded template
      and mctl-agents#418; lower `DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES`
      to `ARGO_IMPLEMENT_MUTEX_WIDTH` — DoD: `worker_plans("implementation")` and
      `worker_plans("all")` refuse a too-large `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES`,
      while `worker_plans("control")` and `worker_plans("execution")` still build
      unaffected (the lazy `implementation_plan()` in
      `orchestrator/temporal/worker.py` already guarantees this — assert it).

- [ ] 3. Add `check_implement_admission_is_safe()` to
      `orchestrator/validate_manifest.py` (depends on 1), beside
      `_check_cluster_workflow_template`, reusing `GITOPS_CWFT_DIR` and
      `_gitops_missing`. It loads `cwft-mctl-agents-implement.yaml`, accepts both
      `synchronization.mutex` and `synchronization.mutexes[]`, and errors when the
      guarded template is not `ARGO_IMPLEMENT_MUTEX_TEMPLATE`, when the mutex is
      absent while the mirror names a template, when the guarded template's
      `activeDeadlineSeconds` exceeds `MAX_LOCKED_STEP_DEADLINE_SECONDS` (1800), or
      when `run-implementer` carries no `activeDeadlineSeconds` — DoD: wired into
      `validate()`/`main()`; every error message names the file and both values; a
      no-match never reads as a pass.

- [ ] 4. Add `PreStartReason` to `orchestrator/temporal/implement_outcome.py`
      (`"lock_wait" | "unscheduled" | "unknown"`), a `_lock_waiting(node)` helper
      reading `synchronizationStatus.waiting` first and falling back to a
      `message` matching `Mutex/` or `Lock status:`, a
      `pre_start_reason: PreStartReason | None` field on `ImplementerObservation`,
      and a `pre_start_reason()` renderer that maps `None` to `"unknown"` — DoD:
      the reason is set only where `ran is False`; an unreadable or empty node graph
      yields `None`, never `"unscheduled"`; `_pod_ran`'s refusal of `startedAt` is
      untouched.

- [ ] 5. Carry the reason through `orchestrator/temporal/activities/argo.py`
      (depends on 4): make `lock_wait` sticky in `_merge_observations` the same way
      `ran=True` is sticky, and add `pre_start_reason: str | None = None` to
      `WorkflowResult`, populated from the folded `best` observation — DoD: a
      mid-flight poll showing "Lock status: 0/1" survives a terminal poll whose node
      message is gone; the field defaults so an older recorded payload still
      deserializes.

- [ ] 6. Surface the reason in `orchestrator/temporal/workflows/dev_loop.py`
      (depends on 5): add `pre_start_reason` to `ImplementExecutionState`, include it
      in `_implement`'s requeue warning and in the `ImplementationNotStarted`
      message — DoD: the `implement_execution` query shows it live; the error type
      set (`ImplementationNotStarted` / `ImplementationFailed` /
      `ImplementationFinalizationFailed`) is unchanged.

- [ ] 7. Persist it (depends on 5): add `outcome: str = ""` and
      `pre_start_reason: str = ""` to `ExecutionRecord` in
      `orchestrator/temporal/activities/state.py`, posted in the
      `/api/v1/agents/executions` body only when non-empty; pass both from `_record`
      in `dev_loop.py` — DoD: a `pre_start` implement that never held the lock is
      distinguishable in the durable record from one that ran and produced nothing;
      `_record`'s best-effort try/except is untouched.

- [ ] 8. Verify mctl-api tolerates the two new fields (depends on 7) — DoD: either a
      confirmed 2xx against `POST /api/v1/agents/executions` with the fields present,
      or a filed mctl-api follow-up issue linked from the code comment, with the
      fields still sent (the write is best-effort by design).

- [ ] 9. Amend ADR-008 D7 in place in
      `docs/adr/008-worker-queue-split-and-capacity.md` with a
      `> **Amended <date> (mctlhq/mctl-agents#418).**` blockquote recording that N is
      now bound to the mutex width in code, that the binding is checked in CI against
      the CWFT, and that the ceiling lifts when the mutex moves off `run-implementer`
      — DoD: no new ADR file; the existing D7 prose about "expected to be at least N"
      is corrected rather than left contradicting the code.

- [ ] 10. Open the mctl-gitops PR moving `synchronization.mutex:
      mctl-agents-proposal-claims` off `run-implementer` onto `commit-and-push` in
      `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`
      — DoD: PR open and linked from mctl-agents#418; it states that mctl-agents CI
      will go red on merge until task 11 lands, by design.

- [ ] 11. After task 10 merges: flip `ARGO_IMPLEMENT_MUTEX_TEMPLATE` to
      `"commit-and-push"` and restore `DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES`
      to 3 (depends on 2, 3, 10) — DoD: a one-line-plus-one-line commit; the task-3
      check passes against the merged CWFT; `argo_admission_width()` returns `None`
      so N is no longer capped.

## Tests

- [ ] T1. `tests/test_implement_outcome.py`: the six 2026-09-19 node shapes.
      A `Failed` `run-implementer` node with `synchronizationStatus.waiting` and no
      pod marks is `pre_start` + `lock_wait`; the same node with only the
      "Waiting for argo-workflows/Mutex/mctl-agents-proposal-claims. Lock status: 0/1"
      message is also `lock_wait`; a `Failed` node with no pod and no lock mark is
      `unscheduled`; a missing and an empty node map are both `unknown`; a node with
      `hostNodeName` reports no reason at all.

- [ ] T2. `tests/test_temporal_activities.py`: `_merge_observations` keeps
      `lock_wait` when a later poll's node graph has lost the message, and
      `implementer_ran=True` from any poll still clears the reason.

- [ ] T3. `tests/test_temporal_activities.py`, extending
      `TestSubmitAndWaitObservesTheImplementer`: a submit whose mid-flight poll shows
      the lock wait and whose terminal poll shows `Failed` returns
      `implementer_ran is False`, `pre_start_reason == "lock_wait"`,
      `implementer_started_at is None`, and no heartbeat whose phase is `running`.

- [ ] T4. Burst regression, `tests/test_dev_loop_workflow.py`: replay the
      00:12-00:31Z shape — six approvals released within the burst window against a
      fake mctl-api that enforces Argo mutex width 1 and kills any implement node
      still queued after its `activeDeadlineSeconds`. Using `tests/temporal_harness.py`
      (which mirrors production N on the implementation queue), assert every loop
      completes with a successful implement, that no `WorkflowResult` reports
      `pre_start`, and that the fake never sees more than `argo_admission_width()`
      Argo implement workflows in flight at once. This is the acceptance criterion
      "no run is killed before it has executed".

- [ ] T5. `tests/test_worker_roles.py`: `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES=3`
      while the mirror names `run-implementer` makes `worker_plans("implementation")`
      raise `SystemExit` naming both numbers; `worker_plans("control")` and
      `worker_plans("execution")` still build; with the mirror on `commit-and-push`,
      N=3 is accepted.

- [ ] T6. `tests/test_manifest.py`: a fixture CWFT with the mutex on
      `run-implementer` alongside a 7200 s deadline produces an error naming the
      template; one with the mutex on `commit-and-push` produces none; a CWFT with
      the mutex removed entirely while the mirror still names a template errors; and
      an absent `GITOPS_CWFT_DIR` is a skip locally and an error under `CI` —
      mirroring `test_a_missing_gitops_checkout_fails_under_ci`.

- [ ] T7. `tests/test_workflow_replay.py` passes unchanged against the existing
      `tests/fixtures/histories/*.prepatch.json`. DoD: the fixtures are NOT
      re-recorded (see `tests/replay_scenarios.py`'s rule); if replay goes red, the
      `_record` payload change is gated behind
      `workflow.patched("implement-prestart-reason")` and a new pre-patch history is
      recorded only for the new marker, never over an old one.

- [ ] T8. Full gate: `uv run pytest tests/`, `uv run ruff check orchestrator config
      tests`, `uv run mypy` all green, both with and without `MCTL_GITOPS_ROOT` set.

## Rollback

Every step is independently revertible and none of them changes durable data.

- **Tasks 1-2 (the ceiling).** Break-glass without a code revert: the refusal only
  fires when N exceeds the width, so setting `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES=1`
  in `platform-gitops/services/admins/mctl-agents-worker-implement/values.yaml` is a
  values edit that always satisfies it. To restore the old permissiveness, revert the
  `SystemExit` branch; `DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` back to 3 is
  a one-line revert.
- **Task 3 (the CI check).** Revert the call from `validate()`; the helper can stay
  dead. It gates PRs only — nothing in production reads it.
- **Tasks 4-7 (the reason).** All fields are optional with defaults. Reverting them
  leaves older records carrying a `pre_start_reason` mctl-api simply stops receiving;
  no reader breaks, because `classify`'s verdict never depended on the reason.
- **Task 10 (the gitops move).** `git revert` in mctl-gitops puts the mutex back on
  `run-implementer`; ArgoCD reconciles the CWFT on the next sync. Task 11 must be
  reverted in this repo in the same window, or the implementation worker will run at
  N=3 against a width-1 mutex — which is the original bug. Pair the two reverts, and
  note that the task-3 check turns the mismatch red rather than silent.
- **Worst case.** Revert tasks 1-11 and the system is byte-for-byte where it is
  today: admission at N=3, the mutex on `run-implementer`, and `pre_start` requeues
  absorbing the losses. Nothing here is one-way.
