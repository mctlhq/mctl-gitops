# Durable manual review-receipt adapter (Tier B, Slice B)

## Context

mctl-api#897 is Slice B of the Tier B adapter for independent review receipts
(epic mctlhq/.github#281, slice mctlhq/mctl-agents#905). Slice A (mctl-api#895)
has merged as the pure library `internal/reviewreceipts`. It holds the Tier A
types (`ReviewRequest`, `ReviewReceipt`, `ReviewSubject`), strict parsing
(`ParseRequest`, `ParseReceipt`), identity recomputation (`SealRequest`,
`SealReceipt`) and `EvaluateReviewGate`. It does no I/O. This slice makes the
library durable and reachable. It adds Postgres tables for requests, receipts
and nonce consumptions, REST routes that ingest sealed requests and accept
manual advisory receipts from a direct human admin, a complete-pool read, a
gate read, and two MCP tools.

The work matters because a review gate is only as trustworthy as its pool. A
pool that is silently truncated, or a receipt that a service principal can
mint, would let `EvaluateReviewGate` answer `satisfied` on evidence that does
not exist. Every read in this slice therefore fails closed. A manual receipt is
structurally advisory and can never satisfy `required_assurance=independent`.
The worker path stays disabled until Slice C (mctl-api#896) supplies an
authoritative `execution_id -> attempt_id + lineage_root`.

## User stories

- AS an authoring agent run (the evidence writer) I WANT to register the sealed
  Tier A `ReviewRequest` for the subject I produced SO THAT a reviewer's
  receipt can later be bound to exactly those bytes.
- AS a direct human platform admin I WANT to submit a manual advisory review
  assertion against an open request SO THAT a human review is recorded durably
  and is visible to the gate as advisory.
- AS a gate consumer (DevLoop, mctl-agents Tier A) I WANT the complete receipt
  pool in ingest order, or a typed error SO THAT I never evaluate a gate on a
  truncated or empty-by-failure pool.
- AS an operator I WANT `mctl_get_review_gate` to return the verdict together
  with the full Tier A gate input SO THAT the answer can be re-evaluated
  byte-for-byte by Tier A.
- AS an auditor I WANT every request and receipt to be immutable and audited SO
  THAT a review trail cannot be rewritten after the fact.

## Acceptance criteria (EARS)

Storage

- WHEN mctl-api starts with a review store configured THE SYSTEM SHALL create
  `review_requests`, `review_receipts` and `review_nonce_consumptions` with
  `CREATE ... IF NOT EXISTS` and guarded trigger creation, so a second start is
  a no-op.
- WHILE a row exists in any of the three tables THE SYSTEM SHALL refuse every
  `UPDATE` on it through a `BEFORE UPDATE` trigger.
- THE SYSTEM SHALL give every request and receipt row a database-assigned,
  strictly increasing `ingest_seq` (`BIGINT GENERATED ALWAYS AS IDENTITY`), and
  every pool read SHALL be ordered by `ingest_seq ASC`.
- THE SYSTEM SHALL enforce `CHECK (mode <> 'manual' OR assurance = 'advisory')`
  on `review_receipts`.
- THE SYSTEM SHALL store `nonce_sha256` (hex SHA-256 of the request nonce) on
  `review_requests` under a UNIQUE index and SHALL keep the nonce itself only
  inside the verbatim sealed document. It SHALL never generate a nonce.

Request ingestion (`POST /api/v1/review-requests`)

- WHEN a caller with `evidence:write` posts a document THE SYSTEM SHALL parse it
  with `reviewreceipts.ParseRequest`, recompute `content_hash` and `request_id`,
  and store the received bytes verbatim.
- IF the document fails Slice A parsing THEN THE SYSTEM SHALL answer 400 with
  the Slice A code (`review_malformed`, `review_unknown_key`,
  `review_bad_subject`, `review_bad_identity`, `review_rubric_mismatch`).
- IF the document omits `content_hash` or `request_id` THEN THE SYSTEM SHALL
  answer 400 `review_unsealed`. Only sealed documents are ingested.
- IF `authoring_execution_id` is empty, or does not resolve to at least one
  stored ExecutionEvidence record (`evidence.Store.List` with `ExecutionID` for
  `we_` ids or `RuntimeExecutionID` for `ex-` ids), THEN THE SYSTEM SHALL
  answer 422 `review_authoring_unresolved`.
- IF the evidence store cannot answer THEN THE SYSTEM SHALL answer 503
  `review_evidence_unavailable`, never "unresolved".
- THE SYSTEM SHALL derive the request's tenant from the resolved evidence
  record's `Ref.Tenant`. IF that tenant is empty THEN THE SYSTEM SHALL answer
  422 `review_tenant_unresolved`.
- IF the body (outside the sealed document) carries `tenant` or `submitted_by`
  THEN THE SYSTEM SHALL answer 400 `review_unknown_key`.
- WHEN the same `request_id` with identical bytes is posted again THE SYSTEM
  SHALL return the stored row with 200 and `replayed: true`.
- IF a stored `request_id` is posted again with different bytes THEN THE SYSTEM
  SHALL answer 409 `review_request_conflict`.
- IF a different request carries a nonce whose `nonce_sha256` is already stored
  THEN THE SYSTEM SHALL answer 409 `review_nonce_reused`.

Closing

- WHILE a request's `ingested_at + REVIEW_REQUEST_TTL` is in the past THE
  SYSTEM SHALL treat it as closed (`closed_reason: ttl`). `REVIEW_REQUEST_TTL`
  is server policy, a Go duration, default `24h`.
- WHILE a later-ingested request exists with the same subject identity and a
  different subject binding THE SYSTEM SHALL treat the earlier request as
  closed (`closed_reason: superseded`, `closed_by: <request_id>`).
- WHEN a request with the same identity and the same binding is ingested THE
  SYSTEM SHALL close no existing request.
- THE SYSTEM SHALL compute closure at read time and SHALL never store it as an
  update.

Manual advisory submission (`POST /api/v1/review-receipts/manual`)

- IF the caller is not `isHumanAdmin`, or `CheckHumanPrincipal` does not
  confirm an active human principal, THEN THE SYSTEM SHALL answer 403
  `review_not_permitted`. A principal-store failure answers 503
  `review_principal_unavailable`. The check SHALL NOT be widened to services,
  relays or surfaces.
- IF the named `request_id` does not exist THEN THE SYSTEM SHALL answer 404
  `review_request_not_found`. IF it is closed THEN THE SYSTEM SHALL answer 409
  `review_request_closed` with `closed_reason`.
- IF the submitted `subject` binding differs from the request's binding THEN
  THE SYSTEM SHALL answer 409 `review_binding_mismatch`.
- WHEN the submission is accepted THE SYSTEM SHALL seal it with
  `reviewreceipts.SealReceipt` using `reviewer_actor` = the server-derived actor
  and `created_at` = server time, store it with `mode=manual` and
  `assurance=advisory`, and audit it.
- IF the sealed receipt fails `Validate` THEN THE SYSTEM SHALL answer 400 with
  the Slice A code (for example `review_pass_with_unobserved`).
- WHEN a manual receipt is stored THE SYSTEM SHALL write no row to
  `review_nonce_consumptions`.
- IF the request's mode is `worker` THEN THE SYSTEM SHALL answer 409
  `review_request_mode_worker` and store nothing. `SealReceipt` takes its mode
  and assurance from the request, so a manual submission against a worker
  request would otherwise seal as `worker/independent`.
- IF the body carries `tenant`, `submitted_by`, `reviewer_actor`, `assurance`,
  `mode`, `nonce` or `created_at` THEN THE SYSTEM SHALL answer 400
  `review_unknown_key`.

Worker receipts

- WHEN any worker or autonomous receipt is submitted (`POST
  /api/v1/review-receipts`) THE SYSTEM SHALL answer 501
  `review_worker_ingest_disabled` and store nothing.

Reads

- WHEN an admin calls `GET /api/v1/review-receipts` THE SYSTEM SHALL return
  every stored receipt in `ingest_seq` order with `complete: true`.
- IF the store fails THEN THE SYSTEM SHALL answer 503
  `review_store_unavailable`. IF the pool exceeds `REVIEW_POOL_MAX` (default
  10000) THEN THE SYSTEM SHALL answer 503 `review_pool_too_large`. In neither
  case SHALL it answer 200 with an empty or truncated list.
- WHEN an admin calls `GET /api/v1/review-gate` with a live subject and
  `required_assurance` THE SYSTEM SHALL return the `EvaluateReviewGate` verdict,
  the selected request document, and the complete pool it was evaluated over.
- WHEN `required_assurance=independent` and only manual receipts match THE
  SYSTEM SHALL answer `advisory_only` (or `not_independent`), never
  `satisfied`.
- WHILE the review store is nil THE SYSTEM SHALL answer 503
  `review_store_unavailable` on every review route.

Surfaces

- THE SYSTEM SHALL register MCP tools `mctl_submit_review_assertion` (not
  read-only, not destructive) and `mctl_get_review_gate` (read-only), record
  their hints in `internal/mcp/annotations_test.go`, add explicit entries to
  `docs/portal-allowlist.json`, and update the tool count.
- THE SYSTEM SHALL document the contract in `docs/review-receipts.md`.

## Out of scope

- Worker or autonomous receipt ingestion and nonce consumption. The route
  exists and refuses. Enabling it needs mctl-api#896 closed and a follow-up
  carrying the run-token binding accepted on 2026-11-01.
- Authoritative `execution_id -> attempt_id + lineage_root` (Slice C,
  mctl-api#896).
- The `independent-review` execution profile and the live acceptance run
  (mctl-agents#905 tasks 7 and 9).
- Retention or purge of review rows.
- Changes to `internal/reviewreceipts` semantics. Only additive helpers are
  allowed.

## Open questions

- Gate request selection: when several requests share the live binding (a
  repeat closes nothing), which one does the gate use? Proposed: the newest by
  `ingest_seq` whose binding equals the live subject, whether closed or not.
  Closure stops new submissions but does not void receipts already stored.
- Manual receipt against a worker-mode request: the issue says a manual
  submission "never consumes the worker nonce", which could mean manual
  receipts on worker requests are expected. `SealReceipt` copies
  `request.Mode`, so that would need a Tier A contract change. This proposal
  takes the conservative reading and refuses with 409
  `review_request_mode_worker`. A human review of a worker-authored subject
  needs a `mode=manual` request for the same binding.
- `GET /api/v1/review-receipts` returns sealed receipts, which carry the
  request nonce (Tier A `SealReceipt` copies it). The reads are admin-only.
  Should the nonce be redacted on read before worker ingest is enabled? Not
  redacted here, because parity needs the exact bytes.
- Tier A makes `authoring_execution_id` optional. Tier B requires it for every
  stored request, because the tenant is derived from it. Confirm this is
  intended for `mode=manual` requests too.
- `REVIEW_POOL_MAX` default (10000) is a guess with no production data behind
  it.
