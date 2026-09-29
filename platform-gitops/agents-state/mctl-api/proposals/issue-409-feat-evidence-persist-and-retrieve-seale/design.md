# Design: issue-409-feat-evidence-persist-and-retrieve-seale

## Current state

mctl-api is a Go 1.25 chi/v5 REST API with a package-per-concern `internal/` layout
(`CLAUDE.md`). Every durable concern owns its own PostgreSQL-backed store package, declares
its schema as a `CREATE TABLE IF NOT EXISTS` string applied at `NewStore`, and is wired
optionally in `cmd/api/main.go` behind a `*_DB_URL` env var with an `AUDIT_DB_URL` fallback.
A nil store makes its routes answer `503`, never an empty result.

The relevant existing pieces, all read in this clone:

**Canonical work and execution state — `internal/workitems`.**
`internal/workitems/store.go` declares `work_items` (`wi_`), `work_item_events`,
`work_item_intents`, `work_item_executions` (`we_`, with `engine`, `engine_ref`, `attempt`,
`phase`, and `UNIQUE (work_item_id, engine, engine_ref)`), `work_item_surface_refs` and the
two idempotency tables. `internal/workitems/types.go` fixes the prefixes
(`WorkItemIDPrefix = "wi_"`, `ExecutionIDPrefix = "we_"`), the engines (`temporal`, `argo`)
and the sentinel errors. `internal/workitems/execution_requests.go` declares
`work_item_execution_requests` (`xr_`); `internal/workitems/action_approvals.go` declares
`action_approval_requests` (`aar_`) with an `execution_id TEXT NOT NULL` column that carries
**no** prefix constraint and **no** foreign key.

**The sealed-immutable-record precedent — `internal/workitems/snapshots.go`.**
`work_item_context_snapshots` (`cs_`) is the closest existing analogue to evidence and the
template this design follows:

- the id is derived deterministically (`SnapshotIDFor(executionID, contentHash)` =
  `"cs_" + hex(sha256(execID + "\x00" + hash))[:32]`);
- `HashCanonical` is `"sha256:" + hex(sha256(bytes))`;
- the canonical bytes are stored as `BYTEA` and served base64 (`canonical_b64`) precisely so
  the hash survives JSON re-encoding;
- `scanSnapshot` recomputes the hash **on every read** and refuses to serve bytes that no
  longer match;
- `SealSnapshot` runs compare-then-insert inside `withTx` under an advisory lock: identical
  bytes and identical claims return the stored row with `created=false`; different bytes are
  `ErrSnapshotDivergence`;
- a `work_item_context_snapshots_no_update` `BEFORE UPDATE` trigger refuses updates
  outright.

`internal/api/handlers_work_item_snapshots.go` is the HTTP counterpart: `201` on create,
`200` on replay via `createdStatus(created)`, typed error codes
(`snapshot_divergence`, `snapshot_not_found`), a body-size cap
(`maxSnapshotBodyBytes`), strict base64 decoding, a writer restriction
(`!user.IsService()` → `403 snapshot_writer_forbidden`) and an audit entry on create.

**The insert-only correlation-ledger precedent — `internal/usage`.**
`internal/usage/store.go` declares `model_usage_records` with a deterministic primary key
used as the idempotency guarantee (`ON CONFLICT (id) DO NOTHING`, `IngestResult` with
`Accepted`/`Deduped`). `Record.EnsureID` in `internal/usage/types.go` rejects a schema
version it does not support (`ErrUnsupportedSchema`) and rejects a client-supplied `id` that
does not equal the derived one — exactly the server-side-recompute discipline this issue
asks for. Critically, `model_usage_records.execution_id` is documented as:

> the work-item store's `we_…` when the run has one, otherwise the runner's
> `ExecutionContext` id (`ex-…`). It is correlation, never part of the identity.

