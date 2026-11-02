# Design: issue-896-feat-review-authoritative-attempt-proven

## Current state

Observed on the clone at `33b292e` (a merge of #904, after the `ede0b3b` cited
in the issue).

**Review contract (Tier A port).** `internal/reviewreceipts` is a pure port
of mctl-agents `orchestrator/review_receipts.py`:

- `types.go` defines `ReviewRequest`, with `AuthoringExecutionID`, `AuthoringAttemptIDs` and `AuthoringLineageRoot`. It also defines `ReviewReceipt`, with `ReviewerExecutionID`, `AttemptID` and `LineageRoot`.
- `gate.go` (`EvaluateReviewGate`) declares a receipt not independent when any of these holds:
  - the reviewer execution equals the authoring execution;
  - its `AttemptID` is in `AuthoringAttemptIDs`;
  - its `LineageRoot` equals `AuthoringLineageRoot`.
  A worker receipt missing any of the three facts is never independent.
- `identity.go` canonicalises with a Python-compatible `canonicalJSON` and seals with SHA-256.
- `parse.go` validates these fields only as bounded strings: any value of 256 characters or fewer is accepted.
- `executionIDRE` is `we_[0-9a-f]{16,64}|ex-[0-9a-f]{16}`.

**Durable review store (Tier B).** `internal/reviewstore`:

- `requests.go` `IngestRequest` stores the sealed document verbatim.
- It resolves only the tenant from evidence (`resolveTenant` lists `evidence.Filter{ExecutionID|RuntimeExecutionID, Limit:1}`).
- It distinguishes `ErrEvidenceUnavailable` (503) from `ErrAuthoringUnresolved` (422).
- `AuthoringAttemptIDs` and `AuthoringLineageRoot` are stored exactly as the creator wrote them.
- The store holds the evidence lookup through `SetEvidence(EvidenceLookup)` (`store.go`).

`internal/api/handlers_review_receipts.go`:

- `SubmitWorkerReview` always answers 501 `review_worker_ingest_disabled` and cites this issue.
- `writeReviewError` maps store sentinels to codes.

`docs/review-receipts.md` ("Disabled worker path") names this issue as one of two prerequisites.

**Executions.** `internal/workitems/store.go`:

- `work_item_executions` has columns `id`, `work_item_id`, `engine`, `engine_ref`, `attempt`, `resumed_from_execution_id`, `phase`, `started_at` and `ended_at`, and the constraints `UNIQUE(work_item_id, engine, engine_ref)` and `UNIQUE(work_item_id, attempt)`.
- `insertExecution` is the single insert point. It mints `ExecutionIDPrefix + uuid.NewString()`, which gives `we_` plus a hyphenated UUID.
- Its callers, all inside `withTx` holding the item lock:
  - `attachNewTx`, used by `AttachExecution` and by start-request fulfilment;
  - `resumeTx`, used by `Resume` and by resume-request fulfilment, which sets `resumed_from_execution_id` to the explicit `from` or to the last execution.
- `attempt` is a per-work-item sequence (`len(execs)+1`).
- `OpenExecutionsOfEngineRun` shows that one engine run can be attached to several work items, and that mctl-agents writes `engine_ref` as `<workflow_id>#<request_id>` for request-dispatched runs.
- `ResolveExecution` and `ExecutionByID` are existing by-id reads.

The routes `POST /work-items/{id}/executions` and `/resume` (`handlers_work_items.go`) need only the tenant `developer` role (`tenant_role.go`).

**Run tokens.**

- `internal/workitems/agent_run_tokens.go` `MintAgentRunToken` refuses unless `ExecutionID` names an existing, non-terminal `work_item_executions` row.
- `ResolveAgentRunToken` yields `auth.AgentRun{ExecutionID, WorkItemID, RunID}`.
- The exchange route (`handlers_agent_run_token_exchange.go`) takes the execution id from the Kubernetes pod binding (`k8s.AgentRunBinding.ExecutionID`), never from the body.
- So any run token for an execution is minted after that execution's row is committed.

**Evidence.**

- In `internal/evidence/types.go`, `Evidence` carries `ExecutionID` (`we_`), `RuntimeExecutionID` (`ex-`, derived by Tier A `execution_identity.seal()`) and `TraceID`.
- Those rows are written by the evidence-writer principal, usually after the work, so they cannot prove anything at execution start.

**Databases.** The work-items store opens `WORK_ITEMS_DB_URL`, else `AUDIT_DB_URL` (`cmd/api/main.go`). The review store uses `EVIDENCE_DB_URL`, else `AUDIT_DB_URL` (`docs/review-receipts.md`). They may be different databases, and `docs/work-context-contract.md` ("ID scheme") forbids cross-store foreign keys.

**Deployed state checked:**

