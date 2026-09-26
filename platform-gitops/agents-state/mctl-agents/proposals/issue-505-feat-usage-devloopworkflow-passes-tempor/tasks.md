# Tasks: issue-505-feat-usage-devloopworkflow-passes-tempor

Order matters. Tasks 1-2 are cross-repo confirmations that can invalidate the
rest; do them before writing code. Tasks 3-6 are the mctl-agents change.

- [ ] 1. Confirm the mctl-gitops#1408 contract before writing any code: read
  `cwft-mctl-agents-implement.yaml` and `cwft-mctl-agents-shepherd.yaml` on
  mctl-gitops main and record, verbatim, which parameter names they declare in
  `arguments.parameters` and which pod env vars their run steps export. Nothing
  in mctl-agents validates CWFT parameter names (`orchestrator/validate_manifest.py`
  checks only that the template *name* exists), so this is the one string pair
  neither repo can check. — DoD: the exact parameter names and env var names
  are written into the PR description; if the templates export anything other
  than `WORKFLOW_TEMPORAL_WORKFLOW_ID` / `WORKFLOW_TEMPORAL_RUN_ID` /
  `WORKFLOW_WORK_ITEM_ID`, task 5 uses their names instead and the mismatch is
  called out in review.

- [ ] 2. Resolve the `temporal_run_id` contract question (depends on 1).
  `docs/adr/012-model-usage-cost-attribution-contract.md:143-153` does not
  declare `temporal_run_id`; lines 188-192 make `temporal_workflow_id` the join
  key. Confirm with the owner whether the run id is wanted on the record, and
  whether mctl-api's usage ingest and `validateCorrelation`
  (`internal/usage/types.go`) accept it. — DoD: a recorded decision. If yes, an
  ADR-012 amendment is drafted and mctl-api accepts the field before task 5
  merges. If no, task 5 is dropped and tasks 3/4 narrow to
  `temporal_workflow_id` + `work_item_id`, which satisfies the join ADR-012
  already defines.

- [ ] 3. Add the patch-id constant and the `_launch_correlation` helper to
  `orchestrator/temporal/workflows/dev_loop.py` (depends on 1). Put
  `LAUNCH_CORRELATION_PATCH = "launch-correlation"` beside the existing patch
  constants at `dev_loop.py:284-321`, and add the `_launch_correlation(self)`
  method returning `{}` when unpatched, and otherwise
  `temporal_workflow_id` / `temporal_run_id` from `workflow.info()` plus
  `work_item_id` only when `self._work_item_id` is truthy. Include a
  cross-repo-dependency comment modelled on `dev_loop.py:2978-2990`, naming
  mctl-gitops#1408, both CWFT filenames, and the env vars from task 1. — DoD:
  `uv run mypy .` and `uv run ruff check .` clean; the helper adds no workflow
  command other than the `patched()` marker; no other call site touched.

- [ ] 4. Wire the helper into the two submits (depends on 3). Add
  `implement_params.update(self._launch_correlation())` after
  `dev_loop.py:2996` and before the `self._implement(...)` call at
  `dev_loop.py:3017`, so the same values ride every pre-start requeue of
  `_implement`'s loop (`dev_loop.py:3359-3366`). Add
  `tick_params.update(self._launch_correlation())` in `_shepherd_tick` after
  `dev_loop.py:3693` and before the submit at `3694`. — DoD: the investigate
  submits (`dev_loop.py:2648`, `2747`), the approve submit (`2936`) and
  `ImplementSweepWorkflow` (`implement_sweep.py:168-170`) are provably
  unchanged; `git diff` touches only `dev_loop.py` in this task.

- [ ] 5. Teach the producer to read the run id (depends on 2). Add
  `("WORKFLOW_TEMPORAL_RUN_ID", "temporal_run_id")` to `_CORRELATION_ENV` at
  `orchestrator/usage_ledger.py:138-142`, and update the module docstring at
  `usage_ledger.py:51-52` so it lists four env-sourced fields instead of
  three. Do not add `WORKFLOW_EXECUTION_ID`: `execution_id` reaches a record
  through the runner's `correlate` scope (`usage_ledger.py:53-62`), and a
  second source would let the two disagree. — DoD: `from_env`
  (`usage_ledger.py:367-381`) yields `temporal_run_id` when the var is set and
  omits it when absent; ADR-012 amended in the same PR; no change to
  `run_implementer.py` or `run_shepherd.py` argparse.

- [ ] 6. Update the recorded-history content assertions for the new marker
  (depends on 3). Extend `tests/test_workflow_replay.py`'s patched-fixture
  content checks so `dev_loop_full.patched.json` is asserted to contain the
  `launch-correlation` marker, following the `exec-queue` pattern at
  `test_workflow_replay.py:299-338`. Do NOT re-record any `*.prepatch.json`:
  `tests/replay_scenarios.py:28-38` warns that re-recording silently replaces
  the only history exercising the unpatched branch while every test keeps
  passing. — DoD: the patched fixture is regenerated with
  `tools/record_workflow_history.py` and the prepatch fixtures are byte-identical
  to `main` (`git diff --stat` shows no prepatch change).