and validated against `executionIDPattern`, which accepts both shapes. The `we_` / `ex-`
split is therefore already an accepted, documented fact in mctl-api storage — but usage
overloads one column with two meanings and resolves neither.

**Correlation, not foreign keys.** `docs/work-context-contract.md` ("ID scheme") states the
rule explicitly: cross-store relationships are joinable by value, never by a database FK,
because the stores may live in different databases and `agent_executions` is deliberately
unconstrained. The same document defines the retention posture
(`WORKITEM_SURFACE_RETENTION_DAYS`, `WORKITEM_RETENTION_DAYS`) that purges terminal work
items; anything FK-cascaded to `work_items` would be purged with them.

**Authorization.** `internal/auth/oidc.go` models a narrow capability principal:
`UsageWriterUserID = "service:mctl-agents-usage"`, `PermissionUsageWrite = "usage:write"`,
`NewUsageWriterUser()`, `IsUsageWriter()`, `HasPermission()`, and a token read from
`MCTL_USAGE_WRITER_TOKEN` that is refused if it equals the service or any surface token.
`usageWriterGate` in `internal/api/handlers_usage.go` confines that principal to exactly one
route. Work-item reads use `canSeeWorkItem` (admin, else tenant access plus
tenant-visibility or ownership) and `visibleWorkItem`, which answers `404` rather than `403`.

**Routing and rate limits.** `internal/api/router.go` puts side-effect-free reads outside the
20/min write group, and gives high-frequency machine writes (lifecycle ownership, execution
request claim/fulfil) their own 120/min groups with the reasoning written out inline. Usage
ingestion is deliberately un-throttled on that group because "the money is spent whether or
not the row lands".

**What does not exist.** There is no evidence table, no `internal/evidence` package, no
`ev-` identifier anywhere in the repo, and no route under `/api/v1/evidence`. There is no
resolver from an `ex-` runtime execution id to a `we_` work execution.

## Proposed solution

Add a new store package `internal/evidence`, a new HTTP surface under `/api/v1/evidence`
plus one work-item-scoped read, a dedicated narrow write principal, and optional wiring in
`cmd/api/main.go`. Nothing existing changes shape; the additions are purely additive.

> **Correction (owner-directed, 2026-09-29).** Sections 1-4 were rewritten after review for two reasons.
>
> 1. The first revision derived `content_hash` and `ev-` differently from Tier A, so every real Tier A envelope would have been rejected with `evidence_hash_mismatch`. It also answered a normal producer retry with a false `409 evidence_divergence`.
> 2. The first revision settled the `we_` / `ex-` join model inside the storage schema. The join shape is now owned by mctlhq/mctl-agents#539 (the ADR 018 amendment, S2), and **#539 is a blocking prerequisite for approving and implementing this proposal**.
>
> Two smaller changes came with it: `produced_by` was removed, because the envelope has no such field, and the optional `MissingFor` task was dropped.

### 1. Two tables: an immutable record and a rebuildable projection

This is the most important structural decision.

- The sealed evidence row must be strictly immutable.
- The useful retrieval keys (repository, issue, PR, Temporal workflow ref) are **derived** from canonical state that can legitimately change after sealing. A PR number appears after the envelope was sealed; a work item is resolved later.
- Putting derived columns in the immutable row forces a choice between "never correct the index" and "update an immutable row". Splitting them removes that choice.

