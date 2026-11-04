# Tasks: Slice A of issue-895

**This implementation run is authorized for Slice A only. Slice B (mctl-api#897) and Slice C / B3 (mctl-api#896) are out of scope and must not be implemented in this run.**

Scope is binary: the run is complete only when every task below is done. Do not do a partial subset and report success. The only paths that may change are under `internal/reviewreceipts/`. If another path seems necessary, stop and report.

- [ ] 1. Vectors first. Copy `tests/fixtures/review/review_receipt_vectors.json` from mctl-agents at commit `2684641c719b7c7b3944243f0f9ae1f70a238693` (mctl-agents#973) byte for byte into `internal/reviewreceipts/testdata/`, and record that commit in the Go test that loads it. Never compute expected values by hand or with the Go code under test, and do not edit the file. — DoD: the file is identical to the mctl-agents one at that commit, and the loader test names the commit. If it cannot be read, stop and report.
- [ ] 2. Types, bounds, rubrics, gate constants, typed errors (`types.go`, `errors.go`) ported from the Tier A source at the pinned commit. Only the seven codes listed in design.md. — DoD: compiles; no other error code exists in the package.
- [ ] 3. Strict parsing (`parse.go`) for subject, request and receipt, sharing validation with sealing (depends on 2). — DoD: every refusal vector yields the vector's code; a sealed document round-trips; oversized fields are rejected identically on both paths.
- [ ] 4. Identity (`identity.go`): canonical JSON, `SealRequest`, `SealReceipt`, recomputation on parse (depends on 2, 3). — DoD: ids and hashes equal the vectors byte for byte; a stored-and-read-back request keeps its identity; an altered nonce is `review_bad_identity`; no function generates a nonce.
- [ ] 5. Outcome rules inside receipt validation (depends on 3): PASS with unmet or missing criteria, CHANGES_REQUESTED with an unobserved criterion, manual forces advisory. — DoD: vectors pass.
- [ ] 6. `EvaluateReviewGate(live, request, pool, requiredAssurance)` (`gate.go`) in the Tier A order, pure (depends on 2, 4). — DoD: every gate vector equals its expected outcome, including one case per rule of mctl-agents#971.
- [ ] 7. Purity test (`purity_test.go`): fails if the package depends on `database/sql`, `pgx`, `net/http`, `internal/api`, `internal/auth`, `internal/mcp`, `internal/lifecycle`, `internal/evidence` or a store. — DoD: green, and red when a forbidden import is added.
- [ ] 8. Mutation proof: for each gate rule (request binding vs live binding, `request_id` scoping, empty worker identity, case-insensitive actors, manual never independent, each of the `unknown` / `missing` / `stale` / `advisory_only` branches) and for each parse and identity guard, remove the guard, run the test, confirm it fails, restore it. Record each mutation and its result in the PR description. — DoD: no surviving mutation.
- [ ] 9. `go fmt`, `go vet`, `golangci-lint run`, `go test ./...`. — DoD: clean.

## Tests

- [ ] T1. Golden sealed requests and receipts for both subject kinds: ids and hashes equal the Tier A values.
- [ ] T2. A request parsed from its own serialization keeps `content_hash` and `request_id`; an altered nonce is `review_bad_identity`.
- [ ] T3. Each parse refusal vector: unknown key, wrong `api_version` or `kind`, wrong type, over-long string, over-long list, bad choice, bad identifier shape, with the exact code.
- [ ] T4. `PASS` with an unobserved or missing criterion -> `review_pass_with_unobserved`; `CHANGES_REQUESTED` with an unobserved criterion -> `review_unobserved_outcome`; rubric not fitting the subject -> `review_rubric_mismatch`; bad subject -> `review_bad_subject`.
- [ ] T5. A manual receipt is advisory whatever the document claims, and never satisfies `required_assurance=independent`.
- [ ] T6. Gate: one vector per outcome (`satisfied`, `changes_requested`, `needs_human`, `unobservable`, `stale`, `missing`, `unknown`, `advisory_only`, `not_independent`).
- [ ] T7. Gate rule vectors: request bound to an older revision -> `unknown`; a receipt of another `request_id` is ignored -> `missing`; empty `reviewer_execution_id`, `attempt_id` or `lineage_root` on a worker receipt -> `not_independent`; `Operator` vs `operator` -> `not_independent`; latest receipt wins; unknown `requiredAssurance` -> error.
- [ ] T8. Purity test as in task 7.
- [ ] T9. Provenance check: the loader test names the mctl-agents commit, the copy is byte-identical to it, and no test computes an expected hash with the code under test.

## Rollback

Revert the PR. Nothing imports the package, so nothing else changes.
