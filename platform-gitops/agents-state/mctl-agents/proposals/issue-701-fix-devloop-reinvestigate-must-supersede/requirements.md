# fix(devloop): reinvestigate must supersede the pending approval grant

## Context
A canonical DevLoop (`CANONICAL_APPROVAL_PATCH`, mctl-agents#636) parks on an `aar_` grant whose `artifact_hash` is the proposal content digest it read when it created the grant (`request_devloop_approval`, mctl-agents#681). `@MCTL reinvestigate` goes through the directive poller (`orchestrator/run_issue_directive_poller.py`), which by design never signals a DevLoop. It rewrites the proposal and leaves the grant alone. In the 2026-10-18 incident (mctlhq/.github#182) the owner reviewed v2, the approval landed on the v1-bound grant, the grant was consumed, and the approve CWFT refused the flip (#681 working as intended). The loop then ended `Completed` with "approve flip refused", and it cannot be restarted on its workflow id (mctl-agents#702).

This proposal makes the DevLoop own the link between the proposal and its grant. The loop never presents a grant whose bound digest differs from the current proposal digest. It supersedes that grant with an audited reason that names both digests, then asks for a fresh grant on the same `we_` as a new attempt. The loop stays decidable and no stale approval is ever spent. This is option 1 (supersede) from the issue. The supersede runs as a check inside the loop rather than as a signal from the directive poller.

## User stories
- AS a proposal owner I WANT an approval I give for a rewritten proposal to be asked again against the current bytes SO THAT my decision is never spent on content I did not see.
- AS a proposal owner I WANT the loop to show me the digest I am deciding next to the digest of the current files SO THAT I can tell when a grant is stale.
- AS a platform operator I WANT every supersede recorded with the old and the new digest SO THAT an incident like mctlhq/.github#182 can be reconstructed from the audit trail.
- AS a platform operator I WANT a rewrite to leave the loop parked and decidable SO THAT no loop is stranded as `Completed` because of a reinvestigation.

## Acceptance criteria (EARS)
- WHEN a canonical DevLoop creates an approval grant THE SYSTEM SHALL record in workflow state the grant's bound `content_digest` and `content_commit` from `ApprovalRequestResult`.
- WHEN a canonical DevLoop is about to run `_delegated_approve`, THE SYSTEM SHALL first re-read the proposal content digest at one resolved gitops commit, using the same reader as #681 (`read_proposal_content_digest`).
- IF the re-read digest differs from the digest bound to the current grant THEN THE SYSTEM SHALL NOT call `submit_delegated_approve` with that grant. It SHALL clear `_approval_ref`, `_requested_ref`, `_approved` and `_signalled_refs`, increment `_approval_attempt`, set `_grant_refresh`, and park again for a fresh grant on the same `we_`.
- WHEN a grant is superseded THE SYSTEM SHALL emit one structured audit record `GRANT_SUPERSEDED` naming the old `aar_`, the old digest and commit, the new digest and commit, the `we_`, the `<service>/<slug>`, and the reason `superseded: proposal rewritten`.
- WHEN a grant is superseded THE SYSTEM SHALL post one comment on the source issue naming the superseded `aar_`, the digest it was bound to, the current digest, and the fresh `aar_` to decide.
- WHILE a canonical DevLoop is parked on a pending grant THE SYSTEM SHALL re-check the proposal digest at a bounded interval (`GRANT_FRESHNESS_INTERVAL`, 15 minutes). On a mismatch it SHALL supersede the grant before any decision arrives.
- IF the proposal digest cannot be read (`ProposalListingError` / `DelegatedApprovalUnavailable` after retries) THEN THE SYSTEM SHALL NOT present the grant. It SHALL keep the loop parked and retry at the next tick. An unreadable digest SHALL never count as a match.
- IF the re-read digest equals the bound digest THEN THE SYSTEM SHALL proceed exactly as today: one grant, approve, and the flip records that digest (the #681 chain is unchanged).
- WHILE a grant has been superseded THE SYSTEM SHALL never adopt that `aar_` again from an `approve` signal or from a `request_devloop_approval` answer.
- IF supersedes for one loop exceed `MAX_GRANT_SUPERSEDES` (8) THEN THE SYSTEM SHALL end the loop with `ended="approval superseded too many times"` and SHALL NOT park indefinitely.
- WHERE an execution history was recorded before this change (no `grant-freshness` patch marker), THE SYSTEM SHALL replay the existing command sequence unchanged.

## Out of scope
- Changing #681's CWFT check (`flip-status` digest refusal). It behaved correctly and remains the last line of defense.
- Making the free-text approval `reason` carry or check a digest.
- Making the directive poller signal or start a DevLoop. Its independence invariant (module docstring) is kept.
- Restarting loops already closed as `Completed` by this bug (mctl-agents#702).
- Any mctl-api change, such as a server-side grant withdraw/deny endpoint or a decision-time digest check in mctl-api. See Open questions.

## Open questions
- mctl-api exposes no withdraw/deny route to the worker. `orchestrator/action_approvals.py` `ROUTES` has only create, get and consume. A superseded grant therefore stays `pending` (or `approved`, if a human already decided it) in mctl-api's store until it expires, and the UI can still show it. In this proposal no consumer ever presents it: the loop is the only spender and drops the ref. If mctl-api adds a withdraw route later, the supersede step should call it. Should an mctl-api issue be filed for that?
- Showing "the digest you are deciding vs. the digest of the current files" in the approval UI (Telegram/portal) is an mctl-api/surface change. This proposal covers it through the issue comment and the audit record only.
- A 15-minute freshness tick can still let a human decide a stale grant inside the window, as in the incident (7 minutes). The decision-time check catches that case, so nothing is spent, but the human is asked again. Is a shorter tick worth the extra GitHub reads (5 reads per tick per parked loop)?
