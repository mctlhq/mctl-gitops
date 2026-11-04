# Authoritative attempt provenance for independent review receipts

## Context

Tier A of the independent-review contract (mctl-agents#971, ADR 025, ported
to Go in `internal/reviewreceipts`) treats a review as independent from the
author by comparing three facts of the reviewer execution with the authoring
facts of the ReviewRequest: `reviewer_execution_id`, `attempt_id` and
`lineage_root`. Tier B (mctl-api#895 and #897, `internal/reviewstore`) has an
authoritative source for none of the last two. Today `attempt_id`,
`lineage_root`, `authoring_attempt_ids` and `authoring_lineage_root` are all
whatever the document's creator wrote. For that reason the worker receipt
route `POST /api/v1/review-receipts` answers 501
`review_worker_ingest_disabled` (`internal/api/handlers_review_receipts.go`),
and only the manual advisory path is live.

This proposal defines one versioned contract, `execution_attempt_v1`, for the
canonical `attempt_id` and `lineage_root` of a work-item execution (`we_`).
It records the mapping `execution_id -> attempt_id + lineage_root` on the
server, in the same transaction that creates the execution row. The
execution itself never writes the record, and the record never changes after
it is written. Tier B gets a lookup that fails closed, and review-request
ingest checks the authoring side against that record instead of trusting the
creator. Enabling worker receipts stays with mctl-api#895.

## User stories

- AS the Tier B review store I WANT to look up the attempt and lineage of an execution from a server-written record SO THAT I never take those facts on the caller's word.
- AS the autonomous review gate I WANT the authoring attempt ids and lineage root of a ReviewRequest to be checked against the same record SO THAT an author cannot pass as its own reviewer by asserting different ids.
- AS a mctl-agents Tier A maintainer I WANT a documented derivation and shared golden vectors SO THAT both tiers compute identical `attempt_id` and `lineage_root` values.
- AS a platform operator I WANT a store outage to read as "unavailable" and not as "no attempt" SO THAT no review is accepted while the facts cannot be read.

## Acceptance criteria (EARS)

- WHEN the work-items store inserts a `work_item_executions` row (through `AttachExecution`, `Resume`, or the fulfilment of an execution request) THE SYSTEM SHALL insert exactly one `execution_provenance` row for that execution in the same database transaction. The row holds `attempt_id`, `lineage_root`, `contract_version = "execution_attempt_v1"`, `engine`, `engine_run`, `parent_execution_id`, `root_execution_id`, the attaching principal and `recorded_at`.
- THE SYSTEM SHALL derive `attempt_id` as `"at_"` followed by the first 32 lowercase hex characters of SHA-256 over the canonical JSON array `["execution_attempt_v1","attempt",<engine>,<engine_run>]`, where `engine_run` is `engine_ref` truncated at its first `#`.
- THE SYSTEM SHALL derive `lineage_root` as `"ln_"` followed by the first 32 lowercase hex characters of SHA-256 over the canonical JSON array `["execution_attempt_v1","lineage",<root_execution_id>]`. `root_execution_id` is the first execution reached by following `resumed_from_execution_id` back to an execution that has none.
- THE SYSTEM SHALL take every derivation input from the stored execution row and its stored parent. No request body field, query parameter or token claim may supply `attempt_id`, `lineage_root`, `root_execution_id` or `parent_execution_id`.
- IF an `UPDATE` is attempted on `execution_provenance` THEN THE SYSTEM SHALL refuse it with a database trigger.
- IF the provenance insert fails THEN THE SYSTEM SHALL roll back the execution insert, so that no execution created after this change exists without provenance.
- WHILE an agent run token is minted for an execution THE SYSTEM SHALL already hold that execution's provenance row. This holds because `MintAgentRunToken` requires the execution row, and that row commits together with its provenance.
- WHEN Tier B or an authorised REST caller looks up the provenance of an execution id that has a record THE SYSTEM SHALL return the stored `attempt_id`, `lineage_root`, `contract_version`, `root_execution_id`, `parent_execution_id` and `recorded_at` without recomputing them.
- IF the execution id has no provenance record (an execution created before this change, an unknown id, or a runtime `ex-` id) THEN THE SYSTEM SHALL return the typed answer `execution_provenance_absent` and never a default or empty attempt.
- IF the provenance store cannot be read or is not configured THEN THE SYSTEM SHALL return the typed error `execution_provenance_unavailable` (HTTP 503) and never `execution_provenance_absent`.
- WHEN a ReviewRequest is ingested whose `mode` is `worker` THE SYSTEM SHALL require all of the following, otherwise answer 422 `review_authoring_unproven` and store nothing:
  - `authoring_execution_id` is a `we_` id with a provenance record.
  - `authoring_lineage_root` equals that record's `lineage_root`.
  - `authoring_attempt_ids` contains that record's `attempt_id`.
  - Every listed attempt id is the attempt of some recorded execution with the same `lineage_root`.
- WHEN a ReviewRequest of `mode` `manual` carries a non-empty `authoring_attempt_ids` or `authoring_lineage_root` THE SYSTEM SHALL apply the same checks. An empty field stays permitted for manual requests, which are advisory only.
- IF the authoring check cannot read provenance THEN THE SYSTEM SHALL answer 503 `review_provenance_unavailable` and store nothing.
- THE SYSTEM SHALL keep `POST /api/v1/review-receipts` at 501 `review_worker_ingest_disabled` in this change. It SHALL expose `reviewstore` method `ProveReviewer(ctx, executionID)`, which returns only server-recorded facts or a typed refusal (`review_execution_unproven` or `review_provenance_unavailable`), for mctl-api#895 to call.
- THE SYSTEM SHALL ship golden vectors (`internal/executionprovenance/testdata/execution_attempt_vectors.json`). Go tests SHALL reproduce every vector byte for byte, and the same file SHALL be published for the mctl-agents parity test.
- THE SYSTEM SHALL treat `internal/executionprovenance/testdata/execution_attempt_vectors.json` in mctl-api as the single canonical vector file. mctl-agents SHALL vendor the exact bytes. A parity test in each repo SHALL recompute every vector and also compare the SHA-256 of the vector file with a pinned digest, so that a byte-level divergence of the file, or a divergence of any derived `attempt_id` or `lineage_root`, fails the build. A change to the file is a `contract_version` change.
- THE SYSTEM SHALL record the attaching principal in `execution_provenance` (`attached_by`, `attached_by_principal`) and SHALL NOT treat an `engine` or `engine_ref` chosen by the attacher as proof of reviewer independence. Provenance proves only which attempt and lineage an execution has, not that it is an eligible reviewer.
- THE SYSTEM SHALL keep `POST /api/v1/review-receipts` at 501 `review_worker_ingest_disabled` until every hard prerequisite in "Worker ingest prerequisites" below has landed. Documentation SHALL list all of them and SHALL NOT claim that the reviewer run-token binding of mctl-api#895 is the only one remaining.
- WHEN any guard listed in tasks.md is removed THE SYSTEM's test suite SHALL fail. The guards are the derivation-input rule, the same-transaction insert, the immutability trigger, absent vs unavailable, and each authoring check.

## Out of scope

- Enabling worker receipt ingest, writing `review_nonce_consumptions`, the run-token binding of the reviewer, and the eligibility check on the principal that attached the reviewer execution. These belong to mctl-api#895 (see "Worker ingest prerequisites").
- Changing the Tier A document regex or Tier A code in mctl-agents, and the matching Tier B `reviewreceipts.executionIDRE`. They are a hard prerequisite of worker ingest (below), tracked as their own issues, and not delivered by this change. The mctl-agents vendoring and parity test of the vector file is likewise a separate PR.
- Backfilling provenance for executions created before this change. They answer `execution_provenance_absent`.
- Provenance for runtime `ex-` ExecutionContext ids (ADR 011) or for runs attached to no work item.
- New MCP tools. The lookup is REST plus in-process only.
- Retention or deletion policy for `execution_provenance`. It follows `work_item_executions` through `ON DELETE CASCADE`.

## Owner decisions (resolved before approval)

1. **Attempt semantics.** `attempt_id` identifies one engine run. If author and reviewer share an engine run, the review is not independent. Accepted as proposed.
2. **Lineage semantics.** `lineage_root` is the root of the `resumed_from_execution_id` chain. A reviewer in the same work-item lineage as the author is not independent. Accepted as proposed. `trace_id` is not used.
3. **`we_` id format.** Real ids are `we_` plus a hyphenated UUID, and the Tier A `executionIDRE` (`we_[0-9a-f]{16,64}|ex-[0-9a-f]{16}`) rejects them, so no real worker ReviewRequest can parse today. This change does not fix the regex. It is a hard prerequisite of worker ingest, see below.
4. **Golden vectors.** The canonical file lives in mctl-api at `internal/executionprovenance/testdata/execution_attempt_vectors.json`. mctl-agents vendors the exact bytes. The parity test detects byte and digest divergence.
5. **Attacher authorization.** Out of this implementation, but the contract is fixed here: provenance records the attaching principal, and mctl-api#895 MUST verify that the reviewer execution was attached by an eligible, platform-authorized principal or path. An arbitrary developer-attached `engine` / `engine_ref` does not by itself establish reviewer independence.

## Worker ingest prerequisites

`POST /api/v1/review-receipts` stays at 501 `review_worker_ingest_disabled` until ALL of these have landed and are verified. This change delivers only the first.

1. Authoritative attempt and lineage provenance, with `ProveReviewer` (this change, mctl-api#896).
2. Tier A and Tier B accept real `we_<hyphenated-uuid>` execution ids: an ADR 025 amendment that changes `executionIDRE` in mctl-agents `orchestrator/review_receipts.py` and in `internal/reviewreceipts/types.go` together, with a shared vector containing a real hyphenated id, verified in both repos. Until it lands, a worker request cannot parse.
3. mctl-agents vendors the canonical vector file and runs the parity test (decision 4).
4. mctl-api#895: run-token binding of the reviewer, nonce consumption, and an eligibility check that the reviewer execution was attached by a platform-authorized principal or path, using the `attached_by` fields recorded here (decision 5).

## Remaining unobserved facts

- Deployed configuration of mctl-api (database URLs, whether `WORK_ITEMS_DB_URL` and `EVIDENCE_DB_URL` point to the same database) could not be observed. The design does not depend on it. See design.md.
