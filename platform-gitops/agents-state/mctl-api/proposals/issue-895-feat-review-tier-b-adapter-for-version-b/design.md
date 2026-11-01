# Design: issue-895-feat-review-tier-b-adapter-for-version-b

## Current state

- **Evidence ingest** is `internal/api/handlers_evidence.go`. `IngestEvidence` handles `POST /api/v1/evidence/records`. It is admitted by `requireEvidenceWriter` (`auth.PermissionEvidenceWrite = "evidence:write"`) and has typed codes such as `evidence_store_unavailable` and `evidence_current_pool_too_large`. Store errors go through `writeEvidenceError`. A nil store answers 503, never an empty result.
- **Evidence storage** is `internal/evidence/store.go`. It keeps an immutable `execution_evidence` table: a `BEFORE UPDATE` trigger `execution_evidence_immutable()` refuses every update, there is no FK to work items, and DELETE is the retention mechanism. It also keeps a rebuildable `execution_evidence_refs` projection that carries `tenant`, `repository`, `pr_number` and so on. The schema is applied idempotently in `NewStore`.
- **Subject kinds** live in `internal/evidence/amendment2.go` (`subjectKinds`, `shaBoundSubjectKinds`, `SubjectRef`). That is the extension the issue rules out.
- **Decision records** (`internal/decisions/store.go`) are the closest analogue: append-only records plus an attempts table, with `UNIQUE (recorded_by, idempotency_key)`, an `EvidenceLookup` interface (`Get(ctx, id)`) wired in `cmd/api/main.go`, and a "nil interface means unobservable, not absent" rule.
- **Writer principals.** In `internal/auth/oidc.go`, `EvidenceWriterUserID = "service:mctl-agents-evidence"` is minted from `MCTL_EVIDENCE_WRITER_TOKEN`, and `evidenceWriterToken()` refuses a token that is too short or that collides with another principal's. `evidenceWriterGate` (`handlers_evidence.go`) confines that principal to its own routes. The Helm chart wires the token through `helm/values.yaml` `evidenceWriterTokenSecret` and `helm/templates/deployment.yaml`.
- **Human checks.** `isHumanAdmin` (`internal/api/handlers_action_approvals.go:87`) is `IsAdmin && !IsService && !relayed && !surface`. `isDirectService` sits beside it. `checkHumanPrincipal` (`internal/api/handlers_surface_identity.go`) calls `auth.HumanPrincipalChecker.CheckHumanPrincipal`, which is implemented by `internal/principals/resolver.go`, and maps the result to `principal_disabled` / `identity_refused`. Any other error means the store could not answer (503). `principalOf` is in `handlers_work_items.go`.
- **Fencing (ADR 010).** In `internal/lifecycle`, `Ownership.Epoch` is the fencing generation and `Store.Get(ctx, EntityRef, phase)` reads it. `LegalPhase(kind, phase)` checks kind/phase pairs; the kinds are `devloop-proposal` and `pull-request`, and the phases include `implement` and `review-remediation`.
- **Router.** `internal/api/router.go` keeps optional stores in `Options` (`Evidence`, `Decisions`, `Lifecycle`). Write routes sit in rate-limited groups (`evidenceIngestPerMinute`), and reads are grouped at about lines 891-905.
- **MCP.** `internal/mcp/server.go` registers tools; `internal/mcp/lifecycle.go` is the pattern of a tool that calls REST. Every tool must be listed in `recordedHints` in `internal/mcp/annotations_test.go`, which asserts that `len(ListTools())` equals the table size, and in `docs/portal-allowlist.json` (`portal_allowlist_test.go`).