```sql
-- internal/evidence/store.go
CREATE TABLE IF NOT EXISTS execution_evidence (
    id                       TEXT PRIMARY KEY,        -- the envelope's evidence_id, ev- + 16 hex, verified server-side
    content_hash             TEXT NOT NULL UNIQUE,    -- sha256:<hex>, Tier A content hash, verified server-side
    api_version              TEXT NOT NULL,           -- evidence.mctl.ai/v1alpha1
    envelope                 BYTEA NOT NULL,          -- the envelope bytes exactly as first received
    -- join columns: exactly the ExecutionJoin fields ADR 018 defines once
    -- mctlhq/mctl-agents#539 has merged (see section 4); copied verbatim
    -- from the envelope, never classified or rewritten by this layer
    execution_id             TEXT NOT NULL,           -- ExecutionJoin.execution_id (v1alpha1: we_)
    work_item_id             TEXT NOT NULL DEFAULT '',-- ExecutionJoin.work_item_id
    trace_id                 TEXT NOT NULL DEFAULT '',-- ExecutionJoin.trace_id
    created_at               TIMESTAMPTZ NOT NULL,    -- envelope created_at: a producer claim, excluded from the hash
    ingested_by              TEXT NOT NULL,           -- authenticated caller
    ingested_by_principal_id TEXT NOT NULL DEFAULT '',-- mctl-api#373 dual-write
    ingested_at              TIMESTAMPTZ NOT NULL
);

-- Rebuildable index projection. It has no authority: if a column here
-- disagrees with canonical state, canonical state wins and the entry is a
-- stale index, never an answer. Deleting and recomputing every row loses
-- nothing.
CREATE TABLE IF NOT EXISTS execution_evidence_refs (
    evidence_id       TEXT PRIMARY KEY
                      REFERENCES execution_evidence (id) ON DELETE CASCADE,
    work_execution_id TEXT NOT NULL DEFAULT '',   -- only ever a real we_, else ''
    work_item_id      TEXT NOT NULL DEFAULT '',
    tenant            TEXT NOT NULL DEFAULT '',
    engine            TEXT NOT NULL DEFAULT '',
    engine_ref        TEXT NOT NULL DEFAULT '',
    repository        TEXT NOT NULL DEFAULT '',
    issue_number      BIGINT,
    pr_number         BIGINT,
    derived_at        TIMESTAMPTZ NOT NULL,
    CONSTRAINT execution_evidence_refs_work_prefix CHECK (
        work_execution_id = '' OR work_execution_id LIKE 'we\_%'
    )
);
```

- The join columns shown are the v1alpha1 ones. If #539 adds a typed field (for example a runtime/control execution id next to `we_`), this table gains exactly that column with exactly its ADR-defined constraint. The storage layer does not invent the field, the discriminator or the primary-retrieval rule; it mirrors what the ADR fixes.
- The `execution_evidence_refs_work_prefix` check is the database-level guarantee that an `ex-` can never be parked in a `we_` field.

Immutability is enforced the same way snapshots enforce it:

```sql
CREATE OR REPLACE FUNCTION execution_evidence_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'execution_evidence rows are immutable';
END;
$$ LANGUAGE plpgsql;
-- BEFORE UPDATE trigger, created in the same DO $$ ... guard shape as
-- work_item_context_snapshots_no_update.
```

- `DELETE` stays permitted; it is the retention mechanism, and it cascades to the projection.
- There is deliberately **no** foreign key from `execution_evidence` to `work_items` or `work_item_executions`:
  - `docs/work-context-contract.md` mandates correlation over foreign keys;
  - the stores may live in different databases;
  - a foreign key would make evidence die with the `WORKITEM_RETENTION_DAYS` sweep.

### 2. Identity, hashing and verification: Tier A's algorithm, exactly

The server never invents its own identity rule. It re-derives Tier A's, as defined by `seal()` in `orchestrator/execution_evidence.py` (ADR 018):

1. Parse the received envelope as strict JSON:
   - reject duplicate keys, unknown top-level keys and unknown block keys, mirroring `ExecutionEvidence.from_dict`'s `_reject_unknown_keys`;
   - check `api_version` against `SupportedAPIVersions`, and check that `kind` matches it.
2. Build the **content payload**: the envelope object minus exactly `evidence_id`, `content_hash` and `created_at`.
   - Tier A's `_content_payload` excludes those three and keeps `api_version` and `kind`.
   - Each optional block (`policy_decisions`, `snapshot_refs`, `execution_request`, `usage`, `approvals`, `artifacts`, `gaps`) takes part only when it is present and non-empty, exactly as Tier A adds it. An empty block that is present must not change the hash.
