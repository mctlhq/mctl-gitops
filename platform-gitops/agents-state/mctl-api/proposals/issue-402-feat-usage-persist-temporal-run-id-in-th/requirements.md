# Persist `temporal_run_id` in the model usage ledger

## Context

The model-usage ledger (`internal/usage`, implementing ADR-012, shipped under
mctl-api#266) already carries a `temporal_workflow_id` correlation field on
every record: it is on `usage.Record` (`internal/usage/types.go:105`), it is a
column on `model_usage_records` (`internal/usage/store.go:64`), it is a query
filter (`usage.Filter.TemporalWorkflowID`, exposed as `?workflow_id=`) and a
summary dimension (`GroupByWorkflow`). What it does not carry is the Temporal
**run** id. A workflow id names the logical DevLoop; a run id names the one
execution of it. Without the run id, two runs of the same `dev-loop-…`
workflow id — a continue-as-new, a reset, a retried execution — are
indistinguishable in the ledger, and spend cannot be attributed to the
execution that actually incurred it.

Owner decision 4 on `mctlhq/.github#50` requires DevLoop-launched implementer
and shepherd usage records to carry both ids. mctlhq/mctl-agents#505 is ready
to emit `WORKFLOW_TEMPORAL_RUN_ID`, but cannot: `usage.Record` has no such
field, `encoding/json` silently discards the unknown key at
`internal/api/handlers_usage.go:162`, and the producer would believe it had
recorded correlation that never became durable. The run-id concept is not new
to mctl-api — `humaninput.Execution.TemporalRunID`
(`internal/humaninput/contract.go:55`) already names the same thing — so this
is an additive correlation field on an existing contract, nothing more.

## User stories

- AS a platform operator I WANT each usage record to name the Temporal run
  that spent the tokens SO THAT I can attribute spend to one execution rather
  than to every run that ever shared a workflow id.
- AS the mctl-agents usage producer (mctlhq/mctl-agents#505) I WANT
  `temporal_run_id` to be a known, persisted field SO THAT emitting
  `WORKFLOW_TEMPORAL_RUN_ID` produces durable correlation instead of a
  silently dropped JSON key.
- AS a finance/audit reader of the ledger I WANT records that omit the run id
  to keep behaving exactly as they do today SO THAT adding the field costs no
  existing row, no existing query and no existing producer.
- AS a maintainer I WANT the run id excluded from the dedupe key SO THAT a
  replay carrying different correlation cannot be counted as a second paid
  invocation.

## Acceptance criteria (EARS)

- WHEN a producer POSTs to `/api/v1/usage/records` a record containing
  `temporal_run_id`, THE SYSTEM SHALL persist that value in the
  `model_usage_records.temporal_run_id` column.
- WHEN a subsequent `GET /api/v1/usage/records` returns that record, THE
  SYSTEM SHALL serialise `temporal_run_id` with byte-identical value to what
  was ingested.
- WHEN a producer POSTs a record that omits `temporal_run_id`, THE SYSTEM
  SHALL accept it and SHALL return it on read with the field absent from the
  JSON body (empty string internally), exactly as it behaves today.
- WHEN two records differ only in `temporal_run_id`, THE SYSTEM SHALL derive
  the same `id` from `DeterministicID` and SHALL dedupe the second via
  `ON CONFLICT (id) DO NOTHING`, counting one paid invocation.
- WHEN `GET /api/v1/usage/records?run_id=<value>` is called, THE SYSTEM SHALL
  return only records whose `temporal_run_id` equals that value.
- IF a supplied `temporal_run_id` does not match the correlation character set
  already enforced for `execution_id` (up to 128 characters from
  `[A-Za-z0-9_.:-]`, starting alphanumeric), THEN THE SYSTEM SHALL reject the
  whole batch with `400` naming the offending record index, consistent with
  `Record.validateCorrelation` in `internal/usage/types.go:288`.
- WHILE rows written before this change exist in `model_usage_records`, THE
  SYSTEM SHALL read their `temporal_run_id` as the empty string and SHALL
  require no backfill.
- WHEN the schema is applied to a database that already has the column, THE
  SYSTEM SHALL succeed unchanged (`ADD COLUMN IF NOT EXISTS`), so `NewStore`
  stays idempotent across restarts.
- WHILE `temporal_run_id` is stored, THE SYSTEM SHALL treat it as correlation
  only: it SHALL NOT appear in `DeterministicID`, in `EnsureID` validation of
  identity, or in any uniqueness constraint.
- WHEN an operator reads `docs/model-usage-ledger.md`, THE SYSTEM
  documentation SHALL list `temporal_run_id` in the correlation-fields table
  next to `temporal_workflow_id` and in the `GET /api/v1/usage/records` filter
  list.

## Out of scope

- Backfilling `temporal_run_id` for historical rows. There is no source of
  truth to backfill from, and the invariant is explicit: absent stays absent.
- Making `temporal_run_id` required, or validating that it pairs with a
  non-empty `temporal_workflow_id`. Every correlation field on this record is
  independently optional and stays that way.
- Any change to `DeterministicID`, `EnsureID`, the primary key, or the
  idempotency semantics of `IngestAs`.
- Adding `temporal_run_id` as a `GroupBy` summary dimension. Run id is a
  strictly finer, unbounded-cardinality version of the `temporal_workflow_id`
  dimension that already exists; `Summary` truncation on that axis is a known
  hazard (`internal/usage/store.go:556`) and the issue does not ask for it.
- Temporal execution-identity redesign: no shared `ExecutionIdentity` type
  across `internal/usage`, `internal/humaninput` and `internal/lifecycle`.
- Emitting the field from mctl-agents. That is mctlhq/mctl-agents#505 and
  must land after this.
- OpenAPI changes: the usage endpoints are not described in
  `internal/openapi/openapi.yaml` today (only `docs/model-usage-ledger.md`
  documents them), so there is no spec entry to extend.

## Open questions

- **Filter, yes; group-by, no.** The issue's scope section asks only for
  persistence and round-trip, but its motivation sentence says an unknown
  field "would not become durable/queryable correlation". This proposal reads
  "queryable" as the record filter (`?run_id=`), mirroring how `execution_id`
  was added in mctlhq/mctl-agents#499, and deliberately stops short of a
  summary dimension. If a reviewer wants persistence only, dropping the filter
  plus its index is a contained subtraction (task 4 and the index in task 2).
- **Validation strictness.** `temporal_workflow_id` is documented as free text
  and unvalidated; `execution_id` is charset-checked because callers filter on
  it. Since this proposal makes the run id filterable, it applies the existing
  `executionIDPattern` to it. A Temporal run id is a UUID and satisfies that
  charset trivially, so the practical rejection risk is near zero — but the
  batch is all-or-nothing, so if mctlhq/mctl-agents#505 turns out to emit a
  decorated value (e.g. `workflowID/runID`), the check must be relaxed to free
  text rather than costing usage records. Confirm the exact emitted shape with
  mctl-agents#505 before merge.
- **Column type.** Modelled as a Go `string` with `omitempty` and a
  `TEXT NOT NULL DEFAULT ''` column, matching `temporal_workflow_id` and
  `execution_id`, not as the `*string` used by
  `humaninput.Execution.TemporalRunID`. The ledger's "absent is not zero" rule
  is about counters, where NULL and 0 are different facts; for correlation
  text, "" already means absent, and a nullable column would give two
  spellings of the same fact.
