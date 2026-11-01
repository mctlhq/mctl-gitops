# Tasks: issue-895-feat-review-tier-b-adapter-for-version-b

Planning only. Blockers B1 and B2 are in requirements.md. Task 4 decides whether the worker path ships live or disabled.

- [ ] 1. Port the Tier A types and codes into `internal/reviewreceipts` (`types.go`, `identity.go`). Copy the golden vectors from mctl-agents#971 into `testdata/`. Do not port `spike_report_digest_v1` and do not define a `spike_digest_refused` error. — DoD: every vector parses or refuses with the same code; `content_hash`, `request_id` and `receipt_id` recompute byte for byte; a stored-and-read-back request keeps its identity; a request with an altered nonce is `review_bad_identity`.
- [ ] 2. Gate (`gate.go`) (depends on 1). Full Tier A input: `live`, `request`, `pool`, `required_assurance`. One policy: call the canonical implementation if feasible, else port it with shared vectors. — DoD: one vector per rule (request binding vs live binding, `request_id` scoping, empty worker identity, case-insensitive actor) plus stale, missing, unknown, advisory_only, manual never independent; each rule's vector fails when the rule is removed.
- [ ] 3. `store.go` (depends on 1): tables with immutable triggers, manual-implies-advisory CHECK, `nonce_sha256` UNIQUE, `ingest_seq`; `CreateRequest` (stores sealed bytes verbatim), `SubmitWorkerReceipt` (one transaction; external proofs read before it), `SubmitManualReceipt` (request exists, not closed, subject binding, structural validity; no nonce consumption), `ListPool` (`limit+1`, typed errors). Closing computed from `REVIEW_REQUEST_TTL` and a later request for the same subject. — DoD: `go test ./internal/reviewreceipts/...` passes against Postgres.
- [ ] 4. Resolve B1/B2 against the code: inspect `agent_run_tokens`, the execution state and the pod binding, and write down in the PR whether a reviewer-agent run token can prove `reviewer_execution_id` and its freshness, and the trust limit. Implement `ReviewerExecutionSource` accordingly; if it cannot be proven, keep the worker path disabled (503) and say so. No static-token proof. — DoD: the decision and its evidence are in the PR description; the disabled path is tested.
- [ ] 5. HTTP handlers, router, `Options.ReviewReceipts`, `reviewerGate` (depends on 3, 4). — DoD: reviewer actor always derived; a different body `reviewer_actor` is `review_bad_identity`; tenant server-derived; manual needs `isHumanAdmin` plus `checkHumanPrincipal`; `isHumanAdmin` is not modified.
- [ ] 6. Wire the store in `cmd/api/main.go` (`REVIEW_RECEIPTS_DB_URL` chain, kill switch, `REVIEW_REQUEST_TTL`, nil lookups answer 503) (depends on 3).
- [ ] 7. MCP tools `mctl_submit_review_assertion` and `mctl_get_review_gate`, hints and portal allowlist (depends on 2, 5).
- [ ] 8. `docs/review-receipts.md` with the proved / carried / not-performable split, blockers, one-receipt-per-request and the concurrency note; CHANGELOG entry (depends on 5).
- [ ] 9. `go fmt`, `go vet`, `golangci-lint`, `go test ./...`.

## Tests

- [ ] T1. Replayed nonce -> `review_nonce_replayed`; receipt count unchanged.
- [ ] T2. Closed request (past TTL, or superseded by a request for the same subject identity with a newer binding; a repeated request for the same binding does not close it) -> `review_request_closed`; nothing stored; nonce not consumed.
- [ ] T3. Subject binding differs from the request's -> `review_subject_mismatch`; nothing stored.
- [ ] T4. Worker-mode body from a non-reviewer principal -> `review_producer_not_enrolled`.
- [ ] T5. A correct reviewer credential with a `reviewer_execution_id` it cannot be tied to -> 403 `review_execution_unproven`; an unreadable source -> 503; a terminal or expired execution -> refused; nothing stored and nonce unconsumed in each case. The authoring/request fence is never accepted as freshness.
- [ ] T6. `pass` with an unobserved criterion -> `review_pass_with_unobserved`; each Tier A code Tier B decides is reproduced from its vector. There is no test or code for `spike_digest_refused`.
- [ ] T7. Request without `authoring_execution_id` -> `review_malformed`; worker receipt with an empty execution, attempt or lineage -> `review_malformed`.
- [ ] T8. Pool read failure -> typed 503; oversize pool -> 500 `review_pool_too_large`; never 200 with `[]`; success returns ingest order with `complete: true`.
- [ ] T9. Mutation check: inject a `rows.Err()` failure into `ListPool`; the test fails with the guard removed (run once during review).
- [ ] T10. Manual receipt from a human admin is stored `manual`/`advisory` even if the body claims `independent`; a pool of only manual receipts never satisfies `independent`.
- [ ] T11. Relayed, surface and service callers are refused manual mode; `CheckHumanPrincipal` disabled -> 403 `principal_disabled`; store error -> 503.
- [ ] T12. The reviewer principal is refused on every route except `POST /api/v1/review-receipts`.
- [ ] T13. MCP: `mctl_get_review_gate` surfaces a REST 503 as a tool error, not as "unsatisfied with no receipts".
- [ ] T14. Request identity: a stored-and-read-back sealed request is byte-identical; an altered nonce is refused; Tier B never returns a nonce it generated.
- [ ] T15. Manual path: a manual receipt for a closed request or a different subject binding is refused like the worker path; a manual receipt does not consume the worker nonce, and a worker receipt is still accepted afterwards.
- [ ] T16. One request, one worker receipt: after any accepted worker receipt, including `UNOBSERVABLE`, a second worker receipt on the same request is `review_nonce_replayed`; a rerun uses a new sealed request.
- [ ] T17. Gate with the full input: request bound to an older revision -> `unknown`; another request's receipt ignored; empty worker identity not independent; mixed-case actor not independent. Each fails with its rule removed.

## Rollback

Opt-in and additive. `REVIEW_RECEIPTS_DISABLED=1` makes every route answer 503. For a full rollback revert the PR; the three tables stay, unreferenced, and can be dropped manually. Evidence, decisions and lifecycle are untouched.
