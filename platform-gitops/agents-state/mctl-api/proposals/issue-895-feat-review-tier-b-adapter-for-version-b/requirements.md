# Tier B adapter for version-bound independent review receipts

## Amendments to the first proposal (planning only, 2026-11-01)

The first version of this proposal was reviewed against merged Tier A (mctl-agents#971) and amended in these seven points. Tier A stays authoritative; Tier B carries and checks, it does not redefine.

1. **Nonce belongs to the sealed request.** Created before sealing, part of `request_id`. Tier B never generates or rewrites it, and stores only `nonce_sha256` for single use.
2. **The gate gets the full Tier A input** (`live`, sealed `request`, candidate `pool`, `required_assurance`) and keeps the four rules of #971: request binding equals live binding, pool scoped to one `request_id`, an empty worker identity is not independent, actor comparison is case-insensitive.
3. **Reviewer identity is never taken from the body.** `reviewer_actor` is derived from the authenticated principal. The proposal names the server-side source that must prove a `reviewer_execution_id` and records that source as a prerequisite with a fail-closed default. Reviewer freshness is specified separately from the authoring fence.
4. **Digest semantics are not overstated.** Tier B cannot recompute `spike_report_digest_v1` (no report bytes). `spike_digest_refused` is removed from the Tier B refusal list. The proposal separates what Tier B proves, what it only carries, and what it cannot check.
5. **Manual path** drops only the worker-specific checks. Request existence, not closed, subject match and structural validity still apply.
6. **No atomicity is promised that the implementation does not provide** (lifecycle state and SQL transaction).
7. **One request, one worker receipt** is stated outright, including `UNOBSERVABLE`, and a manual receipt never consumes the worker nonce.

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

- WHEN an authorized caller POSTs a sealed ReviewRequest to `/api/v1/review-requests` THE SYSTEM SHALL validate it with the ported Tier A rules, recompute `content_hash` and `request_id` from the received document, refuse a mismatch with `review_bad_identity`, store the received bytes verbatim, and return the `request_id`. The nonce is a field of the sealed document. Tier B SHALL NOT generate, replace or rewrite it, and SHALL store only its `nonce_sha256`.
- IF a ReviewRequest has no `authoring_execution_id` THEN THE SYSTEM SHALL refuse it with `review_malformed` and store nothing.
- IF a ReviewRequest's `authoring_execution_id` does not resolve to a stored ExecutionEvidence projection THEN THE SYSTEM SHALL refuse it with `review_bad_subject` and store nothing. (Format of the id is a Tier A check; resolution is a Tier B check.)
- WHEN a request or receipt is accepted THE SYSTEM SHALL derive tenant and actor on the server: tenant from the referenced ExecutionEvidence projection, actor from `principalOf(user)`.
- IF a request or receipt body carries a key outside the Tier A schema (including `tenant`, `submitted_by`) THEN THE SYSTEM SHALL refuse it with `review_unknown_key` and store nothing.
- Closing. The sealed request has no expiry field, so expiry is server policy and never comes from the body: a request is closed when `ingested_at + REVIEW_REQUEST_TTL` has passed (configured, bounded), or when a later request for the same subject identity has been ingested. The request is not closed by receiving a receipt.
- Request identity vectors. THE SYSTEM SHALL ship golden vectors copied from #971 showing that storing and reading back a sealed request leaves `content_hash` and `request_id` byte-identical, and that a request whose nonce was altered after sealing is refused with `review_bad_identity`.

Worker receipts

- A worker receipt is a sealed Tier A ReviewReceipt. WHEN it arrives THE SYSTEM SHALL check, in one transaction and in this order: the request exists, is not closed (`review_request_closed`), the receipt `nonce` equals the sealed request's nonce, the receipt subject binding equals the request subject binding (`review_subject_mismatch`), the Tier A structural rules, then `pass` with an unobserved criterion (`review_pass_with_unobserved`).
- IF the nonce was already consumed THEN THE SYSTEM SHALL refuse with `review_nonce_replayed` and store nothing.
- Reviewer actor. THE SYSTEM SHALL derive the reviewer actor from the authenticated principal and SHALL NOT accept an authoritative actor from the body. IF the body carries `reviewer_actor` and it differs from the derived actor THEN THE SYSTEM SHALL refuse the receipt with `review_bad_identity`.
- Worker identity. A worker receipt SHALL carry non-empty `reviewer_execution_id`, `attempt_id` and `lineage_root`. A missing value is `review_malformed`, never an independent receipt.
- Reviewer execution proof (prerequisite, see "Blockers"). THE SYSTEM SHALL accept a `reviewer_execution_id` only when an authoritative server-side record ties that execution to the authenticated reviewer principal. IF no such record can be read THEN THE SYSTEM SHALL answer 503 `review_store_unavailable`; IF it reads and does not tie them THEN 403 `review_execution_unproven`. A correct reviewer token alone is never sufficient. Both leave the nonce unconsumed and store nothing.
- Reviewer freshness. THE SYSTEM SHALL refuse a worker receipt unless the reviewer execution is still live at submission (its credential unexpired and its execution not terminal), as read from the same authoritative source. The fencing epoch of the authoring or request lifecycle row is NOT evidence of reviewer freshness, and the adapter SHALL NOT use it as such. `review_fence_stale` stays in the contract but is enforced only against a lifecycle row that belongs to the reviewer execution; until that row exists, the code is not emitted and not claimed.
- IF a worker-mode caller is not the enrolled reviewer principal THEN THE SYSTEM SHALL refuse with `review_producer_not_enrolled` and store nothing.
- IF the lifecycle store, the evidence store, the execution source or the review store cannot answer THEN THE SYSTEM SHALL answer a typed 503 and store nothing. Fail closed.
- WHILE any refusal is returned THE SYSTEM SHALL leave the nonce unconsumed and write no row. The database checks, the nonce consumption and the insert are one transaction. Reads of state outside this database are made before it and are not part of its atomicity (see design, "Concurrency").
- Terminal outcomes. A nonce admits at most one worker receipt per ReviewRequest. Any accepted worker receipt, including `UNOBSERVABLE` and `NEEDS_HUMAN`, consumes the nonce. A rerun needs a new sealed ReviewRequest with a new nonce and `request_id`.

Digest and sealed-identifier checks (what Tier B can and cannot prove)

1. Tier B proves independently: the shape of every sealed identifier (`rr_`, `rc_`, `ev-`, `we_`/`ex-`, sha256 digests); that `content_hash` and `request_id` / `receipt_id` recompute from the received document; receipt to request consistency (request id, nonce, rubric, mode, subject binding); that the authoring execution resolves to stored evidence; the Tier A outcome and rubric rules; and every gate invariant.
2. Tier B only carries and binds, from sealed Tier A documents: `spike_report_digest_v1` values, `source_sha` / `base_sha` / `head_sha`, `findings_ref`. It compares them for equality between request, receipt and the live subject, and does not interpret them.
3. Tier B cannot perform: recomputing `spike_report_digest_v1` from report bytes, confirming that a finding reference resolves, or confirming a head sha exists on GitHub. This stays outside Tier B until authoritative report bytes or an artifact fetch exist.
- Consequently `spike_digest_refused` is not a Tier B refusal. It remains a Tier A (producer side) code only, and Tier B SHALL NOT reuse the name for a different failure.

Manual receipts

- WHEN a caller for whom `isHumanAdmin(user)` holds, and whose principal passes `CheckHumanPrincipal`, POSTs a receipt without worker fields THE SYSTEM SHALL store it with `mode=manual` and `assurance=advisory`, whatever assurance the body claims.
- The manual path drops only the worker-specific checks (nonce, reviewer execution proof, reviewer freshness). It SHALL still verify that the request exists, is not closed, that the receipt subject binding equals the request's, and that the document is structurally valid, with the same refusal codes as the worker path.
- A manual receipt SHALL NOT consume the worker nonce. Accepting one does not close the request.
- IF a relayed, surface, agent or service caller attempts a manual receipt THEN THE SYSTEM SHALL refuse it with 403 and store nothing. `isHumanAdmin` is not widened.
- WHILE evaluating a gate with `required_assurance=independent` THE SYSTEM SHALL never count a `manual` / `advisory` receipt toward satisfaction.

Reads and the gate

- WHEN an authorized caller GETs `/api/v1/review-receipts` for a request THE SYSTEM SHALL return the complete candidate pool in ingest order.
- IF the pool cannot be read completely (store error, row decode error, or a pool larger than the bound) THEN THE SYSTEM SHALL answer a typed 5xx (`review_store_unavailable` or `review_pool_too_large`) and never a 200 with an empty or truncated list.
- Gate input. WHEN `mctl_get_review_gate` is called THE SYSTEM SHALL evaluate the gate with the full Tier A input: `live` (the subject as the caller observed it, or absent when it could not be observed), the stored sealed `request`, the complete candidate `pool`, and `required_assurance`. A typed read error is surfaced unchanged.
- Gate rules. THE SYSTEM SHALL preserve the four rules of #971: the request binding must equal the live binding (else `unknown`), the pool is limited to receipts carrying that `request_id` (else `missing`), a worker receipt with an empty `reviewer_execution_id`, `attempt_id` or `lineage_root` is not independent, and reviewer/author actor comparison is case-insensitive.
- Single policy. THE SYSTEM SHALL NOT keep a hand-written second copy of the policy that can drift. Parity with Tier A is enforced by shared golden vectors (at least one per rule, plus the stale, missing, unknown and advisory_only outcomes), run in CI on both sides.

## Blockers and prerequisites

- **B1. Authoritative reviewer principal -> execution mapping.** Observed on mctl-api `ede0b3b`: the closest existing record is the agent run token (mctl-api#376, `workitems/agent_run_tokens.go`: `agent`, `agent_principal_id`, `execution_id`, `work_item_id`, expiry) and the pod binding that mints it (mctl-agents#737, `k8s/agent_run_binding.go`). A run token ties a credential to an `execution_id` of the `we_` form. Limits recorded there: the binding takes `execution_id` from the argument the Workflow was submitted with and does not read it back from any execution row, and no reviewer agent or `independent-review` profile exists yet (mctl-agents#905, task 7). This proposal therefore does NOT assume the static `MCTL_REVIEWER_TOKEN` can prove an execution. The worker path stays disabled (503) until the implementer shows, against the code, that a run-token principal for the reviewer agent can be matched to `reviewer_execution_id` and that its `execution_id` is acceptable as proof, or until the owner accepts the trust limit above in writing. If neither holds, only the manual path ships.
- **B2. Reviewer freshness source.** The same source as B1 must also tell whether the reviewer execution is live. Not observed today for a reviewer.
- **B3. Deployed environment** (token secrets, DB URL, replica count) was not observed.

## Out of scope

- The `independent-review` execution profile and the live acceptance run (mctl-agents#905, tasks 7 and 9).
- Delegation policy (mctl-api#869, which depends on mctl-gitops#1980).
- Extending ExecutionEvidence `SUBJECT_KINDS` or any change to `/api/v1/evidence*`.
- Widening `isHumanAdmin`, or letting relayed callers make manual assertions.
- Any change to the Tier A Python contract in mctl-agents.
- Recomputing spike report digests (no report bytes in Tier B).

## Open questions

- The Tier A schema is in mctl-agents (`orchestrator/review_receipts.py`, ADR 025, merged in #971). The implementer ports it exactly and locks parity with golden fixtures copied from there.
- B1 and B2: which concrete source proves and freshness-checks a reviewer execution. Decision needed from the owner if the run-token route is not enough.
- Who may create requests and read the pool: assumed human admins and the direct mctl-agent service principal (`isDirectService`). The reviewer principal is confined to `POST /api/v1/review-receipts`.
- The value of `REVIEW_REQUEST_TTL`.
