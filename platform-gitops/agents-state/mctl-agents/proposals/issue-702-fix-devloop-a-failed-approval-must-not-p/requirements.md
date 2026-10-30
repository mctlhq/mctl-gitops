# fix(devloop): a failed approval must not project success or completed

## Context
In a canonical DevLoop (one that holds its own `we_` WorkItem execution open
through the approval, #636), a failed or refused approve flip ends the loop
with a normal `DevLoopResult(ended="approve flip ended Failed")`. The exit path
in `DevLoopWorkflow.run` then ends the `we_` with
`self._canonical_pending_phase or self._canonical_end_phase or "Failed"`, and
`_canonical_end_phase` holds the investigator's phase. So the `we_` is recorded
`Succeeded`, the Temporal run ends `Completed`, and both mctl-api's
`restartIfAbandoned` (mctl-api#640) and `orchestrator/temporal/start.py`
`restart_if_abandoned` refuse to restart it. This happened in production on
2026-10-18 (mctlhq/.github#182): a stale grant was correctly refused by the
approve CWFT (#681), yet the WorkItem said `Succeeded` and the loop could not
be retried on its own id.

The same false-success projection applies to every pre-flip exit of the
canonical approve branch in `_run_loop`: a delegated refusal or unavailability
(`approve flip refused: ...` / `approve flip unavailable: ...` from
`_delegated_approve`). This proposal makes every such exit end the `we_`
`Failed`, gives the loop a typed terminal outcome, and defines a retry path so
a refused approval is never a dead end.

## User stories
- AS a platform operator I WANT a refused or failed approval to be recorded as
  a failure on the WorkItem execution SO THAT dashboards and audits do not
  report work that never happened as successful.
- AS a platform operator I WANT the DevLoop result to carry a typed terminal
  outcome (`approval_refused` or `approval_failed`) SO THAT I can tell a
  stale/refused grant from an infrastructure failure without reading logs.
- AS an approver I WANT a loop whose approval was refused because the
  proposal changed to ask me for a fresh grant on the same `we_` SO THAT I do
  not need a new carrier issue to continue.
- AS an operator I WANT a loop that ended with an approval outcome to be
  restartable on its own workflow id SO THAT recovery does not require
  opening a new issue.

## Acceptance criteria (EARS)
- WHEN the approve flip of a canonical loop returns a `WorkflowResult` whose
  phase is not `Succeeded` THE SYSTEM SHALL end the loop's own `we_` with phase
  `Failed`, never `Succeeded`.
- WHEN `_delegated_approve` returns no result (a refusal or an unavailable
  submit) THE SYSTEM SHALL end the loop's own `we_` with phase `Failed`.
- WHEN a canonical loop ends because of an approval refusal THE SYSTEM SHALL
  return a `DevLoopResult` whose new field `outcome` is `"approval_refused"`
  and whose `ended` starts with `APPROVAL_REFUSED_ENDED_PREFIX`
  (`"approval refused: "`).
- WHEN a canonical loop ends because of an approval infrastructure failure
  (delegated submit unavailable, or the CWFT failed while the grant was still
  fresh or its freshness was unreadable) THE SYSTEM SHALL return a
  `DevLoopResult` with `outcome == "approval_failed"` and `ended` starting with
  `APPROVAL_FAILED_ENDED_PREFIX` (`"approval failed: "`).
- IF the approve CWFT ends non-`Succeeded` AND a post-failure
  `check_grant_freshness` shows the grant's digest no longer matches the
  proposal THEN THE SYSTEM SHALL supersede the grant exactly as
  `_supersede_grant_if_stale` does and ask a fresh grant on the SAME `we_`
  (via `_await_canonical_reapproval`), bounded by `MAX_GRANT_SUPERSEDES`,
  instead of ending the loop.
- IF the delegated approve is refused with a typed code that denotes a stale
  or drifted grant THEN THE SYSTEM SHALL take the same re-grant path as above.
- WHEN the approve flip succeeds THE SYSTEM SHALL keep the current behaviour:
  the `we_` ends with the investigator's phase (`Succeeded`), `outcome` is
  empty, and the implementer runs.
- WHEN `restart_if_abandoned` (renamed `restart_if_restartable`, old name kept
  as an alias) reads a COMPLETED run with `implement is None` whose `ended`
  starts with `ABANDONED_ENDED_PREFIX`, `APPROVAL_REFUSED_ENDED_PREFIX` or
  `APPROVAL_FAILED_ENDED_PREFIX` THE SYSTEM SHALL start a new run on the same
  workflow id.
- WHILE a history did not record the new `approval-failure-outcome` patch
  marker THE SYSTEM SHALL replay the previous commands unchanged.
- WHILE the intake poller handles a re-added label THE SYSTEM SHALL keep
  treating a COMPLETED run as already handled (no automatic restart).

## Out of scope
- The mctl-api side: making `restartIfAbandoned` (temporalclient) accept the
  two new prefixes, and surfacing `DevLoopResult.outcome` in
  `GET /api/v1/agents/dev-loop/{workflow_id}` / `mctl_get_dev_loop`. This
  proposal defines the byte-exact prefixes and the result field mctl-api must
  read; the change is a companion mctl-api issue.
- Changing the approve CWFT itself or the digest check from #681.
- Non-canonical (legacy relay) loops' WorkItem behaviour: they own no `we_`;
  they still get the typed `outcome`/prefix on the result.
- Repairing the already-closed run for mctlhq/.github#182.

## Open questions
- Which mctl-api refusal `code` values denote a stale or drifted grant? The
  clone's `DelegatedApproveResult.code` is free-form. The design assumes a
  configurable set (initially codes containing `digest` or `drift`, for
  example `content_digest_mismatch`) and treats every other refusal as a
  terminal `approval_refused`. The implementer must confirm the codes against
  mctl-api.
- The issue asks for the outcome to be visible in `mctl_get_dev_loop`. That
  route today returns Temporal status only, so it depends on the companion
  mctl-api change. Until it ships, the outcome is visible in the
  `DevLoopResult`, the `we_` phase (`Failed`) and the worker log line
  `APPROVAL_OUTCOME`.
- The deployed worker (`services/admins/mctl-agents-worker`) runs image tag
  `1.84.0`. I could not tell from the clone whether that release already
  includes #701 (grant freshness), which this design reuses. The
  implementation targets clone HEAD (`1cfb381`, which includes #701), so
  it ships in a release after that one either way.
- Whether `approval_failed` should map the `we_` to `Error` rather than
  `Failed`. The design uses `Failed` for both, because the canonical
  execution store's terminal set is {Succeeded, Failed, Error} and nothing
  downstream distinguishes `Error` today.
