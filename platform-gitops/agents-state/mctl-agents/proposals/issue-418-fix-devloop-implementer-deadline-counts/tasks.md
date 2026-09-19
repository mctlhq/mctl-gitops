# Tasks: issue-418-fix-devloop-implementer-deadline-counts

- [ ] 1. Add the declared Argo serialization width to
      `orchestrator/temporal/constants.py`: `ARGO_IMPLEMENT_WIDTH_ENV =
      "ARGO_IMPLEMENT_SERIALIZATION_WIDTH"`, `DEFAULT_ARGO_IMPLEMENT_WIDTH = 1`,
      `argo_implement_serialization_width()` (reusing `_int_env`), and
      `effective_implementation_capacity() -> tuple[int, int, int]` returning
      (configured N, declared width, `min(N, width)`). Leave
      `implementation_max_concurrent_activities()` unchanged as the raw reader.
      Comment the fail-closed default against the capacity-1 mutex in
      `cwft-mctl-agents-implement.yaml`. — DoD: unit tests cover unset env,
      a width above N, a width below N, and a malformed value raising
      `SystemExit` like every other `_int_env` consumer.
- [ ] 2. Use it in `orchestrator/temporal/worker.py::implementation_plan()`
      (depends on 1): poll with the effective capacity and log one line naming
      configured N, declared width and effective capacity; warn explicitly when
      the configured value was reduced, naming both settings. — DoD:
      `tests/test_worker_roles.py` asserts the `implementation` plan's
      `max_concurrent_activities` is the effective value and that the reduction
      is logged; `tests/temporal_harness.py` is updated to build its worker
      from the same helper so the tests and the worker cannot disagree.
- [ ] 3. Lower `DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` from 3 to 1
      (depends on 1) with a comment stating the rule - the default must equal
      the width the checked-in CWFT declares, and both move in the commit that
      widens Argo. — DoD: task 6's contract test passes against the current
      `cwft-mctl-agents-implement.yaml`; the PR body notes that
      `services/admins/mctl-agents-worker-implement/values.yaml` must drop to
      `"1"` (or gain `ARGO_IMPLEMENT_SERIALIZATION_WIDTH`) in the companion
      gitops PR, and that until it does the clamp makes the running worker
      behave as 1 anyway.
- [ ] 4. Add `PreStartReason` and `pre_start_reason(status_block)` to
      `orchestrator/temporal/implement_outcome.py`: `queued` when a
      never-ran `run-implementer` node carries a synchronization-lock message
      or stayed `Pending`, `unscheduled` when it never ran with no such
      evidence, `unknown` when the graph is unreadable. Pure function over the
      status block; never inferred from `startedAt` (see `_pod_ran`). — DoD:
      `tests/test_implement_outcome.py` covers the 2026-09-19 Pending-on-mutex
      node, a never-scheduled node, an empty node map and a renamed template,
      and asserts `classify` is unchanged by the addition.
- [ ] 5. Carry the reason end to end (depends on 4): `pre_start_reason` on
      `WorkflowResult` and the observation merge in
      `orchestrator/temporal/activities/argo.py`; `pre_start_reason` on
      `ImplementExecutionState`; the reason and requeue count named in
      `dev_loop._implement`'s `ImplementationNotStarted` message and in its
      requeue log line - all behind `workflow.patched("implement-prestart-reason")`.
      — DoD: `tests/test_dev_loop_workflow.py` asserts the query exposes the
      reason after a pre-start requeue and that the final error message names
      it; `tests/test_workflow_replay.py`'s capability table records the new
      marker.
- [ ] 6. Make the durable record able to say "never started" (depends on 5):
      add `outcome` and `pre_start_reason` to `ExecutionRecord` and the POST
      body in `orchestrator/temporal/activities/state.py`, populate them from
      `dev_loop._record`, and retry the POST once with the pre-existing body
      shape if mctl-api answers 4xx on the extended one. — DoD:
      `tests/test_temporal_activities.py` covers the extended body, the 4xx
      fallback landing the row, and a non-implement operation still sending an
      empty outcome; a companion mctl-api issue is opened for persisting and
      exposing both fields through `mctl_list_agent_executions`.
- [ ] 7. Add `tests/test_implement_cwft_contract.py` (depends on 3), resolving
      the CWFT through `orchestrator.validate_manifest.GITOPS_CWFT_DIR` so it
      honours `MCTL_GITOPS_ROOT` and actually runs in
      `.github/workflows/pr-validation.yml` - not
      `tests/test_agent_inventory.py`'s sibling-only path, which skips in CI.
      Error on a missing checkout under CI, warn locally, following
      `validate_manifest._gitops_missing`. — DoD: the three assertions in
      design.md section 3 pass against today's template and each fails with a
      message naming both repositories when fed a mutated copy.
