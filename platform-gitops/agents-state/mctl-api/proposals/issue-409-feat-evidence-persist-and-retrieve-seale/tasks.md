# Tasks: issue-409-feat-evidence-persist-and-retrieve-seale

Tasks 1-9 are mctl-api and are not blocked by anything. Task 0 is an mctl-agents
prerequisite for the **producer** slice only; it does not gate any task below.

- [ ] 0. (mctl-agents, prerequisite for the producer slice — NOT for this one) Amend ADR 018
  so `ExecutionJoin.execution_id` is an explicitly discriminated execution reference: the
  canonical work execution (`we_`) or the runtime/control execution (`ex-`, ADR 011), with
  one stable primary retrieval identity and no second execution authority. — DoD: the ADR
  amendment is merged in mctl-agents and names the discriminator; `mctl-agents#199` records
  that model (B) was chosen over model (A); the producer slice can start. mctl-api storage
  requires no change either way, because `execution_ref` is stored verbatim.

- [ ] 1. Create `internal/evidence/types.go`: `EvidenceIDPrefix = "ev-"`, `APIVersionV1Alpha1
  = "evidence.mctl.ai/v1alpha1"`, `SupportedAPIVersions`, `MaxEvidenceBytes = 256 << 10`,
  `HashCanonical`, `EvidenceIDFor`, `ExecutionRefKind` (prefix-derived: `we_` → `work`,
  `ex-` → `runtime`, anything else → error), the `Evidence` / `EvidenceRef` structs (canonical
  bytes serialised as `envelope_b64`, mirroring `workitems.ContextSnapshot.Canonical`), the
  `IngestInput` struct and the sentinel errors `ErrEvidenceNotFound`,
  `ErrEvidenceDivergence`, `ErrUnsupportedAPIVersion`, `ErrEvidenceHashMismatch`,
  `ErrInvalidExecutionRef`, `ErrEvidenceTooLarge`. — DoD: `go build ./...` and `go vet ./...`
  pass; `IngestInput.validate()` rejects an unsupported `apiVersion`, an oversize envelope, a
  non-`we_`/`ex-` execution reference, and any client-supplied `id`/`content_hash` that does
  not equal the recomputed value; unit tests cover each rejection.

- [ ] 2. Port Tier A golden vectors into `internal/evidence/testdata/` from mctl-agents
  (`orchestrator/execution_evidence.py`, ADR 018) — at minimum three sealed envelopes with
  their expected `content_hash` and `ev-` id, one with a `we_` join and one with an `ex-`
  join (depends on 1). — DoD: a table-driven test proves `HashCanonical` and `EvidenceIDFor`
  reproduce every vector byte-for-byte; if they do not, only these two functions are changed
  until they do. This test is blocking: nothing ships without it green.

- [ ] 3. Create `internal/evidence/store.go`: the two-table schema from `design.md`
  (`execution_evidence`, `execution_evidence_refs`), the `execution_evidence_immutable()`
  trigger function and its `BEFORE UPDATE` trigger in the `DO $$ ... pg_trigger` guard shape
  used by `work_item_context_snapshots_no_update`, all eight indexes, `NewStore`, `Close`,
  `scanEvidence` (recomputes and verifies the hash on every read, mirroring `scanSnapshot`)
  (depends on 1). — DoD: `NewStore` applies the schema idempotently against a real Postgres;
  a test proves an `UPDATE` of any column raises; a test proves `DELETE` succeeds and
  cascades to `execution_evidence_refs`; a test proves the
  `execution_evidence_refs_work_prefix` check rejects an `ex-` value in `work_execution_id`.

- [ ] 4. Implement `Store.Ingest` as compare-then-insert inside a transaction under an
  advisory lock keyed on the `ev-` id, returning `(*Evidence, created bool, error)` like
  `workitems.SealSnapshot` (depends on 3). — DoD: new envelope → `created=true`; byte-identical
  replay with identical wrapper claims → `created=false` and the stored row; same id with
  different bytes → `ErrEvidenceDivergence` and nothing written; same id and bytes with a
  different `execution_ref`, `execution_ref_kind`, `api_version` or `produced_by` →
  `ErrEvidenceDivergence`; concurrent identical ingests produce exactly one row.

- [ ] 5. Implement `internal/evidence/derive.go`: best-effort projection of
  `work_execution_id`, `work_item_id`, `tenant`, `engine`, `engine_ref`, `repository`,
  `issue_number`, `pr_number` from `work_item_executions` and `work_items.external_key`,
  written in the same transaction as the evidence insert, plus `Store.RebuildRefs(ctx, ids)`
  (depends on 4). — DoD: a `we_` reference that resolves populates `engine` / `engine_ref` /
  `work_item_id` / `tenant`; an `external_key` of the form `owner/repo#N` yields
  `repository` and the correct one of `issue_number` / `pr_number`; an unparseable
  `external_key` leaves all three empty; an `ex-` reference stores the evidence with an
  entirely empty projection and returns no error; `RebuildRefs` is idempotent and changes no
  `execution_evidence` row.

