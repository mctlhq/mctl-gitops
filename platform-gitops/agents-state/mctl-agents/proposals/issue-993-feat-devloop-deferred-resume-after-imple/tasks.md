# Tasks: issue-993-feat-devloop-deferred-resume-after-imple

Amended 2026-11-03. Order rule (owner decisions 6 and 7): the new regression and end-to-end tests are committed first
and fail against the old behaviour; only then is behaviour implemented; existing expectations are rewritten last.
Tests run against real Temporal replay and real Postgres where the existing suites do; every new check is
mutation-verified (revert the change, watch the test fail).

Scope split: tasks 1-13 and tests T1-T11 are Part M, executed by this proposal's implementer on `main`. Tasks S1-S8
and tests TS1-TS8 are Part S: they change code that exists only on PR #992's branch and are executed there by its
owner/shepherd. THE IMPLEMENTER OF THIS PROPOSAL MUST NOT DO S-TASKS (their symbols do not exist on `main`) and must
not edit #991's proposal. Nothing is marked ready, released or deployed before the gates in requirements.md
("Delivery and rollout order").

## Part M

- [ ] 1. Write the new tests T1-T11 against current `main` and confirm each fails for the right reason - DoD: tests
  are in a commit before any behaviour change; each fails on an assertion about the contract, not an import error.
- [ ] 2. Request identity: defaulted `intent_id`, `expected_state_version`, `resumed_from_execution_id` on
  `ResumeDelivery`, filled in `Dispatcher._dispatch` (depends on 1) - DoD: T1 passes; old payload fixtures decode.
- [ ] 3. `DEFERRED_RESUME_PATCH` and carried state (`_deferred_contract`, `_implement_running`, `_pr_merged`,
  `_feedback_done`, `_pending_feedback`) as defaulted `MergeWatchResume` fields, recorded at both `_gates_passed = True`
  sites (depends on 2) - DoD: `tests/test_patch_memoization.py` covers the marker; existing replay fixtures pass.
- [ ] 4. Validator decisions in `_validate_execution_request`: `legacy-loop` and `implement-running` (deferred),
  `work-merged` and `nothing-to-resume` (refused); add the reasons to the vocabularies; add the `contract_state` query
  and CLI `contract-drain-check` (depends on 3) - DoD: T2, T3, T4 pass; no `we_` is minted on refusal; a replayed history
  with an accepted update stays green.
- [ ] 5. `read_rollout_switches` activity (`DEVLOOP_DEFERRED_FEEDBACK` only in this part), registered in the main
  worker's `short_activities`, fail closed on any non-explicit value; the fake in the test activity registry
  (depends on 3) - DoD: T5 passes.
- [ ] 6. Feedback tick: the `_deliver` branch, `_feedback_authority_valid()`, the `_pending_feedback` pickup in `_watch_pr`,
  `_shepherd_tick(..., feedback=...)` params and outcome parsing, dedupe through `_feedback_done` (added before the tick
  awaits), typed landing (`processed` -> Succeeded; `scope-expansion` / `feedback-failed` / `feedback-unobservable` /
  `reapproval-required` / `feedback-not-run` / `feedback-disabled` -> Failed plus `ResumeRejection`) (depends on 4, 5)
  - DoD: T6, T7, T8 pass.
- [ ] 7. `run_shepherd --feedback-intent`: fetch the intent, classify scope against the approved spec, run
  `--review-feedback` for in-scope with the existing fencing, emit `feedback_outcome` (depends on 6) - DoD: unit tests for
  each outcome; existing shepherd tests green.
- [ ] 8. Sibling mctl-gitops PR: the shepherd CWFT declares `intent_id`, `execution_request_id`, `feedback_actor` and the
  `feedback_outcome` output (depends on 7). It must be merged and live before the switch is turned on - DoD: PR linked;
  until live the outcome is `feedback-unobservable`.
- [ ] 9. Closed-loop rewind with proof: the predicate in `run_issue_investigator` (~:3528, ~:4199) and the loop's
  context-only branch, under `DEFERRED_RESUME_PATCH`; the positive-proof reads (status `pr`, GitHub PR and branch, live
  implement Workflow and attempt lease, lifecycle ownership); any unknown -> `needs-triage` (depends on 3) - DoD: T9
  passes; an open or merged PR, a pushed branch, or a failed read never rewinds.
