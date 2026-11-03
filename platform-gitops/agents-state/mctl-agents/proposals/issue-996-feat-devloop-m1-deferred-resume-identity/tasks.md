# Tasks: issue-996-feat-devloop-m1-deferred-resume-identity

Commit order is test-first. The commits for T1-T5 land before the commits for tasks 1-4. Each test fails on the old code on its intended assertion, never with an import error: new constants and fields are referenced through `getattr` or with a `pytest.fail`-guarded lookup until the code commit adds them.

- [ ] 0. Write tests T1-T5 (below) in a first commit that makes no behaviour change. DoD: on the base commit `pytest tests/test_execution_request_resume.py tests/test_execution_request_dispatch.py tests/test_execution_request_replay.py` collects without errors, and exactly the new assertions fail. Record the failing-test list in the PR body as mutation evidence.
- [ ] 1. Request identity (depends on 0). Add `intent_id: int | None = None`, `expected_state_version: int = 0` and `resumed_from_execution_id: str = ""` to `ResumeDelivery` in `orchestrator/temporal/workflows/dev_loop.py`. Pass them from `Dispatcher._dispatch` in `orchestrator/temporal/dispatcher.py`. DoD: T1 passes, and existing dispatcher tests pass unchanged.
- [ ] 2. Replay-safe marker (depends on 1). Add `DEFERRED_RESUME_PATCH = "deferred-resume-contract"` and `self._deferred_resume_contract`, evaluated once in `run` immediately before `self._gates_passed = True`. Add `MergeWatchResume.deferred_resume_contract: bool = False`, carried in `_carry_work_context` and restored in `_resume_merge_watch` without re-evaluation. Add `self._last_pr`, mirrored from `_watch_pr`'s `last` and restored from `resume.last_pr`. DoD: T3 passes, and every fixture in `tests/fixtures/histories/` replays.
- [ ] 3. Validator fence and typed outcomes (depends on 2):
  - Add the gates-passed block to `_validate_execution_request` in the order given in design.md.
  - Add `RESUME_DEFERRAL_REASONS`, and add `work-merged` and `nothing-to-resume` to `xr.RESUME_REFUSAL_REASONS`.
  - Normalise deferral reasons in `TemporalClientPort.deliver`.
  - Have `_defer` audit `resume_deferred:<reason>`.

  DoD: T2 and T4 pass. A refused or deferred delivery leaves no Update-accepted event and no fulfil call.
- [ ] 4. Incomplete-contract gate (depends on 3):
  - Add `OpenDelivery.accepted_after_gates: bool = False`, set at acceptance.
  - In `_deliver`, land `Failed` with `feedback-not-ready` for such a delivery.
  - Rewrite `test_a_resume_delivered_after_the_implement_step_succeeds_at_once` to its M1 meaning: a `MergeWatchResume` with `deferred_resume_contract=False` gives `legacy-loop`, and one with `True` plus an intent gives `feedback-not-ready`. Neither mints a `we_`.

  DoD: T5 passes. No test anywhere expects `Succeeded` for a post-gates delivery.
- [ ] 5. Open the PR against `mctl-agents/main` (depends on 0-4). The PR body gives:
  - the head SHA;
  - the test-before-code commit sequence;
  - the state-transition table from design.md;
  - the mutation evidence (each of the four validator arms is reverted in turn and its test fails);
  - the replay evidence;
  - residual risks.

  Do not merge, release, or touch flags. DoD: independent review with 0 P1/P2 findings, and the PR is left for an explicit human merge decision.

## Tests
- [ ] T1. Identity and compatibility:
  - `Dispatcher._dispatch` delivers a `ResumeDelivery` whose `intent_id`, `expected_state_version` and `resumed_from_execution_id` equal the claimed `ExecutionRequest`'s, with actor, surface, kind and update id unchanged.
  - A JSON payload of the pre-M1 `ResumeDelivery` shape decodes through the Temporal default converter with the three defaults.
  - Same for a pre-M1 `MergeWatchResume` that carries an `OpenDelivery`.
- [ ] T2. Validator vocabulary: extend `test_the_validator_answers_with_the_resume_rules` with `legacy-loop` (`_gates_passed=True`, `_deferred_resume_contract=False`), `implement-running`, `work-merged`, `nothing-to-resume` (three variants: implement failed, PR CLOSED, `intent_id=None`) and `feedback-not-ready` (PR OPEN, and PR not observed). Assert the exact error type and `details`. Assert each refusal reason is in `xr.RESUME_REFUSAL_REASONS` and each deferral reason is in `RESUME_DEFERRAL_REASONS`. Assert that existing reasons keep precedence: for example, `resume-already-pending` beats `feedback-not-ready`.
- [ ] T3. Temporal replay:
  - All `tests/fixtures/histories/*.json` replay with `Replayer` without non-determinism.
  - A gates-passed history recorded without the marker replays with `_deferred_resume_contract == False`.
  - A new fixture recorded with the marker replays, and its history contains exactly one `deferred-resume-contract` marker and no other new command.
  - A continue-as-new run restores the flag from `MergeWatchResume` and records no second marker.
- [ ] T4. Pre-fulfil and idempotence, end to end with `DispatchFakeApi`:
  - A refused delivery (`work-merged`, `nothing-to-resume`) is rejected `resume_refused:<reason>` with zero fulfil calls and zero bind activities.
  - A deferred one (`implement-running`, `feedback-not-ready`, `legacy-loop`) stays claimed with zero fulfil calls.
  - Re-dispatching the same request after the state changes (for example, from implement running to PR merged) produces exactly one outcome and never two `Update accepted` events (`_accepted_updates`).
- [ ] T5. Safety, with a valid intent on an open PR while feedback processing is not implemented:
  - A loop under the marker with gates passed, PR OPEN, and a delivery with `intent_id=7` from a valid surface and actor is deferred `feedback-not-ready`. No `we_` is minted and no execution reaches `Succeeded`.
  - Injecting `OpenDelivery(accepted_after_gates=True)` directly into `_deliver` lands `Failed` with `feedback-not-ready`, never `Succeeded`.
  - Mutation check: removing the `feedback-not-ready` arm makes this test fail.

## Rollback
Revert the PR. The only persisted artefacts are the `deferred-resume-contract` marker in histories recorded after deploy, and defaulted dataclass fields. A reverted build replays such histories correctly: an unknown patch marker in history is not consulted by code that never calls `workflow.patched` for it, and the extra fields are ignored on decode. Requests left deferred are re-claimed and delivered under the old rules after rollback. No flag, release or mctl-api state needs undoing, because M1 enables none.
