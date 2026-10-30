# Design: issue-701-fix-devloop-reinvestigate-must-supersede

## Current state

- `orchestrator/temporal/workflows/dev_loop.py`
  - `CANONICAL_APPROVAL_PATCH = "canonical-approval"` gates the grant-based approval path (#636).
  - `_request_canonical_approval()` (around line 2007) looks up the slug (`find_proposal_slug`) and calls the `request_devloop_approval` activity with `ApprovalRequestInput(execution_id, service, slug, ttl_seconds, attempt=self._approval_attempt)`. It stores `self._approval_slug` and `self._requested_ref`. It discards `requested.content_digest` and `requested.content_commit`, which are returned "for the record only".
  - The approval park (around lines 3520-3570, under `workflow.patched("approval-watch")`) waits on `self._is_approved() or self._abandoned or self._grant_refresh` with `APPROVAL_POLL_INTERVAL = 6h` ticks. Each tick reads only the issue state. On `_grant_refresh` it calls `_request_canonical_approval()` again.
  - `_take_resume_provenance()` (around line 1974) is the only existing "this grant is now the wrong attempt's" transition. It clears `_approved/_approval_ref/_requested_ref/_signalled_refs`, sets `_grant_refresh = True`, and bumps `_approval_attempt`. Proposal rewrites never trigger it.
  - The `approve` signal (around line 1892) adopts `approval_ref` only when it equals `_requested_ref`.
  - The flip is `_delegated_approve()` (around line 2096, called around line 3717). It refuses only when the slug changed (`slug != self._approval_slug`). Any CWFT refusal ends the loop: `ended="approve flip refused: ..."`, so the workflow completes. This is how the incident loop closed as `Completed` (#702).
- `orchestrator/temporal/activities/delegated_approval.py`
  - `request_devloop_approval` reads `read_proposal_content_digest(service, slug)` and binds it as `ActionIntent.artifact_hash` via `approval_intent()`. The key is `aa.idempotency_key(intent, attempt)`, which includes the intent hash, so a new digest is already a new key.
  - `submit_delegated_approve` mints the run token and exercises the grant. mctl-api consumes the grant here, and the CWFT is given the grant's bound digest as `expected_content_digest`.
- `orchestrator/temporal/activities/proposals.py::read_proposal_content_digest` resolves gitops `main` to one SHA and reads `PROPOSAL_DIGEST_FILES` at that SHA. It returns `(content_digest_of(files), sha)` and raises `ProposalListingError` on anything unreadable. This is the "same reader as #681".
- `orchestrator/proposal_state.py::content_digest_of` / `approval_digest_problem` are the canonical digest and its CWFT-side check.
- `orchestrator/action_approvals.py::ActionApprovalClient` has `ROUTES` create/get/consume only. There is no deny or withdraw route.
- `orchestrator/run_issue_directive_poller.py` is the module that "never starts or signals a DevLoopWorkflow". It calls `submit_investigate` (the `mctl-agents-investigate` CWFT), which rewrites the proposal directory on gitops main.
- Tests: `tests/test_dev_loop_workflow.py` already stubs `request_devloop_approval` (`fake_request_devloop_approval`, around line 259) and runs the workflow in a time-skipping environment. `tests/test_delegated_approval.py` and `tests/test_proposal_digest.py` cover the activity and the digest.

Deployed state checked:
- `/workdir/mctl-gitops/platform-gitops/services/admins/mctl-agents-worker/values.yaml`: the worker is deployed under tenant `admins`, `image.tag: "1.84.0"`. Sibling services are `mctl-agents-worker-exec` and `mctl-agents-worker-implement` in the same tenant. Only the control worker's tag was read. Per `orchestrator/temporal/worker.py`, `request_devloop_approval` is registered on the worker that serves the DevLoop.
- mctl MCP tools were not called. The fix is worker code and needs no runtime config. Live DevLoop and grant state for the incident loop was not observed and is taken from the issue text.

## Proposed solution

The DevLoop is the only consumer of its grant, so it is the right place to make the two lifecycles atomic. Before presenting a grant it proves the grant still describes the current bytes. If not, it supersedes the grant and asks again. The directive poller stays independent: the loop detects the rewrite itself, through the same digest reader #681 uses.

1. **Remember what the grant binds.** Add `self._approval_digest` and `self._approval_commit` to `DevLoopWorkflow`, set from `requested.content_digest` / `requested.content_commit` in `_request_canonical_approval()`. Add `self._superseded_refs: list[str]` (bounded like `_signalled_refs`) and `self._supersede_count`.

2. **New read-only activity `check_grant_freshness`** in `orchestrator/temporal/activities/delegated_approval.py`:
   ```python
   @dataclass(frozen=True)
   class GrantFreshnessInput:  service: str; slug: str; bound_digest: str
   @dataclass(frozen=True)
   class GrantFreshnessResult: fresh: bool; current_digest: str; current_commit: str
   ```
   It calls `read_proposal_content_digest`, compares with `bound_digest`, and raises `ApplicationError(type=UNAVAILABLE_TYPE)` on `ProposalListingError`, so an unreadable digest is never "fresh". It is registered in `orchestrator/temporal/worker.py` next to `request_devloop_approval`.

3. **`_supersede_grant_if_stale(issue, target_repo, slug) -> bool`** on the workflow:
   - Runs `check_grant_freshness` (FAST timeout and retry policy). An `ActivityError` returns "not fresh, not superseded": the caller keeps waiting and does not flip.
   - On a mismatch it emits `workflow.logger.warning("GRANT_SUPERSEDED aar=%s we=%s target=%s/%s old_digest=%s old_commit=%s new_digest=%s new_commit=%s reason=%s", ...)` with reason `superseded: proposal rewritten`. This matches the existing `MERGE_APPROVED ...` structured-log audit convention at around line 4745. It also posts an issue comment with both digests through the existing issue-comment activity the loop already uses for replies. If that activity does not exist, a small new `post_issue_comment` activity is added, kept best-effort.
   - It then applies the same reset `_take_resume_provenance` uses: it appends the old ref to `_superseded_refs`, clears `_approved/_approver/_approval_ref/_requested_ref/_signalled_refs`, increments `_approval_attempt` and `_supersede_count`, and sets `_grant_refresh = True`.
   - Over `MAX_GRANT_SUPERSEDES = 8` it returns a terminal `DevLoopResult(ended="approval superseded too many times")`.

4. **Decision-time check (the incident path).** In the canonical branch, call `_supersede_grant_if_stale` immediately before `self._delegated_approve(target_repo, slug)` (around line 3717). If it superseded, re-enter the canonical re-approval park (`_await_canonical_reapproval`, which already requests a fresh grant on `_grant_refresh`) and loop. The loop does not end. `submit_delegated_approve` is never called with the stale `aar_`, so mctl-api never consumes it and no approve CWFT runs with the v1 digest.

5. **Proactive check while parked.** In the canonical approval park loop, replace the single 6h wait with an inner wait of `GRANT_FRESHNESS_INTERVAL = 15min`. On each freshness tick, run `_supersede_grant_if_stale`. Keep the issue-state read at the existing 6h cadence, based on elapsed time. A supersede sets `_grant_refresh`, and the existing branch requests the fresh grant. The deadline (`CANONICAL_APPROVAL_WAIT`) stays bounded from the start of the park, as #420 requires. History cost is about 672 ticks per 7 days, roughly 4k events, well under the 50k limit.

6. **Never re-adopt a superseded ref.** In the `approve` signal, ignore an `approval_ref` in `_superseded_refs`. In `_request_canonical_approval`, treat a returned ref in `_superseded_refs` as a refusal and bump the attempt. This cannot normally happen, because the new digest means a new intent and a new key.

7. **Replay safety.** All new commands (the freshness activity, the shorter timer, the comment) are behind one new marker, `GRANT_FRESHNESS_PATCH = "grant-freshness"`, evaluated once when the canonical park begins and stored on `self`. Pre-patch histories replay byte-identically. The marker is only meaningful when `self._canonical` is true. The legacy, non-canonical path already flips via the direct CWFT, has no bound grant, and is unchanged.

Happy path: no rewrite, so every check reports fresh, the single grant is approved, `_delegated_approve` runs, and the flip records the same digest (the #681 chain). The only difference is one extra read before the flip and the 15-minute freshness reads.

## Alternatives

- **Directive poller supersedes the grant.** After `submit_investigate`, the poller would signal the DevLoop or call mctl-api to deny the grant. Dropped: it breaks the poller's documented "never starts or signals a DevLoopWorkflow" invariant, and its acceptance test pins that. It also misses rewrites from any other path (a manual gitops edit, the investigator re-running), and the poller has no `we_` or `aar_` to name. A check in the loop covers every writer.
- **Refuse at decision time in mctl-api (option 2 only).** mctl-api's decision handler would compare `artifact_hash` with the current digest. Dropped as the primary fix: mctl-api has no gitops reader for proposal content, and it treats `artifact_hash` as opaque (`approval_intent` docstring). It would also be a cross-repo change. It remains a good follow-up for UI visibility (see Open questions).
- **Rely on #681 alone and restart the loop on a flip refusal.** Dropped: the grant is consumed by then, and the issue asks that the v1 grant not be spendable. Restart also hits #702 (the workflow id is closed).

## Platform impact

- **Migration / compatibility:** none for data. A new Temporal patch marker means in-flight loops parked before deploy keep the old behaviour, so a loop parked today is still exposed to this bug until it finishes. New loops get the fix. Worker image bump only, for `mctl-agents-worker` in tenant `admins`.
- **Resource impact:** 5 GitHub API reads (1 commit resolve and 4 files) per parked canonical loop every 15 minutes, plus 5 before each flip. Negligible against the GitHub App rate limit for the handful of parked loops.
- **Risks and mitigations:**
  - A GitHub outage stalls approvals. Mitigation: unreadable means not presented and retried; the park stays bounded by `CANONICAL_APPROVAL_WAIT`, so nothing is stuck forever.
  - A supersede loop (repeated rewrites) asks the human many times. Mitigation: `MAX_GRANT_SUPERSEDES` ends the loop with a clear reason, and every supersede is commented on the issue.
  - Stale grants remain visible in mctl-api until they expire. Mitigation: no spender presents them, the issue comment names the fresh `aar_`, and #681 refuses anything that slips through.
  - Non-determinism. Mitigation: a single patch marker plus a replay test against a recorded pre-patch history, following the existing `tests/test_dev_loop_workflow.py` replay pattern.
