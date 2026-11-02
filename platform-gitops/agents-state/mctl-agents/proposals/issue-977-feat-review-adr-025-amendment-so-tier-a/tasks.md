# Tasks: issue-977-feat-review-adr-025-amendment-so-tier-a

Precondition: the issue says not to implement before the owner authorizes it. Approval of this proposal is that
authorization.

- [ ] 1. Amend `docs/adr/025-independent-review-receipts.md`. Add the execution-id grammar: `we_<lowercase
  8-4-4-4-12 uuid>`, legacy `we_[0-9a-f]{16,64}`, `ex-[0-9a-f]{16}`, full match, no normalisation, byte-exact
  comparison. Add the Tier A/Tier B lockstep rule, an `Amended:` header line (mctl-agents#977 plus the mctl-api
  PR), and `tests/fixtures/review/review_receipt_vectors.json` under `Pinned by`. — DoD: the ADR names all three
  forms and the lockstep rule. No other ADR section changes meaning.
- [ ] 2. In `orchestrator/review_receipts.py`, add a `_UUID` fragment and extend `_EXECUTION_ID_RE` with the
  `we_<uuid>` alternative. Keep both existing alternatives. (depends on 1) — DoD:
  `ReviewRequest.validate()` accepts `we_7ea4cf0c-d8ba-4825-9191-888e17a47eec` and still accepts
  `we_1111111111111111` and `ex-0123456789abcdef`.
- [ ] 3. In `tests/test_review_parity_vectors.py`, add `EXEC_AUTHOR_UUID` / `EXEC_REVIEW_UUID`. Add the sealed
  request and receipt documents, the gate vectors `store_execution_ids_are_independent` (satisfied) and
  `same_store_execution_is_not_independent` (not_independent), and the `review_malformed` refusals for
  uppercase, misplaced hyphens, braces and trailing newline. Require the new names in
  `test_every_gate_outcome_and_the_four_971_rules_are_covered`. Regenerate with
  `python tests/test_review_parity_vectors.py --write`. (depends on 2) — DoD: the fixture is regenerated, and the
  diff only adds entries. Every pre-existing vector's hash and id is byte-identical.
- [ ] 4. Add parametrized accept/refuse unit tests for `_EXECUTION_ID_RE` through the `ReviewRequest` API in
  `tests/test_review_receipts.py`. (depends on 2) — DoD: the tests pass, and each case names its form.
- [ ] 5. Open the mctl-api PR. Change `executionIDRE` in `internal/reviewreceipts/types.go` to the identical
  anchored alternation, re-vendor the regenerated fixture byte-identical, update `vectorsSHA256` in
  `internal/reviewreceipts/vectors_test.go` to its sha256, and make sure the vector-replay test covers the new
  vectors. Cross-link it from the mctl-agents PR and from issue #977. (depends on 3) — DoD: mctl-api CI passes
  with the new fixture, and both PRs reference each other.
- [ ] 6. Revert check in both repos. Locally revert only the regex line and confirm the shared-vector tests fail,
  then restore it. Record the failing test names in each PR description. (depends on 3, 5) — DoD: both PR
  descriptions show the observed failure on revert.
- [ ] 7. Add a CHANGELOG entry through the normal release flow (conventional commit `feat(review): ...`).
  (depends on 2) — DoD: the commit message follows the repo convention.

## Tests

- [ ] T1. `test_checked_in_fixture_is_byte_identical` passes with the regenerated fixture.
- [ ] T2. `test_sealed_documents_round_trip_with_their_expected_identity` round-trips the new `we_<uuid>` request
  and receipt.
- [ ] T3. `test_gate_vectors_replay_from_parsed_documents` yields `satisfied` for distinct `we_<uuid>` ids and
  `not_independent` for equal ones.
- [ ] T4. The refusal vectors (uppercase, misplaced hyphens, braced, trailing newline) all raise `review_malformed`.
  The existing `request_bad_authoring_execution_id` still does.
- [ ] T5. Unit tests: the legacy `we_` + 16 hex, `we_` + 64 hex and `ex-` + 16 hex forms are still accepted.
- [ ] T6. Revert the Tier A regex: T2 and T3 fail (fixture regeneration raises on the new request).
- [ ] T7. mctl-api: the Go vector-replay test passes with the new fixture and fails when the Go regex is reverted.
- [ ] T8. The full test suite (`pytest`) and the repo's lint and format checks pass.

## Rollback

Revert the mctl-agents PR: the regex, the vectors, the regenerated fixture and the ADR text. Revert the mctl-api
PR to go back to the previous fixture. The change is additive and no stored data depends on it, because Tier B
could not ingest worker requests before. Reverting only stops `we_<uuid>` ids from parsing again, which also
re-blocks mctl-api#917. Revert both PRs together so the vendored fixture and the two regexes stay in agreement.