- **Agent run tokens (observed on mctl-api `ede0b3b`).** `internal/workitems/agent_run_tokens.go` stores `agent`, `agent_principal_id`, `execution_id`, `work_item_id`, permissions and expiry for an execution-scoped credential (mctl-api#376). `internal/k8s/agent_run_binding.go` (mctl-agents#737) mints it from a pod's projected ServiceAccount token: pod -> Workflow -> agent, scope and `execution_id`. Its own comment records that `execution_id` is the argument the Workflow was submitted with and is not read back from an execution row. `execution_id` values are `we_`-prefixed (`workitems.ExecutionIDPrefix`), the form Tier A accepts. This is the only existing principal -> execution record; whether it is enough for a reviewer is blocker B1 in requirements.md.
- **Tier A is merged** (mctl-agents#971, ADR 025): the sealed request has no expiry field and no lifecycle reference, and its key set is `api_version, kind, request_id, content_hash, subject, rubric, mode, author_actors, authoring_execution_id, authoring_attempt_ids, authoring_lineage_root, nonce, created_at`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/*` shows tenants admins, karabu, labs and namax66, with no `mctl-api` service directory. mctl-api's deployed values are therefore not observable here.
- `mctl_get_service_config(team=admins, service=mctl-api)` returned "service not found". mctl-api is not a catalogue service, so its deployed env (whether `MCTL_EVIDENCE_WRITER_TOKEN` / `EVIDENCE_DB_URL` are set, and the replica count) was **not observed**. It is not assumed absent.
- The repository's `helm/values.yaml` and `helm/templates/deployment.yaml` show only how optional writer-token Secrets are wired, not their deployed values.

## Proposed solution

### 1. New package `internal/reviewreceipts`

- `types.go`: a Go port of Tier A `ReviewRequest` and `ReviewReceipt` (strict unknown-key detection) with a sentinel error per code that Tier B can actually decide: `ErrRubricMismatch`, `ErrUnobservedOutcome`, `ErrMalformed`, `ErrUnknownKey`, `ErrBadSubject`, `ErrBadIdentity`, `ErrNonceReplayed`, `ErrRequestClosed`, `ErrSubjectMismatch`, `ErrProducerNotEnrolled`, `ErrExecutionUnproven`, `ErrFenceStale` (emitted only under B1/B2), `ErrPassWithUnobserved`, `ErrPoolTooLarge`, `ErrUnavailable`. There is no `ErrSpikeDigestRefused`: Tier B cannot recompute the digest.
- `identity.go`: recomputes `content_hash`, `request_id` and `receipt_id` from the received document exactly as Tier A seals them, and refuses a mismatch with `review_bad_identity`. The nonce is read from the sealed document. Tier B does not generate it and stores the received bytes unchanged. Golden vectors copied from #971 go in `testdata/` and include a stored-and-read-back request whose identity must not change, and a request whose nonce was altered after sealing.
- Gate. There is one policy. Preferred shape: the Go gate takes the same typed input as Tier A (`live`, `request`, `pool`, `required_assurance`) and is checked against the shared vectors; if the implementer finds a way to call the canonical Tier A implementation instead of a port, that is preferred, and the choice is recorded in the PR. Either way parity is enforced by vectors, never by reading the Python. Vectors required: one for each of the four #971 rules (request binding differs from live binding -> `unknown`; receipt of another `request_id` is ignored -> `missing`; empty `reviewer_execution_id`, `attempt_id` or `lineage_root` -> `not_independent`; `Operator` vs `operator` -> `not_independent`), plus `stale`, `missing`, `unknown`, `advisory_only`, and manual-never-independent.
- `store.go`: applied idempotently in `NewStore`, three tables, all with the immutable `BEFORE UPDATE` trigger:
  - `review_requests` (id, content_hash UNIQUE, envelope BYTEA verbatim, authoring_execution_id, tenant, subject columns, nonce_sha256 UNIQUE, ingested_at, created_by). No expiry column from the body: closing is computed from `ingested_at + REVIEW_REQUEST_TTL` and from a later request for the same subject identity.
  - `review_receipts` (id, content_hash UNIQUE, envelope BYTEA, request_id, mode CHECK IN ('worker','manual'), assurance, CHECK `mode <> 'manual' OR assurance = 'advisory'`, reviewer_actor, reviewer_execution_id, attempt_id, tenant, submitted_by_principal_id, ingest_seq BIGSERIAL, ingested_at).
  - `review_nonce_consumptions` (nonce_sha256 PRIMARY KEY, request_id, receipt_id, consumed_at). Only worker receipts write here.
- `Store.CreateRequest` validates and verifies identity, resolves the authoring execution through the injected `EvidenceLookup`, stores the sealed bytes and `nonce_sha256`. It returns the `request_id`.
- `Store.SubmitWorkerReceipt` checks, in one `pgx.Tx`: the request row (`SELECT ... FOR SHARE`), not closed, nonce equals the sealed request's nonce, subject binding, Tier A rules, pass-with-unobserved, then inserts the nonce consumption (unique violation -> `ErrNonceReplayed`) and the receipt. The reviewer execution proof and freshness are read from the injected `ReviewerExecutionSource` BEFORE the transaction (see Concurrency). Every refusal rolls back.
- `Store.SubmitManualReceipt` forces `mode=manual, assurance=advisory`, runs the same request-exists, not-closed, subject-binding and structural checks, writes no nonce consumption and does not close the request.
- `Store.ListPool(ctx, requestID)` returns `([]Receipt, error)`, reads `limit+1` rows, maps more than the bound to `ErrPoolTooLarge`, and maps any scan or `rows.Err()` failure to `ErrUnavailable`. It never returns a partial slice with a nil error.

### 2. Reviewer principal and execution proof

The static bearer `MCTL_REVIEWER_TOKEN` of the first draft is dropped as the proof of execution: it proves a caller holds a secret, not that a given `reviewer_execution_id` is that caller's.

- `reviewer_actor` is always `principalOf(user)`. The sealed receipt carries `reviewer_actor` (it is part of the receipt identity), so the producer sets it, and the server accepts it only when it equals the derived actor; any other value is `review_bad_identity`. The body is never the source of the actor.
- `ReviewerExecutionSource` is an interface: `Prove(ctx, principalID, executionID) (ExecutionProof, error)` returning whether the execution belongs to that principal and whether it is live (credential unexpired, execution not terminal). Error means unobservable (503). A negative answer is 403 `review_execution_unproven`.
- Candidate implementation to verify against the code, not assumed: the agent run token store (`agent_principal_id`, `execution_id`, expiry) and the execution state in `workitems`. If the implementer confirms it, the reviewer authenticates with a reviewer-agent run token and `user.ExecutionID()` must equal `reviewer_execution_id`. Known limit, to be carried into the PR description: the binding trusts the `execution_id` the Workflow was submitted with.
- If the candidate does not hold, the worker path is shipped disabled (every worker submission answers 503 `review_store_unavailable`), and only the manual path is live. That is the fail-closed default, not an error to be worked around with a static token.
- Freshness of the reviewer execution comes from the same source. The authoring or request lifecycle fence is not used for it. `PermissionReviewWrite = "review:write"` and a `reviewerGate` confine the principal to `POST /api/v1/review-receipts` as before.
- The collision refusals between token readers apply to any new token that is introduced.

### 3. HTTP adapter (`internal/api/handlers_review_receipts.go`)

- `POST /api/v1/review-requests` admits `isHumanAdmin` or `isDirectService`. Tenant comes from the `evidence.Store` refs for `authoring_execution_id`. The response is `{request_id}`.
- `POST /api/v1/review-receipts`: worker mode when the sealed receipt has `mode=worker`. The caller must be the reviewer principal (else 403 `review_producer_not_enrolled`), the execution proof is required, and the nonce is checked against the sealed request. Manual mode admits only `isHumanAdmin(user)` plus a passing `checkHumanPrincipal`; a store that does not answer gives 503; relayed and surface callers get 403. Tenant is copied from the request row.
- `GET /api/v1/review-receipts?request_id=` returns `{receipts, complete: true}`; errors map through `writeReviewError`.
- Rate-limited group, `Options.ReviewReceipts`, nil store gives 503, audit of accepted writes as before.

### 4. Wiring (`cmd/api/main.go`)

`REVIEW_RECEIPTS_DB_URL` falling back to `EVIDENCE_DB_URL` then `AUDIT_DB_URL`, kill switch `REVIEW_RECEIPTS_DISABLED`, `REVIEW_REQUEST_TTL`. Lookups (`EvidenceLookup`, `ReviewerExecutionSource`) may be nil interfaces; a write that needs a nil lookup answers 503.

### 5. MCP (`internal/mcp/review_receipts.go`)

- `mctl_submit_review_assertion` posts a manual receipt. Not readOnly, not destructive, not idempotent.
- `mctl_get_review_gate` takes the request id and the observed live subject (or states that it is unobservable), reads the sealed request and the complete pool, evaluates the gate with the full Tier A input, and passes any typed REST error through as a tool error. ReadOnly. A failed read is never reported as "gate unsatisfied".
- Both tools are added to `recordedHints` and `docs/portal-allowlist.json`.

### 6. Concurrency

Option B is chosen, and stated plainly. The reviewer execution proof and freshness, and the evidence lookup, are read from stores outside this SQL transaction before it starts. The transaction then locks the request row (`FOR SHARE`), checks closed, nonce, binding and Tier A rules, and inserts the nonce consumption and the receipt atomically. Residual window: the reviewer execution or its credential can end between the proof read and the commit, so a receipt can be accepted for an execution that ended within that interval. Consequences: the receipt is still bound to a sealed request, a nonce and a subject, so it cannot be replayed or applied to another revision; a later request for the same subject closes the old one; and the gate is re-evaluated on read. The window is bounded by the duration of the transaction and is not a promise of atomicity with the lifecycle or execution state. Option A (locking a lifecycle row in the same transaction) is not used because no reviewer-owned lifecycle row exists and `lifecycle.Store` uses its own pool.

### 7. Docs

`docs/review-receipts.md`: contract, code table, auth matrix, the three-way split of checks (proved / carried / not performable), the blockers B1 and B2, the one-receipt-per-request rule, and the concurrency note. Links ADR 025, mctl-gitops#2337 and mctl-agents#971.

## Alternatives

1. **Extend ExecutionEvidence `SUBJECT_KINDS`.** Dropped; mctl-gitops#2337 decided against it and evidence has no nonce semantics.
2. **Reuse the evidence-writer principal.** Dropped; a leaked evidence credential could forge independent reviews.
3. **A static reviewer token as proof of execution.** Dropped; it proves possession of a secret, not ownership of an execution.
4. **Tier B generates the nonce.** Dropped; it would change the sealed request identity that Tier A defines.
5. **Hand-maintained second copy of the gate.** Avoided; one policy, parity by shared vectors (or the canonical implementation if callable).

## Platform impact

- **Migrations.** Three new tables created idempotently at startup; existing tables unchanged; no backfill.
- **Backward compatibility.** New routes and tools only; MCP tool count +2 with hints and allowlist updated in the same PR.
- **Resources.** Low-volume writes on the existing Postgres; the pool read is bounded.
- **Risks.** Tier A drift (shared vectors per rule); reviewer execution cannot be proven today (B1, worker path disabled by default); partial read presenting as empty (typed errors plus a mutation test); deployed env not observed (feature inert until configured).
