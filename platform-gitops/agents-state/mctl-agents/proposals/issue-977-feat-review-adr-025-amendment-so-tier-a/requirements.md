# ADR 025 amendment: Tier A and Tier B accept real `we_<hyphenated-uuid>` execution ids

## Context

Work-item store executions are minted by mctl-api as `we_` plus a lowercase hyphenated UUID, for example
`we_7ea4cf0c-d8ba-4825-9191-888e17a47eec` (see `tests/fixtures/workitem/executions-two.json` and
`_STORE_EXECUTION_RE` in `orchestrator/policy_checkpoint.py`, documented as "`we_` + uuid"). The review-receipt
contract (ADR 025, `docs/adr/025-independent-review-receipts.md`) validates `ReviewRequest.authoring_execution_id`
in Tier A with `_EXECUTION_ID_RE = we_[0-9a-f]{16,64}|ex-[0-9a-f]{16}` (`orchestrator/review_receipts.py:116`).
The hyphens are outside `[0-9a-f]`, so every real worker ReviewRequest is refused with `review_malformed`. The Tier
B port (mctl-api `internal/reviewreceipts/types.go`, `executionIDRE`) carries the same regex, so no real worker
request can be ingested there either.

This proposal is task 12 of the approved mctl-api#896 proposal (epic mctlhq/.github#281). It amends ADR 025 to name the
accepted execution-id forms. It changes the Tier A regex here and the Tier B regex in a linked mctl-api PR, in
lockstep. It also adds a shared parity vector with a real `we_<hyphenated-uuid>` id, which both repositories must
pass. This is a hard prerequisite of mctl-api#917 (worker ingestion) and of the autonomous live acceptance in
mctl-agents#905.

## User stories

- AS the DevLoop/worker that authors a change I WANT my real store execution id (`we_<uuid>`) accepted as
  `authoring_execution_id` SO THAT a worker ReviewRequest can be sealed, submitted and gated.
- AS the Tier B maintainer (mctl-api) I WANT a canonical vector holding a real `we_<uuid>` SO THAT my Go regex is
  proven equal to Tier A and cannot drift silently.
- AS an operator reading ADR 025 I WANT the accepted execution-id grammar written down SO THAT the contract,
  not the code, is the authority.

## Acceptance criteria (EARS)

- WHEN a ReviewRequest has `authoring_execution_id` equal to `we_` followed by a lowercase canonical 8-4-4-4-12
  hyphenated UUID THE SYSTEM SHALL accept it in `ReviewRequest.validate()`, `ReviewRequest.from_dict()` and
  `seal_request()`, and SHALL produce the identical `content_hash` / `request_id` in Tier A and Tier B.
- WHEN such a request and a worker receipt whose `reviewer_execution_id` is a different `we_<uuid>` are
  evaluated against the matching live subject THE SYSTEM SHALL return `satisfied` in both tiers.
- WHEN the worker receipt's `reviewer_execution_id` equals the request's `we_<uuid>` `authoring_execution_id`
  THE SYSTEM SHALL return `not_independent` in both tiers.
- IF `authoring_execution_id` is `we_` plus an uppercase or mixed-case UUID, a UUID with misplaced or missing
  hyphens, braces, or a `urn:uuid:` prefix THEN THE SYSTEM SHALL refuse it with `review_malformed` in both tiers.
- WHILE the legacy forms `we_[0-9a-f]{16,64}` and `ex-[0-9a-f]{16}` are in use THE SYSTEM SHALL keep accepting
  them unchanged, and every existing vector in `tests/fixtures/review/review_receipt_vectors.json` SHALL keep its
  hash and id.
- IF the Tier A regex change is reverted THEN `tests/test_review_parity_vectors.py` (fixture regeneration and
  replay) SHALL fail. IF the Tier B regex change is reverted THEN the mctl-api shared-vector test SHALL fail.
- WHEN ADR 025 is read THE SYSTEM SHALL document the accepted execution-id grammar, its source (mctl-api work-item
  store, ADR 011 runtime `ex-` id) and the lockstep rule between Tier A and Tier B.

## Out of scope

- Worker ingestion enablement in mctl-api (mctl-api#917) and vendoring and parity of canonical vectors
  (mctl-agents#975). This proposal only adds vectors to the existing generated fixture.
- Adding a pattern check to `ReviewReceipt.reviewer_execution_id` (today Tier A checks only that it is a bounded
  string). It stays as it is.
- Normalising execution ids (case-folding, stripping hyphens). Ids are compared byte-exact in the gate.
- Loosening `_STORE_EXECUTION_RE` in `orchestrator/policy_checkpoint.py` or any other execution-id regex.
- Implementing before the owner authorizes it (the issue says so). The implementer starts only after approval.

## Open questions

- Should the legacy `we_[0-9a-f]{16,64}` form stay accepted? The issue says existing forms keep their behavior,
  so this proposal keeps it. No real minting path for it was found, so a later ADR revision could retire it.
- Is mctl-api's UUID always lowercase (Go `uuid.New().String()` is)? This proposal accepts lowercase only, to
  match the deployed fixtures. If mctl-api ever emits uppercase, it must be lowercased at mint time, not in the
  review contract.
- Tier B validation of `reviewer_execution_id`: the issue states Tier B "has the matching regex" but this run
  could not read mctl-api to see whether Tier B also patterns `reviewer_execution_id`. The mctl-api PR must
  confirm and keep both tiers equal.
