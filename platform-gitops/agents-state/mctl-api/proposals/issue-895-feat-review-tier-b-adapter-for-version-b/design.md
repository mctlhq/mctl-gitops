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

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/*` shows tenants admins, karabu, labs and namax66, with no `mctl-api` service directory. mctl-api's deployed values are therefore not observable here.
- `mctl_get_service_config(team=admins, service=mctl-api)` returned "service not found". mctl-api is not a catalogue service, so its deployed env (whether `MCTL_EVIDENCE_WRITER_TOKEN` / `EVIDENCE_DB_URL` are set, and the replica count) was **not observed**. It is not assumed absent.
- The repository's `helm/values.yaml` and `helm/templates/deployment.yaml` show only how optional writer-token Secrets are wired, not their deployed values.

## Proposed solution

### 1. New package `internal/reviewreceipts`

- `types.go`: a Go port of Tier A `ReviewRequest` and `ReviewReceipt`. It parses with strict unknown-key detection (`review_unknown_key`) and has a sentinel error per Tier A code: `ErrRubricMismatch`, `ErrUnobservedOutcome`, `ErrMalformed`, `ErrUnknownKey`, `ErrBadSubject`, `ErrBadIdentity`, `ErrSpikeDigestRefused`. It also has a sentinel for each Tier B code: `ErrNonceReplayed`, `ErrRequestClosed`, `ErrSubjectMismatch`, `ErrProducerNotEnrolled`, `ErrFenceStale`, `ErrPassWithUnobserved`, `ErrPoolTooLarge`, `ErrUnavailable`.
- `digest.go`: `SpikeReportDigestV1`, and recomputation of the sealed identity (`rr-`/`rq-` id and content hash), in the same verify-what-was-sealed style as evidence ingest. Golden fixtures copied from mctl-agents#971 go in `testdata/` and guarantee byte parity.
- `gate.go`: `EvaluateReviewGate(pool, requiredAssurance)`, a port of `evaluate_review_gate`. A receipt with `mode=manual` or `assurance=advisory` never counts toward `independent`. The evaluator must get the complete pool and has no partial input type.
- `store.go`: it is applied idempotently in `NewStore`, in the evidence/decisions style. It creates three tables:
  - `review_requests` (id, content_hash UNIQUE, envelope BYTEA, authoring_execution_id `ev-…` NOT NULL, tenant, subject columns, fence kind/id/phase, nonce_sha256 UNIQUE, expires_at, created_by, created_at).
  - `review_receipts` (id, content_hash UNIQUE, envelope BYTEA, request_id, mode CHECK IN ('worker','manual'), assurance, CHECK `mode <> 'manual' OR assurance = 'advisory'`, attempt_id, fence_epoch, tenant, submitted_by, submitted_by_principal_id, ingest_seq BIGSERIAL, ingested_at).
  - `review_nonce_consumptions` (nonce_sha256 PRIMARY KEY, receipt_id, consumed_at).

  All three get the immutable `BEFORE UPDATE` trigger. The receipt pool is ordered by `ingest_seq`.
- `Store.SubmitWorkerReceipt(ctx, req)` uses one `pgx.Tx`. It locks the request row (`SELECT … FOR SHARE`) and checks: closed, then subject binding, then the Tier A rules, then `pass_with_unobserved`. It checks the fence through an injected `FenceLookup` interface (`Get(ctx, lifecycle.EntityRef, phase) (*lifecycle.Ownership, error)`, satisfied by `*lifecycle.Store`). The fence is stale if `epoch != ownership.Epoch` or `state != active`. It inserts the nonce consumption; a unique violation maps to `ErrNonceReplayed`, and a replay is also checked first so the refusal is clear. Then it inserts the receipt and commits. Every refusal rolls back, so nothing is stored.
- `Store.SubmitManualReceipt` forces `mode=manual, assurance=advisory`. It does not require a nonce or fence.
- `Store.ListPool(ctx, filter)` returns `([]Receipt, error)`. It reads `limit+1` rows: more than the bound gives `ErrPoolTooLarge`, and any scan or iteration error, including `rows.Err()`, gives `ErrUnavailable`. It never returns a partial slice with a nil error.

### 2. Reviewer principal (`internal/auth/oidc.go`)

Add `ReviewerUserID = "service:mctl-agents-reviewer"`, `PermissionReviewWrite = "review:write"`, the `MCTL_REVIEWER_TOKEN` env var, `NewReviewerUser()` and `IsReviewer()`, and `reviewerToken()` with the same collision refusals as `evidenceWriterToken()`. Also refuse a token equal to `MCTL_EVIDENCE_WRITER_TOKEN`, and add the reverse check to the other token readers. Wire the token in `federation_config.go` and the bearer path the same way as `newEvidenceWriterProvider`. Add Helm `reviewerTokenSecret`. An absent Secret leaves the principal disabled.

### 3. HTTP adapter (`internal/api/handlers_review_receipts.go`)

- `reviewerGate` middleware confines `IsReviewer()` to `POST /api/v1/review-receipts`. It is mounted next to `evidenceWriterGate`.
- `POST /api/v1/review-requests` admits `isHumanAdmin` or `isDirectService`. The tenant comes from `evidence.Store` refs for the `authoring_execution_id`. The handler returns `{request, nonce}`.
- `POST /api/v1/review-receipts`:
  - Worker mode is when the body has worker fields (request_id, nonce, attempt_id, fence_epoch). The caller must be `IsReviewer()`; anyone else gets 403 `review_producer_not_enrolled`. A missing `authoring_execution_id` gets `review_malformed`.
  - Manual mode admits only `isHumanAdmin(user)` plus a passing `checkHumanPrincipal`. A store that does not answer gives 503. Relayed and surface callers get 403.
  - Actor is `principalOf(user)`, and the tenant is copied from the request row.
- `GET /api/v1/review-receipts?request_id=|subject…` returns `{receipts, complete: true}`. Errors map through `writeReviewError`: 400/409/403 for refusals, 500 `review_pool_too_large`, 503 `review_store_unavailable`.
- Routes go in their own rate-limited group (`reviewWritesPerMinute`), with `Options.ReviewReceipts *reviewreceipts.Store`. A nil store gives 503 everywhere.
- Accepted writes are audited through the existing `audit` path that evidence ingest uses.

### 4. Wiring (`cmd/api/main.go`)

`REVIEW_RECEIPTS_DB_URL`, falling back to `EVIDENCE_DB_URL` and then `AUDIT_DB_URL`, with the kill switch `REVIEW_RECEIPTS_DISABLED`, using `initStore` like the decisions block. Call `SetLookups(evidenceStore, lifecycleStore)`. Either lookup may be nil: a nil lookup is a typed nil interface, and a write that needs it answers 503.

### 5. MCP (`internal/mcp/review_receipts.go`)

- `mctl_submit_review_assertion` posts a manual receipt to `/api/v1/review-receipts`. Hints: not readOnly, not destructive, not idempotent.
- `mctl_get_review_gate` gets the pool for one request, runs `reviewreceipts.EvaluateReviewGate`, and passes any typed REST error through as a tool error. It is readOnly.
- Add both tools to `recordedHints` (`annotations_test.go`) and `docs/portal-allowlist.json`.

### 6. Docs

`docs/review-receipts.md` covers the contract, codes, auth matrix and the fail-closed rules, and links ADR 025 and mctl-gitops#2337.

## Alternatives

1. **Extend ExecutionEvidence `SUBJECT_KINDS` with a review kind and reuse `/api/v1/evidence/records`.** Dropped. mctl-gitops#2337 explicitly decided against it, and evidence has no nonce or fence semantics, so a receipt would gain no replay protection.
2. **Reuse the evidence-writer principal for receipts.** Dropped. A leaked evidence credential could then forge independent reviews, which defeats independence. A separate principal also keeps attribution explicit.
3. **Evaluate the gate in mctl-agents only, with mctl-api just storing receipts.** Partly kept: mctl-agents keeps its own evaluator. But the MCP tool needs a server-side answer, and a Go port pinned by golden fixtures keeps both sides consistent.

## Platform impact

- **Migrations.** Three new tables are created idempotently at startup. Existing tables are not changed. No backfill.
- **Backward compatibility.** These are new routes and tools only. The evidence and decisions behaviour is unchanged. The MCP tool count rises by 2, and the hint table and allowlist are updated in the same PR.
- **Resources.** These are low-volume writes on the existing Postgres (shared with the evidence DB by default). The pool read is bounded.
- **Risks and mitigations.**
  - Tier A drift: golden fixtures from mctl-agents#971, plus a parity test per code.
  - TOCTOU between the fence check and the insert: both run in one transaction. The fence value is read inside it, so a concurrent epoch bump either commits first (and the receipt is refused) or is ordered after the receipt was accepted under a valid epoch.
  - The reviewer token collides with another principal's: `reviewerToken()` refuses it.
  - Partial reads presenting as empty: the explicit `ErrUnavailable` / `ErrPoolTooLarge` path, plus a mutation test.
  - Deployed env not observed: the feature is inert until `MCTL_REVIEWER_TOKEN` and a DB URL are set, so rollout is opt-in.
