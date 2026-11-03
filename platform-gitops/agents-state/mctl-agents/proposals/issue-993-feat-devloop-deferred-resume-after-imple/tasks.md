# Tasks: issue-993-feat-devloop-deferred-resume-after-imple

Order rule (owner decision 6): the new regression and end-to-end tests (T1-T9) are committed first and
fail against the old behaviour. Only then is behaviour implemented. Existing expectations (task 10) are
rewritten last.

- [ ] 1. Write the new tests T1-T9 against the current code and confirm they fail for the right reason —
  DoD: the tests are in a commit before any behaviour change; each fails on main / #992 with an assertion about
  the contract, not an import error.
- [ ] 2. Request identity: add defaulted `intent_id`, `expected_state_version`, `resumed_from_execution_id` to
  `ResumeDelivery` (`orchestrator/temporal/workflows/dev_loop.py`), and fill them in `Dispatcher._dispatch`
  (`orchestrator/temporal/dispatcher.py`) (depends on 1) — DoD: T1 passes; old payload fixtures still decode.
- [ ] 3. Add `DEFERRED_RESUME_PATCH` and the carried state (`_deferred_contract`, `_implement_running`,
  `_pr_merged`, `_feedback_done`, `_pending_feedback`) as defaulted `MergeWatchResume` fields, recorded at both
  `_gates_passed = True` sites (depends on 2) — DoD: `tests/test_patch_memoization.py` covers the marker; replay
  of existing fixtures passes.
- [ ] 4. Validator refusals `implement-running` (deferred), `work-merged` and `nothing-to-resume` (refused) in
  `_validate_execution_request`; add the reasons to `xr.RESUME_REFUSAL_REASONS`
  (`orchestrator/work_context/execution_requests.py`) (depends on 3) — DoD: T2, T3 pass; no `we_` is minted on refusal.
- [ ] 5. Feedback tick: the `_deliver` branch, `_feedback_authority_valid()`, the `_pending_feedback` pickup in
  `_watch_pr`, `_shepherd_tick(..., feedback=...)` params and outcome parsing, dedupe through `_feedback_done`,
  and typed landing (`processed` -> Succeeded; `scope-expansion` / `feedback-failed` / `feedback-unobservable` /
  `reapproval-required` / `feedback-not-run` -> Failed plus `ResumeRejection`) (depends on 3) — DoD: T4, T5, T6 pass.
- [ ] 6. `run_shepherd --feedback-intent`: fetch the intent, classify scope against the approved spec, run the
  `--review-feedback` path for in-scope feedback with the existing fencing, and emit `feedback_outcome`
  (depends on 5) — DoD: unit tests for each outcome; the fencing and gates are unchanged (existing shepherd tests green).
- [ ] 7. Sibling mctl-gitops PR: the shepherd CWFT declares `intent_id`, `execution_request_id`,
  `feedback_actor` and the `feedback_outcome` output (depends on 6) — DoD: the PR is linked; until it merges the
  outcome is `feedback-unobservable`.
- [ ] 8. Closed-loop rewind: the predicate in `run_issue_investigator` (~:3528, ~:4199) and the loop's
  context-only branch, under `DEFERRED_RESUME_PATCH`. `accepted` / `needs-triage` with no PR, a dispatched resume
  and an available intent -> `proposed`, followed by a fresh canonical approval (depends on 3) — DoD: T7 passes;
  an open or merged PR is never rewound.
- [ ] 9. Orphan sweep: extract `_orphan_verdict`, add `Dispatcher.sweep_orphans_once()` run from
  `run_dispatcher` every `EXECUTION_ORPHAN_SWEEP_SECONDS`, with source A (mctl-api list, if #931 provides it)
  and source B (Temporal visibility + `work_item_id` in the start memo in `orchestrator/temporal/start.py`)
  (depends on 1) — DoD: T8 passes; existing `_reconcile_closed_loops` tests pass unchanged.
- [ ] 10. Rewrite the 21 #992 resume tests (`test_execution_request_resume.py` 17, `test_execution_request_dispatch.py` 1,
  `test_execution_request_replay.py` 3) to the new contract, including
  `test_a_resume_delivered_after_the_implement_step_succeeds_at_once` -> `nothing-to-resume` refusal / feedback
  tick (depends on 4, 5, 8) — DoD: each rewritten test asserts a delivered or typed-refused request, and none
  asserts a lost request.
