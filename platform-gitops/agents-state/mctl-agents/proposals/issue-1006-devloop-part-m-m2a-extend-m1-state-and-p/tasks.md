# Tasks: issue-1006-devloop-part-m-m2a-extend-m1-state-and-p

Order rule (taken over from #993): tests are committed first and fail for the right reason; behaviour comes
after. Each new check is mutation-verified: revert the line under test, watch the test fail, and record that
in the PR body. Nothing here touches #993's `.status.yaml`, any flag, a release or another repository.

- [ ] 1. Gap audit against M1. Confirm in code that `ResumeDelivery`'s identity fields, `Dispatcher._dispatch`
  propagation, `DEFERRED_RESUME_PATCH`, the validator order and the canonical and legacy vocabulary exist
  exactly as described in design.md "Current state". List anything genuinely missing. — DoD: the list is in
  the PR body. Only the items on it are implemented, and no M1 symbol is redefined.
- [ ] 2. Write the tests (T1-T10 below), red where they cover new behaviour, before any production change
  (depends on 1). — DoD: one commit containing only tests. Each new-behaviour test fails on a contract
  assertion, not on an import error. The import of `closed_loop` is guarded with `pytest.importorskip` in the
  test-only commit. Later-slice tests are marked `xfail(strict=True, reason=...)`.
- [ ] 3. Feedback state. Add `_feedback_done` and `_pending_feedback` to `DevLoopWorkflow.__init__`, add
  `feedback_done` and `pending_feedback` to `MergeWatchResume`, fold them in `_carry_work_context` and restore
  them in `_rehydrate_work_context` (`orchestrator/temporal/workflows/dev_loop.py`). No writer (depends on 2).
  — DoD: T3, T4 and T5 pass. All history fixtures replay. The marker is still evaluated only at the
  gates-passed site in `run`.
- [ ] 4. `contract_state` query (`ContractState` dataclass) in `dev_loop.py` (depends on 3). — DoD: T6 passes.
  No command, no patch.
- [ ] 5. `cli.py contract-drain-check`, read-only, with the classification and exit codes from design.md
  (depends on 4). — DoD: T7 passes. The command writes, signals and starts nothing.
- [ ] 6. `orchestrator/temporal/closed_loop.py`. Add the tri-state `PRRead`, `BranchRead` and `GatesRead`,
  `read_pr_by_branch`, `read_branch` (with the repository probe), `read_gates`, the `ClosedLoopReadPort` and
  `GitHubClosedLoopReads`, and the pure `closed_loop_decision`. Add `CLOSED_LOOP_UNOBSERVED` to
  `dispatcher.DEFERRAL_AUDITED` (depends on 2). — DoD: T8 and T9 pass. `Dispatcher`, `worker.py` and `cli.py`
  dispatch construction are unchanged, which T10 asserts.
- [ ] 7. Investigate the mctl-api execution-request list contract: route, envelope, pagination and
  completeness, and principal access (depends on 1). — DoD: the PR body records the source file and lines
  read, or the exact missing piece.
- [ ] 7a. Only if task 7 confirms the contract: add `ROUTES["list_execution_requests"]`,
  `xr.answer_from_list` and `WorkItemClient.list_execution_requests` (fail-closed, `FOUND` only when the list
  is complete) (depends on 7). — DoD: T11 passes. Otherwise this task is skipped, the dependency is written
  into `docs/temporal-flow.md` and the PR body, and T11 stays a strict xfail. This task is never marked done
  in that case.
- [ ] 8. Documentation. Add an M2a section to `docs/temporal-flow.md`: the new state, the query, the CLI, the
  closed-loop primitives and their non-wiring, and the remaining parts of tasks 4 and 4b with their owners
  (depends on 3-7). — DoD: the "not done in M2a" list below is reproduced verbatim in the PR body.

Not done in M2a, which must stay open:
- task 4: replacing the `feedback-not-ready` / `recovery-not-ready` deferrals with the accept path (M2c, after
  the feedback tick, tasks 5-8). Recovery is #1005 (M3).
- task 4b: wiring `closed_loop_decision` and the reads into `Dispatcher._dispatch`, and the per-claim
  audit counter (M2c).
- task 4b: the list read, if task 7 finds the dependency missing (a dependency issue against mctl-api, filed by
  the owner).

## Tests

- [ ] T1. Identity propagation, one case per field (`intent_id`, `expected_state_version`,
  `resumed_from_execution_id`) with distinct non-default values. A pre-M1 `ResumeDelivery` JSON decodes
  through `DataConverter.default` to the defaults. Mutation: drop one field in `_dispatch`, and that case fails.
- [ ] T2. Real `DevLoopWorkflow` in the time-skipping environment, gates passed, `_last_pr` MERGED: the resume
  is rejected `resume_refused:work_merged`, with zero fulfils and no `we_`, and the row keeps `intent_id`,
  surface and requester. A second dispatch of the same request after the lease lapses gives the same reason.
  Mutation: delete the `work_merged` arm, and the test fails.
- [ ] T3. A contract loop, gates passed, no intent: refused `no_actionable_intent` with identity preserved. With
  an intent and an open PR: deferred `feedback-not-ready`, request still claimed, nothing `Succeeded`.
  Mutation: return early (accept) instead of deferring, and the test fails.
- [ ] T4. Legacy loop: replay of `dev_loop_full.patched.json` / `dev_loop_issue_keyed.json` (no marker) and of
  `dev_loop_deferred_resume.json` (marker) is unchanged. On a legacy loop with gates passed, a resume defers
  `legacy-loop`. Add a `tests/test_patch_memoization.py` case: the marker is recorded once on the fresh path and
  zero times in `_resume_merge_watch`. Mutation: call `workflow.patched(DEFERRED_RESUME_PATCH)` in
  `_resume_merge_watch`, and the memoization case fails.
- [ ] T5. Feedback state:
  - a pre-M2a `MergeWatchResume` JSON (without `feedback_done` / `pending_feedback`) decodes them as empty and
    keeps `deferred_resume_contract`;
  - a non-empty value survives a `_carry_work_context` then `_rehydrate_work_context` round trip, and a
    converter round trip, with `pending_feedback` order preserved and `feedback_done` sorted;
  - an extra unknown key in the payload is tested, which documents the forward-compat behaviour.
  Mutation: omit either field from `_carry_work_context`, and the round trip fails.
- [ ] T6. `contract_state` on contract, legacy and pre-gates validator doubles returns the expected fields, and
  `last_pr_state == "unknown"` when `_last_pr is None`. Mutation: return `"absent"` for None, and the test fails.
- [ ] T7. `contract-drain-check` with a fake client covers one loop of each class, a query error (`UNKNOWN`,
  exit 2) and a listing failure (`UNKNOWN`, exit 2, never 0). It is asserted that no signal, update or start
  method is called on the fake. Mutation: count a query error as `legacy`, and the test fails.
- [ ] T8. Tri-state reads with `httpx.MockTransport`:
  - pulls 200 `[]` gives absent, a merged entry gives merged, open gives open, closed gives closed;
  - 403, 404, 5xx, a timeout, invalid JSON or a missing token gives unknown;
  - branch 200 gives exists; 404 after a repository 200 gives absent; 404 when the repository read is a
    404 or 403 gives unknown;
  - gates: `accepted` / `implementing` / `review-fixing` / `merged` give passed, `proposed` gives not-passed,
    and anything else or a failed read gives unknown.
  Mutation: map a branch 404 to absent without the probe, and the test fails.
- [ ] T9. `closed_loop_decision` table, covering every combination of
  {running, closed, absent} x {merged, open, closed, absent, unknown} x {intent, none} x
  {passed, not-passed, unknown}:
  - running always gives `pass`;
  - merged gives `refuse:work_merged`;
  - an unknown PR gives `defer:closed-loop-unobserved`;
  - no intent with gates passed gives `refuse:no_actionable_intent`;
  - no intent with gates unknown gives defer.
  The reasons belong to `xr.RESUME_REFUSAL_REASONS` / `DEFERRAL_AUDITED`. Mutation: treat unknown as absent,
  and the matching cells fail.
- [ ] T10. Vocabulary and non-wiring (T9b extended):
  - a stored `resume_refused:work-merged` / `nothing-to-resume` still decodes unchanged through the real port
    (the existing tests stay green);
  - the source of `dev_loop.py`, `dispatcher.py` and `closed_loop.py` contains no minted legacy spelling;
  - `dispatcher.py` does not import or reference `closed_loop`;
  - `Dispatcher.__init__`'s signature is unchanged.
- [ ] T11. Only if task 7a is implemented: `list_execution_requests` returns FOUND for a complete page, and
  UNKNOWN for a 5xx, 401, 403, a wrong `schema_version`, one unparsable entry or an incomplete page. Otherwise
  it is a strict xfail with reason "mctl-api list contract unconfirmed (task 4b dependency)".

Red until their owning slice (all `xfail(strict=True)`, listed in the PR body):
- [ ] R1. T2b end-to-end: a closed loop with a merged PR. The dispatcher refuses `work_merged` before `deliver()`
  and no new run is started; a failed PR read defers and neither refuses nor delivers. Owner: M2c.
- [ ] R2. Accept path: a contract loop with an open PR and an intent is accepted, and exactly one feedback tick
  runs. Owner: the slice for tasks 5-8, then M2c.
- [ ] R3. Recovery: a failed implement or closed PR with an intent is no longer deferred `recovery-not-ready`.
  Owner: #1005 (M3).

## Rollback

M2a changes no live decision and adds no flag, so rollback means reverting the PR's commits. Points to watch:

- **Merge-watch payloads.** If M2a workers recorded continue-as-new hops, those payloads contain empty
  `feedback_done` / `pending_feedback` keys. T5 records whether a pre-M2a worker ignores unknown keys.
  - If it does, revert at any time.
  - If it does not, drain or wait out M2a-recorded hops (`contract-drain-check` lists the running loops)
    before deploying the older image.
- **Workflow histories.** No history depends on the new query or CLI, and no new `patched()` marker exists, so
  replay of older images is unaffected.
- **Strict-xfail tests.** These are removed or flipped only by their owning slices, never by the rollback.
