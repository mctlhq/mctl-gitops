# Design: issue-991-feat-devloop-pass-execution-id-to-the-im

## Current state
All references are `orchestrator/temporal/workflows/dev_loop.py` unless noted.

- Canonical execution. `_run_loop` sets `self._canonical = workflow.patched(CANONICAL_APPROVAL_PATCH)`
  (~:3537). A dispatched loop pins `self._canonical_execution = dispatched.execution_id` (~:3553); any other
  canonical loop calls `_ensure_canonical_execution` (~:3342). `_canonical_execution_id()` (~:2391) returns it;
  its docstring says "the grant, the run token and the flip must all name this one".
- Investigate submit (the reference). ~:3605-3617: when `dispatched is not None or self._canonical_open`,
  `investigate_params["execution_id"] = dispatched.execution_id if dispatched is not None else
  self._canonical_execution_id()`.
- Canonical end. `_end_canonical_execution(phase)` (~:3488) advances the `we_` through
  `_advance_dispatched_execution` once; its docstring: held non-terminal "because mctl-api only binds an `aar_`
  to, mints a run token for, and resolves an approve to a NON-TERMINAL execution; it ends right after the approve
  flip". The flip-site call is ~:4157-4160 (`if self._canonical: await self._end_canonical_execution(
  self._canonical_end_phase or "Failed")`), with `_canonical_end_phase` set from the investigator's result
  (~:3663, ~:3815). `run` (~:3449-3486) ends it again on every exit if still open (`_canonical_open`), using
  `_canonical_pending_phase` when an earlier advance did not land.
- Implement submit. ~:4194-4205 builds `implement_params` (`service`, `slug`, `agent_image`, `agent_version`)
  and `update(self._launch_correlation())`. `_launch_correlation` (~:4586-4607) is gated on
  `LAUNCH_CORRELATION_PATCH` and returns `temporal_workflow_id`, `temporal_run_id`, `work_item_id`; it is also
  used for the shepherd tick (~:4970-4971). After the after-flip re-approval gate (~:4216-4231) the loop calls
  `self._implement(...)` (~:4236), whose pre-start requeue loop reuses the same params.
- After-flip re-approval. `_await_canonical_reapproval(after_flip=True)` (~:2505-2522) waits for a resume to
  open a NEW execution (`opened()`), then requests the grant on `self._executions[-1].execution_id`.
- Runner side. `orchestrator/run_implementer.py` ~:6012-6034: `EXECUTION_ID_ENV = "WORKFLOW_EXECUTION_ID"`;
  `_setup_run_token` exits 2 under `enforce` if empty, else `run_token.setup(shadow_scope="implement")`.
  `orchestrator/run_token.py` notes a token "ends with its run, by expiry or its execution turning terminal".
- Tests. `tests/test_dev_loop_workflow.py::test_neither_submit_carries_an_execution_id` (~:5409-5446) asserts
  `"execution_id" not in implement_log[0]` and `not in shepherd_log[0]`. Replay harness:
  `tests/test_workflow_replay.py`, `tests/replay_scenarios.py` (scenario `dev_loop_full` driven by
  `_fake_activities`), fixtures `tests/fixtures/histories/dev_loop_*.json`; patch memoisation in
  `tests/test_patch_memoization.py`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`: declares parameter
  `execution_id` (default ""), maps it to env `WORKFLOW_EXECUTION_ID` (~:848), sets `MCTL_RUN_TOKEN_MODE=observe`
  (~:785) and `MCTL_RUN_TOKEN_SA_TOKEN_FILE`. No gitops change is needed.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker{,-exec,-implement}/values.yaml`: all at image tag
  `1.117.0` (tenant `admins`).
- Not checked: the live Argo Workflows `mctl-agents-implement-21260455` / `-55052262` cited in the issue and the
  mctl-api side (`internal/k8s/agent_run_binding.go`); no live-cluster or mctl-api source read was made in this
  run. The issue's statement about them is taken as reported, not observed.

## Proposed solution
One new marker, `IMPLEMENT_EXECUTION_PATCH = "implement-execution-id"`, declared beside
`LAUNCH_CORRELATION_PATCH` with a comment in the same style (why, migration by attrition).

1. Decide once, at the flip site (~:4157). Replace the unconditional canonical end with:
   ```
   if self._canonical:
       self._hold_canonical_for_implement = workflow.patched(IMPLEMENT_EXECUTION_PATCH)
       if not self._hold_canonical_for_implement:
           await self._end_canonical_execution(self._canonical_end_phase or "Failed")
   ```
   Placement matters: in a pre-patch history the next command at this point is the advance activity; replaying
   with no marker makes `patched()` return False and schedules exactly that. A new history records the marker
   instead and no advance here. `self._hold_canonical_for_implement` is initialised False in `__init__`.
2. Add the id to the implement params only (~:4205), never to `_launch_correlation`, so the shepherd tick is
   untouched:
   ```
   if self._hold_canonical_for_implement:
       execution_id = self._canonical_execution_id()
       if not execution_id:
           raise ApplicationError("implement run has no canonical execution to bind its run token to",
                                  type=IMPLEMENT_EXECUTION_MISSING_ERROR_TYPE, non_retryable=True)
       implement_params["execution_id"] = execution_id
   ```
   Source: `_canonical_execution_id()` is `dispatched.execution_id` for a dispatched canonical loop and the
   ensured `we_` otherwise, i.e. the investigate source. The raise goes through `run`'s exception path, which
   ends the still-open `we_` as Failed. Because the dict is built before `_implement`'s requeue loop, every
   requeued attempt carries the same id.
3. End after the implement (~:4236, right after `_implement` returns, before the abandon check):
   ```
   if self._hold_canonical_for_implement:
       self._canonical_end_phase = "Succeeded" if implement_result.succeeded else "Failed"
       await self._end_canonical_execution(self._canonical_end_phase)
   ```
   If the advance does not land, `_canonical_pending_phase` keeps it and the existing `run` exit retries, as for
   the flip today. Exits between the flip and this point are already covered by `run`'s two end calls.
4. After-flip re-approval under the marker (see Open questions). With the `we_` still open, a resume cannot
   attach a new execution, so `after_flip=True` waiting for `opened()` would only expire. Under the marker pass
   `after_flip=False` binding semantics (grant requested on the canonical `we_`, `execution_id=""`) to
   `_await_canonical_reapproval`; it is only reached when a transition cleared the decision. The implementer
   verifies this against the fake activities and keeps it behind the same marker (no extra command shape for
   old histories).
5. Docstrings: update `_end_canonical_execution` and `_canonical_execution_id` to say the `we_` is held
   through the implement run under the marker.

## Alternatives
- Mint or reuse a separate execution for the implement run (e.g. a new `we_` attached as
  `(argo, mctl-agents-implement-...)`). Rejected by the resolved clarification (option a) and by the issue
  ("never a newly invented value").
- Add `execution_id` inside `_launch_correlation`. Rejected: it also feeds the shepherd tick, which the issue
  puts out of scope, and is memoised under `LAUNCH_CORRELATION_PATCH`, whose recorded histories must not change.
- Only add the param, keep ending the `we_` at the flip. Rejected: the exchange would bind to a terminal
  execution and mctl-api would refuse it; observe would show a refusal instead of the proof.

## Platform impact
- Migration/back-compat: migration by attrition. Running loops whose history passed the flip without the marker
  keep the old sequence for their whole life (merge watch included); only loops reaching the flip after deploy
  record it. No gitops or schema change; the CWFT already declares the parameter.
- Behaviour: the canonical `we_` stays Running for the implement duration (typically 1-10 min, bounded by the
  implement step timeout). During that window mctl-api refuses a new execution for the item
  (`execution_active`); dispatcher reconciliation of closed loops is unaffected because the loop is running.
  The end phase now reflects the implement outcome instead of the investigator's.
- Risks: (1) non-determinism if the marker is placed anywhere other than the flip site - mitigated by the
  replay tests below; (2) a stuck `we_` if the post-implement advance never lands - mitigated by the existing
  pending-phase retry in `run`; (3) after-flip resume semantics change - tested and recorded.
- Resource impact: none (one marker, no new activity type; the advance activity moves position).
- Release order: this slice -> release -> worker deploy -> first real DevLoop implement as S5 observe proof.
  Sweep/manual paths remain without `execution_id` and are not masked.