3. Serialise the payload with Tier A's canonical-JSON rule, `context_snapshot._canonical_json`: `json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)`, UTF-8. This means:
   - `ensure_ascii` is on, so every non-ASCII character becomes `\uXXXX`, with surrogate pairs above the BMP;
   - there is **no** HTML escaping; Go's `encoding/json` escapes `<`, `>` and `&` by default, and that must be turned off;
   - keys are sorted recursively;
   - Python's float/int formatting applies (Tier A carries no floats; reject non-integer numbers rather than guess).
4. Compute `content_hash = "sha256:" + hex(sha256(canonical))`, then `evidence_id = "ev-" + content_hash[7:23]`, i.e. 16 lowercase hex characters, as in `seal()`.
5. The envelope's own `content_hash` and `evidence_id` must equal the recomputed values. Otherwise answer `400 evidence_hash_mismatch`, echoing both values. Never correct them silently.

Further rules:

- The received bytes are stored verbatim in `envelope` and served back as `envelope_b64`. On every read, `scanEvidence` re-runs steps 1-4 over the stored bytes and refuses to serve a row whose recomputed hash no longer equals its `content_hash`, the same discipline `scanSnapshot` applies.
- The derivation is keyed by `api_version`: a future version with a different sealing rule is a new entry, never a change to the v1alpha1 one.
- **Tier A conformance is a hard gate.** Golden vectors from mctl-agents are ported into `internal/evidence/testdata/`: the #520 fixture plus the #539 vectors for every join shape the amended ADR allows, including one with non-ASCII text and one with `<`, `>` and `&` in a string. The Go implementation must reproduce each `content_hash` and `evidence_id` byte for byte.

### 3. Ingest: compare-then-insert on the content hash

This follows the `SealSnapshot` pattern. Inside `withTx`, under an advisory lock keyed on the `ev-` id, `SELECT` by `id`, then:

- **no row** → `INSERT` and return `created = true` (`201`);
- **row with the same `content_hash`** → this is the same evidence. Return the stored row with `created = false` (`200`) and write nothing. This covers a byte-identical replay, and also a producer retry that re-sealed the same content with a different `created_at`: Tier A excludes `created_at` from the hash precisely so that sealing identical inputs twice yields one identity. The first stored bytes and `created_at` win.
- **row with the same `ev-` id but a different `content_hash`** → a 64-bit id-prefix collision between different content. Answer `ErrEvidenceDivergence` (`409 evidence_divergence`) and write nothing. The `content_hash UNIQUE` constraint backs this up at the database level.

Server-owned ingest provenance (`ingested_by`, `ingested_at`) is not a claim about the evidence and is not compared. A replay from a different authorised principal still returns the first record.

### 4. The `we_` / `ex-` split is owned by mctl-agents#539, not by this layer

This proposal no longer chooses the join model. The contract question is recorded, analysed and decided in **mctlhq/mctl-agents#539**, the ADR 018 amendment and slice S2 of #199. That slice decides between:

- **(A)** governed implementer/shepherd runs resolve to a canonical `we_`; or
- **(B)** an explicit two-identity join with distinct typed fields for the canonical work execution `we_` and the runtime/control execution `ex-`.

It then fixes the exact `ExecutionJoin` shape, which field is the primary retrieval identity, and the golden vectors.

This layer's obligations, whatever #539 decides:

- **Mirror, never classify.** The join columns are exactly the `ExecutionJoin` fields of the amended ADR, copied verbatim from the envelope and validated with the same prefix rules Tier A validates (`_check_execution_join` and whatever #539 adds). This layer never derives a discriminator of its own, never maps `ex-` to `we_`, and never puts one shape in another's column.
- **Primary retrieval identity** is the one the ADR names. Section 6 indexes that column unconditionally; any second typed identity gets a partial index.
- **Unresolvable is not an error.** An envelope with a valid join that mctl-api cannot resolve to a work item is stored, with an empty projection; it is not rejected for lacking a `we_`.
- **No second execution authority.** Nothing here mints, reconciles or resolves execution identities.

**Answer to issue question 12:** yes. #539 must merge before this proposal is approved and implemented, because it determines the join columns of `execution_evidence` and the conformance vectors. Tasks 1-10 below depend on it (task 0). If #539 settles on a shape this section did not anticipate, this proposal is re-reviewed before approval; the implementer does not adapt it ad hoc.

### 5. Derivation of the secondary references

`internal/evidence/derive.go` resolves the projection at ingest, best-effort, in one query
path, and never fails the ingest:

- a `we_` join value (the ADR-defined work-execution field) → `work_execution_id` = that
  value; look up `work_item_executions` by id for `work_item_id`, `engine`, `engine_ref`;
  look up `work_items` for `tenant` and `external_key`.
- a join with no `we_` (only possible if #539 allows one) → nothing is resolvable in
  mctl-api today, so the projection stays empty — an honest absence, not an error.
- `repository` / `issue_number` / `pr_number` are parsed from `work_items.external_key` when
  it matches `owner/repo#N`, with the issue-versus-PR distinction taken from the work item's
  own correlation; when it does not parse, all three stay empty and the row stays out of the
  partial indexes.
- The `engine_ref` column is precisely the Temporal workflow / Argo workflow reference the
  issue asks for, reached "where it can be derived, for example through
  `work_item_executions.engine_ref`" — which is literally the column
  `internal/workitems/store.go` declares.

Because the projection is rebuildable, a future `ex-` → `we_` resolver, or a later-arriving
PR number, is handled by recomputing rows — never by touching the sealed record.

### 6. Indexes

The issue forbids nullable indexes added merely to satisfy a list. Every index below is
either on a `NOT NULL` column or is a **partial** index that excludes the unresolved rows
entirely, so an index only ever contains rows it can actually answer for — the same technique
`work_items_tenant_external_key_open` and `event_outbox_unpublished` already use in this
codebase.

```sql
-- the primary execution join; always present, so unconditional
-- the ADR-named primary retrieval identity (v1alpha1: execution_id); a second typed
-- identity added by mctl-agents#539, if any, gets a partial index WHERE <col> <> ''
CREATE INDEX IF NOT EXISTS execution_evidence_exec
    ON execution_evidence (execution_id, ingested_at DESC);
-- trace_id is in ExecutionJoin but defend against an empty one
CREATE INDEX IF NOT EXISTS execution_evidence_trace
    ON execution_evidence (trace_id, ingested_at DESC) WHERE trace_id <> '';
-- retention sweep and operator listing
CREATE INDEX IF NOT EXISTS execution_evidence_ingested
    ON execution_evidence (ingested_at DESC);

CREATE INDEX IF NOT EXISTS execution_evidence_refs_work_exec
    ON execution_evidence_refs (work_execution_id) WHERE work_execution_id <> '';
CREATE INDEX IF NOT EXISTS execution_evidence_refs_item
    ON execution_evidence_refs (work_item_id) WHERE work_item_id <> '';
CREATE INDEX IF NOT EXISTS execution_evidence_refs_engine
    ON execution_evidence_refs (engine, engine_ref) WHERE engine_ref <> '';
CREATE INDEX IF NOT EXISTS execution_evidence_refs_repo_issue
    ON execution_evidence_refs (repository, issue_number)
    WHERE repository <> '' AND issue_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS execution_evidence_refs_repo_pr
    ON execution_evidence_refs (repository, pr_number)
    WHERE repository <> '' AND pr_number IS NOT NULL;
```

`content_hash` is covered by its `UNIQUE` constraint; there is no index on `api_version` (low cardinality, and a full scan of a version cohort is a migration task,
not a hot path).

### 7. HTTP surface

New `internal/api/handlers_evidence.go`, routes added in `internal/api/router.go`:

| Method | Path | Scope |
|---|---|---|
| `POST` | `/api/v1/evidence/records` | `evidence:write` (admins + the evidence writer) |
| `GET` | `/api/v1/evidence/{id}` | admin |
| `GET` | `/api/v1/evidence` | admin; filters `execution_id` (and any #539 typed identity), `trace_id`, `engine`+`engine_ref`, `work_item_id`, `repository`+`issue`, `repository`+`pr` |
| `GET` | `/api/v1/work-items/{id}/evidence` | `visibleWorkItem` / `canSeeWorkItem` |

The ingest body is the producer API of issue question 13:

```json
{
  "envelope_b64":  "<base64 of the sealed Tier A envelope JSON, verbatim>"
}
```

The envelope carries its own `api_version`, `evidence_id` and `content_hash`; all three are
verified per section 2, so the wrapper repeats none of them. `envelope_b64` mirrors
`snapshotBody.CanonicalB64` and is decoded with
`base64.StdEncoding.Strict()` so a re-encoded envelope cannot silently change its hash. The
body cap follows `maxSnapshotBodyBytes`: `(MaxEvidenceBytes/3+1)*4 + 16<<10`.

Reads return the wrapper plus `envelope_b64`, never a re-serialised JSON object, so the
caller can verify the hash themselves.

Routing placement follows the reasoning already written into `router.go`: the reads sit
outside the 20/min write group (they are side-effect free and operator-driven), and ingest
gets its own 120/min group with the same argument the lifecycle and execution-request groups
use — a single short Postgres transaction that a producer makes once per governed run must
not compete with the budget reserved for calls that trigger Argo and Temporal.

### 8. Authorization

`internal/auth/oidc.go` gains, modelled one-for-one on the usage writer:

```go
const (
    EvidenceWriterUserID    = "service:mctl-agents-evidence"
    PermissionEvidenceWrite = "evidence:write"
    evidenceWriterTokenEnv  = "MCTL_EVIDENCE_WRITER_TOKEN"
)
```

`HasPermission` returns true for `evidence:write` when the caller is the evidence writer or
an admin. The token loader reuses the existing refusals: too short, equal to
`MCTL_AGENT_SERVICE_TOKEN`, or equal to any surface token or the usage-writer token → the
principal is disabled with an `slog.Error`. `evidenceWriterGate` in
`handlers_evidence.go` confines the principal to `POST /api/v1/evidence/records`, an exact
copy of `usageWriterGate`'s shape, and is added to the same middleware chain.

Reads are admin-only by default, for the reason `handlers_usage.go` gives for the ledger:
cross-cutting governance evidence is more sensitive than a workflow status. The one
tenant-visible read is work-item-scoped and reuses `visibleWorkItem`, which already answers
`404` (not `403`) to a caller who may not see the item — so the existence of evidence never
leaks. Evidence whose projection has no `work_item_id` is admin-only: fail closed.

Every accepted ingest writes an audit entry through the existing `h.logAudit` path, in the
shape `auditWorkItem` uses, naming `evidence_id`, the join's primary execution identity and the ingesting principal.

### 9. Non-fatal producer failure with an observable gap (issue question 14)

mctl-api's half of this contract is to make the three outcomes distinguishable and cheap:

- **Store not configured** → `503 evidence_store_unavailable` on every evidence route. Never
  an empty list. This is the `requireUsageAdmin` reasoning verbatim: "the ledger is not
  configured" and "this DevLoop cost nothing" must never be the same answer.
- **Evidence genuinely absent** → `404 evidence_not_found` on `GET /api/v1/evidence/{id}`,
  and an empty `"evidence": []` on the list routes. An operator asking "did this governed run
  leave evidence?" gets an unambiguous no.
- **Evidence present** → `200`.

Because the gap is a plain absence keyed on the join's primary execution identity, it is derivable by an ordinary
left join from `work_item_executions` / `action_approval_requests` to `execution_evidence`;
no separate gap table is invented, and no coverage route is added in this slice.

The producer's own non-fatality — treat any non-2xx as a warning, never fail the governed
workflow — lives in the mctl-agents slice and is out of scope here. The endpoint is designed
to make that easy: bounded body, single short transaction, safely retryable because the
`ev-` identity is deterministic, and a generous rate-limit group so a retry burst is not
throttled into a false gap.

### 10. What stops this becoming a second execution or work-item store (issue question 15)

Five structural constraints, not conventions:

1. **No lifecycle.** The tables have no state column, no transition table, no version
   counter, and no `UPDATE` path. Compare `internal/workitems/types.go`, which needs
   `Transitions`, `Next` and `IsTerminal` precisely because it *is* a lifecycle owner.
2. **The database refuses mutation.** The `BEFORE UPDATE` trigger makes "just patch the
   phase onto the evidence row" fail at the storage layer, not at review time.
3. **No copied state.** `phase`, `state`, `attempt`, approval state and intent text are
   absent by construction. The only execution-shaped columns are correlation references the
   contract already says are references.
4. **The derived columns have no authority, and it is written down.** They live in a separate
   rebuildable table whose whole contents can be dropped and recomputed. Any disagreement
   with canonical state is a stale index entry, never an answer.
5. **Bounded and scanned content.** `MaxEvidenceBytes` (256 KiB) plus `internal/secretscan`
   over the canonical bytes stop the envelope becoming a place to park transcripts or
   payloads, the same way `MaxIntentBytes` and `checkText` do in `internal/workitems`.

### 11. Retention boundary (issue question 8)

Retention belongs to mctl-api and its storage layer, and nowhere else. `EVIDENCE_RETENTION_DAYS`
(default `0` = retain indefinitely) follows the `WORKITEM_RETENTION_DAYS` pattern documented
in `docs/work-context-contract.md`. The sweep deletes whole rows — evidence is never partially
redacted, because a redacted envelope no longer hashes to its `content_hash` and would be
refused on read by the verification in `scanEvidence`. Deletion cascades to
`execution_evidence_refs`. Nothing is written to GitOps or any public repository; the rejected
`mctl-agents#483` `_evidence/` direction is not reintroduced in any form.

## Alternatives

**A. One table with derived columns on the immutable row.** Simplest schema, one insert, no
projection. Dropped because it forces an impossible choice: either the immutable row is
updated when a PR number or a later `ex-` → `we_` resolution arrives (violating insert-only,
and defeating the `BEFORE UPDATE` trigger that makes immutability real), or the retrieval
indexes are permanently wrong for every row sealed before its canonical facts existed. The
split costs one extra table and one extra insert in the same transaction.

**B. Store the envelope as `JSONB` and query inside it.** Attractive because Postgres could
then index expressions over the envelope and no projection would be needed. Dropped because
`JSONB` normalises key order and drops duplicate keys, so the stored value no longer
round-trips to the received bytes and the sealed `content_hash` becomes unverifiable — which
destroys the single property the whole feature exists to provide. `internal/workitems/snapshots.go`
already made this call: `canonical BYTEA` served as `canonical_b64`. Evidence follows it.

**C. Reuse `work_item_context_snapshots` or extend `model_usage_records`.** Rejected on
contract grounds. Snapshots are `UNIQUE` per `we_` execution with a mandatory FK to
`work_items`, so they structurally cannot hold evidence for an `ex-` run — and widening them
would break the frozen `cs_` contract. `model_usage_records` is a financial read model under
ADR-012 whose invariants (pricing version, NUMERIC money, token semantics) have nothing to do
with sealed evidence; bolting evidence onto it would overload a second identifier column and
make two unrelated retention policies share one table.

**D. Decide the `we_` / `ex-` model here, in the storage schema.** This was the first
revision: one verbatim `execution_ref` plus a prefix-derived `execution_ref_kind`. Dropped
on review. It fixes the envelope's join semantics in a storage table while Tier A still
rejects every non-`we_` join, and it pre-empts a contract that belongs to ADR 018. The
decision moved to mctlhq/mctl-agents#539, which this proposal now depends on.

**E. Hash the received bytes verbatim and derive `ev-` from that digest.** This was also
the first revision. Dropped on review. Tier A hashes the canonical content payload without
`evidence_id`, `content_hash` and `created_at`, and takes `ev-` as `content_hash[7:23]`. A
verbatim-bytes rule would reject every real Tier A envelope and turn a normal re-seal retry
into a false divergence.

## Platform impact

**Migrations.** Purely additive: two new tables, one trigger function, one trigger, eight
indexes, applied by `NewStore` in the established `CREATE TABLE IF NOT EXISTS` style. No
existing table, column, index or constraint is altered. No backfill — there is no prior
evidence to migrate, and the rejected GitOps `_evidence/` data is explicitly not imported.

**Backward compatibility.** No existing route, response shape or error code changes. No MCP
tool is added, so the tool-count expectation in `internal/mcp/server_test.go` is untouched
(`CLAUDE.md`). Without `EVIDENCE_DB_URL` / `AUDIT_DB_URL`, or with `EVIDENCE_DISABLED` set,
the store is nil and the new routes answer `503` — the pattern `WORK_ITEMS_DISABLED` already
uses in `cmd/api/main.go`. Existing deployments are unaffected until the env vars are set.

**Resource impact.** One row per governed run, each bounded at 256 KiB, realistically a few
KiB. At current DevLoop volumes this is low tens of MB per year; the partial indexes keep
index size proportional to *resolvable* rows, not to all rows. Ingest is one short
transaction with one advisory lock keyed on the `ev-` id, so producers never contend with
each other. `MaxEvidenceBytes` caps the worst case and the body limit rejects over-large
requests before decoding.

**Risks and mitigations.**

- *The Go `ev-` derivation does not match Tier A byte-for-byte* (canonical-JSON details:
  `ensure_ascii`, no HTML escaping, recursive key order, empty optional blocks omitted). Highest-severity risk: every
  stored identity would be wrong and the store would be silently useless. Mitigated by making
  golden-vector conformance (`internal/evidence/testdata/`, ported from mctl-agents) a
  blocking test, by keeping the derivation in two small functions keyed on `apiVersion`, and
  by shipping the writer principal disabled by default so no production rows are written
  before the vectors pass.
- *The ADR 018 amendment (#539) lands with a join shape this design did not anticipate.*
  Mitigated by sequencing: #539 merges before this proposal is approved, and a shape this
  design did not foresee sends the proposal back for re-review instead of being adapted ad hoc.
- *Stale projection rows mislead an operator.* Mitigated by labelling the projection
  non-authoritative in the table comment and in `docs/execution-evidence.md`, by exposing
  `derived_at` on every read, and by making a full rebuild a supported, lossless operation.
- *The evidence writer token leaks.* Mitigated exactly as the usage writer is: one permission,
  no admin, no tenant, confined to one route by `evidenceWriterGate`, refused at startup if it
  collides with the service, surface or usage-writer tokens, and every row records
  `ingested_by`.
- *An envelope carries content it should not.* Mitigated by `MaxEvidenceBytes` and by running
  the existing `internal/secretscan` over the canonical bytes at ingest, rejecting rather than
  redacting — a redacted envelope would not hash to its seal.
- *Evidence outliving the work item it references.* Intentional and load-bearing: no FK, no
  cascade from `work_items`. The cost is dangling references after a
  `WORKITEM_RETENTION_DAYS` purge, which is the correct trade — evidence of a governed
  mutation must not be deletable as a side effect of work-item housekeeping. Documented in
  `docs/execution-evidence.md`.
