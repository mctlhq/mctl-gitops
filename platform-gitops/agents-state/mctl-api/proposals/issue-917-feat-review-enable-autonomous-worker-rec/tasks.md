# Tasks: issue-917-feat-review-enable-autonomous-worker-rec

- [ ] 1. Add `ActorDirectService bool` to `workitems.Mutation`
  (`internal/workitems/inputs.go`), excluded from `RequestHash`. Set it in
  `mutationFor` (`internal/api/handlers_work_items.go`) as
  `isDirectService(user) && !user.IsAgent()`.
  - DoD: unit test shows true for the direct service principal, and false
    for a human, a relayed service, an agent run and a surface.
- [ ] 2. Extend `execution_provenance` with `attach_path TEXT NOT NULL
  DEFAULT ''` and `attached_direct_service BOOLEAN NOT NULL DEFAULT false`
  via `ADD COLUMN IF NOT EXISTS` in `internal/workitems/store.go`. Thread an
  explicit `attachPath` through `insertExecution` and `insertProvenance`:
  - `attachNewTx` passes `attach` or `fulfil_start`;
  - `resumeTx` passes `resume` or `fulfil_resume`;
  - the fulfil callers in `execution_requests.go` pass the fulfil paths.

  Add `AttachPath`/`AttachedDirectService` to `Provenance`, the column list
  and the scan. (depends on 1)
  - DoD: every `insertExecution` caller passes a non-empty path.
  - DoD: the provenance read route returns both fields.
  - DoD: the immutability trigger still refuses UPDATE of the new columns.
  - DoD: `docs/execution-provenance.md` is updated.
- [ ] 3. Add `AgentScopeReview = "review"` to
  `internal/auth/agent_scope.go`:
  - agents `["review-worker"]`;
  - routes `GET /api/v1/whoami` and `POST /api/v1/review-receipts`;
  - no tools, `AuditRequests`, `Deny: agentDeniedRoutes`;
  - not mintable by tenant members.

  In `handlers_agent_run_tokens.go`, refuse minting the `review` scope
  without an execution.
  - DoD: scope tests show every other route and tool refused.
  - DoD: a mint with `review` + `WithoutExecution` is refused.
- [ ] 4. Add the new store errors to `internal/reviewstore/store.go`:
  - `ErrRequestModeManual`
  - `ErrNonceMismatch`
  - `ErrNonceConsumed`
  - `ErrReviewerIneligible`
  - `ErrReviewerNotIndependent`
  - `ErrRunTokenUnbound`

  Add the guarded `review_receipts_worker_independent` CHECK.
  - DoD: the schema applies idempotently twice on an existing DB.
- [ ] 5. Implement `reviewstore.Store.SubmitWorker(ctx, WorkerInput, Reviewer,
  now)` in `internal/reviewstore/receipts.go`, with the check order of
  design.md section 3. The nonce consumption and the receipt insert run in
  one transaction. (depends on 2, 4)
  - DoD: every refusal path returns its typed error with zero rows written
    to either table.
  - DoD: the success path writes exactly one row to each, with
    `mode=worker`, `assurance=independent` and server-derived reviewer
    facts.
- [ ] 6. Rewrite `SubmitWorkerReview` in
  `internal/api/handlers_review_receipts.go`:
  - an enable gate from the new `api.Options.ReviewWorkerIngestEnabled`;
    the 501 path is unchanged when off;
  - the run-token check;
  - a strict body decode, extracting the decode helper shared with the
    manual handler;
  - the `SubmitWorker` call;
  - audit on success and refusal;
  - the new `reviewRefusals` rows.

  Wire `REVIEW_WORKER_INGEST_ENABLED` (default false) in `cmd/api/main.go`.
  (depends on 3, 5)
  - DoD: the handler tests in T-section pass.
  - DoD: `SubmitManualReview` behaviour is byte-identical in the existing
    tests.
