# Controlled, lease-aware operator drain for outstanding execution requests

## Context
The mctl-agents#996 (M1) review found that the existing reject path cannot be used to drain outstanding
execution requests. `POST /api/v1/execution-requests/{request_id}/reject` (`RejectExecutionRequest` in
`internal/api/handlers_execution_requests.go` and `internal/workitems/execution_requests.go`) admits only the
service principal acting directly. It also requires a request in state `claimed`, an unexpired lease, and a
matching `claimed_by` and `claim_token`. Reads never serialize `claim_token` (`json:"-"`). The only per-item list
is newest-first and capped at 100. No global enumeration exists. The only targeted way to obtain a token is
`POST /execution-requests/claim`, which takes the oldest claimable request out of 8 candidates. With the
queue-while-active switch on, it also skips every request queued behind an open execution. So the runbook step
"pause dispatcher -> list -> reject by id" is invalid. Requests the mctl-agents dispatcher left claimed after a
deferral (`legacy-loop`, `feedback-not-ready`, `recovery-not-ready`) cannot be drained by any supported path, and
neither can pending requests.

This proposal is a spike plus a design. It defines the smallest new mctl-api capability for an explicitly
authorized, bounded, auditable drain. A direct human administrator pages through open requests with a stable
cursor, then rejects selected requests one at a time. Each reject is guarded by a compare-and-set on a new
per-request `revision`. A reject is refused while any lease is live, so an owned claim is never taken. Everything
not selected stays untouched. The capability ships dark behind a default-off switch. This proposal authorizes no
release, deployment or flag change. M1 must still not be rolled out to production as a partial release until M3
and this drain path exist.

## User stories
- AS a platform operator I WANT to page through every open (pending or claimed) execution request across tenants, with its lease state and whether it is queued behind an open execution, SO THAT I can decide what to drain without the dispatcher and without claim tokens.
- AS a platform operator I WANT to reject one explicitly selected request, with a logged reason, only when nobody holds a live claim on it, SO THAT I can clear deferred or stuck work before a worker-image rollback without racing a live dispatcher.
- AS the execution platform (dispatcher) I WANT a lapsed or superseded claim to be refused on fulfil after an operator reject, SO THAT a re-claim or late fulfil can never record a false `Succeeded`.
- AS an auditor I WANT every drain read and reject recorded with the human actor, request id, prior state, prior claimant and reason, SO THAT a drain can be reconstructed after the fact.

## Acceptance criteria (EARS)

Discovery
- WHEN a direct human administrator (`isHumanAdmin`) calls `GET /api/v1/execution-requests/open` THE SYSTEM SHALL return at most `limit` (1..100, default 50) open requests ordered by `(created_at, id)` ascending, plus an opaque `next_cursor` while more rows exist.
- WHEN a caller presents `cursor` THE SYSTEM SHALL return only rows strictly after the cursor's `(created_at, id)` under the same filters. A cursor issued for other filters SHALL be refused with 400 `invalid_cursor`.
- THE SYSTEM SHALL include in each row: the request fields already returned by `GET /work-items/{id}/execution-requests/{request_id}`, plus `revision`, `lease_state` (`pending`, `claimed_live` or `claimed_lapsed`, computed against the server clock), `claimed_by`, `claim_expires_at`, the item's `tenant`, `state` and `state_version`, and `open_execution_id` when the item has a non-terminal execution.
- THE SYSTEM SHALL NOT include `claim_token` in any discovery row, error or audit entry.
- WHILE the queue-while-active switch is on THE SYSTEM SHALL still list requests queued behind an open execution, because discovery does not use the claim candidate query.
- IF the caller is the service principal, a relayed surface, a surface identity or a non-admin THEN THE SYSTEM SHALL answer 403 `execution_request_operator_forbidden` and audit the refusal.
- IF the store cannot be read THEN THE SYSTEM SHALL answer 503. It SHALL NOT answer an empty list.
- WHERE `tenant` or `state` filters are given THE SYSTEM SHALL apply them in SQL before the limit, and SHALL still check each row's item with `canSeeWorkItem`.

