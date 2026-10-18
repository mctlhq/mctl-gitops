# Tasks: issue-702-fix-devloop-a-failed-approval-must-not-p

- [ ] 1. Add `outcome: str = ""` to `DevLoopResult` and the constants
  `APPROVAL_REFUSED_ENDED_PREFIX`, `APPROVAL_FAILED_ENDED_PREFIX`,
  `RESTARTABLE_ENDED_PREFIXES`, `APPROVAL_FAILURE_OUTCOME_PATCH`,
  `STALE_GRANT_REFUSAL_CODES` in `orchestrator/temporal/workflows/dev_loop.py`
  — DoD: old serialized results still decode; constants carry a "mirror in
  mctl-api" comment.
- [ ] 2. (depends on 1) Add `_approval_ended(...)` helper that builds the typed
  result, logs `APPROVAL_OUTCOME`, and sets `self._canonical_end_phase = "Failed"`
  — DoD: unit-callable; used by every approval-failure return.
- [ ] 3. (depends on 2) Make `_delegated_approve` return a classification
  (refused / unavailable / stale) alongside the reason — DoD: `unavailable`
  -> `approval_failed`; refusal with a stale code -> stale; other refusals ->
  `approval_refused`.
- [ ] 4. (depends on 2, 3) Under `workflow.patched(APPROVAL_FAILURE_OUTCOME_PATCH)`,
  replace the two failure returns in `_run_loop`'s canonical approve branch:
  on a non-`Succeeded` `approve_result` run `_supersede_grant_if_stale` once
  and classify (`superseded` -> re-grant, `capped` -> `approval_refused`,
  `fresh`/`unreadable` -> `approval_failed`) — DoD: no path in the branch
  returns without `outcome` set; unpatched histories take the old returns.
- [ ] 5. (depends on 4) Wrap the canonical flip in a bounded re-grant loop
  (`_ensure_fresh_grant` -> `_delegated_approve` -> `_await_canonical_reapproval`)
  on the same `we_` — DoD: bounded by `MAX_GRANT_SUPERSEDES` and
  `CANONICAL_APPROVAL_WAIT`; abandon still ends it with the abandoned prefix.
- [ ] 6. Non-canonical branch (`_run_cwft("mctl-agents-approve")`): set
  `outcome="approval_failed"` and the prefixed `ended` under the same patch —
  DoD: legacy loops get the typed outcome; no `we_` logic touched.
- [ ] 7. (depends on 1) `orchestrator/temporal/start.py`: rename to
  `restart_if_restartable`, check `RESTARTABLE_ENDED_PREFIXES`, keep
  `restart_if_abandoned` alias; update `cli.py` and the docstring — DoD: intake
  poller path unchanged.
- [ ] 8. Update the comment in `run` (exit path) and the module docstring's
  grant-freshness paragraph to describe the new outcomes — DoD: comments
  match behaviour.
- [ ] 9. File the companion mctl-api issue (extend `restartIfAbandoned` with
  the two prefixes; expose `outcome` in the dev-loop GET / `mctl_get_dev_loop`)
  and link it from the PR — DoD: issue URL in the PR body.

## Tests
- [ ] T1. `tests/test_dev_loop_workflow.py`: canonical loop, delegated approve
  returns `DelegatedApproveResult(result=WorkflowResult(phase="Failed"))`,
  digest still fresh -> `advance_log` phases == `["Failed"]`,
  `result.outcome == "approval_failed"`, `result.ended.startswith("approval failed: ")`,
  implementer never ran. Fails on revert (phase would be `Succeeded`).
- [ ] T2. Canonical loop, delegated approve returns `refusal="HTTP 409 ..."`
  with a non-stale code -> `["Failed"]`, `outcome == "approval_refused"`.
- [ ] T3. Canonical loop, delegated approve raises (unavailable) ->
  `["Failed"]`, `outcome == "approval_failed"`.
- [ ] T4. Approve succeeds -> unchanged: `advance_log == ["Succeeded"]`,
  `outcome == ""`, implementer ran (existing happy-path assertions kept).
- [ ] T5. Retry path: first flip returns `Failed`, `digest_state["current"]`
  changed before the post-failure check -> loop supersedes, asks
  `aar_test_a1` on the same `we_test_own` (assert `approval_requests[-1].execution_id`),
  test signals approve with the fresh ref, second flip succeeds -> implementer
  runs, single `advance` of `Succeeded`, `GRANT_SUPERSEDED` comment posted.
- [ ] T6. Retry cap: repeated stale failures past `MAX_GRANT_SUPERSEDES` ->
  `outcome == "approval_refused"`, `["Failed"]`.
- [ ] T7. `tests/test_temporal_cli.py`: `restart_if_restartable` starts a new
  run for a COMPLETED result with `ended="approval refused: ..."` and with
  `"approval failed: ..."` and `implement is None`; does NOT restart when
  `implement` is set or `ended` is `"approve flip ended Failed"` (legacy text).
- [ ] T8. Replay: `tests/fixtures/histories/dev_loop_delegated.json` and
  `dev_loop_issue_started_delegated.json` still replay without
  nondeterminism (no patch marker -> old commands).
- [ ] T9. Revert check: run T1, T2, T5 against the pre-fix `dev_loop.py`
  locally and confirm they fail.

## Rollback
Revert the PR and release. Because every new command is behind the
`approval-failure-outcome` patch, a revert is only safe once no running
execution has recorded that marker; otherwise keep the patched branch and
roll forward a fix instead (standard `workflow.patched` rule in this repo).
The `DevLoopResult.outcome` field is additive, so results written by the new
version still decode after a revert. `restart_if_abandoned` remains the
alias, so `cli.py` callers are unaffected either way.