- [ ] 7. Docs and contract:
  - `docs/review-receipts.md`: routes, codes, a "Worker path" section with
    the eligibility rule, the enable switch and what enabling still needs
    (the real reviewer agent name from mctl-agents#905 and the operator's
    gitops change), and the `review_nonce_consumptions` writer;
  - `internal/openapi/openapi.yaml`;
  - `helm/values.yaml` comment for `REVIEW_WORKER_INGEST_ENABLED`;
  - mark prerequisites 2 (mctl-agents#980 and #923) and 3 (mctl-agents#979)
    in "Disabled worker path" as delivered, and reword item 4 as delivered.
    Item 4 currently says eligibility uses "the recorded `attached_by`
    fields". Change it to the new `attached_direct_service` rule.
    The current `#895` mentions, at lines 4 and 138, already credit Slice A
    correctly.

  (depends on 6)
  - DoD: openapi lint/tests pass.
  - DoD: the docs name mctl-api#917 as the worker-enablement owner. They
    show prerequisites 1-4 as delivered, and they name the remaining
    enablement step: the agent name from mctl-agents#905 plus
    `REVIEW_WORKER_INGEST_ENABLED`.
- [ ] 8. Run `go fmt`, `go vet`, `golangci-lint` and `go test ./...`.
  Confirm the MCP tool count in `internal/mcp/server_test.go` is unchanged.
  (depends on 1-7)
  - DoD: CI green.

## Tests

- [ ] T1. Happy path (store + handler, Postgres-backed like
  `internal/reviewstore/store_test.go`): a direct-service-fulfilled reviewer
  execution, distinct lineage, `review` run token and matching nonce give
  201. One consumption row and one receipt row exist. The gate under
  `required_assurance=independent` returns PASS for a PASS outcome.
- [ ] T2. Flag off: 501 `review_worker_ingest_disabled`, and the body is
  never read (a body reader that fails the test if touched).
- [ ] T3. Token-binding mutations, each giving 403
  `review_run_token_required` and zero rows:
  - human admin;
  - service principal;
  - surface-relayed service;
  - agent token with scope `investigate`;
  - unscoped agent token;
  - `review` token minted without an execution.
- [ ] T4. Caller-asserted identity: bodies carrying `reviewer_execution_id`,
  `attempt_id`, `lineage_root`, `reviewer_actor`, `assurance`, `mode`,
  `tenant` or `created_at` each give 400 `review_unknown_key` and zero rows.
- [ ] T5. Token for execution A while execution B is an eligible one: the
  stored receipt names A's execution, attempt and lineage, or is refused per
  A's eligibility. It never uses B's.
- [ ] T6. Nonce replay: a second valid submit for the same request gives 409
  `review_nonce_consumed`. The receipt count is unchanged.
- [ ] T7. Nonce race: N concurrent valid submits produce exactly one 201 and
  N-1 `review_nonce_consumed`, with exactly one consumption row.
- [ ] T8. Nonce mismatch: 403 `review_nonce_mismatch` with zero rows.
- [ ] T9. Atomicity: the receipt INSERT is forced to fail after the
  consumption INSERT (for example a `receipt_id` collision seeded by direct
  SQL). The consumption row is rolled back, and the answer is 503.
- [ ] T10. Attacher eligibility mutations, each giving 403
  `review_reviewer_ineligible` and zero rows:
  - execution attached by a developer through `POST
    /work-items/{id}/executions`;
  - execution resumed by a developer;
  - execution attached by an agent run token;
  - provenance row with `attached_direct_service=false` (a legacy-shaped row
    inserted directly).
- [ ] T11. Independence: reviewer execution = authoring execution, reviewer
  attempt in `authoring_attempt_ids`, reviewer lineage = authoring lineage
  (resumed from the author), and reviewer actor in `author_actors`. Each
  gives 409 `review_reviewer_not_independent` and zero rows.
- [ ] T12. Fail closed:
  - provenance lookup error gives 503 `review_provenance_unavailable`;
  - provenance not wired (`SetProvenance` unset) gives 503;
  - an evidence DB error on the nonce insert gives 503
    `review_store_unavailable`;
  - absent provenance gives 403 `review_execution_unproven`.

  Zero rows in every case.
- [ ] T13. Request state: closed (ttl and superseded) gives 409
  `review_request_closed`, a manual-mode request gives 409
  `review_request_mode_manual`, and a binding mismatch gives 409
  `review_binding_mismatch`.
- [ ] T14. Manual path regression: the existing `SubmitManualReview` tests
  pass unchanged. A manual receipt still never writes
  `review_nonce_consumptions`.
- [ ] T15. Provenance recording: each of attach, resume, fulfil_start and
  fulfil_resume records the right `attach_path` and
  `attached_direct_service`. A guard test fails if a new `insertExecution`
  caller is added without a path.
- [ ] T16. Mutation check: deleting each guard (scope check, nonce compare,
  consumption insert, eligibility check, independence check) in turn makes
  at least one of T3-T11 fail. Do this by local mutation runs, recorded in
  the PR description.

## Rollback

- Immediate: unset `REVIEW_WORKER_INGEST_ENABLED` (or set
  `REVIEW_RECEIPTS_DISABLED=true` for all review routes). The worker route
  returns to 501 without a redeploy of code.
- Code: revert the PR. The added columns and CHECK are additive and
  harmless to the previous binary:
  - old code does not read the new columns, and their defaults satisfy NOT
    NULL;
  - the CHECK only constrains worker rows.

  They may stay in place.
- Data: worker receipts written while enabled are append-only. To discard
  them, DELETE from `review_receipts` and `review_nonce_consumptions` for the
  affected request ids (DELETE is permitted, and only UPDATE is refused).
