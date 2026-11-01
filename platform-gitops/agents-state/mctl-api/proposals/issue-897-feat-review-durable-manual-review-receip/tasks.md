# Tasks: issue-897-feat-review-durable-manual-review-receip

- [ ] 1. Add exported `SubjectIdentity.Key()` and `SubjectBinding.Key()`
  (canonical JSON) to `internal/reviewreceipts`. This is additive only, with no
  new imports. — DoD: `purity_test.go` and `vectors_test.go` still pass. Keys
  are equal if and only if the structs are equal, checked over the golden
  vectors.
- [ ] 2. Create `internal/reviewstore`. It holds the `schema` const for
  `review_requests`, `review_receipts` and `review_nonce_consumptions`, with
  `ingest_seq` identity columns, the `nonce_sha256` unique index, the
  `mode <> 'manual' OR assurance = 'advisory'` CHECK, `review_rows_immutable()`
  and guarded `BEFORE UPDATE` triggers. It also holds
  `NewStore(ctx, dbURL, Config{TTL, PoolMax})` and `Close`. (depends on 1) —
  DoD: two consecutive `NewStore` calls on one database succeed. An UPDATE on
  each table raises.
- [ ] 3. Implement `IngestRequest`: a narrow `EvidenceLookup` interface
  satisfied by `evidence.Store`, `SetEvidence`, tenant derivation from
  `Ref.Tenant`, verbatim bytes, replay versus `ErrIdempotencyConflict`, and
  `ErrNonceReused`, `ErrUnsealed`, `ErrAuthoringUnresolved`,
  `ErrTenantUnresolved` and `ErrEvidenceUnavailable`. (depends on 2) — DoD:
  store tests cover every error and the replay path.
- [ ] 4. Implement `Request` with computed closure (`ttl` and `superseded` with
  `closed_by`, where a same-binding repeat closes nothing). (depends on 3) —
  DoD: table-driven tests for TTL expiry, supersession by a newer binding, and
  a same-binding repeat.
- [ ] 5. Implement `SubmitManual`: not-found, closed, `mode=worker` refusal,
  binding equality, `SealReceipt` with a server actor and time, the
  manual/advisory assertion, insert with the request's tenant, and no nonce
  consumption. (depends on 4) — DoD: tests prove the stored row is
  `manual/advisory` and `review_nonce_consumptions` stays empty.
- [ ] 6. Implement `Pool` (`ORDER BY ingest_seq`, `LIMIT max+1`,
  `ErrPoolTooLarge`, re-parse, `ErrStoreCorrupt`) and `GateInput` (the newest
  request for the binding plus the full pool). (depends on 5) — DoD: tests for
  ordering, the over-limit case and a corrupt row. No partial result is ever
  returned.
- [ ] 7. Add HTTP handlers in `internal/api/handlers_review_receipts.go`:
  `POST /review-requests`, `POST /review-receipts/manual`,
  `POST /review-receipts` (501), `GET /review-requests/{id}`,
  `GET /review-receipts` and `GET /review-gate`. Also add
  `Options.ReviewStore`, the nil-store 503, a typed error table, a 64 KiB body
  cap, unknown-key refusal for `tenant`/`submitted_by` and the other
  server-owned fields, and audit entries without the nonce. (depends on 6) —
  DoD: handler tests for every status and code listed in design.md.
- [ ] 8. Router: add a review write group with
  `httprate.Limit(reviewWritesPerMinute=30)` keyed `"review:"+rateLimitSubject`,
  put the reads in the admin read block, and extend `evidenceWriterGate` and
  its 403 message with `POST /api/v1/review-requests`. (depends on 7) — DoD:
  the rate-limit test shows the bucket. The evidence writer reaches review
  ingest but not the manual route or the reads.
- [ ] 9. Wire `cmd/api/main.go`: `evidenceDBURL`, `REVIEW_RECEIPTS_DISABLED`,
  `REVIEW_REQUEST_TTL` (default 24h; an invalid value leaves the store nil and
  logs an error) and `REVIEW_POOL_MAX` (default 10000), plus `SetEvidence` when
  the evidence store exists. Add the same items to the Helm values comments.
  (depends on 8) — DoD: `go build ./...`. A missing DB or the kill switch logs
  and answers 503.
- [ ] 10. MCP: `internal/mcp/review_receipts.go` with
  `mctl_submit_review_assertion` (write, not destructive) and
  `mctl_get_review_gate` (read-only), registered in `server.go`. Add both to
  `recordedHints` and to `docs/portal-allowlist.json` (gate enabled, submit
  disabled, each with a reason). (depends on 7) — DoD: `server_test.go`,
  `annotations_test.go` and `portal_allowlist_test.go` pass with the count up
  by 2.
