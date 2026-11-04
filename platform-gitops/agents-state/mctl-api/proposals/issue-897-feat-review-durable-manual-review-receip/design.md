# Design: issue-897-feat-review-durable-manual-review-receip

## Current state

- `internal/reviewreceipts/` (Slice A, mctl-api#895) has merged. It is pure, and
  `purity_test.go` forbids I/O imports.
  - `types.go`: `ReviewSubject` with `Identity()` (a 4-tuple) and `Binding()`
    (for a proposal, `gitops_commit` and `approval_ref` are provenance only).
    `ReviewRequest` and `ReviewReceipt`. Constants `ModeWorker`/`ModeManual` and
    `AssuranceIndependent`/`AssuranceAdvisory`/`AssuranceAny`, plus the gate
    answers.
  - `parse.go`: `ParseRequest`/`ParseReceipt` decode strictly. They recompute
    and verify `content_hash`/`request_id` when present, but do not require
    them. `ReviewReceipt.Validate` forces `manual => advisory` and
    `worker => independent`, and enforces the PASS and CHANGES_REQUESTED rules.
  - `identity.go`: `SealRequest` (the nonce is an input and is never
    generated) and `SealReceipt(request, in)`. The receipt takes the request's
    subject, rubric, mode and nonce. A manual request forces `advisory`.
  - `errors.go`: the codes `review_malformed`, `review_unknown_key`,
    `review_bad_subject`, `review_bad_identity`, `review_rubric_mismatch`,
    `review_pass_with_unobserved` and `review_unobserved_outcome`, with
    `errors.Is` sentinels.
  - `gate.go`: `EvaluateReviewGate(live, request, pool, requiredAssurance)`.
    The pool must be complete and in ingest order, oldest first. A
    manual/advisory receipt yields `advisory_only` under
    `required_assurance=independent`.
- Durable-store pattern that this slice copies:
  - `internal/decisions/store.go` and `internal/evidence/store.go` hold a
    `schema` const applied in `NewStore`, `CREATE TABLE IF NOT EXISTS`, a shared
    `*_immutable()` plpgsql function, and `BEFORE UPDATE` triggers created
    under `IF NOT EXISTS (SELECT 1 FROM pg_trigger ...)`. DELETE stays allowed.
  - `cmd/api/main.go` (around lines 660-770) wires the evidence store from
    `EVIDENCE_DB_URL`, falling back to `AUDIT_DB_URL`. Decisions reuse
    `evidenceDBURL` with a `DECISIONS_DISABLED` kill switch through
    `initStore(initCtx, storeFailures, ...)`. On failure it logs and leaves the
    store nil, so the routes answer 503.
- Evidence lookup: `evidence.Store.List(ctx, evidence.Filter{ExecutionID |
  RuntimeExecutionID, Limit})` (`internal/evidence/read.go`). Records carry
  `Ref *EvidenceRef` with `Tenant` (`internal/evidence/types.go:180, 239`).
  `executionIDRE` in Slice A accepts both `we_...` and `ex-...` ids, and the
  evidence table separates them into `execution_id` and `runtime_execution_id`
  (`internal/evidence/store.go:51-61`).
- Authorization:
  - `isHumanAdmin(u)` (`internal/api/handlers_action_approvals.go:87`) means
    admin, not a service, not relayed and not a surface.
  - `checkHumanPrincipal(ctx, pr, prn)` (`internal/api/handlers_surface_identity.go:363`)
    wraps `auth.HumanPrincipalChecker.CheckHumanPrincipal` and maps
    `ErrPrincipalDisabled` and `ErrIdentityRefused` to codes. Any other error
    means 503.
  - `requireEvidenceWriter` (`handlers_evidence.go:97`) admits
    `PermissionEvidenceWrite` holders.
  - `evidenceWriterGate` (`handlers_evidence.go:82`) restricts the evidence
    writer to an explicit route list (`POST /evidence/records`, the decision
    write routes).
- HTTP conventions: `writeErrorCode(w, status, code, msg, details)`
  (`handlers_read.go:1011`), `h.logAudit(r, audit.Entry{...})`
  (`clientmeta.go:172`). Per-route `httprate.Limit(...)` groups are keyed by
  `rateLimitSubject` (`router.go:808, 849, 1265`). There is a global 300/min
  per principal, of which evidence uses 120 and decisions 150. Reads sit in the
  admin read block at `router.go:894-908`.
- MCP: tools call the in-process REST API with the caller's token. One example
  is `toolGetUsageSummary` in `internal/mcp/usage.go`, registered in
  `internal/mcp/server.go:353-362`. `recordedHints` in
  `internal/mcp/annotations_test.go` must list every tool, and `server_test.go`
  compares `len(ListTools())` against it. `docs/portal-allowlist.json` needs an
  explicit `enabled` and `reason` per tool, enforced by
  `internal/mcp/portal_allowlist_test.go`.
- No review store, route, MCP tool or `docs/review-receipts.md` exists yet.
  `grep review_requests` finds nothing outside Slice A.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/`: the tenants listed are `admins`, `karabu`,
  `labs` and `namax66`. No `*/mctl-api/values.yaml` exists there. mctl-api is
  not deployed as a tenant service in this checkout, so its deployed env
  (`EVIDENCE_DB_URL`, `AUDIT_DB_URL`, kill switches) was not observed. That is
  a gap, not an absence.
- No mctl MCP read tools were called. This slice adds new, default-off-safe
  config and does not depend on observed runtime values.

## Proposed solution

### 1. New package `internal/reviewstore`

The package is kept separate from `internal/reviewreceipts` so that Slice A
stays pure. It depends on `reviewreceipts`, `pgshared`/pgx, and a narrow
`EvidenceLookup` interface that `evidence.Store` satisfies.

Schema (a `schema` const applied in `NewStore`, idempotent):

```sql
CREATE TABLE IF NOT EXISTS review_requests (
    ingest_seq        BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
    request_id        TEXT PRIMARY KEY CHECK (request_id ~ '^rr_[0-9a-f]{16}$'),
    content_hash      TEXT NOT NULL,
    document          BYTEA NOT NULL,          -- bytes verbatim as received
    subject_kind      TEXT NOT NULL,
    identity_key      TEXT NOT NULL,           -- canonical JSON of Identity()
    binding_key       TEXT NOT NULL,           -- canonical JSON of Binding()
    mode              TEXT NOT NULL CHECK (mode IN ('worker','manual')),
    nonce_sha256      TEXT NOT NULL,
    authoring_execution_id TEXT NOT NULL,
    tenant            TEXT NOT NULL CHECK (tenant <> ''),
    ingested_by       TEXT NOT NULL,
    ingested_by_principal_id TEXT NOT NULL DEFAULT '',
    ingested_at       TIMESTAMPTZ NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS review_requests_nonce ON review_requests (nonce_sha256);
CREATE INDEX IF NOT EXISTS review_requests_identity ON review_requests (identity_key, ingest_seq);

CREATE TABLE IF NOT EXISTS review_receipts (
    ingest_seq        BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
    receipt_id        TEXT PRIMARY KEY CHECK (receipt_id ~ '^rc_[0-9a-f]{16}$'),
    request_id        TEXT NOT NULL REFERENCES review_requests (request_id),
    content_hash      TEXT NOT NULL,
    document          BYTEA NOT NULL,
    mode              TEXT NOT NULL CHECK (mode IN ('worker','manual')),
    assurance         TEXT NOT NULL CHECK (assurance IN ('independent','advisory')),
    tenant            TEXT NOT NULL,
    submitted_by      TEXT NOT NULL,
    submitted_by_principal_id TEXT NOT NULL DEFAULT '',
    submitted_at      TIMESTAMPTZ NOT NULL,
    CONSTRAINT review_receipts_manual_advisory CHECK (mode <> 'manual' OR assurance = 'advisory')
);

CREATE TABLE IF NOT EXISTS review_nonce_consumptions (
    nonce_sha256 TEXT PRIMARY KEY,
    request_id   TEXT NOT NULL REFERENCES review_requests (request_id),
    receipt_id   TEXT NOT NULL,
    consumed_at  TIMESTAMPTZ NOT NULL
);
-- review_rows_immutable() + guarded BEFORE UPDATE triggers on all three,
-- exactly the decision_records_immutable shape.
```

`review_nonce_consumptions` is created now, so the worker follow-up needs no
schema change. Nothing in this slice writes to it. A store test asserts that
the table stays empty after manual submissions.

The identity and binding keys are canonical JSON of the Slice A tuples. Slice A
gets a small additive exported helper (`SubjectIdentity.Key()`,
`SubjectBinding.Key()`) so that Go and SQL agree on equality. The gate itself
still compares structs.

Store API:

- `IngestRequest(ctx, raw []byte, actor Actor) (*StoredRequest, replayed bool, error)`.
  1. Run `reviewreceipts.ParseRequest(raw)`. A `*reviewreceipts.Error` passes
     through.
  2. Require a non-empty `ContentHash`/`RequestID`, else `ErrUnsealed`.
  3. Resolve `AuthoringExecutionID` through `EvidenceLookup`: `we_` maps to
     `Filter.ExecutionID`, `ex-` maps to `Filter.RuntimeExecutionID`, with
     `Limit: 1`. A lookup error gives `ErrEvidenceUnavailable`. No records
     gives `ErrAuthoringUnresolved`. An empty `Ref.Tenant` gives
     `ErrTenantUnresolved`.
  4. INSERT ... ON CONFLICT (request_id) DO NOTHING. On conflict, re-read the
     stored row and compare the document bytes: equal means a replay, otherwise
     `ErrIdempotencyConflict` (409 `review_request_conflict`). A unique
     violation on `review_requests_nonce` gives `ErrNonceReused`.
- `Request(ctx, id) (*StoredRequest, error)` returns the row plus computed
  `Closed`, `ClosedReason` (`ttl` | `superseded`) and `ClosedBy`.
  - TTL: `ingested_at + ttl <= now`.
  - Supersession: `EXISTS (SELECT 1 FROM review_requests r2 WHERE
    r2.identity_key = r.identity_key AND r2.binding_key <> r.binding_key AND
    r2.ingest_seq > r.ingest_seq)`.
  - Closure is computed on every read and is never written back.
- `SubmitManual(ctx, in ManualInput, actor Actor, now time.Time) (*StoredReceipt, error)`.
  1. Load the request. Not found gives `ErrRequestNotFound`, closed gives
     `ErrRequestClosed`, and `mode != manual` gives `ErrRequestModeWorker`.
  2. If `in.Subject.Binding() != req.Subject.Binding()`, return
     `ErrBindingMismatch`.
  3. Call `reviewreceipts.SealReceipt(req, SealReceiptInput{Outcome, Criteria,
     FindingsRef, ReviewerActor: actor.Name, CreatedAt: now.UTC() RFC3339})`.
     Its errors pass through.
  4. Defence in depth: assert `Mode==manual && Assurance==advisory` before the
     INSERT. The CHECK also enforces it.
  5. INSERT into `review_receipts` with the request's tenant. Do not touch
     `review_nonce_consumptions`.
  6. Idempotency: the receipt id is a content hash, so an identical
     resubmission within the same second replays. A different `created_at`
     gives a new receipt, which is acceptable for an append-only pool.
- `Pool(ctx) ([]reviewreceipts.ReviewReceipt, []StoredReceipt, error)` runs
  `SELECT ... ORDER BY ingest_seq ASC LIMIT max+1`. More than `max` rows gives
  `ErrPoolTooLarge`. Each document is re-parsed with `ParseReceipt`, and any
  parse failure gives `ErrStoreCorrupt`, which the HTTP layer reports as 503
  `review_store_unavailable`. A partial pool is never returned.
- `GateInput(ctx, live reviewreceipts.ReviewSubject) (*StoredRequest, []ReviewReceipt, error)`
  selects the newest request (max `ingest_seq`) with
  `binding_key = live.Binding().Key()`, open or closed, plus the full pool.

### 2. HTTP (`internal/api/handlers_review_receipts.go`)

`Options.ReviewStore *reviewstore.Store` is a nil-able pointer, never a typed
nil in an interface.

| Route | Auth | Notes |
| --- | --- | --- |
| `POST /api/v1/review-requests` | `requireEvidenceWriter` | Own `httprate` group of `reviewWritesPerMinute = 30`, keyed `"review:"+rateLimitSubject`. The sum of evidence (120), decisions (150) and review (30) stays at or under the 300/min global. `evidenceWriterGate` gains this route. |
| `POST /api/v1/review-receipts/manual` | `isHumanAdmin` and `checkHumanPrincipal` | Same rate group. Audited as `review.manual_submit`. |
| `POST /api/v1/review-receipts` | any authenticated caller | Always 501 `review_worker_ingest_disabled`. Reads no body. |
| `GET /api/v1/review-requests/{id}` | admin | Returns the request plus closure. |
| `GET /api/v1/review-receipts` | admin | `{receipts:[...], count, complete:true}` or a typed 503. |
| `GET /api/v1/review-gate` | admin | Query: subject fields and `required_assurance`. |

Body shape for manual submission:
`{"request_id", "subject", "outcome", "criteria":[{"id","status"}],
"findings_ref":{"name","kind","content_hash"}}`. It is decoded with
`DisallowUnknownFields` semantics mapped to 400 `review_unknown_key`. That
mapping covers `tenant`, `submitted_by`, `reviewer_actor`, `assurance`,
`mode`, `nonce` and `created_at`. The request ingest body is the sealed
document itself, so any non-Tier-A top-level key such as `tenant` is already
`review_unknown_key` from `ParseRequest`. Bodies are capped at 64 KiB.

The error table follows the `writeDecisionError` pattern:
- 400: Slice A codes and `review_unsealed`.
- 403: `review_not_permitted`.
- 404: `review_request_not_found`.
- 409: `review_request_closed`, `review_binding_mismatch`,
  `review_request_mode_worker`, `review_nonce_reused`,
  `review_request_conflict`.
- 422: `review_authoring_unresolved`, `review_tenant_unresolved`.
- 501: `review_worker_ingest_disabled`.
- 503: `review_store_unavailable`, `review_pool_too_large`,
  `review_evidence_unavailable`, `review_principal_unavailable`.

Gate response:
`{verdict, required_assurance, live_subject, request: <document|null>,
request_closed, pool: [...], pool_count, complete: true}`. This is the full
Tier A input (`live`, `request`, `pool`, `required_assurance`), so Tier A can
re-run `evaluate_review_gate` and get the same answer. When no request matches,
`request` is null and the verdict is whatever `EvaluateReviewGate` answers
(`missing`, `stale` or `unknown`).

Audit: `review.request_ingest` and `review.manual_submit`, carrying the
request/receipt id, tenant and outcome, never the nonce.

### 3. Wiring (`cmd/api/main.go`)

The store lives in the evidence database (`evidenceDBURL`) behind
`REVIEW_RECEIPTS_DISABLED`, using the `initStore` shape of decisions.
`reviewStore.SetEvidence(evidenceStore)` is called only when the evidence store
is non-nil. Without it, ingestion answers 503 `review_evidence_unavailable`.
New env:
- `REVIEW_REQUEST_TTL`: Go duration, default `24h`. An invalid value fails the
  store closed: it is logged and the store stays nil.
- `REVIEW_POOL_MAX`: default `10000`.

Both are documented in `cmd/api/main.go` defaults and in the Helm values
comments.

### 4. MCP (`internal/mcp/review_receipts.go`)

- `mctl_submit_review_assertion`: args `request_id`, `subject` (JSON),
  `outcome` (enum), `criteria` (JSON array), `findings_ref` (JSON). It POSTs to
  `/api/v1/review-receipts/manual`. Hints: `readOnlyHint=false`,
  `destructiveHint=false`, `idempotentHint=false`. The description says it is
  a human-admin-only advisory receipt that never satisfies
  `required_assurance=independent`.
- `mctl_get_review_gate`: args are the subject fields and `required_assurance`
  (enum `independent|any`, default `independent`). It GETs
  `/api/v1/review-gate`. Hints: `readOnlyHint=true`.
- Both are registered in `server.go`, added to `recordedHints`, and get
  `docs/portal-allowlist.json` entries with a reason. Proposed setting:
  `mctl_get_review_gate` enabled, `mctl_submit_review_assertion` disabled on
  the shared portal (a human admin write).

### 5. Docs

`docs/review-receipts.md` covers the tables, immutability, closure rules, the
error codes, the routes, the "manual is never independent" invariant, and the
disabled worker path with its enabling preconditions (mctl-api#896 and the
run-token binding).

## Alternatives

1. **Store closure as a column, set by UPDATE.** Dropped because it contradicts
   the immutability trigger and creates write races between concurrent
   ingests. Computing closure at read time is cheap with the
   `(identity_key, ingest_seq)` index.
2. **Put the store inside `internal/reviewreceipts`.** Dropped because
   `purity_test.go` forbids I/O imports there, and Slice A's parity
   guarantees depend on that purity.
3. **Paginate `GET /review-receipts`.** Dropped because the gate needs the
   complete pool. A cursor would let a caller evaluate a partial pool. A hard
   bound with a typed `review_pool_too_large` is the fail-closed option. A
   per-identity filter can be added later without breaking the contract.
4. **Accept manual receipts on worker requests by sealing a manual-mode copy.**
   Dropped because the resulting receipt's `request_id` would not match the
   request it claims to answer. That would be a Tier A contract change and is
   left as an open question.

## Platform impact

- Migrations: three new tables, created idempotently at startup in the
  existing evidence database. No existing table changes. DELETE stays allowed
  for future retention.
- Backward compatibility: the change is purely additive. New routes, new MCP
  tools (the tool count goes up by 2) and new allowlist entries. Existing
  callers are unaffected.
- Resources: small rows. The pool read is bounded by `REVIEW_POOL_MAX`, at
  roughly 2-4 KiB per receipt, so at most about 40 MiB of JSON in the worst
  case. That cap can be lowered if needed.
- Risks and mitigations:
  - A service mints a manual receipt. Mitigated by `isHumanAdmin` plus
    `CheckHumanPrincipal`, which is not widened, and by tests for service,
    relay and surface callers.
  - A manual receipt reads as independent. Mitigated by `SealReceipt` forcing
    advisory, the DB CHECK, the pre-insert assertion, and a gate test under
    `required_assurance=independent`.
  - A partial pool. Mitigated by `LIMIT max+1`, re-parsing every row, and
    returning a typed 503 instead of a 200.
  - Nonce leakage. The nonce is never logged or audited, and only its SHA-256
    is indexed. Receipt documents still carry it, behind admin-only reads (see
    the open question).
  - Evidence store absent. Ingestion returns 503, never "unresolved".
  - Kill switch: `REVIEW_RECEIPTS_DISABLED`.

## Open questions

- Gate request selection among several requests with the same binding.
  Proposed: the newest by `ingest_seq`, open or closed.
- Whether manual receipts against worker-mode requests should ever be allowed.
  They are refused here with `review_request_mode_worker`.
- Whether to redact the nonce from receipt documents on read before worker
  ingest is enabled.
- Requiring `authoring_execution_id` for `mode=manual` requests, which is
  stricter than Tier A.
- `REVIEW_POOL_MAX` default, and the shared-portal enablement of the two
  tools. Both are owner decisions.
- mctl-api's deployed env was not observable from the gitops checkout. Confirm
  that `EVIDENCE_DB_URL` or `AUDIT_DB_URL` is set in production, so the store
  does not come up nil.