## Tests

- [ ] T1. `tests/test_dev_loop_workflow.py`: a full DevLoop run asserts the
  `submit_and_wait` input for `mctl-agents-implement` carries
  `temporal_workflow_id` and `temporal_run_id` equal to the handle's workflow id
  and run id. Assert on the recorded activity input, not on a log line.
- [ ] T2. Same file: the in-loop shepherd tick's `mctl-agents-shepherd` submit
  carries the same two values as the implement submit in the same execution.
- [ ] T3. A dispatched loop (`work_item_id` set, e.g. via the
  `tests/fixtures/histories/dev_loop_dispatched.json` scenario shape) puts
  `work_item_id` on both submits; an issue-url-only loop, where
  `self._work_item_id` is `""` (`dev_loop.py:1439`), omits the key entirely
  rather than sending `""`.
- [ ] T4. Neither submit carries an `execution_id` key — pins the deliberate
  omission argued in design.md against a later well-meaning addition.
- [ ] T5. The approve submit (`dev_loop.py:2936`) and both investigate submits
  are byte-identical to their pre-change parameter sets, including the
  continuation's `pop` of `work_item_id` / `execution_id`
  (`dev_loop.py:2744-2745`).
- [ ] T6. `tests/test_implement_sweep_replay.py` / the sweep's own workflow test:
  `ImplementSweepWorkflow`'s `SubmitAndWaitInput.params` is unchanged, pinning
  "no behaviour change for non-DevLoop submits".
- [ ] T7. `tests/test_workflow_replay.py`: `dev_loop_full.prepatch.json` and
  `dev_loop_dispatched.json` still replay green against the new code. Note in
  the test docstring that this proves only the absence of a *command* change —
  the module docstring at lines 15-46 records that an extra activity argument is
  invisible to `Replayer` on temporalio 1.31.0 — and that the real coverage of
  the unpatched branch is T8.
- [ ] T8. A `WorkflowEnvironment` test in the spirit of
  `tests/test_patch_memoization.py`: a loop whose history lacks the
  `launch-correlation` marker submits implement and shepherd with no
  correlation keys for the rest of its life, even after the marker is deployed.
  This is the only real test of the unpatched branch.
- [ ] T9. `tests/test_usage_ledger.py`: extend
  `test_correlation_comes_from_the_runner_pod_environment`
  (`test_usage_ledger.py:157-168`) so a pod environment carrying
  `WORKFLOW_TEMPORAL_RUN_ID` yields `temporal_run_id` on the record, and a pod
  without it yields a record with the field absent and no warning.
- [ ] T10. `tests/test_usage_correlation.py`: a `run_implementer` and a
  `run_shepherd` invocation under a DevLoop-shaped environment produce the
  correlation scope with all four env fields, and the same invocations with an
  empty environment record usage unchanged.
- [ ] T11. Post-deploy verification, not a unit test: after mctl-gitops#1408 is
  live, trigger one DevLoop and read the actual ingested usage records for its
  implementer and shepherd from mctl-api. A stripped parameter only logs a
  warning on the mctl-api side (`StripUndeclared`, per
  `docs/observability/execution-traces.md:205-208`), so this change can ship,
  pass every test above, and still do nothing. Also check the pod logs for the
  `ignoring undeclared operation parameters` line
  (`docs/observability/execution-traces.md:294`).

## Rollback

Three independent levers, smallest first.

1. **Neutralise without a deploy.** None available — the gate is a patch
   marker, not an env flag. If a kill switch is wanted, say so in review and
   the helper can read one instead of `patched()`; that trade is why
   alternative 2 in design.md is worth reading before merge.
2. **Revert the workflow change (tasks 3, 4, 6).** Drop the
   `_launch_correlation` calls and the constant. Because `patched()` memoises,
   loops started while the marker was deployed keep taking the patched branch
   from *history*, so after the revert the branch no longer exists in code and
   those loops replay a marker with no reader — which is exactly what
   `deprecate_patch` exists for. Prefer leaving the constant and the helper in
   place and having the helper return `{}` unconditionally: that keeps the
   marker readable, needs no `deprecate_patch`, and is a one-line change.
3. **Revert the producer change (task 5).** Remove the `_CORRELATION_ENV`
   entry. Self-contained and safe at any time: records simply stop carrying
   `temporal_run_id`, and nothing in this repo reads it back.

If a submit starts failing after mctl-api tightens `StripUndeclared` into a
rejection, lever 2 (helper returns `{}`) stops the parameters immediately for
every new loop while mctl-gitops#1408 is fixed. Already-running loops are
unaffected either way, which is the property the patch gate was chosen for.
Records already ingested are not rolled back; correlation fields are additive
and a mixed population is expected during the soak.
