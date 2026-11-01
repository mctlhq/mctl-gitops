# Tier B adapter for version-bound independent review receipts

## Context

Epic mctlhq/.github#281, slice mctlhq/mctl-agents#905, defines independent,
version-bound review receipts. Tier A is merged in mctl-agents#971 (ADR 025,
`orchestrator/review_receipts.py`: sealed `ReviewRequest` / `ReviewReceipt`,
`spike_report_digest_v1`, `evaluate_review_gate`), and the amended proposal is
in mctl-gitops#2337. mctl-api has no durable store and no write path for these
documents. Its only related Tier B surface is `POST /api/v1/evidence/records`
(`internal/api/handlers_evidence.go`, gated by `evidence:write`). mctl-gitops#2337
decided that review receipts get a NEW append-only resource. They must not be
squeezed into ExecutionEvidence's `SUBJECT_KINDS` (`internal/evidence/amendment2.go`).

This proposal adds that resource to mctl-api. It covers sealed review requests,
receipts submitted by an enrolled reviewer worker (with nonce, attempt and
fencing checks), advisory manual receipts from direct human admins, and a
complete-or-typed-error read of the receipt pool. Two MCP tools sit on top. The
point is that the autonomous review gate can only pass on an independent,
fenced, version-bound receipt. A replayed, forged or partially read receipt
must never be able to pass it.

## User stories

- AS the mctl-agents orchestrator I WANT to register a sealed ReviewRequest for an authoring execution SO THAT a reviewer can be bound to exactly that subject and version.
- AS the enrolled reviewer worker (`service:mctl-agents-reviewer`) I WANT to submit a ReviewReceipt bound to a request, nonce, attempt and fencing epoch SO THAT my verdict can satisfy the independent review gate.
- AS a direct human platform admin I WANT to record a manual review assertion SO THAT a human judgement is kept on file without ever being mistaken for an independent autonomous review.
- AS the DevLoop gate consumer I WANT the complete candidate pool or a typed error SO THAT a failed read can never look like "no receipts" or "gate passes".
- AS an operator using MCP I WANT `mctl_submit_review_assertion` and `mctl_get_review_gate` SO THAT I can assert and inspect review state without raw REST calls.

## Acceptance criteria (EARS)

Requests

- WHEN an authorized caller POSTs a well-formed ReviewRequest to `/api/v1/review-requests` THE SYSTEM SHALL validate it against the ported Tier A rules, recompute its content identity, store it verbatim, and return the request id together with a server-generated single-use nonce. Only a hash of the nonce is stored.
- IF a ReviewRequest has no `authoring_execution_id` THEN THE SYSTEM SHALL refuse it with `review_malformed` and store nothing.
- IF a ReviewRequest's `authoring_execution_id` does not resolve to a stored ExecutionEvidence record (an `ev-` id) THEN THE SYSTEM SHALL refuse it with `review_bad_subject` and store nothing.
- WHEN a request or receipt is accepted THE SYSTEM SHALL derive tenant and actor on the server: tenant from the referenced ExecutionEvidence projection, actor from `principalOf(user)`.
- IF a request or receipt body carries a `tenant`, `actor`, `submitted_by` or any other key outside the Tier A schema THEN THE SYSTEM SHALL refuse it with `review_unknown_key` and store nothing.

Worker receipts