- [ ] 10. Orphan sweep spike C0: in the Temporal test environment terminate a DevLoop that holds an open `we_` and query
  `work_context` on the closed run; also query a pre-hop recorded history - DoD: the result is written into the ADR. If
  it fails, STOP and record the blocker `ORPHAN_SOURCE_BLOCKED`; ship task 11 disabled and open the separate API
  follow-up proposal. Do not fabricate a list endpoint.
- [ ] 11. Orphan sweep: extract `_orphan_verdict`, add `Dispatcher.sweep_orphans_once()` run from `run_dispatcher` every
  `EXECUTION_ORPHAN_SWEEP_SECONDS` (default 0), with the two lanes, batch caps, the in-process converged set, audit
  counters, 409-as-converged and fail-closed reads (depends on 10, 1) - DoD: T10, T11 pass; existing
  `_reconcile_closed_loops` tests pass unchanged.
- [ ] 12. Rewrite the `main` test `test_a_resume_delivered_after_the_implement_step_succeeds_at_once` to the contract
  (`nothing-to-resume` refusal / feedback tick) (depends on 4, 6) - DoD: it asserts a delivered or typed-refused request,
  none asserts a lost one; done only after T2-T8 exist and were mutation-checked.
- [ ] 13. ADR `docs/adr/026-deferred-resume-contract.md` (table, authority rule, two switches, sweep and division of
  labour with #931, spike result) (depends on 4-11) - DoD: merged.

## Part S (executed on PR #992's branch by its owner/shepherd; not by this proposal's implementer)

- [ ] S1. Run the 21 failing tests (`test_execution_request_resume.py` 17, `test_execution_request_dispatch.py` 1,
  `test_execution_request_replay.py` 3) with a fake `read_rollout_switches` defaulted off, unchanged, and record which
  pass - DoD: the list is in the PR body.
- [ ] S2. Write TS1-TS8 and confirm they fail for the right reason on the branch - DoD: committed before S3-S6.
- [ ] S3. Hold switch: `IMPLEMENT_HOLD_SWITCH_PATCH`, `implement_hold` on `RolloutSwitches`, the flip-site read; unpatched
  histories hold (depends on S2) - DoD: TS1, TS2 pass; the existing `.patched.json` fixture still replays.
- [ ] S4. `IMPLEMENT_END_RETRY_PATCH`: per-poll retry in `_watch_pr`, last attempt before the hop, new defaulted
  `MergeWatchResume` fields folded in `_carry_work_context` and rehydrated in `_resume_merge_watch` (depends on S3) - DoD:
  TS3, TS4, TS5 pass; no retry command for histories without the marker.
- [ ] S5. Docstrings: `_await_canonical_reapproval`, `_launch_correlation`, `_end_canonical_execution`; the line after
  `_implement` documented as success-only (depends on S3) - DoD: no stale text.
- [ ] S6. Replay fixtures: hold on, hold off, retried advance, retried across a hop (depends on S3, S4) - DoD: TS5 passes.
- [ ] S7. Parametrise the 21 tests over `implement_hold in {off, on}`; off legs untouched; write the on legs last
  (depends on Part M tasks 4, 6, 12 merged and S2-S6) - DoD: each on leg asserts a delivered or typed-refused request.
- [ ] S8. Rollout record: keep #992 draft until the gates 1-5 of the rollout order hold; release with
  `DEVLOOP_IMPLEMENT_HOLD` off; the human sets it on after the functional check (requirements.md) - DoD: gate evidence
  linked in the release PR.

## Tests

Part M
- [ ] T1. Dispatcher -> `ResumeDelivery` carries `intent_id`, `expected_state_version`, `resumed_from_execution_id`; a
  pre-change payload decodes to the defaults.
- [ ] T2. Resume after the merge watch observed MERGED -> `resume_refused:work-merged`, no fulfil, the request row keeps
  the intent.
- [ ] T3. Resume with no intent after the gates passed -> `resume_refused:nothing-to-resume`. Mutation: restore the
  at-once Succeeded -> fails.
- [ ] T4. Legacy loop: a history recorded without `DEFERRED_RESUME_PATCH`, gates passed, receives a resume -> `legacy-loop`
  deferred, the request is not lost and nothing ends Succeeded; replay of that history with an accepted update is
  unchanged. `contract-drain-check` lists it. Mutation: drop the fence -> silent Succeeded returns.
- [ ] T5. Switch read: on / off / unset / malformed / activity error -> only an explicit on is on. The command sequence
  is identical in every case (same activities scheduled).
- [ ] T6. End-to-end, switch on: a resume with an intent delivered while the loop is in its merge watch with the PR open.
  Exactly one tick runs with the `intent_id`; the `we_` ends Succeeded only on `processed`. Redelivery and
  continue-as-new produce no second tick. Mutation: remove the `_feedback_done` guard -> a second tick appears.
  Switch off: the same delivery ends Failed `feedback-disabled`, no tick.
- [ ] T7. Tick outcomes `scope-expansion`, `failed`, `unobservable`, an activity failure, and the watch ending before the
  tick -> `we_` Failed with the typed `ResumeRejection`; never Succeeded.
- [ ] T8. Grant binding changed (content digest or authority) before the tick -> `reapproval-required`, no tick; stale
  `expected_state_version` -> the fulfil refuses `state_version_conflict`, the request is rejected, no tick.
- [ ] T9. A resume after implement Failed, Cancelled and TimedOut (loop closed): Update-with-Start runs; the proposal is
  rewound to `proposed` ONLY when every proof holds; with an open PR, a merged PR, a pushed branch, a live lease, an
  active ownership claim, or any unreadable input it becomes/stays `needs-triage`; no implementer is released without a
  fresh approval. Mutation: skip one proof read -> the matching case fails.
- [ ] T10. Sweep: a terminated loop with an open `#run_` `we_` and no request is ended Failed within one full pass; a
  RUNNING holder and a ContinuedAsNew run are untouched; an argo/a2a execution is untouched; a Temporal, query or
  mctl-api read error skips and counts `unobserved`, and a failed listing does not advance the cursor; a second writer
  (409 `invalid_transition`) counts as converged. Mutation: treat a read error as "gone" -> fails.
- [ ] T11. Sweep starvation: with `batch + 1` permanently unresolvable closed runs ahead, a later orphan is still found
  within ceil(total / batch) cycles; a fresh close is found in the next cycle; the cursor wraps. Mutation: always restart
  from the newest `batch` rows -> the later orphan is never found.

Part S (on #992's branch)
- [ ] TS1. Hold switch on: the `we_` is held through implement, `execution_id` is passed, it ends after implement Succeeded.
  Off: it ends at the flip, no `execution_id`, equal to `main`. No answer / error -> off. Mutation: ignore the switch -> fails.
- [ ] TS2. A failed implement (the fake RAISES `ApplicationError`): exactly one advance `Failed`, recorded by `run`'s exit
  path, none by the line after `_implement`, no phase other than `Succeeded`/`Failed` ever sent.
- [ ] TS3. End-advance retried during the merge watch: the post-implement advance fails (no answer) first, then lands; the
  fake PR stays OPEN for many polls. The `we_` is closed (query `canonical_open` False) at a poll while the watch is
  running, `Succeeded`, and nothing is sent afterwards. Mutation: remove the retry -> the `we_` stays open until the
  watch ends. This is the 14-day evidence.
- [ ] TS4. Retry across a hop: the advance keeps failing past a continue-as-new hop; the continued run retries, the `we_`
  ends exactly once, a `MergeWatchResume` built without the new fields decodes, the `work_context` query is accurate after
  the hop. Mutation: drop the carried fields -> the `we_` is never ended by the watch.
- [ ] TS5. Replay: a history recording `implement-execution-id` only (existing fixture), one recording the switch marker
  (hold on and off), and one recording `implement-end-retry` replay unchanged. Mutation: evaluate
  `patched(IMPLEMENT_END_RETRY_PATCH)` unconditionally -> the old fixture raises non-determinism.
- [ ] TS6. A legacy `resume` signal between flip and implement under the hold: the loop does not hang on `opened()`; the
  grant is requested on the canonical `we_` (`after_flip=False`). Mutation: `after_flip=True` -> waits on `opened()`.
- [ ] TS7. End-to-end with the hold on: a resume queued during implement is delivered after implement Succeeded with the PR
  open (one tick), and after Failed/Cancelled/TimedOut (closed-loop path). Depends on Part M.
- [ ] TS8. The 21 tests, both legs of `implement_hold`: off legs unchanged and green; on legs rewritten last.

## Rollback
See design.md "Rollback". Order: hold off, then feedback off, then the mctl-api switch; image rollback only for loops
that never recorded the new markers; the sweep is disabled with `EXECUTION_ORPHAN_SWEEP_SECONDS=0`.
