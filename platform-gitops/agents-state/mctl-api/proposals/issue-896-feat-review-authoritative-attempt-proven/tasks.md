# Tasks: issue-896-feat-review-authoritative-attempt-proven

- [ ] 1. Add the pure package `internal/executionprovenance`. It holds `ContractVersion`, `EngineRun`, `AttemptID`, `LineageRoot`, the id regexes and a Python-compatible canonical JSON encoder for string arrays. DoD:
  - `go vet` and `golangci-lint` are clean.
  - A purity test (same forbidden-import list as `reviewreceipts/purity_test.go`, plus `/internal/workitems`) passes.
- [ ] 2. Write the golden vectors `internal/executionprovenance/testdata/execution_attempt_vectors.json` (depends on 1). Each entry lists inputs, the canonical bytes, `attempt_id` and `lineage_root`. DoD: at least 8 vectors covering:
  - `#` suffix stripping;
  - the empty suffix after `#`;
  - non-ASCII and escaped characters;
  - a hyphenated `we_` UUID root;
  - each engine (`temporal`, `argo`, `a2a`).
- [ ] 3. In `internal/workitems/store.go`, add the `execution_provenance` table, the `(lineage_root, attempt_id)` index and the `execution_provenance_immutable()` UPDATE-refusing trigger. DoD: schema creation is idempotent on a second `NewStore`.
- [ ] 4. Extend `insertExecution` to write the provenance row in the same transaction (depends on 1, 3). Pass the `Mutation` actor through `attachNewTx` and `resumeTx`. The root comes from the parent's provenance row, or from a walk of stored `resumed_from_execution_id` rows for a parent created before this change. DoD:
  - Every execution created through `AttachExecution`, `Resume` and request fulfilment has exactly one provenance row.
  - A forced provenance insert failure leaves no execution row.
- [ ] 5. Add `Store.ExecutionProvenance`, `Store.LineageAttempts`, `ErrProvenanceAbsent` and the `Provenance` type (depends on 4). DoD:
  - An unknown id returns `ErrProvenanceAbsent`.
  - A query error, or a stored row failing re-validation, returns a non-absent error.