- [ ] 8. Update ADR-008 D7 and ADR-010's non-goals note (depends on 3): record
      that the coupling between admission N and Argo's serialization width is
      now enforced rather than expected, name the env var and the contract
      test, and state that widening the mutex requires moving both numbers in
      one change. — DoD: `tests/test_diagram_facts.py` /
      `tools/diagram_facts.py` still pass; no diagram fact drifts.
- [ ] 9. Open the companion mctl-gitops issue for the `assert-attempt` start
      marker described in design.md (per-attempt `optional: true` artifact at a
      parameter-keyed S3 key, a distinct exit code and a
      `workflow_never_started:implement:*` fingerprint), noting the canary
      needed to confirm Argo resolves that key for a skipped step. — DoD: the
      issue links back to #418 and to the `run-implementer` deadline invariant
      that task 7 now pins.

## Tests

- [ ] T1. Rewrite `tests/test_dev_loop_workflow.py::TestImplementationAdmission::
      test_a_burst_of_approvals_is_admitted_n_at_a_time` as
      `test_the_2026_09_19_burst_completes_every_item`: nine approvals released
      at once against a submit fake that models BOTH gates - Temporal admission
      (the worker's effective capacity) and an inner Argo gate of
      `argo_implement_serialization_width()` which, when an item cannot enter
      within its simulated deadline, returns a `pre_start` result instead of a
      success. Assert every loop completes, no result is `pre_start`, the peak
      occupancy of the inner Argo gate never exceeds the declared width, and
      the number of Argo submits equals the number of approvals. Pin it to the
      burst in the docstring. — This test must fail on `main` (N=3, width 1:
      two of every three submits enter the Argo gate and are killed) and pass
      after tasks 1-3.
- [ ] T2. `tests/test_worker_roles.py`: the `implementation` plan's capacity is
      `min(N, width)` for N>width, N<width and N==width, and the clamp is
      logged once with both numbers.
- [ ] T3. `tests/test_implement_outcome.py`: `pre_start_reason` answers
      `queued` for the Pending-on-mutex node shape, `unscheduled` for a
      never-placed pod, `unknown` for an absent or renamed graph; and never
      answers `queued` for a node that only has `startedAt`.
- [ ] T4. `tests/test_temporal_activities.py`: an implement submit whose graph
      shows a queued kill produces `implementer_ran is False` and
      `pre_start_reason == "queued"` on `WorkflowResult`, and the heartbeat
      never reports phase `running` for it (extending the existing
      `test_a_deadline_killed_pending_node_is_not_a_run`).
- [ ] T5. `tests/test_temporal_activities.py`: `record_execution` posts
      `outcome`/`pre_start_reason`, and still records the row when the first
      POST is refused with 400.
- [ ] T6. `tests/test_implement_cwft_contract.py` (task 7): template-level
      deadline present on `run-implementer`; spec deadline at least one full
      drain of the declared width; declared width at least the checked-in
      default N. Each assertion additionally exercised against an in-memory
      mutated template so a green run cannot be a vacuous one.
- [ ] T7. `tests/test_dev_loop_workflow.py`: an execution whose history
      predates `implement-prestart-reason` still replays
      (`tests/test_workflow_replay.py`), and the unpatched branch reports the
      same `ImplementationNotStarted` it did before.

## Rollback

Revert the mctl-agents release. Nothing persistent is created: no migration, no
gitops write, no `.status.yaml` transition is introduced by this change, and
the two new execution-record fields are additive and ignorable. The workflow
change sits behind `workflow.patched("implement-prestart-reason")`, so loops
started under the new release keep replaying their recorded branch and loops
started before it never took it.

Partial rollbacks, in increasing order of preference:

1. Set `ARGO_IMPLEMENT_SERIALIZATION_WIDTH` on the implement worker to the
   value that restores the previous admission behaviour (3). This un-does only
   the clamp, instantly, from a values file, and restores exactly the
   2026-09-19 exposure - use it only to prove the clamp is what changed.
2. Revert task 3 alone (default N back to 3) if the contract test is found to
   be reading the CWFT wrongly; the clamp still protects the worker because the
   width default is 1.
3. Full revert if the pre-start classification is found to answer `queued` for
   runs that actually executed - that would be a wrong durable record, which is
   worse than no record. `classify` is untouched by this change, so requeue
   behaviour is unaffected either way, but the incorrect field must not stand.

The companion mctl-gitops and mctl-api changes are independently revertible and
neither is required for this one to be correct.
