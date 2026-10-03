# Tasks: issue-402-feat-usage-persist-temporal-run-id-in-th

- [ ] 1. Add `TemporalRunID string \`json:"temporal_run_id,omitempty"\`` to
      `usage.Record` in `internal/usage/types.go`, immediately after
      `TemporalWorkflowID` (currently line 105), with a comment stating that
      it names the single execution of the workflow, that it is correlation
      only, and that it is deliberately not in `DeterministicID`.
      — DoD: `go build ./...` passes; `DeterministicID` and `EnsureID` are
      textually unchanged.

- [ ] 2. Extend the schema in `internal/usage/store.go` (depends on 1): append
      `ALTER TABLE model_usage_records ADD COLUMN IF NOT EXISTS temporal_run_id TEXT NOT NULL DEFAULT '';`
      to the `usageSchema` constant next to the existing `execution_id` ALTER
      (line 112), with the same additive-comment style, plus
      `CREATE INDEX IF NOT EXISTS model_usage_run_idx ON model_usage_records (temporal_run_id);`
      beside `model_usage_execution_idx` (line 121).
      — DoD: `NewStore` applies cleanly against a fresh database and against
      one that already has the table; running it twice is a no-op.

- [ ] 3. Wire the write and read paths in `internal/usage/store.go`
      (depends on 2): append `temporal_run_id` as the **last** column of
      `insertRecordSQL` (new `$39`) and `r.TemporalRunID` as the last argument
      of the `tx.Exec` call in `IngestAs`; append `temporal_run_id` to
      `selectColumns` and `&r.TemporalRunID` as the last `rows.Scan` target in
      `scanRecord`. Do not renumber any existing placeholder.
      — DoD: the three ordered lists agree position for position; a diff shows
      only appended entries, no reordering.

- [ ] 4. Make the value queryable (depends on 3): add
      `TemporalRunID string` to `usage.Filter`, a guarded
      `add("temporal_run_id = $%d", f.TemporalRunID)` clause in
      `Filter.where()`, and `TemporalRunID: q.Get("run_id")` in
      `usageFilterFromQuery` (`internal/api/handlers_usage.go:208`). Do **not**
      add a `GroupBy` entry.
      — DoD: `GET /api/v1/usage/records?run_id=X` returns only matching rows;
      an absent `run_id` adds no predicate; `groupColumns` is unchanged.

- [ ] 5. Validate the shape (depends on 1): in `Record.validateCorrelation`
      (`internal/usage/types.go:288`), reject a non-empty `TemporalRunID` that
      does not match the existing `executionIDPattern`, with an
      `ErrInvalidRecord`-wrapped message naming the field. Reuse the pattern;
      do not copy it.
      — DoD: an empty run id is still valid; a UUID is valid; a value with a
      space or over 128 characters is a `400` naming the record index.

- [ ] 6. Update `docs/model-usage-ledger.md` (depends on 4 and 5): add
      `temporal_run_id` to the correlation-fields table (line 130) naming the
      same charset as `execution_id`, add `run_id` to the
      `GET /api/v1/usage/records` filter list (line 147), and add a short
      paragraph stating what the run id distinguishes (one execution of a
      workflow id that survives continue-as-new/reset/retry), that it is
      optional, and that it is not part of the dedupe key.
      — DoD: the correlation block documents both Temporal ids; no claim in
      the doc contradicts the code. `CHANGELOG.md` is not hand-edited
      (release-please owns it).

- [ ] 7. Verify nothing else needs the field (depends on 3): confirm
      `internal/openapi/openapi.yaml` still describes no `/api/v1/usage/*`
      path (so `internal/openapi/embed_test.go` needs no change), and confirm
      the MCP tool count in `internal/mcp/server_test.go` is untouched because
      no tool is added.
      — DoD: `go test ./internal/openapi/... ./internal/mcp/...` passes with
      no edits to either file.

- [ ] 8. Run the gates (depends on 1-7): `go fmt ./...`, `go vet ./...`,
      `golangci-lint run`, `go test ./...` (and with `TEST_DATABASE_URL` set,
      the Postgres-backed suites).
      — DoD: all clean; `go test -p 1 ./...` green against Postgres, matching
      the CI invocation noted in `internal/usage/store_test.go:36`.

## Tests

