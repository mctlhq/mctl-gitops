# Design: issue-917-feat-review-enable-autonomous-worker-rec

## Current state

- **Worker route is a stub.** `internal/api/handlers_review_receipts.go`
  `SubmitWorkerReview` checks only that a user exists, then writes `501
  review_worker_ingest_disabled`. The route is registered in
  `internal/api/router.go` (`r.Post("/review-receipts",
  h.SubmitWorkerReview)`) inside the `review:` 30/min rate-limit group, next
  to `/review-requests` and `/review-receipts/manual`.
- **Manual path.** `SubmitManualReview` admits only `isHumanAdmin` (plus an
  active human principal check) and decodes `manualReceiptBody` with
  `DisallowUnknownFields`. It calls `reviewstore.Store.SubmitManual`
  (`internal/reviewstore/receipts.go`), which refuses closed, worker-mode and
  binding-mismatched requests, seals with `reviewreceipts.SealReceipt`
  (manual forces `assurance=advisory`) and inserts into `review_receipts`. It
  never touches the nonce.
- **Schema.** `internal/reviewstore/store.go` creates `review_requests`
  (unique `nonce_sha256`), `review_receipts` (CHECK manual implies advisory)
  and `review_nonce_consumptions (nonce_sha256 PK, request_id FK,
  receipt_id, consumed_at)`, which nothing writes yet. All three have
  UPDATE-refusing triggers. The DB is the evidence DB (`EVIDENCE_DB_URL`,
  else `AUDIT_DB_URL`), wired in `cmd/api/main.go` (~line 780), where
  `reviewStore.SetProvenance(workItemsStore)` is also called.
- **Provenance.** `internal/workitems/provenance.go`: `insertProvenance`
  writes one `execution_provenance` row in the same transaction as
  `insertExecution` (`internal/workitems/store.go`). `attached_by =
  m.Actor` and `attached_by_principal = m.ActorPrincipalID`. Rows are
  immutable. `Provenance` carries `AttachedBy`/`AttachedByPrincipal`, but the
  comment says they are "an audit trail, not an eligibility decision".
  `reviewstore.ProveReviewer` returns only attempt and lineage.
  `reviewstore.checkAuthoring` already verifies worker request authoring
  facts against provenance at request ingest.
- **Who can attach executions.**
  - `POST /api/v1/work-items/{id}/executions` (`AttachWorkItemExecution`,
    `internal/api/handlers_work_items.go`) admits any principal with
    `workItemWriteRole` on the tenant and takes `engine`/`engine_ref` from
    the body. A developer can therefore mint an execution with any engine
    run, and so any `attempt_id`/`lineage_root`. Its `attached_by` would be
    `github:<login>`/`oidc:<id>`.
  - Resume (`resumeTx`) is the same.
  - Execution-request fulfilment (`FulfilExecutionRequest`,
    `internal/workitems/execution_requests.go`) is reachable only through
    `executionPlatform` (`isDirectService`:
    `u.IsService() && !relayed`).
  - `Mutation` (`internal/workitems/inputs.go`) carries `Actor`,
    `ActorPrincipalID`, `ViaPrincipalID` and `ViaExecutionID`, but no
    "direct service" fact and no path.
- **Run tokens.** `internal/workitems/agent_run_tokens.go`
  `ResolveAgentRunToken` binds token to `ExecutionID`/`WorkItemID`/`Scope`,
  refuses revoked, expired and terminal-execution tokens, and builds
  `auth.NewAgentUser` (`internal/auth/agent.go`). `User.ExecutionID()`,
  `AgentRunID()`, `AgentName()` and `AgentScope()` expose them. Scopes are
  server-defined in `internal/auth/agent_scope.go` (`investigate`, `support`).
  A scoped token reaches only listed routes, and a scoped mint refuses extra
  permissions (`artCodePermissionsUnexpected` in
  `handlers_agent_run_tokens.go`).
- **Tier A.** `reviewreceipts.SealReceipt(request, SealReceiptInput)` fills
  `ReviewerActor`, `ReviewerExecutionID`, `AttemptID` and `LineageRoot` from
  its input. A worker request yields `assurance=independent`.
  `EvaluateReviewGate` (`gate.go`) treats a worker receipt as independent only
  when all three reviewer facts are present and differ from the authoring
  execution, attempts and lineage, and the actor is not an author.