- [ ] 11. Rollout gate: the `probe_execution_queue_capability` activity, `IMPLEMENT_HOLD_CAPABILITY_PATCH`
  placed before `IMPLEMENT_EXECUTION_PATCH` in #992's flip site, and the read-only CLI
  `orchestrator/temporal/cli.py capability execution-queue` (depends on #992 branch) — DoD: T9 passes; an
  unanswered probe means no hold.
- [ ] 12. Documents: ADR `docs/adr/026-deferred-resume-contract.md`; amend the #991 requirements/design/tasks;
  fix the `_await_canonical_reapproval` and `_launch_correlation` docstrings; request a new approval digest
  (depends on 4-11) — DoD: the ADR is merged and the amended #991 spec is approved with a new digest.

## Tests
- [ ] T1. Dispatcher -> `ResumeDelivery` carries `intent_id`, `expected_state_version`, `resumed_from_execution_id`;
  a pre-change payload decodes to the defaults.
- [ ] T2. Resume after the merge watch observed MERGED -> `resume_refused:work-merged`, no fulfil, request row
  keeps the intent.
- [ ] T3. Resume with no intent after the gates passed -> `resume_refused:nothing-to-resume` (mutation check: it
  fails if the old at-once Succeeded comes back).
- [ ] T4. End-to-end: a resume queued during implement is delivered after implement Succeeded with the PR open.
  Exactly one feedback tick runs, with the `intent_id`; the `we_` ends Succeeded only on `processed`. Redelivery and
  continue-as-new produce no second tick.
- [ ] T5. Feedback tick outcomes `scope-expansion`, `failed`, `unobservable`, an activity failure, and the watch
  ending before the tick -> `we_` Failed with the typed `ResumeRejection`; never Succeeded.
- [ ] T6. Grant binding changed (content digest or authority) before the tick -> `reapproval-required`, no tick.
- [ ] T7. End-to-end: a resume is delivered after implement Failed, Cancelled and TimedOut (the loop closed).
  Update-with-Start runs; the proposal is rewound to `proposed` only with no PR; the loop parks for a fresh
  approval and no implementer is released without one.
- [ ] T8. Orphan sweep: a terminated loop with an open `#run_` `we_` and no request is ended Failed within one
  sweep. A RUNNING holder is untouched. A Temporal/mctl-api read error skips.
- [ ] T9. Capability probe on / off / no answer -> hold / no hold / no hold. Replay of histories recorded before
  and after the `implement-execution-id` marker and `deferred-resume-contract` (new fixtures in
  `tests/fixtures/histories/`, driven from `tests/test_workflow_replay.py`).
- [ ] T10. Stale `expected_state_version`: the fulfil refuses `state_version_conflict` -> the request is rejected and
  the loop's delivery ends without a feedback tick.

## Rollback
Every behaviour is behind workflow markers, so rollback is a worker image rollback to the previous tag in
`services/admins/mctl-agents-worker*/values.yaml`. Two exceptions need care:
- Running histories that already recorded `deferred-resume-contract` or `implement-hold-capability` would hit
  nondeterminism on an older image. Before rolling back, let them drain, or abandon them with
  `mctl_abandon_dev_loop`. The orphan sweep (or the new image's exit path) ends their `we_`.
- To stop the hold without a rollback, turn the mctl-api queue switch off: the capability probe then answers off,
  and new loops end the `we_` at the flip as before.
The orphan sweep can be disabled on its own with `EXECUTION_ORPHAN_SWEEP_SECONDS=0`. The shepherd CWFT params are
additive and can stay in place.
