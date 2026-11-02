# Enable autonomous worker review-receipt ingestion with run-token binding, durable nonce consumption and attacher eligibility

## Context

`POST /api/v1/review-receipts` (the worker receipt route) is deliberately
disabled: `SubmitWorkerReview` in `internal/api/handlers_review_receipts.go`
answers `501 review_worker_ingest_disabled` without reading a body. The
pieces it depends on now exist in the tree. Tier A sealing and gate are in
`internal/reviewreceipts` (mctl-api#895/#898). The durable store, manual
advisory path and the `review_nonce_consumptions` table (created but never
written) are in `internal/reviewstore` (mctl-api#897). Execution provenance
with `attempt_id`, `lineage_root`, `attached_by` and `attached_by_principal`
is in `internal/workitems/provenance.go`, with
`reviewstore.Store.ProveReviewer` (mctl-api#896). Tier B already accepts
`we_<hyphenated-uuid>` ids (`executionIDRE` in
`internal/reviewreceipts/types.go`, merged in #923).

This issue owns the remaining work. An autonomous reviewer run must be able
to answer a worker-mode review request so that the gate can return an
`independent` verdict. The reviewer's identity, execution, attempt and
lineage must come only from the authenticated, execution-bound agent run
token and server-written provenance, never from the request body. The nonce
must be consumed exactly once, durably. An execution attached by an arbitrary
developer, who chose its `engine`/`engine_ref` freely, must never establish
independent-review eligibility. This unblocks the autonomous live acceptance
of mctlhq/mctl-agents#905.

## User stories

- AS the autonomous reviewer agent run I WANT to submit a review receipt
  with my execution-bound run token SO THAT a worker-mode review request gets
  an `independent` receipt without a human in the loop.
- AS a platform operator I WANT the worker route behind an explicit enable
  switch that defaults off SO THAT it opens only after every cross-repo
  prerequisite (mctl-agents vector parity) is proven.
- AS the owner of the review gate I WANT the reviewer's execution, attempt,
  lineage and actor to be server-derived and checked against the authoring
  facts SO THAT no caller can assert independence.
- AS a security reviewer I WANT executions attached by developers through
  `POST /api/v1/work-items/{id}/executions` to be ineligible SO THAT a chosen
  `engine`/`engine_ref` cannot fabricate a "different" attempt or lineage.

## Acceptance criteria (EARS)

- WHILE `REVIEW_WORKER_INGEST_ENABLED` is unset or not `true` THE SYSTEM SHALL
  answer every `POST /api/v1/review-receipts` with `501
  review_worker_ingest_disabled` and read no body (current behaviour).
- WHEN an agent principal authenticated with an unrevoked, unexpired run token
  minted with the `review` scope and bound to an execution submits a valid
  body for an open worker-mode request whose subject binding matches, with the
  matching nonce, and the bound execution is eligible and independent, THE
  SYSTEM SHALL atomically record one `review_nonce_consumptions` row and one
  `review_receipts` row with `mode=worker`, `assurance=independent`, and
  answer `201` with the sealed receipt.
- THE SYSTEM SHALL take `reviewer_actor` from the authenticated principal
  (`agent:<name>`), `reviewer_execution_id` from the run token's bound
  execution, and `attempt_id`/`lineage_root` from that execution's
  `execution_provenance` row.
- IF the body carries any key other than `request_id`, `subject`, `nonce`,
  `outcome`, `criteria`, `findings_ref`, `evidence_ref` (for example
  `reviewer_execution_id`, `attempt_id`, `lineage_root`, `reviewer_actor`,
  `assurance`, `mode`, `tenant`, `created_at`) THEN THE SYSTEM SHALL refuse
  with `400 review_unknown_key` and store nothing.
- IF the caller is not an agent run token, or the token has no bound
  execution, or its scope is not `review` THEN THE SYSTEM SHALL refuse with
  `403 review_run_token_required` and store nothing.
- IF the presented nonce does not equal the request's nonce THEN THE SYSTEM
  SHALL refuse with `403 review_nonce_mismatch` and store nothing.
- IF the request's nonce already has a `review_nonce_consumptions` row THEN
  THE SYSTEM SHALL refuse with `409 review_nonce_consumed` and store no
  receipt.
- IF the reviewer execution has no provenance record THEN THE SYSTEM SHALL
  refuse with `403 review_execution_unproven`.
- IF the reviewer execution's provenance was not attached by the service
  principal acting directly (`attached_direct_service = false`, which
  includes every row recorded before this change) THEN THE SYSTEM SHALL
  refuse with `403 review_reviewer_ineligible` and store nothing.
- IF the reviewer execution equals the authoring execution, or its attempt
  is in `authoring_attempt_ids`, or its lineage equals
  `authoring_lineage_root`, or the reviewer actor is in `author_actors` THEN
  THE SYSTEM SHALL refuse with `409 review_reviewer_not_independent` and
  store nothing.
- IF the request is closed THEN THE SYSTEM SHALL refuse with `409
  review_request_closed`. IF it is manual-mode THEN THE SYSTEM SHALL refuse
  with `409 review_request_mode_manual`. IF the subject binding differs THEN
  THE SYSTEM SHALL refuse with `409 review_binding_mismatch`.
- IF provenance cannot be read THEN THE SYSTEM SHALL answer `503
  review_provenance_unavailable`. IF the review store (including the nonce
  table) cannot be read or written THEN THE SYSTEM SHALL answer `503
  review_store_unavailable`. In both cases no row is stored.
- WHEN a new execution is inserted THE SYSTEM SHALL record in its
  `execution_provenance` row the server-derived `attach_path` (`attach`,
  `resume`, `fulfil_start`, `fulfil_resume`) and `attached_direct_service`
  (true only when the mutating principal is the service principal acting
  directly, not relayed and not an agent).
- THE SYSTEM SHALL keep `POST /api/v1/review-receipts/manual` and its
  behaviour, codes and advisory-only guarantee unchanged.
- WHEN a worker receipt is stored or refused after authentication THE SYSTEM
  SHALL write an audit entry (`review.worker_submit` /
  `review.worker_submit_refused`) naming the run id, execution id, request id
  and refusal code.

## Out of scope

- Vendoring `execution_attempt_vectors.json` into mctl-agents and its parity
  test (mctl-agents#975). It is a prerequisite tracked there. This proposal
  only keeps the route switched off until it is proven.
- The ADR 025 regex amendment in mctl-agents (mctl-agents#977). The Tier B
  side already landed in #923.
- The reviewer agent itself, and how mctl-agents dispatches it and mints its
  token (mctl-agents#905).
- Receipt retention and per-identity pool reads (the `REVIEW_POOL_MAX`
  follow-up in docs/review-receipts.md).
- A new MCP tool. The worker path is REST-only for agent runs.
- Backfilling `attach_path` / `attached_direct_service` for pre-existing
  provenance rows. They stay ineligible.

## Open questions

- Agent name admitted by the new `review` scope. This proposal uses
  `review-worker`. The real name of the mctl-agents reviewer
  (mctl-agents#905) must replace it before enabling.
- Whether the reviewer must present the request nonce in the body. This
  proposal requires it as proof that the run was dispatched for this request.
  The stored request document already contains the nonce, so it is
  defence-in-depth, not secrecy.
- Whether "eligible attacher" should also be limited by an allowlist of
  `attached_by_principal` ids or engines (for example only the Temporal
  dev-loop's executions). This proposal uses "service principal acting
  directly", which excludes every developer, agent and relayed attach.
- Whether the reviewer execution's work item must be in the same tenant as
  the review request. This proposal does not require it, because reviewer
  runs may live in the platform tenant.
- A retry after a successful submit gets `409 review_nonce_consumed`, not a
  replay. `created_at` changes per call, so the receipt id is not stable.
  Accept, or add an idempotency key?
- The deployed mctl-api configuration could not be observed (see design.md).