- `mctl_get_service_config(team=admins, service=mctl-api)` answered "service not found". mctl-api is not a tenant catalogue service, so its deployed config could not be observed this way.
- `$MCTL_GITOPS_ROOT/services/` holds `admins`, `karabu`, `labs` and `namax66`. `services/admins/` has no `mctl-api` directory (it lists mctl-agents-worker*, mctl-design, mctl-docs, mctl-support, mctl-web and umami).
- So it was not observed whether `WORK_ITEMS_DB_URL` and `EVIDENCE_DB_URL` are set or share a database. The design does not depend on it, because the lookup goes through an interface and not through SQL joins. The gap is recorded under "Remaining unobserved facts" in requirements.md.

## Proposed solution

### 1. Contract `execution_attempt_v1` (new pure package `internal/executionprovenance`)

The package is pure, with no I/O, and has a purity test like `reviewreceipts/purity_test.go`.

```go
const ContractVersion = "execution_attempt_v1"
func EngineRun(engineRef string) string            // engine_ref up to the first '#'
func AttemptID(engine, engineRef string) string    // "at_" + hex(sha256(cj(["execution_attempt_v1","attempt",engine,EngineRun(engineRef)])))[:32]
func LineageRoot(rootExecutionID string) string    // "ln_" + hex(sha256(cj(["execution_attempt_v1","lineage",root])))[:32]
var AttemptIDRE, LineageRootRE                      // ^at_[0-9a-f]{32}$, ^ln_[0-9a-f]{32}$
```

`cj` is the same Python-compatible canonical JSON that `reviewreceipts` uses. Tier A reproduces it with `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=True)`.

Rationale:

- **Attempt is the engine run.** One physical Temporal or Argo run that is attached to two work items, or re-attached as a request-dispatched `#<request_id>` ref, is one attempt. This is the case that `reviewer_execution_id != authoring_execution_id` alone cannot catch.
- **Lineage is the root of the resume chain.** `resumeTx` always links a resume to its predecessor, so every execution of one work item shares a lineage. A reviewer inside the author's work item is therefore never independent.
- **Prefixes and the version string are part of the hash input**, so a future `execution_attempt_v2` can never collide with v1 values.

The contract is documented in a new `docs/execution-provenance.md`, and its golden vectors are in `internal/executionprovenance/testdata/execution_attempt_vectors.json`. Each vector lists inputs, the expected canonical bytes and the expected ids. It includes `#` suffixes, non-ASCII engine refs, and a hyphenated `we_` UUID root.

**Ownership.** This file in mctl-api is the canonical copy. mctl-agents vendors the exact bytes. Each repo's parity test recomputes every vector and also checks the SHA-256 of the whole file against a pinned digest, so a divergence in bytes or in any derived id fails the build. Changing the file is a `contract_version` change.

### 2. Server-side record (`internal/workitems`)

The new table is created idempotently in the existing schema block in `store.go`:

```sql
CREATE TABLE IF NOT EXISTS execution_provenance (
    execution_id          TEXT PRIMARY KEY REFERENCES work_item_executions (id) ON DELETE CASCADE,
    contract_version      TEXT NOT NULL,
    attempt_id            TEXT NOT NULL,
    lineage_root          TEXT NOT NULL,
    engine                TEXT NOT NULL,
    engine_run            TEXT NOT NULL,
    parent_execution_id   TEXT NOT NULL DEFAULT '',
    root_execution_id     TEXT NOT NULL,
    attached_by           TEXT NOT NULL,
    attached_by_principal TEXT NOT NULL DEFAULT '',
    recorded_at           TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS execution_provenance_lineage ON execution_provenance (lineage_root, attempt_id);
-- trigger execution_provenance_immutable(): RAISE on UPDATE (same pattern as review_rows_immutable()).
```

The foreign key stays inside the work-items database, so the cross-store rule is respected.

`insertExecution` gains the `Mutation` actor and inserts the provenance row in the same `tx`, right after the execution row:

- It computes `root_execution_id` as follows. With `from == ""` the root is the new execution's own id. Otherwise it reads the parent's stored provenance row and copies its `root_execution_id`. A parent without provenance (created before this change) falls back to walking `work_item_executions.resumed_from_execution_id` to its root. This walk uses stored server rows, never caller input.
- Any failure returns an error, so the whole transaction rolls back.

Ordering guarantee: provenance commits atomically with the execution row, and `MintAgentRunToken` and the exchange both require that row to exist. So the facts are readable before any run token for the execution exists, and therefore before a reviewer could submit anything. No new refusal is needed for "not yet written", but the read side still distinguishes absent from unavailable.

Read API:

```go
type Provenance struct{ ExecutionID, ContractVersion, AttemptID, LineageRoot, Engine, EngineRun,
    ParentExecutionID, RootExecutionID, AttachedBy, AttachedByPrincipal string; RecordedAt time.Time }
var ErrProvenanceAbsent = errors.New("execution provenance absent")
func (s *Store) ExecutionProvenance(ctx, executionID string) (*Provenance, error)       // ErrProvenanceAbsent | wrapped read error
func (s *Store) LineageAttempts(ctx, lineageRoot string, attemptIDs []string) (map[string]bool, error)
```

On read the store re-validates `contract_version` and the id regexes. A row that fails is reported as an error (unavailable), never as absent.

