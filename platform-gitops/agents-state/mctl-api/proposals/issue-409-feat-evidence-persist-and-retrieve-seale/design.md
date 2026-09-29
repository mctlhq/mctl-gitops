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

### 1. Two tables: an immutable record and a rebuildable projection

The single most important structural decision. The sealed evidence row must be strictly
immutable, but the useful retrieval keys (repository, issue, PR, Temporal workflow ref) are
**derived** from canonical state that can legitimately change after sealing — a PR number
appears after the envelope was sealed, a work item is resolved later. Putting derived
columns in the immutable row forces a choice between "never correct the index" and
"update an immutable row". Splitting them removes the choice.

```sql
-- internal/evidence/store.go
CREATE TABLE IF NOT EXISTS execution_evidence (
    id                       TEXT PRIMARY KEY,        -- ev-<hex>, recomputed server-side
    api_version              TEXT NOT NULL,           -- evidence.mctl.ai/v1alpha1
    content_hash             TEXT NOT NULL,           -- sha256:<hex> of `canonical`
    canonical                BYTEA NOT NULL,          -- the sealed envelope, verbatim
    execution_ref            TEXT NOT NULL,           -- ExecutionJoin.execution_id, verbatim
    execution_ref_kind       TEXT NOT NULL
        CHECK (execution_ref_kind IN ('work', 'runtime')),
    trace_id                 TEXT NOT NULL DEFAULT '',
    produced_by              TEXT NOT NULL DEFAULT '', -- from the envelope
    sealed_at                TIMESTAMPTZ NOT NULL,     -- from the envelope
    ingested_by              TEXT NOT NULL,            -- authenticated caller
    ingested_by_principal_id TEXT NOT NULL DEFAULT '', -- mctl-api#373 dual-write
    ingested_at              TIMESTAMPTZ NOT NULL,
    CONSTRAINT execution_evidence_ref_kind_matches CHECK (
        (execution_ref_kind = 'work'    AND execution_ref LIKE 'we\_%') OR
        (execution_ref_kind = 'runtime' AND execution_ref LIKE 'ex-%')
    )
);

-- Rebuildable index projection. No authority: if a column here disagrees with
-- canonical state, canonical state wins and this is a stale index entry, never
-- an answer. Deleting and recomputing every row loses nothing.
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

The `execution_evidence_refs_work_prefix` check is the database-level guarantee that the
storage layer can never park an `ex-` in a `we_` field, which the issue names as a hard
requirement.

Immutability is enforced the same way snapshots do it:

```sql
CREATE OR REPLACE FUNCTION execution_evidence_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'execution_evidence rows are immutable';
END;
$$ LANGUAGE plpgsql;
-- BEFORE UPDATE trigger, created in the same DO $$ ... guard shape as
-- work_item_context_snapshots_no_update.
```

`DELETE` remains permitted — it is the retention mechanism — and cascades to the projection.
There is deliberately **no** foreign key from `execution_evidence` to `work_items` or
`work_item_executions`: `docs/work-context-contract.md` mandates correlation over FKs, the
stores may live in different databases, and an FK would make evidence die with the
`WORKITEM_RETENTION_DAYS` sweep. It would also make an unresolvable `ex-` reference
unstorable, which is exactly the failure mode the issue forbids.

### 2. Identity, hashing and verification

`internal/evidence/types.go`, mirroring `workitems.HashCanonical` / `SnapshotIDFor`:

```go
const (
    EvidenceIDPrefix = "ev-"
    APIVersionV1Alpha1 = "evidence.mctl.ai/v1alpha1"
    MaxEvidenceBytes = 256 << 10
)

// HashCanonical is the content hash of the received envelope bytes, verbatim:
// no re-encoding, no key re-ordering, no whitespace normalisation.
func HashCanonical(canonical []byte) string // "sha256:" + hex(sha256(canonical))

