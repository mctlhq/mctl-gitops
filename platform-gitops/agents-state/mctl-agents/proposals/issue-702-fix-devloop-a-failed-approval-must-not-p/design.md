# Design: issue-702-fix-devloop-a-failed-approval-must-not-p

## Current state
All references are to `orchestrator/temporal/workflows/dev_loop.py` at clone
HEAD `1cfb381` (after #704 / #701 grant freshness merged) unless noted.

- `DevLoopWorkflow.run` (around lines 3355-3390) wraps `_run_loop`. On
  exception it ends the canonical `we_` with `_canonical_pending_phase or
  "Failed"`. On a normal return it calls
  `_end_canonical_execution(self._canonical_pending_phase or self._canonical_end_phase or "Failed")`.
  The comment says a loop that exited "before any flip" ends with the
  investigator's phase.
- `_canonical_end_phase` is set to `"Succeeded" if investigate_result.succeeded else "Failed"`
  after investigate (lines ~3538 and ~3682).
- In `_run_loop`'s atomic-approve branch (lines ~3920-3966), the canonical
  path runs `_ensure_fresh_grant` (#701), then `_delegated_approve`:
  - `approve_result is None` -> `return DevLoopResult(..., ended=refused)`
    where `refused` is `"approve flip refused: ..."` or
    `"approve flip unavailable: <cause>"` (`_delegated_approve`, ~line 2271).
  - `not approve_result.succeeded` ->
    `return DevLoopResult(..., approve=approve_result, ended=f"approve flip ended {approve_result.phase}")`.
  Both returns flow into `run`'s normal exit and so end the `we_` with the
  investigator's `Succeeded`. Only the success path calls
  `_end_canonical_execution(self._canonical_end_phase ...)` at line ~3969, which
  is correct there.
- `DevLoopResult` (~line 1099) has `ended: str = ""` and no typed outcome.
  `ABANDONED_ENDED_PREFIX = "abandoned: "` (~line 1095) is the only
  restart marker, mirrored byte-for-byte in mctl-api
  (`temporalclient.AbandonedEndedPrefix`).
- `orchestrator/temporal/start.py::restart_if_abandoned` restarts a COMPLETED
  run only when `implement is None` and `ended` starts with
  `ABANDONED_ENDED_PREFIX`, using `RESTART_ID_REUSE_POLICY = ALLOW_DUPLICATE`.
  `orchestrator/temporal/cli.py` is its only caller; tests in
  `tests/test_temporal_cli.py`. The intake poller uses
  `ALLOW_DUPLICATE_FAILED_ONLY` and never restarts a COMPLETED run.
- Re-grant machinery on the same `we_` already exists (#636, #701):
  `_supersede_grant_if_stale` drops a grant whose digest no longer matches
  (adds it to `_superseded_refs`, bumps `_approval_attempt` and
  `_supersede_count`, sets `_grant_refresh`), and
  `_await_canonical_reapproval` asks a fresh `aar_` on the own `we_` and parks,
  bounded by `CANONICAL_APPROVAL_WAIT` and `MAX_GRANT_SUPERSEDES`. The `we_`
  is held non-terminal until the flip, so a re-grant after a failed flip is
  still possible on the same execution.
- `orchestrator/temporal/activities/delegated_approval.py`:
  `DelegatedApproveResult(result, refusal, code)`; a CWFT that ran and failed
  comes back as `result.phase in {"Failed","Error"}` with no code, so the
  workflow cannot tell a digest-mismatch refusal by the CWFT from a push
  failure from the phase alone. `check_grant_freshness` /
  `GrantFreshnessInput` can answer that question.
- WorkItem execution terminal phases: `{"Succeeded","Failed","Error"}`
  (`activities/canonical_execution.py::_TERMINAL_PHASES`).
- Tests: `tests/test_dev_loop_workflow.py` has the canonical fakes
  (`delegated_result`, `advance_log`, `digest_state` parameters, ~line 230)
  and a precedent, `test_a_failed_continuation_ends_the_canonical_execution_failed`
  (~line 6269), asserting `[a.phase for a in advances] == ["Failed"]`.
  Replay fixtures: `tests/fixtures/histories/dev_loop_delegated.json`,
  `dev_loop_issue_started_delegated.json`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: the
  worker runs `ghcr.io/mctlhq/mctl-agents` tag `1.84.0` in tenant `admins`
  (siblings `mctl-agents-worker-exec`, `mctl-agents-worker-implement` exist).
  I did not verify whether 1.84.0 already contains #701 (the clone carries no
  release tags); see Open questions in requirements.md.
- mctl MCP tools were not called; this change is workflow logic and its
  behaviour is fully described by the issue's incident record.

## Proposed solution
All new behaviour sits behind one new patch,
`APPROVAL_FAILURE_OUTCOME_PATCH = "approval-failure-outcome"`, evaluated once
at the start of the canonical approve branch (next to the existing
`workflow.patched("work-context-resume")` use). Histories without the marker
replay exactly as today.

1. Typed outcome on the result.
   - Add `outcome: str = ""` to `DevLoopResult` (defaulted so old results
     deserialize). Values: `""` (pipeline or any pre-existing ending),
     `"approval_refused"`, `"approval_failed"`.
   - Add constants beside `ABANDONED_ENDED_PREFIX`:
     `APPROVAL_REFUSED_ENDED_PREFIX = "approval refused: "` and
     `APPROVAL_FAILED_ENDED_PREFIX = "approval failed: "`, plus
     `RESTARTABLE_ENDED_PREFIXES = (ABANDONED_..., APPROVAL_REFUSED_..., APPROVAL_FAILED_...)`,
     with a comment that mctl-api must mirror them byte for byte.
   - Add a helper `_approval_ended(kind, detail, investigate_result, approve, human_input) -> DevLoopResult`
     that sets `outcome`, builds `ended = prefix + detail` (detail keeps the
     old text, e.g. `"approve flip ended Failed"`, so log searches still
     match), logs `APPROVAL_OUTCOME outcome=... we=... detail=...`, and sets
     `self._canonical_end_phase = "Failed"` so every exit path (the normal
     return and a later exception) ends the `we_` `Failed`.

2. Classification at the two failure returns in `_run_loop`.
   - `_delegated_approve` returns `(None, refused)`: change it to also return
     a kind. `"approve flip unavailable: ..."` -> `approval_failed`;
     `"approve flip refused: ..."` (slug changed, no grant, typed refusal) ->
     `approval_refused`. A refusal whose `code` is in
     `STALE_GRANT_REFUSAL_CODES` (initially any code containing `digest` or
     `drift`) is routed to step 3 instead of ending.
   - `approve_result` not `Succeeded`: run `_supersede_grant_if_stale(target_repo, slug)`
     once (it is a no-op returning `"fresh"` when no digest is bound).
     - `"superseded"` -> step 3 (re-grant on the same `we_`).
     - `"capped"` -> `approval_refused`, detail
       `"approval superseded too many times"`.
     - `"fresh"` or `"unreadable"` -> `approval_failed`, detail
       `f"approve flip ended {approve_result.phase}"` (the CWFT failed for a
       reason other than a provable stale grant).

3. Re-grant on the same `we_` (the preferred retry for `approval_refused`
   after a rewrite). Wrap the canonical flip in a bounded loop:
   `_ensure_fresh_grant` -> `_delegated_approve` -> on a stale outcome call
   `_await_canonical_reapproval(issue, target_repo, investigate_result, human_input=...)`
   and go round again. The loop is bounded by `MAX_GRANT_SUPERSEDES` (every
   pass bumps `_supersede_count`) and by `CANONICAL_APPROVAL_WAIT` inside the
   park; abandon is observed by the park as today. The `we_` stays open the
   whole time, which mctl-api requires for binding a new `aar_`. The
   superseded ref is never adopted again (`_superseded_refs`).

4. Restart for terminal approval outcomes. In
   `orchestrator/temporal/start.py`, rename `restart_if_abandoned` to
   `restart_if_restartable` (keep `restart_if_abandoned = restart_if_restartable`
   for callers), and test `ended.startswith(RESTARTABLE_ENDED_PREFIXES)` with
   the same `implement is None` guard. `cli.py` keeps calling it. A restart
   re-investigates and asks a new grant, which is safe because
   `resolve_slug` reuses the issue-numbered proposal dir (#246). The intake
   poller is unchanged, so a lingering label never auto-restarts a refused
   loop. Companion mctl-api issue: extend `restartIfAbandoned` with the two
   prefixes and expose `outcome` in the dev-loop GET response.

5. `run`'s exit comment is updated: a loop that exits before the flip ends
   with the investigator's phase only if the loop never attempted the flip;
   any approval outcome forces `Failed`.

## Alternatives
- **Raise a non-retryable `ApplicationError` so the Temporal run ends
  `Failed`.** Existing `ALLOW_DUPLICATE_FAILED_ONLY` policies would make it
  restartable with no mctl-api change, and `mctl_get_dev_loop` would show
  `Failed` immediately. Dropped: a failed workflow returns no `DevLoopResult`
  (the issue asks for the outcome there), the intake poller would then
  auto-restart on any lingering label, and it conflates an expected,
  well-typed refusal with workflow crashes in alerting. Kept as a fallback if
  the mctl-api companion stalls.
- **Only fix the phase (end `we_` `Failed`) and add no retry.** Smallest
  diff, but a refused approval stays a dead end, which the issue explicitly
  rejects.
- **Re-present the same `aar_` after a failed CWFT.** Dropped: the grant may
  be consumed by mctl-api, and a grant bound to stale bytes must never be
  spent again (#701); a new attempt is the only safe ask.

## Platform impact
- Migrations: none. `DevLoopResult.outcome` is defaulted; old results
  deserialize. New commands (the post-failure freshness read, the re-grant
  park) are gated by the `approval-failure-outcome` patch, so in-flight
  histories replay unchanged. Add a replay test against the existing
  delegated fixtures.
- Backward compatibility: `ended` text changes for the two paths (now
  prefixed). Anything grepping `"approve flip ended"` still matches because
  the old text is kept as the detail. `restart_if_abandoned` stays importable.
- mctl-api: until its companion change ships, mctl-api still answers
  `already_exists` for these runs; the operator CLI (`cli.py`) can restart
  them. Risk documented; no mctl-api breakage because it only reads `ended`
  prefixes it already knows.
- Resource impact: one extra `check_grant_freshness` read per failed flip;
  re-grant parks are bounded by existing caps.
- Risk: a re-grant loop that never converges (e.g. the proposal is rewritten
  repeatedly). Mitigation: `MAX_GRANT_SUPERSEDES` and `CANONICAL_APPROVAL_WAIT`
  already bound it, ending with `approval_refused`.
- Risk: misclassifying a real infra failure as stale. Mitigation: stale is
  only ever declared on a positive digest mismatch; unreadable is
  `approval_failed`.
