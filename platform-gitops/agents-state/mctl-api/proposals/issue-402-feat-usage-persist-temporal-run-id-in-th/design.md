# Design: issue-402-feat-usage-persist-temporal-run-id-in-th

## Current state

The ledger lives in one small package plus one handler file.

**`internal/usage/types.go`** defines `Record` (line 86). Its correlation
block (lines 105-115) is a flat set of optional fields:

```go
TemporalWorkflowID string `json:"temporal_workflow_id,omitempty"`
ArgoWorkflowName   string `json:"argo_workflow_name,omitempty"`
ExecutionID        string `json:"execution_id,omitempty"`
Agent              string `json:"agent,omitempty"`
...
```

There is no run id. `DeterministicID` (line 174) hashes only
`session_id | result_uuid | model_key` (or the `num_turns` fallback), and
`EnsureID` (line 210) recomputes it unconditionally rather than trusting the
wire. `Validate` (line 239) calls `validateCorrelation` (line 288), which
shape-checks `target_repo` against `targetRepoPattern` and `execution_id`
against `executionIDPattern` (line 281: `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`)
and pairs issue/PR numbers with a repository. Fields not on the struct are
discarded by `encoding/json` at decode time — silently.

**`internal/usage/store.go`** holds the schema as a Go constant
(`usageSchema`, line 54) executed with `CREATE TABLE IF NOT EXISTS` at startup
in `NewStore` (line 140). The repo does not use migration files here — the
comment at line 29 states the convention explicitly and points at
`internal/lifecycle`, `internal/alerts` and `internal/agentregistry`. Columns
added after the original table are appended as separate statements in the same
constant:

```sql
ALTER TABLE model_usage_records ADD COLUMN IF NOT EXISTS ingested_by TEXT NOT NULL DEFAULT '';
ALTER TABLE model_usage_records ADD COLUMN IF NOT EXISTS ingested_by_principal_id TEXT NOT NULL DEFAULT '';
ALTER TABLE model_usage_records ADD COLUMN IF NOT EXISTS execution_id TEXT NOT NULL DEFAULT '';
```