- [ ] 6. Implement the read paths: `Store.Get(id)`, `Store.List(ctx, Filter)` covering
  `execution_ref`, `trace_id`, `work_item_id`, `engine`+`engine_ref`, `repository`+`issue`,
  `repository`+`pr`, and `Store.ByWorkItem(ctx, workItemID)`, all returning a list-shaped
  result with a bounded default and maximum limit in the style of `MaxApprovalList` (depends
  on 5). — DoD: each filter is served by its intended index (verified with `EXPLAIN` in an
  integration test or, at minimum, asserted by an index-name test); a stored row whose bytes
  no longer hash to `content_hash` is refused rather than served; an unknown id returns
  `ErrEvidenceNotFound`.

- [ ] 7. Add the evidence-writer principal in `internal/auth/oidc.go`:
  `EvidenceWriterUserID = "service:mctl-agents-evidence"`,
  `PermissionEvidenceWrite = "evidence:write"`, `NewEvidenceWriterUser()`,
  `IsEvidenceWriter()`, `HasPermission` handling for the new permission, and an
  `MCTL_EVIDENCE_WRITER_TOKEN` loader that refuses a token that is too short or equal to
  `MCTL_AGENT_SERVICE_TOKEN`, any surface token, or `MCTL_USAGE_WRITER_TOKEN` — modelled
  one-for-one on the usage writer. — DoD: tests mirroring `internal/auth/auth_test.go`'s
  usage-writer cases prove the principal is not an admin, not a service, holds no groups,
  holds exactly `evidence:write`, and is disabled with an `slog.Error` on each collision.

- [ ] 8. Create `internal/api/handlers_evidence.go` and wire the routes in
  `internal/api/router.go`: `POST /api/v1/evidence/records`, `GET /api/v1/evidence/{id}`,
  `GET /api/v1/evidence`, `GET /api/v1/work-items/{id}/evidence`; add `Evidence
  *evidence.Store` to `api.Options`; add `evidenceWriterGate` to the middleware chain next to
  `usageWriterGate`; put ingest in its own 120/min rate-limit group and the reads outside the
  20/min write group; map every sentinel error to one status and typed code
  (`evidence_unsupported_api_version`, `evidence_hash_mismatch`, `evidence_divergence`,
  `evidence_execution_ref_invalid`, `evidence_too_large`, `evidence_not_found`,
  `evidence_store_unavailable`); run `internal/secretscan` over the canonical bytes at ingest;
  emit an audit entry on every accepted ingest (depends on 6, 7). — DoD: `201` on create,
  `200` on replay via `createdStatus`, `409` on divergence, `403` for a caller without
  `evidence:write`, `403` for the evidence writer on any other route, `404` (not `403`) for a
  work item the caller cannot see, `503` with `evidence_store_unavailable` when
  `Options.Evidence` is nil; `envelope_b64` round-trips to the exact bytes that were sent.

- [ ] 9. (optional, small) Add `Store.MissingFor(ctx, refs []string) ([]string, error)` and an
  admin read that reports which of a set of execution references have no evidence, so a
  producer gap is queryable rather than only inferable (depends on 6). — DoD: given three
  references of which one has evidence, the call returns exactly the other two; the route is
  admin-only and outside the write budget.

- [ ] 10. Wire the store in `cmd/api/main.go` behind `EVIDENCE_DB_URL` with an `AUDIT_DB_URL`
  fallback, an `EVIDENCE_DISABLED` kill switch and `EVIDENCE_RETENTION_DAYS` (default `0` =
  retain indefinitely), following the `WORK_ITEMS_DB_URL` / `WORK_ITEMS_DISABLED` block
  exactly; add the new env vars to `.env.example` and to `helm/` (depends on 8). — DoD: with
  no env vars set the API starts unchanged and the evidence routes answer `503`; with
  `EVIDENCE_DISABLED` set the store stays nil and an `slog.Warn` explains why; an init failure
  logs and degrades to `503` rather than failing startup.

- [ ] 11. Document and publish the surface: add `docs/execution-evidence.md` (the contract
  boundary, the `we_` / `ex-` recommendation and its rationale, the retention boundary, the
  explicit statement that `execution_evidence_refs` is non-authoritative and that evidence
  deliberately has no FK to `work_items`), and add the four paths and their schemas to
  `internal/openapi/openapi.yaml` next to the existing
  `/api/v1/work-items/{id}/snapshots` entries (depends on 8). — DoD:
  `internal/openapi/embed_test.go` still parses the spec; the doc states plainly that
  evidence is never written to GitOps and that `mctl-agents#483` / `_evidence/` is superseded.

