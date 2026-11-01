# Review receipts, Slice A: Tier A-compatible Go library and gate

## Scope decision (owner, 2026-11-01)

The first proposal for this issue covered the whole Tier B adapter and the implementer declined it (`no-commits`). The work is split into three slices and **this proposal authorizes Slice A only**:

- **Slice A (this issue, mctl-api#895):** a pure Go library. Tier A-compatible types, strict parsing with typed errors, recomputation of `content_hash`, `request_id` and `receipt_id`, `EvaluateReviewGate`, and parity vectors with mutation tests.
- **Slice B (mctl-api#897):** the durable manual adapter (Postgres, HTTP, MCP, docs). Out of scope here.
- **Slice C (mctl-api#896):** authoritative `execution_id -> attempt_id + lineage_root`. Out of scope here. Worker / autonomous ingestion stays off until it is closed.

The full design of the adapter is kept in mctl-gitops#2337, #2343 and #2344 (earlier revisions of this proposal) and is not repeated here.

## Context

Tier A is merged: mctl-agents#971 (merge commit `577306dd`), ADR 025 and `orchestrator/review_receipts.py`. It defines sealed `ReviewRequest` and `ReviewReceipt` documents, the subject binding and the gate. mctl-api needs the same contract in Go so that later slices store and evaluate these documents without re-deciding policy. Slice A delivers only that contract as a deterministic library and proves byte and policy parity with Tier A.

## User stories

- AS a later Tier B slice I WANT a Go package that parses and seals review documents exactly as Tier A does SO THAT a stored document has the same identity on both sides.
- AS a later Tier B slice I WANT `EvaluateReviewGate` over the full Tier A input SO THAT the adapter never carries a second, drifting copy of the policy.
- AS a reviewer of this change I WANT parity vectors and mutation proofs SO THAT I can see each rule is enforced and not merely present.

## Acceptance criteria (EARS)

Package and purity

- THE SYSTEM SHALL add the package `internal/reviewreceipts` and change no other production code. Allowed paths: `internal/reviewreceipts/**` only (including its `testdata/`).
- THE SYSTEM SHALL keep the package free of I/O: it SHALL NOT import `database/sql`, `pgx`, `net/http`, `internal/api`, `internal/auth`, `internal/mcp`, `internal/lifecycle`, `internal/evidence` or any store. A test SHALL fail if one of them appears in the package's dependency list.
- THE SYSTEM SHALL add no HTTP route, no MCP tool, no table, no migration, no environment variable, no reviewer principal and no authentication code.

Types and strict parsing

- THE SYSTEM SHALL provide Go types for `ReviewSubject` (spike and proposal kinds, with `identity()` and `binding()` as in Tier A), `Criterion`, `ArtifactRef`, `ReviewRequest` and `ReviewReceipt`, with the same field set, key set and rubrics as Tier A.
- WHEN a document is parsed THE SYSTEM SHALL reject unknown keys with `review_unknown_key`, wrong `api_version` or `kind`, wrong types, over-long strings (more than 256 characters), over-long lists (more than 64 entries), values outside the closed choices, and malformed identifiers (`rr_`, `rc_`, `ev-`, `we_` / `ex-`, `sha256:` digests, `created_at`), with `review_malformed`.
- THE SYSTEM SHALL apply the same bounds in the constructors (sealing) and in parsing, so that a sealed document always round-trips.
- IF a subject is invalid, or its fields do not fit its kind THEN THE SYSTEM SHALL refuse with `review_bad_subject`. IF the rubric does not fit the subject kind THEN `review_rubric_mismatch`.

Identity

- WHEN a document is sealed THE SYSTEM SHALL compute `content_hash` as Tier A does (sha256 of the canonical JSON of the payload, with Tier A's exact canonicalization) and the ids as Tier A does (`rr_` / `rc_` plus the same slice of the hash).
- WHEN a document that carries `content_hash` or an id is parsed THE SYSTEM SHALL recompute them and refuse a mismatch with `review_bad_identity`. A request whose nonce, or any other payload field, was altered after sealing is refused.
- THE SYSTEM SHALL NOT generate, replace or rewrite a nonce. The nonce is a field of the sealed request and part of its identity.

Outcome rules (the document-level rules Tier A applies)

- IF a receipt asserts `PASS` while any rubric criterion is not `met` or is missing THEN `review_pass_with_unobserved`.
- IF a receipt asserts `CHANGES_REQUESTED` while a criterion is `unobserved` THEN `review_unobserved_outcome`.
- A `manual` receipt SHALL be `advisory`, whatever assurance the document claims, exactly as Tier A decides.
- A worker request without `authoring_execution_id` is representable; the gate answers `unknown` for it.

Gate

- THE SYSTEM SHALL provide `EvaluateReviewGate(live, request, pool, requiredAssurance)` with the full Tier A input: the observed live subject (absent when it could not be observed), the sealed request (absent when unavailable), the complete candidate pool in ingest order, and the required assurance (`independent` or `any`). An unknown `requiredAssurance` is an error, not a default. The outcome strings are the Tier A gate constants, byte for byte.
- THE SYSTEM SHALL reproduce the Tier A gate order: unobserved live -> `unknown`; pool by exact binding (`stale` when only other bindings exist, else `missing`); no request, a request bound to a different revision than `live`, an unsealed request, or a worker request without `authoring_execution_id` -> `unknown`; only receipts of the request's own `request_id` (none left -> `missing`); independence; assurance (`advisory_only`); the latest remaining receipt maps to `satisfied`, `changes_requested`, `needs_human` or `unobservable`.
- THE SYSTEM SHALL preserve the four rules of mctl-agents#971: the request binding equals the live binding; the pool is scoped to one `request_id`; a worker receipt with an empty `reviewer_execution_id`, `attempt_id` or `lineage_root` is not independent; reviewer and author actors compare case-insensitively.
- A manual or advisory receipt SHALL never satisfy `required_assurance=independent`.
- The function SHALL be pure: no clock, no randomness, no I/O. The gate has no GitHub, `commit_id`, dismissal or check input.

Parity and proof

- THE SYSTEM SHALL ship golden vectors, in `internal/reviewreceipts/testdata/`, that are produced by the canonical Tier A implementation and never computed by hand or by the Go code under test. Source of truth: the fixture `tests/fixtures/review/review_receipt_vectors.json` in mctl-agents, merged in mctl-agents#973 (merge commit `2684641c719b7c7b3944243f0f9ae1f70a238693`), generated by `tests/test_review_parity_vectors.py` from `orchestrator/review_receipts.py`. The implementer copies that file byte for byte into `internal/reviewreceipts/testdata/` and records the mctl-agents commit it was read from in the Go test that loads it. Sections: `documents` (sealed requests and receipts with expected `content_hash` and id), `parse_refusals` (each with its expected code), `parse_acceptances`, and `gate` (inputs as full documents and the expected outcome; an expected value of `error` means the call is refused). IF the file cannot be read at that commit THEN the implementer SHALL stop and report instead of hand-computing expected values.
- The fixture already covers (the implementer adds no expected values of its own): sealed requests and receipts for both subject kinds with their expected ids and hashes; a stored-and-read-back request keeping its identity; a request with an altered nonce; every parse refusal above with its code; PASS with an unobserved criterion; the manual-forces-advisory rule; and gate cases for every outcome (`satisfied`, `changes_requested`, `needs_human`, `unobservable`, `stale`, `missing`, `unknown`, `advisory_only`, `not_independent`) plus one case per rule of mctl-agents#971.
- Each gate rule and each parse guard SHALL be proved by mutation: the implementer removes the guard, runs the test, and watches it fail, and records this in the PR description. A rule whose test passes with the rule removed is a defect.

## Out of scope (must not be implemented in this run)

- Everything of Slice B (mctl-api#897): tables, Postgres, immutable storage, TTL and supersession, manual submission, pool reads, HTTP handlers, MCP tools, docs, tenant and actor derivation.
- Everything of Slice C (mctl-api#896): `execution_id -> attempt_id + lineage_root`, reviewer execution proof, run-token binding, worker receipt ingestion.
- `spike_report_digest_v1` recomputation (Tier B has no report bytes) and `spike_digest_refused`. The digest fields of a spike subject are validated for shape and compared for equality only.
- The nonce-consumption, request-closing, subject-mismatch, producer-enrollment, execution-proof, fence and pool-size refusals: they belong to Slice B and C and have no code in this slice.
- Any change to the Tier A Python contract in mctl-agents.

## Open questions

- None that block this slice. The Tier A source is fixed by commit; the vector generator is described above.