`execution_id` (mctlhq/mctl-agents#499) is the exact precedent this change
follows: an ALTER at the end of `usageSchema` (line 112), an index
(`model_usage_execution_idx`, line 121), the column appended **last** to
`insertRecordSQL` (line 178, `$38`) and to `selectColumns` (line 388) and to
`scanRecord` (line 463), a `Filter` field (line 301), a `where()` predicate
(line 330) and a `GroupBy` dimension (line 483).

**`internal/api/handlers_usage.go`** exposes the three routes registered at
`internal/api/router.go:601-603`. `usageFilterFromQuery` (line 208) maps query
parameters to `usage.Filter`; `?execution_id=` maps to `Filter.ExecutionID`
(line 213) and `?workflow_id=` to `Filter.TemporalWorkflowID` (line 211). The
read responses embed the store result types directly
(`listUsageResponse`, line 127) precisely so that adding a field to the store
type cannot fail to reach the wire — the comment at line 120 records that a
hand-built map had already caused that drift once.

**Precedent for the concept.** `internal/humaninput/contract.go:55` already
carries `TemporalRunID *string` beside `TemporalWorkflowID string` on
`Execution`, validated at line 323 as "null or a non-empty string". So the run
id is an established mctl-api correlation value; only the usage ledger lacks
it.

**Tests.** `internal/usage/store_test.go` and
`internal/api/handlers_usage_test.go` run against a real Postgres
(`TEST_DATABASE_URL`, skipped locally, a service container in CI) — see
`newTestStore` at `store_test.go:39`. `TestRecordsAreQueryableByExecutionAndPullRequest`
(`store_test.go:498`) is the end-to-end template for a correlation field, and
`TestExecutionIDIsNotPartOfTheDedupeKey` (`usage_test.go:415`) is the template
for the dedupe invariant. `internal/openapi/openapi.yaml` does not describe
the usage endpoints at all, so `internal/openapi/embed_test.go` is unaffected.

## Proposed solution

Add one additive correlation field end to end, mirroring `execution_id`
statement for statement. Six touch points, no new abstraction.

**1. `Record.TemporalRunID`** — `internal/usage/types.go`, inserted directly
after `TemporalWorkflowID` so the two ids read as the pair they are:

```go
// TemporalRunID names the single execution of TemporalWorkflowID that spent
// the tokens (mctlhq/.github#50 decision 4). A workflow id survives a
// continue-as-new, a reset and a retry; the run id does not, so spend is
// attributable to the execution that actually incurred it. Correlation only.
TemporalRunID string `json:"temporal_run_id,omitempty"`
```

Plain `string`, not `*string`. The "absent is not zero" rule that makes every
counter a pointer is about measurement (`NULL` = not reported, `0` = reported
zero); for a correlation string, `""` is already the only spelling of absent,
and a nullable column would create a second one. `omitempty` keeps the wire
byte-identical for producers that do not send it, satisfying the issue's
"byte-for-byte as before" invariant.

**2. Schema** — one statement appended to `usageSchema`, with the same
additive comment style as the `execution_id` block, plus one index:

```sql
-- The single Temporal execution of temporal_workflow_id that spent the
-- tokens (mctlhq/.github#50 decision 4, prerequisite for
-- mctlhq/mctl-agents#505). Additive and defaulted: rows written before it
-- read as '' and producers that do not send it are unaffected. No backfill.
ALTER TABLE model_usage_records ADD COLUMN IF NOT EXISTS temporal_run_id TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS model_usage_run_idx ON model_usage_records (temporal_run_id);
```

The ALTER goes in `usageSchema` rather than into the `CREATE TABLE` body —
same as `execution_id` — so that the single constant is correct both for a
fresh database and for the deployed one. `NOT NULL DEFAULT ''` on Postgres 11+
is a catalog-only rewrite: no table scan, no lock held for the length of a
rewrite, which matters on a ledger nobody wants to rewrite.

**3. Write path** — append `temporal_run_id` as the **last** column of
`insertRecordSQL` (new `$39`) and `r.TemporalRunID` as the last argument of
the `tx.Exec` call in `IngestAs`. Appending rather than inserting mid-list
keeps every existing placeholder number unchanged, which is the whole reason
`execution_id` sits after `ingested_by_principal_id` despite being a
correlation field: a renumbered positional list is the easiest way to silently
write the wrong value into the wrong column.

**4. Read path** — append `temporal_run_id` to `selectColumns` and
`&r.TemporalRunID` as the last `rows.Scan` target in `scanRecord`. Because
`listUsageResponse` embeds `*usage.ListResult`, the field reaches the wire
with no handler change.

**5. Filter** — `Filter.TemporalRunID string`, a `where()` clause
`add("temporal_run_id = $%d", f.TemporalRunID)` guarded by non-empty, and
`TemporalRunID: q.Get("run_id")` in `usageFilterFromQuery`. This is what makes
the stored value *queryable* rather than merely durable, which is the issue's
stated motivation. No `GroupBy` entry: a run-id bucket is a strictly finer cut
of the `temporal_workflow_id` dimension that already exists, with unbounded
cardinality, and `Summary` truncates by record count — adding it would create
a new way to read a clipped breakdown as complete spend.

**6. Validation** — extend `validateCorrelation` to check a non-empty
`temporal_run_id` against the existing `executionIDPattern`. The rationale in
`docs/model-usage-ledger.md:126` applies exactly: shapes are checked for the
fields callers filter on, because a value with whitespace is not a smaller
answer later, it is no answer. A Temporal run id is a UUID and satisfies the
pattern trivially. The pattern is reused rather than copied so the two
filterable opaque-id fields cannot drift apart.

**Explicitly untouched:** `DeterministicID`, `EnsureID`, the primary key,
`ON CONFLICT (id) DO NOTHING`. The invariant is asserted by a new test rather
than left implicit.

**Docs** — `docs/model-usage-ledger.md`: add `temporal_run_id` to the
correlation-fields table at line 130 (grouped with `temporal_workflow_id`, or
given its own row naming the charset now that it is validated), add `run_id`
to the filter list at line 147, and add two sentences explaining what the run
id distinguishes and that it is not in the dedupe key. `CHANGELOG.md` is
release-please managed and is not hand-edited.

## Alternatives

1. **Nullable `TEXT` column with `*string`, mirroring
   `humaninput.Execution.TemporalRunID`.** Rejected: it would make this the
   only correlation field on `model_usage_records` where `NULL` and `''` are
   both reachable and mean the same thing, so every future filter and
   group-by would need a `COALESCE` the other correlation fields do not need.
   The human-input contract is a sealed document with explicit JSON `null`
   semantics for a fixed schema; the ledger is a wide append-only table whose
   convention is `NOT NULL DEFAULT ''`.

2. **A structured `TemporalExecution { WorkflowID, RunID }` sub-object shared
   across `internal/usage`, `internal/humaninput` and `internal/lifecycle`.**
   Rejected: it changes the JSON shape of `temporal_workflow_id` for every
   existing producer, which directly violates the issue's "byte-for-byte as
   before" invariant, and the issue says in so many words not to broaden this
   into a Temporal execution-identity redesign. It would also be a breaking
   read-model change for anyone consuming `GET /api/v1/usage/records`.

3. **Persist only, no filter and no index.** This is the literal minimum the
   Scope bullets ask for and is a defensible reviewer preference. Rejected as
   the default because a correlation value you cannot select on does not
   satisfy the issue's own framing ("durable/queryable correlation"), and
   adding the filter later means a second schema touch on the same table to
   add the index. Kept as a contained subtraction: dropping the `where()`
   clause, the `Filter` field, the `?run_id=` mapping and the index leaves the
   rest of the change intact.

4. **A real migration file instead of `ALTER ... IF NOT EXISTS` in
   `usageSchema`.** Rejected: mctl-api has no migration runner. `internal/usage`,
   `internal/lifecycle`, `internal/alerts` and `internal/agentregistry` all
   apply schema at startup, and the comment at `store.go:29` names that as the
   convention. Introducing a migration tool for one additive column would be a
   platform change wearing a feature's clothes.

## Platform impact

**Migration.** One `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ... TEXT NOT NULL
DEFAULT ''` plus one `CREATE INDEX IF NOT EXISTS`, both executed by `NewStore`
at pod start. Additive and idempotent: applying it to a database that already
has the column is a no-op, so a rolling restart and a rollback-then-restart
are both safe. The `DEFAULT ''` is metadata-only on modern Postgres — no table
rewrite. The index build is the only real cost; on a ledger of current size it
is seconds, and `CREATE INDEX` (non-concurrent) briefly blocks writes to
`model_usage_records`. If the table has grown large enough for that to matter
at deploy time, the index statement can be split out and run as
`CREATE INDEX CONCURRENTLY` by hand, since the column itself does not depend
on it.

**Backward compatibility.** Old producer + new server: the field is absent,
the column defaults to `''`, and `omitempty` keeps it out of the response
body — byte-identical to today. New producer + old server (the window before
this deploys, and the reason for the ordering constraint): the unknown key is
silently dropped, which is exactly the failure mctlhq/mctl-agents#505 must not
ship into. Hence the ordering: this merges and deploys first. Old rows read as
`''` with no backfill. No existing filter, summary or response field changes.

**Ordering / cross-repo.** Merge and deploy mctl-api before
mctlhq/mctl-agents#505 begins emitting `WORKFLOW_TEMPORAL_RUN_ID`. Verify
against the deployed API with a single record round-trip before flipping the
producer.

**Risks and mitigations.**

- *Positional-argument drift.* `insertRecordSQL` / `selectColumns` /
  `scanRecord` are three hand-maintained ordered lists; a value written into
  the wrong column on a financial ledger is the worst outcome here.
  Mitigation: append last everywhere, never insert; the round-trip test in
  task T1 fails loudly on any mismatch, and a wrong-position scan is a type
  error or a visibly wrong value rather than a silent one.
- *Over-strict validation rejects a batch.* `IngestAs` is all-or-nothing, so a
  run id that fails `executionIDPattern` costs the producer its whole batch.
  Mitigation: the pattern admits every UUID; confirm the emitted shape with
  mctl-agents#505 (open question), and relax to free text if it turns out to
  be decorated.
- *Scope creep into execution identity.* Mitigated by an explicit out-of-scope
  list and by touching no shared type.
- *Dedupe regression.* Mitigated by an explicit assertion test
  (`TestTemporalRunIDIsNotPartOfTheDedupeKey`) modelled on the existing
  `execution_id` one, so a future refactor that folds correlation into the
  hash fails CI rather than double-counting spend.

**Resource impact.** One `TEXT` column (mostly empty strings) and one btree
index on an append-only table. Negligible write amplification; no change to
request latency, memory or the 1 MiB / 500-record batch caps.
