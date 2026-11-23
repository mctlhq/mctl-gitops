# Deliver the DevLoop approve and abandon signals reliably after the decision is recorded

## Context

On the DevLoop decide page the approval decision is committed first
(`decideDevLoopApproval` writes the grant to `approved`), and the Temporal
`approve` signal is sent second, on the HTTP request context
(`ApproveDevLoopWorkflow` in `internal/api/handlers_dev_loop.go`). If that
context is cancelled between the two steps (client disconnect, aborted
redirect, pod shutdown), the grant stays `approved` and is never `consumed`. The
proposal stays `proposed`, and the workflow stays parked on the approve signal
with nothing logged. Reopening the link leads nowhere ("already approved,
nothing left to decide" or "already used"). This happened on 2026-11-22 to
`dev-loop-mctlhq-.github-41` (grant `aar_10a43ccaf863441c85974a33848a20da`). The
cancel came 35 ms after the decision, and an operator fixed it by hand with
`mctl_approve_dev_loop`.

The abandon signal (`AbandonDevLoopWorkflow`) uses the same request-bound
context. This is the same class of bug as the release-window settle fix
(#1156), which detached only that path. This proposal detaches both DevLoop
signals from the request. It also adds a background redelivery path for
approved-but-unconsumed DevLoop grants, a page state that offers a retry in
place of a dead end, and a metric plus logs for the partial state.

## User stories

- AS a platform admin approving a DevLoop on the decide page I WANT my recorded approval to reach the workflow even if my browser drops the request SO THAT the DevLoop proceeds without operator intervention.
- AS a platform admin reopening a decide link for a grant that is approved but not consumed I WANT to see that state and retry the delivery SO THAT I am not stuck at "Could not decide".
- AS an operator I WANT a metric and an alert for approved DevLoop grants that stay unconsumed SO THAT a stuck delivery is visible before someone asks why a DevLoop is idle.
- AS an operator abandoning a DevLoop I WANT the abandon signal to survive my client disconnecting SO THAT the loop really ends.

## Acceptance criteria (EARS) — revision 2

The following criteria replace the revision-1 acceptance criteria and unresolved assumptions. They are mandatory for any later implementer GO; no production write is authorized by this proposal.

### S1. Request cancellation and bounded delivery

- WHEN an authorized human approval is durably decided THEN the approve signal SHALL use a distinct, deadline-bounded context created by `context.WithTimeout(context.WithoutCancel(requestContext), 15*time.Second)`, not the browser request cancellation context.
- WHEN an already-authorized abandon operation signals Temporal THEN its signal SHALL use the same detached bounded context, preserving its existing explicit run-id binding.
- IF the browser disconnects after the decision was committed THEN delivery SHALL continue until a result or the independent deadline, with an accurate audit trail and without rolling back a human decision.
- IF the 15-second deadline is reached THEN the handler SHALL return a transport failure when possible and leave the existing approved grant eligible for safe reconciliation; it SHALL NOT create or approve a second grant.

### S2. Exactly the authorized Temporal run (P1-1)

- BEFORE sending any recovery signal THE SYSTEM SHALL establish the immutable association of (execution_id, workflow_id, concrete Temporal run_id, approval_ref, approved context/content digest, approval attempt). A workflow-id-only or `#xr_` engine reference is NOT sufficient evidence of run identity.
- WHEN the reconciler sends an approve signal THE SYSTEM SHALL target that exact run via a run-bound Temporal client method, equivalent in run pinning to `SignalAbandon`; an empty/latest run id SHALL NOT be used.
- IF the execution/run association cannot be proven, the run is no longer Running, or a continuation/restart changes its identity THEN the reconciler SHALL fail closed and expose a typed reason; it SHALL NOT signal the latest run as fallback.
- WHEN the run changes between Describe and Signal THEN Temporal MUST reject delivery to the old closed run or deliver only to the original still-running run. The new run SHALL never receive the old grant.
- This protection SHALL also apply to the authenticated manual retry path and shall not remove the worker's existing current-approval-ref guard.

### S3. Current grant, context, freshness and content (P1-2, P2-1)

- BEFORE claiming a delivery attempt and AGAIN just before signalling THE SYSTEM SHALL verify the grant is still the newest approval for its execution/attempt, state approved, not consumed, not denied/superseded, within both `expires_at` and `fresh_until` (if set), and bound to the exact workflow/run.
- THE SYSTEM SHALL compare the recorded `decided_context_digest`, action intent/target, approved artifact/content digest and current proposal content digest. An unreadable repository/digest or an ambiguous grant/run/attempt mapping SHALL fail closed; cached digest guesses SHALL NOT authorize delivery.
- WHEN a proposal changes and a new grant is pending/approved, or a previous run was abandoned/restarted, the older approved grant SHALL NOT be redelivered even if its database row remains approved.
- No reconciler or retry SHALL change a grant's decision, issue an MFA decision, create a replacement grant, change the proposal status, or consume the grant on the user's behalf.
- A successful Temporal signal acknowledgement SHALL NOT be equated with grant consumption or with the proposal being accepted: report those stages separately.

### S4. Cross-replica retry, restart and failure semantics (P2-2)

- THE SYSTEM SHALL use the existing durable approved-grant ledger as the source of pending delivery intent. It SHALL add a database-backed per-grant delivery lease / attempt record, or an equivalently proved atomic coordination mechanism, to fence competing reconcilers across replicas. An in-process `lastSent` map is not sufficient as the delivery gate.
- A lease SHALL have a bounded expiry, a unique owner/fencing token, a durable last-attempt/result and a database-enforced retry backoff. Expired workers SHALL NOT settle another worker's lease.
- WHEN the deciding pod terminates or a lease-holder crashes THEN another replica SHALL recover the undelivered, still-authorized grant from durable state after lease expiry/backoff. An ambiguous signal result MAY cause at-least-once delivery to the SAME pinned run and SAME grant only; worker spending remains compare-and-set and no exactly-once transport guarantee is claimed.
- WHEN two replicas compete to deliver one grant THEN at most one SHALL hold its active delivery lease. Duplicate delivery caused by a crash/retry MUST be tested as safe, and bounded to the pinned run.
- Candidate selection SHALL use a keyset-paged, snapshot-consistent enough enumeration that does not silently miss older grants, with a separately computed accurate count for monitoring.

### S5. MFA page retry, authorization and state transitions (P2-3)

- WHEN the signed-in administrator opens a binding-matched, already approved but unconsumed grant THEN the page SHALL say `Approved — delivery not confirmed` and offer retry without presenting another approve/reject decision.
- WHEN the user presses Retry THE SYSTEM SHALL validate a new CSRF-protected, browser-bound, one-use challenge whose offered action is explicitly `redeliver`, revalidate the authenticated platform admin (including the established MFA semantics), and re-read exact newest grant, decision identity/actor policy, context digest, content digest, freshness, execution and run ownership before sending.
- The manual retry SHALL use a delivery-only method that refuses pending/denied/consumed/expired/superseded grants; it SHALL NOT fall back to the regular `DecideActionApproval` path, mint a grant, or re-use an already-spent decision challenge.
- Whether a different platform admin may re-deliver an approved decision MUST be an explicit policy; for this slice, require the original deciding principal or an independently authorized platform-admin recovery role, with audited identity and no impersonation.
- WHEN grant state changes between page render and POST THEN re-read and fail closed, rendering a factual state rather than sending a signal. A consumed grant SHALL show `Already consumed`; signalled-but-unconsumed SHALL say only `Delivery attempted`, not `DevLoop received`.

### S6. Observability and dark launch (P2-4, P2-6)

- THE SYSTEM SHALL expose a correct gauge of all eligible approved-but-unconsumed grants older than the minimum age, regardless of page size, with an explicit failure/staleness indicator if a DB scan fails; a truncated batch count MUST NOT masquerade as a total.
- THE SYSTEM SHALL emit bounded-label counters for `claimed`, `signalled`, `signal_failed`, `run_mismatch`, `stale_grant`, `claim_lost`, `describe_failed`, `run_closed`, and `disabled` where appropriate; log workflow_id, run_id, approval_ref, execution_id, age, attempt number and typed reason without secrets.
- The alert `mctl_devloop_approval_undelivered > 0 for 10m` SHALL have an explicitly owned monitored deployment location (e.g. governed GitOps monitoring config) or a distinct tracked follow-up with an owner and gate; do not claim the alert deployed from this API PR alone.
- `DEVLOOP_APPROVAL_REDELIVER_ENABLED` SHALL default to FALSE. The new reconciler SHALL first be validated in read-only/dry-run mode with synthetic/fake Temporal, then require a separate owner GO and a digest/image-pinned rollout for enabling any real resends.
- WHEN disabled, the reconciler SHALL perform no Temporal mutations. Rollback SHALL disable it without deleting the durable grant or delivery state; a change to the detached HTTP signal helper remains a separately reviewable containment fix.

### S7. Evidence and test matrix (P2-5)

- Tests SHALL deterministically exercise: begin signal -> cancel browser request -> independently release fake signal -> observe success, and separately test the 15s detached timeout; tests must not wait for the signal context to cancel when the browser cancels.
- Tests SHALL cover old-run-to-new-run races, unpinned `engine_ref`, restart, ContinueAsNew, abandoned run, latest-run mismatch, old approved grant followed by new pending/approved, changed proposal digest, wrong actor, stale `fresh_until`, and database/repository/Temporal unavailable.
- Tests SHALL cover two reconcilers contending for the same grant, lease expiry/restart, ambiguous transport outcome, bounded retries, pagination above the batch limit, telemetry failures and stale grant count.
- MFA page tests SHALL include exact binding, new/changing grant between GET and POST, consumed/expired/denied grants, different admin, one-time challenge reuse and cancelled POST.
- CI SHALL run actual Go test/vet/lint and Postgres-backed store/lease migration tests before any merge; a source-only assertion is insufficient.

## Out of scope

- No change to the mctl-agents signal parser is assumed necessary, but its existing current-ref and consume CAS guarantees must be covered by integration evidence.
- No rollback of a human approval on signal failure; no automatic new MFA decisions or production deploy.
- No automatic abandon replay without its own durable decision record; only the bounded detached signal is in scope.
- Release-window, deploy, commerce and Glovo approval semantics remain outside this slice.
- A real MCP Tasks adapter and mctlhq/.github PR #387/#388 are separate workstreams.

## Resolved architecture decisions and still-required evidence

- The intended authorization model is **at-least-once delivery to a single immutable Temporal run**, **at-most-once consumed grant**, with a durable fenced claim and fail-closed current-grant revalidation. No exactly-once end-to-end transport claim.
- Approved grant rows are durable intent; a new small lease/attempt table (migration subject to review) is recommended for coordination and observability. A transactional full outbox may be substituted only with an equally testable proof.
- Decision freshness is configuration-dependent: `h.maxDecisionAge()` defaults to 24 hours, but deployment overrides remain possible. Never infer spendability from `expires_at` alone.
- Existing chart default `replicaCount: 1` is NOT evidence of the deployed replica count, and observed worker consume latency does not define a safety guarantee.
- The alert deployment owner/path, exact current run-identity persistence route for unpinned engine refs, and migration/index evidence must be resolved **in revision-2 review** before owner approval; no hand-wave implementation fallback is allowed.