- [ ] 11. Write `docs/review-receipts.md` covering the tables, closure, routes,
  codes, the manual-is-advisory invariant and the disabled worker path with its
  preconditions (mctl-api#896, run-token binding). (depends on 7) — DoD: every
  code in the handler table appears in the doc.
- [ ] 12. Run `go fmt`, `go vet`, `golangci-lint` and `go test ./...`.
  (depends on 1-11) — DoD: all clean.

## Tests

- [ ] T1. Schema idempotency and immutability: a double `NewStore`; UPDATE on
  each of the three tables raises; inserting a `manual/independent` receipt row
  directly violates the CHECK.
- [ ] T2. Ingest: a golden sealed request is stored with byte-identical
  `document`. An unsealed document gives `review_unsealed`. A tampered
  `content_hash` gives `review_bad_identity`. A top-level `tenant` key gives
  `review_unknown_key`.
- [ ] T3. Ingest authoring: a `we_` id and an `ex-` id resolving to evidence
  are accepted, with the tenant taken from `Ref.Tenant`. No evidence gives 422
  `review_authoring_unresolved`. An empty tenant gives 422
  `review_tenant_unresolved`. An erroring lookup or an unset evidence store
  gives 503 `review_evidence_unavailable`.
- [ ] T4. Replay and nonce: identical bytes give 200 `replayed:true`. A
  different request with the same nonce gives 409 `review_nonce_reused`.
- [ ] T5. Closure: a request older than TTL is closed (`ttl`). A newer request
  with the same identity and a different binding closes the older one
  (`superseded`, `closed_by`). A same-binding repeat leaves both open.
- [ ] T6. Manual authorization: a human admin is accepted. A service with the
  admins group, a relayed caller, a surface caller and a non-admin all get 403
  `review_not_permitted`. `CheckHumanPrincipal` returning
  `ErrPrincipalDisabled` gives 403, and any other error gives 503
  `review_principal_unavailable`.
- [ ] T7. Manual validation: unknown request gives 404. Closed gives 409
  `review_request_closed`. A worker-mode request gives 409
  `review_request_mode_worker`. A binding mismatch (for a proposal, a different
  `content_digest`; a different `gitops_commit` is NOT a mismatch) gives 409
  `review_binding_mismatch`. PASS with an unmet criterion gives 400
  `review_pass_with_unobserved`. A body containing `reviewer_actor`,
  `assurance`, `tenant` or `submitted_by` gives 400 `review_unknown_key`.
- [ ] T8. Manual storage: the row is `manual/advisory`, `reviewer_actor` is the
  server actor, the tenant equals the request's, and
  `review_nonce_consumptions` has zero rows. An audit entry exists and does not
  contain the nonce.
- [ ] T9. Worker refusal: `POST /api/v1/review-receipts` gives 501
  `review_worker_ingest_disabled`, and the table is unchanged.
- [ ] T10. Pool: rows come back in `ingest_seq` order with `complete:true`. At
  `REVIEW_POOL_MAX+1` rows the answer is 503 `review_pool_too_large` with no
  list. A store error gives 503 `review_store_unavailable`. A nil store gives
  503 on every route.
- [ ] T11. Gate: with only a manual PASS receipt, `required_assurance=any`
  gives `satisfied` and `independent` gives `advisory_only`. No request gives
  `missing`/`stale`/`unknown`, matching `EvaluateReviewGate`. The response
  carries the request document and the full pool. Re-running
  `EvaluateReviewGate` on the returned input reproduces the verdict.
- [ ] T12. MCP: both tools hit the expected REST path with the caller's token,
  the hints match `recordedHints`, and the portal allowlist test passes.
- [ ] T13. Rate limit: the 31st review write in a minute from one principal
  gets 429, while evidence ingest from the same principal is unaffected.

## Rollback

- Fast: set `REVIEW_RECEIPTS_DISABLED=true` and redeploy. Every review route
  answers 503 `review_store_unavailable` and the MCP tools surface that. No
  other subsystem depends on the store.
- Full: revert the PR. The three tables stay behind, inert, because they are
  created with `IF NOT EXISTS` and nothing else reads them. They can be dropped
  manually (`DROP TABLE review_nonce_consumptions, review_receipts,
  review_requests; DROP FUNCTION review_rows_immutable();`) once no consumer
  needs the stored review history. Before dropping, export the tables if the
  manual receipts carry audit value.
- Remove the two entries from `docs/portal-allowlist.json` and re-apply the
  portal mapping if they were enabled.