- **Docs.** `docs/review-receipts.md` "Disabled worker path" lists four
  prerequisites. Items 1-3 have landed: 1 is #896; 2 is #923 (Tier B,
  mctl-api 4.151.0) and mctl-agents#980 (Tier A); 3 is mctl-agents#979
  (mctl-agents 1.116.0). The docs still describe 2 and 3 as pending. Item 4
  is this issue.

Deployed state checked:
- mctl-api is not a catalogue tenant service, and no
  `services/*/mctl-api/values.yaml` exists. Its env lives in the ArgoCD
  Application `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`
  in mctl-gitops (verified on main 2026-11-02).
- That file sets `AUDIT_DB_URL` (shared-pg database `mctl-api`) and
  `LIFECYCLE_DB_URL`. It sets no `REVIEW_*` variable, no `EVIDENCE_DB_URL` and
  no `WORK_ITEMS_DB_URL`.
- So `REVIEW_RECEIPTS_DISABLED` is unset and the review routes are live. The
  review store and the work-items store both fall back to `AUDIT_DB_URL`, the
  same database. The code must still not assume one DB: see Cross-DB
  atomicity below.
- Enabling the worker route means adding `REVIEW_WORKER_INGEST_ENABLED:
  "true"` to that file in a separate mctl-gitops PR. That is an operator
  decision and not part of this proposal.

## Proposed solution

### 1. Server-recorded attacher eligibility (workitems)

- Add `ActorDirectService bool` to `workitems.Mutation`. It is not part of
  `RequestHash`, like `ActorClientID`. `mutationFor` in
  `internal/api/handlers_work_items.go` sets it to
  `isDirectService(user) && !user.IsAgent()`. An agent principal is never
  `IsService`, but the explicit guard keeps a future change from widening it.
- Extend the `execution_provenance` schema in `internal/workitems/store.go`
  additively:
  `ALTER TABLE execution_provenance ADD COLUMN IF NOT EXISTS attach_path TEXT NOT NULL DEFAULT ''`
  and
  `... ADD COLUMN IF NOT EXISTS attached_direct_service BOOLEAN NOT NULL DEFAULT false`.
  ADD COLUMN does not fire the row UPDATE trigger. Old rows get `''`/`false`
  and are therefore ineligible (fail closed, no backfill).
- `insertExecution` and `insertProvenance` take an `attachPath` argument.
  - `attachNewTx` passes `attach` for `AttachExecution` and `fulfil_start`
    for start fulfilment.
  - `resumeTx` passes `resume` for `Resume` and `fulfil_resume` for resume
    fulfilment.
  - The fulfil callers pass the path through the existing tx helpers.
  - `attached_direct_service` is written from `m.ActorDirectService`.
- `Provenance` gains `AttachPath` and `AttachedDirectService` (JSON
  `attach_path`, `attached_direct_service`), scanned in
  `ExecutionProvenance`. `validProvenance` is unchanged.
  `GET /api/v1/executions/{id}/provenance` exposes the new fields
  (additive). `docs/execution-provenance.md` is updated.
- Eligibility rule, in `reviewstore`, not in workitems:
  `p.AttachedDirectService == true`. This means the execution's `engine` and
  `engine_ref` were chosen by the platform (the service principal acting
  directly), whether through fulfilment or a platform-side attach. Developer,
  agent, relayed-surface and pre-change rows are all ineligible.
  `AttachedByPrincipal` stays in the audit record and is not used as a
  credential.

### 2. A `review` agent scope (auth)

Add `AgentScopeReview = "review"` to `internal/auth/agent_scope.go`:

- `Agents: []string{"review-worker"}` (see Open questions).
- Not `ReadAllTenants`, not `BoundTenant`, not `MintByTenantMember`, so only
  the direct service principal can mint it, as for `investigate`.
- `AuditRequests: true`, `Tool: func(string) bool { return false }`.
- `Routes`: `GET ^/api/v1/whoami$` and `POST ^/api/v1/review-receipts$`.
- `Deny: agentDeniedRoutes`.

The mint handler must also refuse a `review` scope with `WithoutExecution`:
the token must be execution-bound.

### 3. Store: `SubmitWorker` (reviewstore)

New in `internal/reviewstore/receipts.go`:

```go
type WorkerInput struct { RequestID string; Subject reviewreceipts.ReviewSubject; Nonce, Outcome string;
    Criteria []reviewreceipts.Criterion; FindingsRef reviewreceipts.ArtifactRef; EvidenceRef string }
type Reviewer struct { Actor Actor; ExecutionID, RunID string } // all from auth.User, never the body
func (s *Store) SubmitWorker(ctx, in WorkerInput, rv Reviewer, now time.Time) (*StoredReceipt, error)
```

Order of checks. Every refusal happens before any write.

1. `rv.ExecutionID` must match `we_` and the Tier B `executionIDRE`, else
   `ErrRunTokenUnbound`.
2. `s.Request` gives not found (404), closed (`ErrRequestClosed`), or
   `Mode != worker` (new `ErrRequestModeManual`). A binding mismatch is
   `ErrBindingMismatch`.
3. Nonce: `subtle.ConstantTimeCompare(nonceDigest(in.Nonce),
   nonceDigest(req.Request.Nonce))`, else new `ErrNonceMismatch`.
4. `lookupProvenance(rv.ExecutionID)`: absent is `ErrExecutionUnproven`,
   a read failure is `ErrProvenanceUnavailable`.
   `!p.AttachedDirectService` is new `ErrReviewerIneligible`.
5. Independence, mirroring the gate:
   - `p.ExecutionID != req.AuthoringExecutionID`
   - `p.AttemptID` not in `AuthoringAttemptIDs`
   - `p.LineageRoot != AuthoringLineageRoot`
   - `rv.Actor.Name` not in `AuthorActors` (case-insensitive)

   Any failure is new `ErrReviewerNotIndependent`.
6. `SealReceipt(req.Request, SealReceiptInput{ReviewerActor: rv.Actor.Name,
   ReviewerExecutionID: p.ExecutionID, AttemptID: p.AttemptID,
   LineageRoot: p.LineageRoot, ...})`. Assert `rc.Mode == worker &&
   rc.Assurance == independent` (defence in depth).
7. A single `pgx` transaction:
   - `INSERT INTO review_nonce_consumptions (nonce_sha256, request_id,
     receipt_id, consumed_at)`. A unique violation on the PK is new
     `ErrNonceConsumed`, and the tx rolls back.
   - Then `INSERT INTO review_receipts (...)` (no `ON CONFLICT DO NOTHING`
     here: a conflict is an error and rolls back the consumption).
   - Commit. Any other error rolls back and surfaces as a driver error,
     which becomes 503 `review_store_unavailable`.
8. Return `s.receipt(ctx, rc.ReceiptID)`.

`ProveReviewer` stays as is. `SubmitWorker` reads the full `Provenance`
because it needs `AttachedDirectService`. The `ProvenanceLookup` interface is
unchanged.

Add a `review_receipts` CHECK, `review_receipts_worker_independent CHECK (mode
<> 'worker' OR assurance = 'independent')`. It is added idempotently in a
`DO $$ ... IF NOT EXISTS (pg_constraint) ...` block, mirroring the manual
CHECK.

### 4. Handler (api)

`SubmitWorkerReview` becomes:

1. `if !h.opts.ReviewWorkerIngestEnabled` gives the existing 501. A new
   `api.Options` field (`internal/api/router.go`, held as `h.opts`) is read
   from `REVIEW_WORKER_INGEST_ENABLED` in
   `cmd/api/main.go`, default false, and documented in `helm/values.yaml`
   comments.
2. `reviewStoreOrUnavailable`.
3. The user must be `user.IsAgent()`, `user.ExecutionID() != ""`, and
   `AgentScope().Name == auth.AgentScopeReview`. Otherwise 403
   `review_run_token_required`.
4. `readReviewBody` and decode `workerReceiptBody` (`request_id`, `subject`,
   `nonce`, `outcome`, `criteria`, `findings_ref`, `evidence_ref`) with
   `DisallowUnknownFields` and a trailing-data check, reusing the manual
   decode helper extracted into one function.
5. Call `SubmitWorker` with `Reviewer{Actor: reviewActor(user), ExecutionID:
   user.ExecutionID(), RunID: user.AgentRunID()}`.
6. Audit `review.worker_submit` on success. On refusal, audit
   `review.worker_submit_refused` with the code.
7. Answer 201 with `receipt_id`, `request_id`, `mode`, `assurance`,
   `tenant` and `receipt`.

New codes are added to the `reviewRefusals` table:

| Error | Status | Code |
| --- | --- | --- |
| `ErrRequestModeManual` | 409 | `review_request_mode_manual` |
| `ErrNonceMismatch` | 403 | `review_nonce_mismatch` |
| `ErrNonceConsumed` | 409 | `review_nonce_consumed` |
| `ErrReviewerIneligible` | 403 | `review_reviewer_ineligible` |
| `ErrReviewerNotIndependent` | 409 | `review_reviewer_not_independent` |
| `ErrRunTokenUnbound` | 403 | `review_run_token_required` |

The route stays in the `review:` rate-limit group. `rateLimitSubject` keys an
agent per run.

### 5. Docs and contract

- Update `docs/review-receipts.md`:
  - Routes table and Codes.
  - Replace "Disabled worker path" with "Worker path": enable switch,
    prerequisites status, eligibility rule.
  - Change "`review_nonce_consumptions`: created for the worker follow-up"
    to describe its writer.
- Update `internal/openapi/openapi.yaml` for `POST /api/v1/review-receipts`.
- Update `CHANGELOG` through release-please conventional commit.
- No MCP tool is added, so the `server_test.go` count is unchanged.

## Alternatives

1. **Use `attached_by_principal` against a configured allowlist of
   principal ids** (for example `REVIEW_ELIGIBLE_ATTACHERS=prn_...`). Dropped
   as the primary rule:
   - It relies on string identity in an audit column and on deployment
     config being correct.
   - It cannot tell a service principal acting directly from the same
     principal relayed by a surface.
   - An empty allowlist either opens everything or blocks everything.

   Recording `attached_direct_service` at write time from the same
   `isDirectService` predicate the platform already trusts for fulfilment is
   precise and fails closed for legacy rows. An allowlist may be layered on
   later (Open questions).
2. **Accept `reviewer_execution_id`/`attempt_id`/`lineage_root` in the body
   and verify them against provenance.** Dropped: the issue forbids
   caller-asserted reviewer identity. Verifying asserted facts also leaves a
   confused-deputy gap: a token for execution A could assert execution B if
   B's facts verify. Deriving from the token removes the field entirely.
3. **Consume the nonce by a conditional UPDATE on `review_requests`.**
   Dropped: those rows are immutable by trigger, and the dedicated
   `review_nonce_consumptions` table with its PK already exists for exactly
   this. An INSERT-PK conflict is the atomic single-use primitive.
4. **Rely only on the gate to reject non-independent worker receipts.**
   Dropped: the receipt would still be stored and the nonce burnt by an
   ineligible reviewer, which is a denial of service on the request. Refusing
   at ingest stores nothing. The gate check remains as a second layer.

## Platform impact

- **Migrations.** All additive and idempotent at startup:
  - two `ADD COLUMN IF NOT EXISTS` on `execution_provenance` (workitems DB);
  - one guarded CHECK on `review_receipts` (evidence DB). The CHECK cannot
    fail on existing data, because no worker receipts exist today: the route
    has always been 501.

  No backfill.
- **Backward compatibility.**
  - The provenance read API gains two fields (additive).
  - Manual route, request ingest and gate are untouched.
  - The worker route stays 501 until `REVIEW_WORKER_INGEST_ENABLED=true`, so
    deploying the code changes no live behaviour.
  - `Mutation` gains a field, but no `RequestHash` change, so idempotency
    replays of existing keys are unaffected.
- **Cross-DB atomicity.** Provenance lives in the workitems DB and receipts
  and nonces in the evidence DB. Provenance rows are immutable, so reading
  them before the evidence-DB transaction has no TOCTOU risk on the facts
  used.
- **Resources.** One provenance read and one 2-insert transaction per
  submit, rate-limited at 30/min per principal. Negligible.
- **Risks and mitigations.**
  - *Service principal attaches executions for developers via some other
    path.* The only direct-service attach paths are the execution platform's
    own. A test enumerates every `insertExecution` caller and fails if a new
    caller does not pass an explicit path.
  - *Enabling with a placeholder agent name.* The flag defaults off. The
    docs say that enabling also needs the real reviewer agent name from
    mctl-agents#905 in the `review` scope.
  - *Burnt nonce on a transient failure after consumption.* Consumption and
    receipt insert share one transaction, so either both commit or neither
    does.
  - *Agent name mismatch with mctl-agents.* Until the name is confirmed, the
    scope admits a name nobody mints, which fails closed.