- [ ] T1. `internal/usage/store_test.go` —
      `TestTemporalRunIDRoundTrips`: ingest a record built by `testRecord`
      with `TemporalRunID` set to a UUID-shaped value, read it back with
      `Filter{TemporalRunID: …}`, assert exactly one row and that
      `Records[0].TemporalRunID` equals what was sent, and that a second
      record with a different run id is not returned by that filter. Model it
      on `TestRecordsAreQueryableByExecutionAndPullRequest` (line 498).
- [ ] T2. `internal/usage/store_test.go` — same test or a sibling: ingest a
      record with no run id and assert it is accepted and reads back as `""`.
- [ ] T3. `internal/usage/usage_test.go` —
      `TestTemporalRunIDIsNotPartOfTheDedupeKey`, copied in shape from
      `TestExecutionIDIsNotPartOfTheDedupeKey` (line 415): two records
      identical but for `TemporalRunID` derive the same `DeterministicID`.
- [ ] T4. `internal/usage/store_test.go` — dedupe at the database level: ingest
      the same record twice with different run ids and assert the second lands
      in `IngestResult.Deduped`, the table holds one row, and the stored run id
      is the first write's (ON CONFLICT DO NOTHING keeps the original, matching
      how `ingested_by` behaves).
- [ ] T5. `internal/usage/usage_test.go` — validation table cases alongside the
      existing correlation cases (lines 375-402): a UUID run id is valid, an
      empty run id is valid, a run id with a space / a slash / over 128
      characters is `ErrInvalidRecord`.
- [ ] T6. `internal/usage/store_test.go` — additive-schema coverage: insert a
      row with raw SQL naming only the pre-change columns (or `NewStore`
      against a database where the column was just added), then `List` it and
      assert `TemporalRunID == ""` and no error — i.e. pre-existing rows stay
      readable with no backfill. Also assert applying `usageSchema` twice
      succeeds, proving the ALTER and the index are idempotent.
- [ ] T7. `internal/api/handlers_usage_test.go` — HTTP round trip modelled on
      `TestUsageHandlers_CorrelationRoundTripsOverHTTP` (line 538): POST a body
      with `"temporal_run_id"` via `postUsage`, GET
      `/api/v1/usage/records?run_id=…`, assert the value survives JSON in and
      out; and POST a body with a malformed run id, asserting `400` naming
      `record 0`.
- [ ] T8. `internal/api/handlers_usage_test.go` — filter parsing: extend the
      `usageFilterFromQuery` test (around line 527) so
      `?run_id=…` populates `Filter.TemporalRunID`, and confirm an omitted
      `run_id` leaves it empty.
- [ ] T9. Wire-compatibility guard: a record ingested without
      `temporal_run_id` marshals to JSON with no `temporal_run_id` key
      (`omitempty`), so an existing consumer sees a byte-identical body.

## Rollback

The change is additive in every direction, so rollback is a code revert with
no data step.

1. **Revert the code.** Redeploy the previous mctl-api image (or revert the
   PR). The old binary does not reference `temporal_run_id` in
   `insertRecordSQL`, `selectColumns` or `scanRecord`, so it ignores the
   column entirely; the column is `NOT NULL DEFAULT ''`, so inserts from the
   old code still succeed. No schema step is required and none should be
   taken.
2. **Leave the column and index in place.** Dropping them is a destructive
   operation that buys nothing: an empty-defaulted `TEXT` column costs
   effectively no storage, and keeping it means a re-roll-forward is a code
   deploy with no migration. If a later decision genuinely retires the field,
   `ALTER TABLE model_usage_records DROP COLUMN temporal_run_id;` and
   `DROP INDEX model_usage_run_idx;` are the statements, run deliberately and
   never as part of an incident rollback.
3. **Cross-repo ordering.** If mctlhq/mctl-agents#505 has already shipped,
   roll it back (or disable `WORKFLOW_TEMPORAL_RUN_ID` emission) **before**
   reverting mctl-api. Otherwise the producer emits a field the reverted
   server silently drops — the exact failure this issue exists to prevent.
   Data already written to `temporal_run_id` is preserved through the revert
   and becomes readable again on roll-forward.
4. **Partial rollback.** If only the filter is unwanted (see the open question
   in `requirements.md`), revert task 4 and the index from task 2 and keep
   persistence: the column, the round trip and the docs row stand on their own.
