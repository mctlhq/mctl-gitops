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
- WHEN any guard listed in tasks.md is removed THE SYSTEM's test suite SHALL fail. The guards are the derivation-input rule, the same-transaction insert, the immutability trigger, absent vs unavailable, and each authoring check.

## Out of scope

- Enabling worker receipt ingest, writing `review_nonce_consumptions`, and the run-token binding of the reviewer. These belong to mctl-api#895.
- Changing the Tier A document regex or Tier A code in mctl-agents. The parity test and vector file are published for it, but the mctl-agents change is a separate PR.
- Backfilling provenance for executions created before this change. They answer `execution_provenance_absent`.
- Provenance for runtime `ex-` ExecutionContext ids (ADR 011) or for runs attached to no work item.
- New MCP tools. The lookup is REST plus in-process only.
- Retention or deletion policy for `execution_provenance`. It follows `work_item_executions` through `ON DELETE CASCADE`.

## Open questions

- Tier A semantics of `attempt_id`. This proposal defines an attempt as one engine run, so the same Temporal or Argo run attached to two work items is one attempt. If a DevLoop Temporal workflow hosts both the authoring stage and a reviewer stage under one `engine_ref`, the two share an attempt and the review is never independent. Tier A (ADR 025) owners must confirm this, or ask for the attempt to be per execution row. Proceeding with per engine run because it is the stricter choice.
- Lineage root equals the root of the `resumed_from_execution_id` chain. In practice this is the first execution of the work item, so a reviewer in the same work item as the author always shares a lineage. The issue also mentions "same trace". The evidence `trace_id` is written later by the evidence writer, so it cannot be authoritative at execution start, and it is not used here.
- Real `we_` ids are `we_` plus a hyphenated UUID (`workitems.insertExecution`). The Tier A regex `executionIDRE = we_[0-9a-f]{16,64}` in `internal/reviewreceipts/types.go` rejects them, so no real worker request can parse today. The regex needs an ADR 025 amendment in both tiers. That fix is a prerequisite for #895, not part of this change.
- Who may attach executions. `POST /work-items/{id}/executions` and `/resume` need only the tenant `developer` role. The record is written by mctl-api, and the run token can only exist after it, but `engine`/`engine_ref` are still chosen by the attacher. The attaching principal is recorded so that #895 can restrict eligible reviewers to platform-attached executions. Whether to enforce that here is left to the reviewer.
- Where the canonical golden-vector file lives (this repo or mctl-agents). The proposal ships it here and asks Tier A to vendor it.
- Deployed configuration of mctl-api (database URLs, whether `WORK_ITEMS_DB_URL` and `EVIDENCE_DB_URL` point to the same database) could not be observed. See design.md.