- WHEN `service:mctl-agents-reviewer` POSTs a ReviewReceipt that carries the request id, nonce, attempt id and ADR 010 fencing epoch, and every check passes, THE SYSTEM SHALL store it with `mode=worker`. Its assurance SHALL be what the Tier A rules give for the receipt, which is `independent` for a valid independent review.
- IF the nonce was already consumed THEN THE SYSTEM SHALL refuse with `review_nonce_replayed` and store nothing.
- IF the referenced request has expired or is closed THEN THE SYSTEM SHALL refuse with `review_request_closed` and store nothing.
- IF the receipt's subject binding (kind, repository, ref, revision, authoring execution id) differs from the request's THEN THE SYSTEM SHALL refuse with `review_subject_mismatch` and store nothing.
- IF a worker-mode caller is not the enrolled reviewer principal THEN THE SYSTEM SHALL refuse with `review_producer_not_enrolled` and store nothing.
- IF the presented fencing epoch is not the current epoch of the lifecycle ownership row named by the request, or that row is not active, THEN THE SYSTEM SHALL refuse with `review_fence_stale` and store nothing.
- IF the lifecycle store, the evidence store or the review store cannot answer THEN THE SYSTEM SHALL answer a typed 503 and store nothing. Fail closed: such a receipt is never accepted.
- IF a receipt asserts `pass` while any rubric outcome is unobserved THEN THE SYSTEM SHALL refuse with `review_pass_with_unobserved` and store nothing.
- WHEN a receipt violates a Tier A rule THE SYSTEM SHALL refuse with the Tier A code of the same meaning: `review_rubric_mismatch`, `review_unobserved_outcome`, `review_malformed`, `review_unknown_key`, `review_bad_subject`, `review_bad_identity` or `spike_digest_refused`. Nothing is stored.
- WHILE any refusal is returned THE SYSTEM SHALL leave the nonce unconsumed and write no row, so every check and the insert happen in one transaction.

Manual receipts

- WHEN a caller for whom `isHumanAdmin(user)` holds, and whose principal passes `CheckHumanPrincipal`, POSTs a receipt without worker fields THE SYSTEM SHALL store it with `mode=manual` and `assurance=advisory`, whatever assurance the body claims.
- IF a relayed, surface, agent or service caller attempts a manual receipt THEN THE SYSTEM SHALL refuse it with 403 and store nothing. `isHumanAdmin` is not widened.
- WHILE evaluating a gate with `required_assurance=independent` THE SYSTEM SHALL never count a `manual` / `advisory` receipt toward satisfaction.

Reads

- WHEN an authorized caller GETs `/api/v1/review-receipts` for a request or subject THE SYSTEM SHALL return the complete candidate pool in ingest order.
- IF the pool cannot be read completely (store error, row decode error, or a pool larger than the bound) THEN THE SYSTEM SHALL answer a typed 5xx (`review_store_unavailable` or `review_pool_too_large`) and never a 200 with an empty or truncated list.
- WHEN `mctl_get_review_gate` is called THE SYSTEM SHALL run the Go port of `evaluate_review_gate` over the complete pool, or surface the typed error unchanged.

## Out of scope

- The `independent-review` execution profile and the live acceptance run (mctl-agents#905, tasks 7 and 9).
- Delegation policy (mctl-api#869, which depends on mctl-gitops#1980).
- Extending ExecutionEvidence `SUBJECT_KINDS` or any change to `/api/v1/evidence*`.
- Widening `isHumanAdmin`, or letting relayed callers make manual assertions.
- Any change to the Tier A Python contract in mctl-agents.

## Open questions

- The Tier A schema (`review_receipts.py`, ADR 025) is not in this repository. Field names here follow the issue text. The implementer must port them exactly from mctl-agents#971 and lock parity with golden fixtures copied from it.
- What "enrolled" means: this proposal reads it as a dedicated bearer-token principal (`MCTL_REVIEWER_TOKEN`), modelled on the evidence-writer principal. If enrollment is meant to come from the agent registry or a per-attempt run token, only the enrollment check changes.
- Which lifecycle `kind/phase` the fence names. Assumed: the request carries `{kind, id, phase}` and the server checks it with `lifecycle.LegalPhase`. A dedicated review phase may need a new entry in `internal/lifecycle/types.go` bounds, or reuse `pull-request/review-remediation`.
- When a request is "closed": assumed to be at `expires_at` (a bounded TTL that the request sets) or once a later request supersedes it for the same subject. Accepting one worker receipt consumes the nonce but does not close the request.
- Who may create requests and read the pool: assumed human admins and the direct mctl-agent service principal (`isDirectService`). The reviewer principal is confined to `POST /api/v1/review-receipts`.
