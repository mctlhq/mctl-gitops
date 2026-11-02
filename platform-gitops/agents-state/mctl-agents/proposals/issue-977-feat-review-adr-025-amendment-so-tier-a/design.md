# Design: issue-977-feat-review-adr-025-amendment-so-tier-a

## Current state

- `orchestrator/review_receipts.py:116` defines
  `_EXECUTION_ID_RE = re.compile(r"(?:we_[0-9a-f]{16,64}|ex-[0-9a-f]{16})")`. Its only user is
  `ReviewRequest.validate()` (line ~572), which checks `authoring_execution_id` when it is non-empty.
  `from_dict()` reads the field with `_str(..., empty=True)`, then calls `validate()`. `_str` applies patterns
  with a full match (the existing `"nope"` refusal vector depends on that).
- `ReviewReceipt.validate()` checks `reviewer_execution_id` only as a bounded string (the loop at line ~721).
  It has no pattern check. The gate (`evaluate_review_gate`, around line 853-868) compares
  `r.reviewer_execution_id == request.authoring_execution_id` byte-exact, and answers `unknown` for a worker
  request that has an empty `authoring_execution_id`.
- Real store execution ids are `we_` plus a hyphenated lowercase UUID:
  `tests/fixtures/workitem/executions-two.json` (`we_7ea4cf0c-d8ba-4825-9191-888e17a47eec`,
  `we_a11b5572-fed2-482b-bedf-2b4160476cb9`) and `orchestrator/policy_checkpoint.py:802`
  (`_STORE_EXECUTION_RE`, "`we_` + uuid"). The runtime `ex-` + 16 hex form comes from
  `orchestrator/execution_evidence.py:125` / `execution_identity.seal()`. So `we_<uuid>` fails `_EXECUTION_ID_RE`
  only because of the hyphens.
- `tests/test_review_parity_vectors.py` generates `tests/fixtures/review/review_receipt_vectors.json`, the
  external contract the Tier B Go port in mctl-api `internal/reviewreceipts` is tested against. The test
  `test_checked_in_fixture_is_byte_identical` pins it. Every execution id in it is synthetic: `EXEC_AUTHOR =
  "we_" + "1"*16`, `EXEC_REVIEW`, `EXEC_REVIEW_2`. Refusals include `request_bad_authoring_execution_id`
  (`"nope"`). `_acceptances()` and `_gate()` hold the accept and gate cases.
- `docs/adr/025-independent-review-receipts.md` (status: proposed) names the `rr_`/`rc_`/`ev-` id shapes but no
  execution-id grammar.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/` listing: tenants `admins`, `karabu`, `labs`, `namax66`, and more. This change is a
  pure library and contract change in mctl-agents (with a sibling mctl-api code change). It has no deployed config,
  env var, replica or hostname impact, so no service values were relevant. No mctl MCP calls were made: no
  runtime state bears on a regex.
- mctl-api source (`internal/reviewreceipts/types.go`) is not in this clone and was not observed. The claim that
  Tier B's `executionIDRE` matches Tier A comes from the issue body only (see Open questions in requirements.md).

## Proposed solution

1. **ADR 025 amendment.** Add an `## Identifiers` subsection (or extend `## Documents`) stating:
   - `authoring_execution_id`, when non-empty, must full-match exactly one of:
     - `we_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}`: a work-item store execution as
       mctl-api mints it (ADR 011 work-item resume), lowercase canonical UUID text;
     - `we_[0-9a-f]{16,64}`: legacy hex form, kept unchanged;
     - `ex-[0-9a-f]{16}`: runtime execution identity (`execution_identity.seal()`).
   - No normalisation: ids compare byte-exact, so uppercase or unhyphenated UUID text is refused rather than
     folded.
   - Tier A `_EXECUTION_ID_RE` and Tier B `executionIDRE` change only together. The shared vectors in
     `review_receipt_vectors.json` are the proof.
   - An `Amended:` line in the header citing mctl-agents#977 and the mctl-api PR. Also add
     `tests/fixtures/review/review_receipt_vectors.json` to `Pinned by`.