Operator reject
- WHEN a direct human administrator calls `POST /api/v1/execution-requests/{request_id}/operator-reject` with `expected_revision`, `reason` and `idempotency_key`, and the request's current revision equals `expected_revision`, and the request is `pending` or `claimed` with `claim_expires_at <= now`, THE SYSTEM SHALL move it to `rejected` in one transaction under the item's advisory lock. In that transaction it SHALL record `reason`, `closed_at`, `rejected_by` (the operator), `rejection_kind = operator`, clear `claim_token`, increment `revision`, append an `execution_request_operator_rejected` event and answer 200.
- IF the request is `claimed` and `claim_expires_at > now` THEN THE SYSTEM SHALL refuse with 409 `execution_request_claim_live`, return `claim_expires_at` and `claimed_by`, and change nothing.
- IF the request's revision differs from `expected_revision` THEN THE SYSTEM SHALL refuse with 412 `execution_request_revision_moved`, return the current `revision`, `state` and `lease_state`, and change nothing.
- IF the request is already `fulfilled` or `rejected` THEN THE SYSTEM SHALL refuse with 409 `execution_request_closed`. A same-actor replay with the same `idempotency_key` and the same body SHALL instead return the stored rejected request with 200 and `replayed: true`.
- IF `reason` is empty, longer than 1024 bytes or contains a secret-shaped value THEN THE SYSTEM SHALL refuse with 400 and change nothing.
- IF the operator-drain switch `MCTL_EXECUTION_REQUEST_OPERATOR_DRAIN` is not `on` THEN THE SYSTEM SHALL answer 404 on both new routes.
- THE SYSTEM SHALL accept exactly one request id per call. No batch, filter-based or automatic reject exists.
- THE SYSTEM SHALL NOT create, approve, consume or alter any execution, action approval, DevLoop approval grant or work item state when it rejects a request.

Fencing
- WHEN a claim, fulfil, dispatcher reject or operator reject changes a request THE SYSTEM SHALL increment its `revision` in the same UPDATE.
- WHEN a previous claimant presents its claim token to fulfil or reject a request that an operator rejected THE SYSTEM SHALL refuse with 409 `execution_request_closed`, as today for a rejected request.
- WHILE an operator reject transaction holds the item lock THE SYSTEM SHALL serialize it with claim, fulfil and dispatcher reject of the same request, so exactly one of them takes effect and the others observe the result.
- IF a dispatcher re-claims a lapsed request between an operator's discovery read and reject THEN THE SYSTEM SHALL refuse the reject with 412 (revision moved) or 409 (claim live).

Audit
- WHEN an operator reject succeeds THE SYSTEM SHALL write an audit entry with `RiskHigh`, containing the operator, request id, work item id, tenant, prior state, prior `claimed_by`, prior `claim_expires_at` and `revision`. The audit entry SHALL NOT contain the token. The reason text SHALL be stored on the row only, as for the dispatcher reject.
- WHEN an operator reject is refused for authorization, a live claim, a moved revision or a closed request THE SYSTEM SHALL write a failed audit entry with the typed code.

## Out of scope
- Rolling out, deploying or turning on `MCTL_EXECUTION_REQUEST_OPERATOR_DRAIN`, `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE` or the dispatcher flag. This proposal authorizes none of these.
- Any change to mctl-agents (the dispatcher, its deferral reasons or its handling of `execution_request_closed`), beyond stating what the E2E test expects from it.
- MCP tools for the new routes. If added later, each tool must be a mutating, policy-checkpoint-gated tool, and the `server_test.go` tool count must change with it.
- Tenant self-service drain by tenant admins. This version is for platform administrators only.
- A "release back to pending" operation. To preserve a request, the operator leaves it alone.
- Storing dispatcher deferral reasons in mctl-api.
- Any data migration that rewrites existing rows, other than adding nullable or defaulted columns.

## Open questions
- Deferral reasons (`legacy-loop`, `feedback-not-ready`, `recovery-not-ready`) exist only in mctl-agents logs. mctl-api cannot show them in discovery. Should a later change let the claimant annotate a deferral, so the operator can see it in discovery? Assumed no for this proposal. The operator correlates by request id with mctl-agents logs.
- Is one direct human administrator enough authority, or should each operator reject also consume a single-use action approval (mctl-api#366) decided by a second admin? Assumed one admin plus revision CAS, reason and audit. The second-person gate is designed as an optional extension (see design.md, Alternatives).
- What is the deployed mctl-api configuration (replicas, whether `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE` is on)? The gitops checkout available to this run has no mctl-api service values. The repo default is `helm/values.yaml` `replicaCount: 1`. This was not verified against production.
- Does a clock skew bound between API replicas matter? `lease_state` and the live-claim check both use the database transaction's `s.now()` in one replica's process. The proposal assumes the API host clock, as `ClaimExecutionRequest` already does.