## Tests

- [ ] T1. Golden-vector conformance (task 2): `HashCanonical` and `EvidenceIDFor` reproduce
  every Tier A vector exactly, including at least one `we_`-joined and one `ex-`-joined
  envelope. Blocking.
- [ ] T2. Identity discipline: a client-supplied `id` or `content_hash` that disagrees with
  the recomputation is `400 evidence_hash_mismatch`, and the mismatching pair is echoed.
- [ ] T3. Unsupported `apiVersion` is `400 evidence_unsupported_api_version` and names the
  supported set; nothing is written.
- [ ] T4. Idempotent replay: the same envelope POSTed twice yields `201` then `200`, the same
  `ev-` id, and exactly one row.
- [ ] T5. Divergence: the same `ev-` id with different canonical bytes, and the same bytes
  with different wrapper claims, each yield `409 evidence_divergence` with the stored row
  unchanged.
- [ ] T6. Immutability: a direct `UPDATE` of any `execution_evidence` column raises at the
  database level; `DELETE` succeeds and cascades to `execution_evidence_refs`.
- [ ] T7. Read verification: a row whose stored bytes are tampered with out-of-band is
  refused on read rather than served under its old `content_hash`.
- [ ] T8. The `we_` / `ex-` split: an `ex-` reference is stored with
  `execution_ref_kind='runtime'`, an empty projection and no error; the database rejects any
  attempt to place an `ex-` value in `work_execution_id`; a `we_` reference resolves its
  engine, engine ref, work item and tenant.
- [ ] T9. Retrieval: every documented filter returns the expected rows and an identically
  shaped response regardless of which filter was used; partial indexes contain no
  unresolved rows.
- [ ] T10. Authorization: a non-admin without `evidence:write` gets `403` on ingest; the
  evidence writer gets `403` on every route other than `POST /api/v1/evidence/records`; a
  tenant member reads evidence for a work item they can see and gets `404` for one they
  cannot; evidence with no resolved work item is admin-only.
- [ ] T11. Availability semantics: a nil store gives `503 evidence_store_unavailable` on all
  four routes, and an absent record gives `404 evidence_not_found` — the two are never
  conflated, and an empty list is never returned in place of the `503`.
- [ ] T12. Content discipline: an envelope over `MaxEvidenceBytes` is `400
  evidence_too_large` and nothing is stored; canonical bytes matching a `secretscan` pattern
  are rejected, not redacted.
- [ ] T13. Concurrency: N concurrent identical ingests produce exactly one row and N
  successful responses.
- [ ] T14. Projection rebuild: `RebuildRefs` is idempotent, corrects a stale
  `repository`/`pr_number`, and leaves every `execution_evidence` row byte-identical.
- [ ] T15. Regression: `go test ./...` passes, `golangci-lint` is clean, and
  `internal/mcp/server_test.go`'s tool-count expectation is unchanged (no MCP tool is added).

## Rollback

The feature is additive and gated at three independent levels, so rollback is graded rather
than all-or-nothing.

1. **Stop ingest without touching data.** Unset `MCTL_EVIDENCE_WRITER_TOKEN`. The producer
   principal disappears, ingest returns `403` for it, admins retain access, and every stored
   record stays readable. This is the first move for a producer misbehaving.
2. **Disable the whole surface.** Set `EVIDENCE_DISABLED=1` (or unset `EVIDENCE_DB_URL` when
   it is not falling back to `AUDIT_DB_URL`). The store stays nil and all four routes answer
   `503 evidence_store_unavailable` — never an empty list, so no operator misreads the outage
   as "no evidence exists". Nothing else in the API is affected, exactly as
   `WORK_ITEMS_DISABLED` behaves today.
3. **Revert the code.** Deploy the previous image. The two new tables and the trigger remain
   but are unreferenced; no existing table, column, index or constraint was altered, so the
   prior revision runs unchanged against the same database.
4. **Remove the schema (last resort, destructive).** `DROP TABLE execution_evidence_refs;
   DROP TABLE execution_evidence; DROP FUNCTION execution_evidence_immutable();` Only after
   step 3, and only with an explicit decision to discard sealed evidence — it is by design
   not reconstructible from anywhere else, and specifically not from GitOps.

If the Tier A golden vectors (task 2) fail, nothing is deployed at all: the writer principal
ships disabled by default, so no production row can be written under a wrong `ev-` identity
before conformance is proven.