// EvidenceIDFor derives the immutable identity from the sealed content hash
// alone, so byte-identical envelopes are one record by construction.
func EvidenceIDFor(contentHash string) string // "ev-" + hex(sha256(contentHash))[:32]
```

Server-side recompute is unconditional, following `usage.Record.EnsureID`: a client-supplied
`id` or `content_hash` that does not equal the derived value is `400`
`evidence_hash_mismatch`, never silently corrected. On read, `scanEvidence` recomputes the
hash of the stored bytes and returns an error rather than serving a mismatched row, exactly
as `scanSnapshot` does.

`apiVersion` is validated against an allowlist (`SupportedAPIVersions`), and the digest
function is selected by that version, so a future `v1alpha2` with a different sealing rule is
a new entry, never a mutation of the old one.

**Tier A conformance is a hard gate, not an assumption.** Because
`orchestrator/execution_evidence.py` is not in this repo, the Go implementation must be
validated against golden vectors ported into `internal/evidence/testdata/` from mctl-agents.
If Tier A's derivation differs, only these two functions change.

### 3. Ingest: compare-then-insert, not `ON CONFLICT DO NOTHING`

`usage` uses `ON CONFLICT (id) DO NOTHING`, which dedupes but cannot distinguish an identical
replay from a conflicting write under the same id. The issue requires both, so evidence uses
the `SealSnapshot` pattern instead: inside `withTx` under an advisory lock keyed on the `ev-`
id, `SELECT` the existing row, then

- no row → `INSERT`, return `created = true` (`201`);
- row with identical `canonical` bytes **and** identical wrapper claims (`execution_ref`,
  `execution_ref_kind`, `api_version`, `produced_by`) → return it, `created = false` (`200`);
- row with different bytes or different claims → `ErrEvidenceDivergence` (`409`
  `evidence_divergence`), nothing written.

The "different bytes under the same id" branch is a hash-collision and truncation guard: the
id is a truncated digest of the content hash, so the comparison must be on the full bytes,
not on the id.

### 4. The `we_` / `ex-` split — recommendation and why

**Recommended: model (B), an ADR 018 amendment that distinguishes the canonical work
execution from the runtime/control execution in the join**, realised in storage as a single
verbatim `execution_ref` plus a derived-by-prefix `execution_ref_kind` discriminator.

Answering the issue's four constraints directly:

- *One stable primary retrieval identity.* `execution_ref` is that identity. It is stored
  exactly as the producer sealed it, it is `NOT NULL`, it is the primary non-PK index, and it
  never changes. Retrieval by execution never has to ask "which kind was it" first.
- *Deterministic linkage from mutations, policy decisions and approvals.*
  `action_approval_requests.execution_id` and `POLICY_DECISION` records carry `ex-` today;
  with a verbatim `execution_ref` they join by value to evidence with no translation step and
  no lossy mapping. Under model (A) that linkage would depend on a `we_` being minted for
  every governed run first — which does not exist yet and which no storage layer can
  manufacture.
- *No overloaded identifier semantics.* This is where the design improves on the existing
  `model_usage_records.execution_id`, which holds two meanings in one untagged column. The
  explicit `execution_ref_kind`, derived from the prefix alone and constrained by
  `execution_evidence_ref_kind_matches`, means no reader ever has to guess.
- *No second execution authority.* `execution_ref_kind` is a classification of the one string
  the producer sealed, computed by `strings.HasPrefix`. It mints nothing, it reconciles
  nothing, and it can be recomputed from `execution_ref` at any time.

Model (A) — force every governed implementer and shepherd run to resolve to a `we_` — is the
cleaner end-state and this design does not foreclose it. It is rejected **as a prerequisite**
because it requires a change in mctl-agents (minting or attaching a work execution for
implementer and shepherd runs) that mctl-api cannot make, and blocking evidence storage on it
would stall Tier B behind another repository's slice for no storage benefit.

**Forward compatibility is exact.** If the platform later adopts model (A), every new row
simply carries `execution_ref_kind = 'work'`; the `CHECK` already allows it, the indexes
already serve it, `work_execution_id` in the projection is already populated for that case,
and there is no migration. Model (B) is a strict superset of model (A) in this schema.

**Answer to issue question 12 — does resolving the split require a separate mctl-agents slice
before implementation?** No, not for this storage slice. Yes, as a prerequisite for the
*producer* slice: the ADR 018 amendment that blesses a discriminated execution reference in
`ExecutionJoin` must land in mctl-agents before the producer starts sealing `ex-` values, or
the producer would be writing something the frozen contract does not sanction. That
prerequisite is named explicitly in `tasks.md` as task 0, owned by mctl-agents, and it does
not gate tasks 1-9 here.

### 5. Derivation of the secondary references

`internal/evidence/derive.go` resolves the projection at ingest, best-effort, in one query
path, and never fails the ingest:

- `execution_ref_kind = 'work'` → `work_execution_id = execution_ref`; look up
  `work_item_executions` by id for `work_item_id`, `engine`, `engine_ref`; look up
  `work_items` for `tenant` and `external_key`.
- `execution_ref_kind = 'runtime'` → nothing is resolvable in mctl-api today, so everything
  stays empty. This is recorded as an honest absence, not an error.
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
CREATE INDEX IF NOT EXISTS execution_evidence_exec
    ON execution_evidence (execution_ref, ingested_at DESC);
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

No index on `content_hash` (it is a function of the primary key), none on `produced_by`, none
on `api_version` (low cardinality, and a full scan of a version cohort is a migration task,
not a hot path).

### 7. HTTP surface

New `internal/api/handlers_evidence.go`, routes added in `internal/api/router.go`:

| Method | Path | Scope |
|---|---|---|
| `POST` | `/api/v1/evidence/records` | `evidence:write` (admins + the evidence writer) |
| `GET` | `/api/v1/evidence/{id}` | admin |
| `GET` | `/api/v1/evidence` | admin; filters `execution_ref`, `trace_id`, `engine`+`engine_ref`, `work_item_id`, `repository`+`issue`, `repository`+`pr` |
| `GET` | `/api/v1/work-items/{id}/evidence` | `visibleWorkItem` / `canSeeWorkItem` |

The ingest body is the producer API of issue question 13:

```json
{
  "api_version":   "evidence.mctl.ai/v1alpha1",
  "id":            "ev-...",           // optional; verified, never trusted
  "content_hash":  "sha256:...",       // optional; verified, never trusted
  "envelope_b64":  "<base64 of the sealed envelope, verbatim>"
}
```

`envelope_b64` mirrors `snapshotBody.CanonicalB64` and is decoded with
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
shape `auditWorkItem` uses, naming `evidence_id`, `execution_ref` and the ingesting
principal.

### 9. Non-fatal producer failure with an observable gap (issue question 14)

mctl-api's half of this contract is to make the three outcomes distinguishable and cheap:

- **Store not configured** → `503 evidence_store_unavailable` on every evidence route. Never
  an empty list. This is the `requireUsageAdmin` reasoning verbatim: "the ledger is not
  configured" and "this DevLoop cost nothing" must never be the same answer.
- **Evidence genuinely absent** → `404 evidence_not_found` on `GET /api/v1/evidence/{id}`,
  and an empty `"evidence": []` on the list routes. An operator asking "did this governed run
  leave evidence?" gets an unambiguous no.
- **Evidence present** → `200`.

Because the gap is a plain absence keyed on `execution_ref`, it is derivable by an ordinary
left join from `work_item_executions` / `action_approval_requests` to `execution_evidence`;
no separate gap table is invented. `Store.MissingFor(ctx, refs []string) ([]string, error)`
exposes that join for an admin coverage read, and it is optional (task 9).

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

**D. Model (A) as a prerequisite: mint a `we_` for every governed run first.** Architecturally
the tidiest, and the design stays compatible with it. Dropped as a *prerequisite* because it
is an mctl-agents change mctl-api cannot make; it would block Tier B indefinitely behind
another repository's slice; and model (B)'s schema absorbs the (A) outcome with zero
migration if it later lands.

**E. Enforce `execution_ref LIKE 'we\_%'` and reject runtime references.** Would guarantee a
single identifier shape. Dropped because the issue explicitly forbids it: the storage layer
must not assume every governed run already has a `we_`, and rejecting implementer and
shepherd evidence would mean no evidence for exactly the runs that perform governed
mutations.

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

- *The Go `ev-` derivation does not match Tier A byte-for-byte.* Highest-severity risk: every
  stored identity would be wrong and the store would be silently useless. Mitigated by making
  golden-vector conformance (`internal/evidence/testdata/`, ported from mctl-agents) a
  blocking test, by keeping the derivation in two small functions keyed on `apiVersion`, and
  by shipping the writer principal disabled by default so no production rows are written
  before the vectors pass.
- *The ADR 018 amendment lands with different join semantics.* Mitigated by storing
  `execution_ref` verbatim and deriving `execution_ref_kind` from it: if the amendment renames
  or re-scopes the field, the stored string is still the exact thing the producer sealed, and
  reclassification is a projection rebuild.
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
