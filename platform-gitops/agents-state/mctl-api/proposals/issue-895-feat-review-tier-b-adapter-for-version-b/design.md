# Design: Slice A of issue-895 (Tier A-compatible Go library and gate)

## Current state

- Tier A is merged (mctl-agents#971, `577306dd`): `orchestrator/review_receipts.py` defines the sealed documents (`seal_request`, `seal_receipt`), `ReviewSubject` with `identity()` and `binding()`, the closed rubrics, the bounds (`MAX_STR = 256`, `MAX_ACTORS = 64`), the error codes, the gate `evaluate_review_gate`, and `canonical_json` / `hash_bytes` for identity. ADR 025 (`docs/adr/025-independent-review-receipts.md`) is the prose contract. Since mctl-agents#973 the fixture `tests/fixtures/review/review_receipt_vectors.json` also holds the sealed-document, parse and gate vectors (the earlier `spike_digest_vectors.json` is for spike digests, which Tier B does not recompute).
- mctl-api (`ede0b3b` observed) has no review-receipt code. The package name `internal/reviewreceipts` is free. mctl-api uses plain Go tests; `go test ./...`, `go vet` and `golangci-lint` are the repository gates.
- Earlier revisions of this proposal (mctl-gitops#2337, #2343, #2344) hold the full Tier B design. Slice A takes only the library part of it.

## Proposed solution

One package, `internal/reviewreceipts`, standard library only.

- `types.go`: `ReviewSubject` (spike and proposal), `Criterion`, `ArtifactRef`, `ReviewRequest`, `ReviewReceipt`, the closed rubrics and choices, the bounds, and the Tier A gate constants. Field and key sets are ported from Tier A exactly; the implementer reads the Python source at the pinned commit, not this prose.
- `errors.go`: one typed error with a stable `Code` string, and sentinels for exactly these codes: `review_malformed`, `review_unknown_key`, `review_bad_subject`, `review_bad_identity`, `review_rubric_mismatch`, `review_pass_with_unobserved`, `review_unobserved_outcome`. No other code exists in this package.
- `parse.go`: strict decoding of requests, receipts and subjects (unknown keys, types, bounds, shapes, choices). Parsing and sealing share the same validation so a sealed document always round-trips.
- `identity.go`: Tier A's canonical JSON and hashing, `SealRequest`, `SealReceipt`, and recomputation on parse. The nonce is an input to sealing and never produced here.
- `gate.go`: `EvaluateReviewGate(live *ReviewSubject, request *ReviewRequest, pool []ReviewReceipt, requiredAssurance string) (string, error)`, a pure function in the Tier A order. Return values are the Tier A constants.
- `testdata/review_receipt_vectors.json`: a verbatim copy of the Tier A fixture; the loader test records the mctl-agents commit it was copied from.
- `purity_test.go`: runs `go list -deps` for the package and fails if a forbidden import is present.

Vector provenance. Expected values come only from the canonical Tier A Python, through the fixture `tests/fixtures/review/review_receipt_vectors.json` merged in mctl-agents#973 (`2684641c`). That file is built by `tests/test_review_parity_vectors.py` from Tier A functions and a test there fails if it drifts. The Go tests load a verbatim copy and compare; a Go test never computes an expected hash with the Go code it is testing. When Tier A changes, the fixture is regenerated in mctl-agents and the copy is refreshed in a follow-up.

Why a port and not a call: mctl-api cannot run Python in its request path, and Slice B needs a synchronous gate. One policy is preserved by the shared vectors, which run on the Go side in CI and are produced from Tier A.

## Alternatives

1. **Implement the whole adapter in one run.** Tried; the implementer declined it. Replaced by the three slices.
2. **Hand-write expected values in Go tests.** Rejected: it proves the Go code against itself.
3. **Include the Postgres store in this slice.** Rejected by the owner: a clean deterministic library first, storage after parity is proven.

## Platform impact

- **Code.** One new package; no change to existing packages, routes, tools, tables or configuration.
- **Runtime.** Nothing imports the package yet, so there is no runtime effect and no rollback beyond reverting the PR.
- **Risks.** Tier A drift (shared vectors, recorded source commit); a vector that the Go code computed instead of Tier A (provenance rule above, checked in review); hidden I/O creeping into the package (purity test).
