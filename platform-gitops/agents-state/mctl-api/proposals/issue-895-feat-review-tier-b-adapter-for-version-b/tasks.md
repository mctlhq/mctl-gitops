# Tasks: issue-895-feat-review-tier-b-adapter-for-version-b

- [ ] 1. Port the Tier A types, codes and `spike_report_digest_v1` into `internal/reviewreceipts` (`types.go`, `digest.go`). Copy golden fixtures from mctl-agents#971 into `internal/reviewreceipts/testdata/`. — DoD: every Tier A fixture parses or refuses with the same code. Digests and ids match byte for byte.
- [ ] 2. Port `evaluate_review_gate` to `EvaluateReviewGate` (`gate.go`) (depends on 1). — DoD: the fixture outcomes match Tier A. A manual or advisory receipt never satisfies `independent`.
- [ ] 3. Add `internal/reviewreceipts/store.go` (depends on 1): the `review_requests`, `review_receipts` and `review_nonce_consumptions` tables with immutable triggers, the manual-implies-advisory CHECK, and `ingest_seq`. Add `SubmitWorkerReceipt` (a single transaction holding all checks, the nonce consumption and the insert), `SubmitManualReceipt`, `CreateRequest` (returns a nonce, stores only its sha256) and `ListPool` (`limit+1` bound, typed errors, never a partial slice). Add the `EvidenceLookup` and `FenceLookup` interfaces. — DoD: `go test ./internal/reviewreceipts/...` passes against Postgres, as the store tests already do.
- [ ] 4. Add the reviewer principal to `internal/auth/oidc.go` and the federation/bearer wiring: `service:mctl-agents-reviewer`, `review:write`, `MCTL_REVIEWER_TOKEN`, and collision refusals in both directions. Add `reviewerTokenSecret` to the Helm `values.yaml` and `deployment.yaml`. — DoD: unit tests cover token minting and each collision refusal.
- [ ] 5. Add `internal/api/handlers_review_receipts.go`: `reviewerGate`, `CreateReviewRequest`, `SubmitReviewReceipt` (worker or manual by body shape), `ListReviewReceipts` and `writeReviewError`. Add routes and the rate-limited group in `router.go`, and `Options.ReviewReceipts` (depends on 3, 4). — DoD: tenant and actor are derived on the server; a body `tenant`/`actor` gives `review_unknown_key`; manual mode needs `isHumanAdmin` plus `checkHumanPrincipal`; `isHumanAdmin` is not modified.
- [ ] 6. Wire the store in `cmd/api/main.go`: the `REVIEW_RECEIPTS_DB_URL` fallback chain, the `REVIEW_RECEIPTS_DISABLED` kill switch, and `SetLookups(evidenceStore, lifecycleStore)` with nil-interface handling (depends on 3). — DoD: a missing lookup makes writes 503, never accept.
- [ ] 7. Add the MCP tools `mctl_submit_review_assertion` and `mctl_get_review_gate` in `internal/mcp/review_receipts.go`, and register them in `server.go` (depends on 2, 5). — DoD: `recordedHints` in `annotations_test.go` and `docs/portal-allowlist.json` are updated, and the tool-count assertions pass.
- [ ] 8. Write `docs/review-receipts.md` (contract, code table, auth matrix, fail-closed rules) and add a CHANGELOG entry (depends on 5). — DoD: the docs list every code from the requirements.
- [ ] 9. Run `go fmt`, `go vet` and `golangci-lint`, then `go test ./...`. — DoD: clean.

## Tests

- [ ] T1. Replayed nonce: a second worker receipt with a consumed nonce gives `review_nonce_replayed`, and the receipt count is unchanged.
- [ ] T2. Closed request (past `expires_at`) gives `review_request_closed`, and nothing is stored and the nonce is not consumed.
- [ ] T3. A subject whose repository, revision or authoring execution id differs from the request's gives `review_subject_mismatch`, and nothing is stored.
- [ ] T4. A worker-mode body from a non-reviewer principal (admin, mctl-agent service, evidence writer) gives `review_producer_not_enrolled`, and nothing is stored.
- [ ] T5. A fencing epoch lower than the lifecycle row's current epoch, or a row that is not active, gives `review_fence_stale`, and nothing is stored. A lifecycle lookup error gives 503, and nothing is stored.
- [ ] T6. `pass` with an unobserved rubric outcome gives `review_pass_with_unobserved`. Each Tier A code is reproduced from its golden fixture.
- [ ] T7. A worker request without `authoring_execution_id` is refused (`review_malformed`).
- [ ] T8. A pool read failure gives a typed 503, and an oversize pool gives 500 `review_pool_too_large`, never 200 with `[]`. A successful read returns rows in ingest order with `complete: true`.
- [ ] T9. Mutation check: a test that injects a `rows.Err()` failure into `ListPool` and asserts the typed error. The test documents that removing the guard makes it fail. Run it once with the guard removed during review to confirm.
- [ ] T10. A manual receipt from a human admin is stored as `manual`/`advisory` even when the body claims `independent`. `EvaluateReviewGate(required_assurance=independent)` over a pool of only manual receipts is not satisfied.
- [ ] T11. A relayed caller, a surface caller and the service principal (all of which carry the admins group) are refused manual mode. A `CheckHumanPrincipal` disabled result gives 403 `principal_disabled`, and a store error gives 503.
- [ ] T12. The reviewer principal is refused on every route other than `POST /api/v1/review-receipts`.
- [ ] T13. MCP: `mctl_get_review_gate` surfaces a REST 503 as a tool error, not as "gate unsatisfied with no receipts".

## Rollback

The feature is opt-in and additive. To disable it, set `REVIEW_RECEIPTS_DISABLED=1` or remove `reviewerTokenSecret`. Every route then answers 503 and the reviewer principal is disabled. For a full rollback, revert the PR. The three new tables are left in place, harmless and unreferenced, and can be dropped manually if needed. Evidence, decisions and lifecycle are untouched, so no other data needs restoring.