2. **Tier A regex** (`orchestrator/review_receipts.py`):
   ```python
   _UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
   _EXECUTION_ID_RE = re.compile(rf"(?:we_{_UUID}|we_[0-9a-f]{{16,64}}|ex-[0-9a-f]{{16}})")
   ```
   This adds an alternative and removes nothing. The UUID alternative is a strict superset addition, so every
   string accepted before is still accepted. Length is at most 39 characters, well under `MAX_STR`.
3. **Shared vectors** (`tests/test_review_parity_vectors.py`, then regenerate the fixture with `--write`):
   - Constants `EXEC_AUTHOR_UUID = "we_7ea4cf0c-d8ba-4825-9191-888e17a47eec"` and
     `EXEC_REVIEW_UUID = "we_a11b5572-fed2-482b-bedf-2b4160476cb9"` (real shapes from the work-item fixtures).
   - `documents.requests`: `proposal_worker_request_store_execution_id`, a sealed request with
     `EXEC_AUTHOR_UUID`. Its `expected` hash and id must round-trip in both tiers.
   - `documents.receipts`: `proposal_worker_pass_store_execution_id` (reviewer `EXEC_REVIEW_UUID`).
   - `gate`: `store_execution_ids_are_independent` -> `satisfied`, and
     `same_store_execution_is_not_independent` -> `not_independent`.
   - `parse_refusals` (code `review_malformed`): `request_uppercase_store_execution_id`,
     `request_store_execution_id_without_hyphens_wrong_length` (`we_` + 32 hex is still accepted by the legacy
     form, so the refusal uses a misplaced-hyphen variant such as `we_7ea4cf0cd-8ba-...`),
     `request_braced_store_execution_id`, `request_store_execution_id_trailing_newline`. The last one guards
     against `$`-style partial matches in the Go port.
   - Extend `test_every_gate_outcome_and_the_four_971_rules_are_covered` so it requires the new vector names.
     Deleting a vector then fails the test, not just the byte-identical check.
   - Existing vectors are untouched, so their hashes stay identical, and this is also asserted.
4. **Unit tests** in `tests/test_review_receipts.py`: parametrized accept/refuse cases on `ReviewRequest`
   for the three forms. Each must name the form so a revert produces a readable failure.
5. **Tier B (mctl-api, separate PR, linked from the mctl-agents PR and this issue):** change
   `reviewreceipts.executionIDRE` in `internal/reviewreceipts/types.go` to the identical alternation, anchored
   `^(?:...)$` (Go `regexp` has no fullmatch). Re-vendor the regenerated fixture and confirm the existing
   vector-replay test covers the new names. The ordering is: mctl-agents merges first (the fixture is
   generated here), then mctl-api vendors it. If mctl-api's vendoring CI compares against mctl-agents main,
   the two PRs must land close together.

## Alternatives

- **Reuse `_STORE_EXECUTION_RE` (`we_[A-Za-z0-9][A-Za-z0-9-]{0,127}`).** Dropped: it accepts mixed case and
  arbitrary hyphenation. Because the gate compares byte-exact, two spellings of one execution would then pass
  as different executions, which weakens the independence check.
- **Normalise ids (lowercase, strip hyphens) before validation and comparison.** Dropped: it changes the sealed
  bytes and so the `content_hash` of requests, needs identical normalisation in Go, and hides minting bugs. A
  strict grammar is simpler and fails closed.
- **Replace the legacy `we_[0-9a-f]{16,64}` form with the UUID form.** Dropped for now: the issue requires
  existing forms to keep their behavior, and every existing vector uses that form. Retiring it can be a later ADR
  revision.

## Platform impact

- **Migrations:** none. No stored data changes. Tier B has never been able to ingest a worker request, so no
  stored receipts depend on the old regex.
- **Backward compatibility:** strictly additive. Every previously accepted id is still accepted, and every
  existing vector keeps its hash and id. Only the new UUID form becomes newly valid.
- **Resources:** none. This is a pure validation change.
- **Risks and mitigations:**
  - Tier A and Tier B drift: mitigated by the shared vectors (accept, gate and refusal) that both repos replay,
    and by the explicit revert check in tasks.md.
  - A Go regex without anchors could accept a suffix such as a trailing newline or extra characters: mitigated by
    the trailing-newline and braced refusal vectors.
  - An mctl-api PR that lands late leaves Tier B rejecting the new vectors: mitigated by landing order and by
    linking both PRs. mctl-api#917 stays blocked until both are merged.