### 3. Tier B wiring (`internal/reviewstore`)

- New interface `ProvenanceLookup { ExecutionProvenance; LineageAttempts }`, plus `SetProvenance(ProvenanceLookup)`, mirroring `SetEvidence`. It is wired in `cmd/api/main.go` when both stores exist. If it is not wired, every check answers `ErrProvenanceUnavailable`.
- New sentinels: `ErrAuthoringUnproven` (422 `review_authoring_unproven`), `ErrExecutionUnproven` (403 `review_execution_unproven`, matching the code reserved by #895) and `ErrProvenanceUnavailable` (503 `review_provenance_unavailable`). They are added to the `writeReviewError` table in `handlers_review_receipts.go`.
- `IngestRequest` calls `checkAuthoring(ctx, req)` before the insert, under the rules in requirements.md:
  - Worker mode: all three facts are required and must match the record.
  - Manual mode: the facts are checked when non-empty.
  - An `ex-` authoring id with attempt facts is unproven.
  The sealed document is never rewritten, only accepted or refused.
- New `ProveReviewer(ctx, executionID) (attemptID, lineageRoot string, err error)` returns only stored values. It is unused by routes in this change. #895 calls it with the run token's `ExecutionID`, and the stored values replace any caller-supplied ones.

### 4. REST read

`GET /api/v1/executions/{execution_id}/provenance` returns 200 with the record, 404 `execution_provenance_absent`, or 503 `execution_provenance_unavailable`.

Callers allowed:

- a platform admin (`requireReviewAdmin`-style);
- an agent run token whose `ExecutionID()` equals the path id, so that a Tier A worker can read and echo its own facts.

It lives in the admin read group of `router.go`, next to `/review-gate`. There are no new MCP tools, so the `server_test.go` tool count is unchanged.

### 5. Documentation

- New `docs/execution-provenance.md` covering the contract, derivation, vectors, guarantees and codes.
- Update `docs/review-receipts.md`: authoring verification, new codes, and the "Disabled worker path" section, which lists every hard prerequisite of worker ingest: this provenance change, the `we_` id regex amendment in both tiers, the vendored vector parity in mctl-agents, and #895 (run-token binding, nonce consumption and the attacher eligibility check). It must not say that only the run-token binding remains.
- Update `docs/work-context-contract.md`, adding `execution_provenance` to the resource model.

## Alternatives

1. **Use `WorkItemExecution.Attempt` or the `we_` id as `attempt_id`.** Dropped. `Attempt` is a per-item counter, so values collide across items, and `1` means nothing globally. The `we_` id duplicates `reviewer_execution_id`, so it adds no check and misses the same engine run attached under two work items.
2. **Derive lineage from evidence `trace_id`.** Dropped. Evidence is written by the evidence-writer principal, usually after the run. It may not exist when a receipt arrives, and its `trace_id` is supplied by the run's telemetry, so it is not server-authoritative at start.
3. **Compute on read, with no stored table.** Dropped. The issue requires an immutable written record. Recompute-on-read would silently change the answer if a future contract version or a cascading delete altered the chain, and it gives no `recorded_at` or attacher audit trail.
4. **Write the record at token exchange instead of execution insert.** Dropped. Executions without a run token (Temporal-driven, human-attached) would have no record, and the exchange runs inside the execution's own pod flow, which is closer to "written by the execution itself".

## Platform impact

- **Migration.** Additive `CREATE TABLE IF NOT EXISTS`, an index and a trigger in the existing idempotent work-items schema. No backfill. Executions created before deployment answer `execution_provenance_absent`; a worker review request naming one is refused.
- **Backward compatibility.**
  - Manual review requests with empty attempt and lineage fields are unaffected.
  - Requests that carried creator-asserted values (worker or manual) are now refused with 422 `review_authoring_unproven` unless the values match the record. This is intended ("no fallback to caller-supplied ids"), but mctl-agents' request creator must compute the facts from the record, for example through the REST read, before this deploys.
  - Worker requests cannot be parsed today anyway, because of the `we_` regex mismatch. Fixing it is a hard prerequisite of worker ingest (requirements.md, "Worker ingest prerequisites") and stays outside this change.
- **Resources.** One extra small insert per execution, plus one PK read during request ingest. Negligible.
- **Risks and mitigations.**
  - Provenance insert failure blocks execution attach. This is intentional and fail closed; it is covered by a test and visible as a 500 on attach.
  - Tier A and Tier B could diverge on the derivation. Mitigation: one canonical vector file in mctl-api, vendored byte for byte by mctl-agents, with a parity test in both repos that also pins the file digest.
  - The attacher chooses `engine`/`engine_ref`. Mitigation: the attaching principal is recorded, and #895 MUST verify that the reviewer execution was attached by an eligible platform-authorized principal or path before it enables worker ingest. Provenance alone never establishes reviewer independence. The run token can only follow the record.
  - The cross-database deployment layout is unknown. Mitigation: the lookup goes through an interface with no SQL join across stores.