- [ ] 6. In `internal/reviewstore`, add `ProvenanceLookup`, `SetProvenance`, the sentinels `ErrAuthoringUnproven`, `ErrExecutionUnproven` and `ErrProvenanceUnavailable`, `checkAuthoring` (called from `IngestRequest` before the insert) and `ProveReviewer` (depends on 5). DoD: the authoring rules of requirements.md are enforced for worker and manual modes, with nothing stored on refusal.
- [ ] 7. In `internal/api/handlers_review_receipts.go`, map the new sentinels in `writeReviewError`: 422 `review_authoring_unproven`, 403 `review_execution_unproven`, 503 `review_provenance_unavailable` (depends on 6). Leave `SubmitWorkerReview` at 501. DoD: handler tests assert each code.
- [ ] 8. Add `GET /api/v1/executions/{execution_id}/provenance` in `router.go` and a handler (depends on 5). It allows a platform admin, or an agent run token whose `ExecutionID()` equals the path id. DoD: answers 200, 404 `execution_provenance_absent`, 503 `execution_provenance_unavailable` and 403 for any other caller.
- [ ] 9. Wire `reviewStore.SetProvenance(workItemsStore)` in `cmd/api/main.go` when both stores are configured (depends on 6). DoD: with either store absent, the authoring checks answer `review_provenance_unavailable`, never pass.
- [ ] 10. Docs (depends on 1-8). DoD:
  - New `docs/execution-provenance.md` covers the contract, derivation, guarantees and codes.
  - `docs/review-receipts.md` is updated with authoring verification and the new codes, and its "Disabled worker path" lists all four hard prerequisites of worker ingest (provenance, `we_` regex amendment in both tiers, vendored vector parity, #895 binding plus attacher eligibility) and never says that only #895 remains.
  - `docs/work-context-contract.md` resource model lists `execution_provenance`.
- [ ] 11. Add a pinned-digest parity test for the vector file (depends on 2). DoD: the Go test recomputes every vector and compares the SHA-256 of `execution_attempt_vectors.json` with a digest pinned in the test. The digest is also written to `docs/execution-provenance.md` so that mctl-agents can pin the same value.
- [ ] 12. Open the cross-repo follow-ups and link them to #895. DoD: issues filed, linked from the PR and recorded as hard blockers on mctl-api#895 for:
  - the mctl-agents vendoring of the exact vector file with a parity test that detects byte and digest divergence;
  - the ADR 025 amendment so that mctl-agents `executionIDRE` and `reviewreceipts.executionIDRE` accept real `we_<hyphenated-uuid>` ids, with a shared vector containing a real id;
  - the #895 acceptance item: verify the reviewer execution was attached by an eligible platform-authorized principal or path using the recorded `attached_by` fields, and refuse a developer-attached `engine`/`engine_ref` on its own.

## Tests

- [ ] T1. Vector parity: `executionprovenance` reproduces every vector's canonical bytes and both ids byte for byte. Guard proof: changing the version string or dropping `EngineRun` truncation fails the test.
- [ ] T2. Input-source guard: `insertExecution` computes ids only from stored row fields. The test attaches with an `engine_ref` carrying a `#` suffix and asserts the stored `attempt_id` equals the vector for the stripped run. A second run attached to another work item gets the same `attempt_id` and a different `lineage_root`.
- [ ] T3. Lineage chain: start, then resume twice. All three executions share `lineage_root` and `root_execution_id`. A resume from a parent created before this change (no provenance row) walks stored rows to the correct root.
- [ ] T4. Same-transaction guard: inject a failing provenance insert (a test hook, or a trigger raising on a sentinel engine) and assert no `work_item_executions` row remains. Removing the in-transaction insert makes this fail.
- [ ] T5. Immutability: `UPDATE execution_provenance` fails. Dropping the trigger makes the test fail.
- [ ] T6. Absent vs unavailable: an unknown id returns `ErrProvenanceAbsent`. A closed pool, or a stored row with a bad `contract_version`, returns a non-absent error. Collapsing the two fails the test.
- [ ] T7. Ordering: `MintAgentRunToken` for a new execution succeeds, and `ExecutionProvenance` for it is readable inside the same test without retry.
- [ ] T8. Authoring checks, one test per rule. Each must fail when its guard is removed:
  - worker request with an `ex-` authoring id: 422;
  - lineage mismatch: 422;
  - the authoring execution's own attempt missing from the list: 422;
  - a listed attempt from a foreign lineage: 422;
  - manual request with empty facts: accepted;
  - manual request with wrong non-empty facts: 422;
  - lookup error: 503;
  - lookup not wired: 503.
- [ ] T9. `ProveReviewer` returns the stored facts, `ErrExecutionUnproven` for an absent record and `ErrProvenanceUnavailable` on a read error. There is no code path that accepts caller-supplied ids; a test passes a caller value and asserts it is ignored.
- [ ] T10. REST read: admin gets 200. A run token for the same execution gets 200; a run token for another execution gets 403. Absent gives 404 and unavailable gives 503.
- [ ] T11. Vector file pin: changing one byte of `execution_attempt_vectors.json` fails the digest check even when every derived id still matches. Removing the digest comparison makes the test fail.
- [ ] T12. Contract recorded: a test asserts that `execution_provenance` stores `attached_by` and `attached_by_principal` for an execution attached by a developer, and that `ProveReviewer` does not return any field that could be read as an eligibility decision.
- [ ] T13. Regression: the existing `reviewreceipts` vectors, `reviewstore` tests, worker route 501, and the MCP tool count in `internal/mcp/server_test.go` are unchanged.

## Rollback

Revert the PR. The `execution_provenance` table, index and trigger are additive and can stay in place harmlessly. After a revert nothing reads them, and execution inserts stop writing them. Review-request ingest returns to accepting creator-asserted authoring facts, and the worker receipt route stays at 501 throughout, so autonomous review is never enabled by either state. To also remove the data, run `DROP TABLE execution_provenance` (and its trigger function). No other table depends on it.
