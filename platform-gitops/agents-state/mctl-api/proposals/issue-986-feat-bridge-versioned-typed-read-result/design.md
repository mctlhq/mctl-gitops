# Design: issue-986-feat-bridge-versioned-typed-read-result

## Amendment 2026-11-09 (c), round 5 of the AMEND PR

Fold-in of the round-4 findings; simplified, no new mechanism beyond the one named per row. Where this section and older text disagree, this section wins.

| Finding | Change here |
|---|---|
| F1 (undetectable idempotency) | §4, task 3, T16: `pg_locks` on the open transaction, not `log_statement`; mutation step |
| F2 (over-cap code) | §5 step 2, task 6, T7: the handler keeps 400 `invalid_document` as the merged #1059 contract says; 413 only for the in-Store cap |
| F3 (read-level consumer) | §4a: `bridge.ReadSchemaLevel` is owned here; the `NewRuntimeStore` leg moves to #985 T26; T4c split |

## Amendment 2026-11-09 (c), round 4 of the AMEND PR

Resolves the round-3 findings R3-1, R3-2 and R3-3 and the cross-slice findings X-3 (one owner of the read DDL) and N3 (the Go JCS implementation). Where this section and older text disagree, this section wins.

| Finding | Change here |
|---|---|
| R3-1 (`irv_` has no storage; the read-command projection cannot emit `install_revision_ref`) | §4: new column `install_revision_ref TEXT` on `bridge_commands`, NULL for write kinds, and `bridge_commands_read_shape_chk` requires it NOT NULL and matching `^irv_[A-Za-z0-9]{16,40}$` for read kinds. `EnqueueRead` writes `ReadRequest.InstallRevisionRef` there. For read kinds `projection()` reads it (through the read-path extras query of §4a) and emits it together with the other fields the #1059 `read-command.schema.json` requires (`issuer`, `audience`, `nonce`, `issued_at`, `expires_at`, `ttl_seconds`), taken from the same sources as the v1alpha1 projection uses for them. New test T4b: the projected read command validates against the vendored `read-command.schema.json` |
| R3-2 (`payload_too_large` unreachable; sentinels not in `codedErrors`) | §5 step 2: the `bridgeMaxBody` cap belongs to the HTTP handler. Round 5 (F2): the handler keeps today's answer, 400 `invalid_document`, for `*http.MaxBytesError`, which is exactly the merged #1059 contract ("over-cap is `invalid_document` at the mctl-api route and `payload_too_large` in the reference validator"); this slice adds no 413 branch. The Store owns the `JCS(payload)` over 12288 bytes check, and returns `ErrPayloadTooLarge`. `ErrPayloadTooLarge`, `ErrReadUnavailable` and `ErrReadNotAuthorized` are registered in `codedErrors` (`payload_too_large`, `read_unavailable`, `read_not_authorized`) with explicit `bridgeStatus` cases (413, 503, 403), so none can surface as 500 `bridge_internal`. These are bridge-provider-route codes and in-process sentinels, local to this slice; they are not part of the #957 §4.1 Glovo set and never reach the Glovo wire (#957 maps the sentinels). Tasks 6 and T7 |
| R3-3 (new columns in the shared scan path break v1alpha1 on a database that never ran the migrator) | New §4a. `cmdCols`/`scanCmd` are unchanged, so every v1alpha1 query still works on a database built only from today's `bridgeSchema`. The three new columns (`wire_version`, `read_request_id`, `install_revision_ref`) are read only in read-kind paths, through a separate extras query; the wire version of a write kind is v1alpha1 by definition. A read level (table `bridge_read_schema_version`) is created by `ApplyReadSchemaTx`; `EnqueueRead` and `ReadClient.Read` refuse below it (`ErrReadUnavailable`, #957 `not_ready`), and `bridge.CheckReadLevel` is called by #985 `NewRuntimeStore`. Test: v1alpha1 `Claim`, `SubmitResult`, `Cancel` and `permitTx` pass on a database built only from today's `bridgeSchema`, on one migrated by `ApplyReadSchemaTx`, and on one migrated by an older `ApplySchema` without the read level |
| X-3 (read DDL claimed by #985 and #986) | One owner: this slice. `bridge.ApplyReadSchemaTx(ctx, tx pgx.Tx, runtimeRole string) error` creates all read objects of §4 and the grants on them. #985 `bridge.ApplySchema` calls it inside its own transaction and depends on task 3 here. It is tested standalone on a database built from today's `bridgeSchema` (it needs no #985 object: its version table is its own). Merge order #1059, #959, #988, #960, #961, #989, #986, #985 (#957 §6d.1, round 5); no cycle |
| N3 (nobody owns the Go JCS implementation) | #988 owns `internal/jcs` (`Canonicalize`, `Precheck`). This slice imports it: `internal/bridge/rawcheck.go` is a thin wrapper over `jcs.Precheck`, and `JCS(payload)` is `jcs.Canonicalize`. The #1059 basket files (`approval-basket.schema.json`, `basket-fingerprint.json`, `must-reject.json`, `pattern-parity.json`) are vendored by #988 in `internal/glovo/basket/contract/`; this slice vendors only the read-command and read-result schemas and fixtures, and a test asserts that the `approval-basket.schema.json` it needs by `$ref` is byte-identical (sha256) to #988's copy |
| Class sweep (#959 F1) | `FetchReadResult` expiry compares use `clock_timestamp()`; the result `expires_at` is set from `clock_timestamp()` |

## Amendment 2026-11-09 (c), round 2 of the AMEND PR

Re-review of the AMEND PR head `dc1fe6e5`; code references re-checked at mctl-api
`ceac9ed`. Cross-slice seams are owned by mctl-api#957 design §6d (roles and grants,
interfaces, approval-basket source) and §4 (refusal codes). Where this section and older
text disagree, this section wins; the older passages are edited.

| Finding | Change |
|---|---|
| F1 (NULL refs on read rows break every scanner and the expiry sweep) | No NOT NULL is relaxed. Read rows store `''` in `workflow_id`, `execution_id`, `work_item_id` and `order_ref` (`run_id` already defaults to `''`, `internal/bridge/store.go:74`), so `cmdCols`/`scanCmd` (`store.go:284-298`), `claimTx`, `lockOwned`, `Cancel` and `permitTx` keep scanning plain strings. The kind-conditional CHECK requires `''` for read kinds and non-empty values otherwise. `expireTx` (`store.go:868-910`) returns `operation_kind` and skips the `bridge_signal_outbox` insert (`:904`) for read kinds; `permitTx` refuses a read kind. T5b, T7d |
| F3 (#957 request lacks owner id and scopes) | #957 design §5 now passes the full `ReadRequest` below. `FetchReadResult` is the **authoritative** binding check for reads, not defence in depth; T10b crosses principals through the #957 adapter |
| P3 F2 (checker bound to a #959 API that does not exist) | `ConnectionChecker` is bound to #959 `LiveConnection(ctx, glovo.Owner)` (#957 §6d.4), which fences `expires_at`; its `no_connection`, revoked and expired answers and a different revision map to the §5 sentinels |
| X-5 (`irv_` has no owner) | `irv_` is a #988 `glovo.join_refs` kind (`install_revision`), minted by #957 read routes through `MintJoinRefTx` (#957 §2a). Round 3 (X-2): it is wire-only. `ReadRequest` carries two fields, the decimal `InstallRevision` (stored on `bridge_read_results.install_revision` and compared with #959 `LiveConnection`) and `InstallRevisionRef` (the `irv_`, written only to the command's `install_revision_ref`); OPEN-986-3 is closed |
| Round 3, N1 (read rows collide on `UNIQUE (execution_id, sequence)`) | §4: `bridge_commands_sequence` becomes a partial unique index that excludes the read kinds; `claimTx` ordering is unchanged and, because every read has `sequence` 1, never serializes reads (T5c) |
| Round 3, N3 (MUST 10 has no owner) | Assigned to mctl-api#957 (design §5a, `glovo.join_read_refs`); this slice is a transport and validates params only against the #1059 schema. T10b is rewritten |
| #957 F2, X-4 (DDL by the runtime role) | The §4 changes are part of `bridge.ApplySchema` (#985) under the migration role, not of a runtime `bridgeSchema` run; grants per #957 §6d.1 |
| X-2 (read TTL vs preview) | Prepare no longer re-reads: #957 stores the approval-basket bytes with the preview. `MCTL_BRIDGE_READ_RESULT_TTL` defaults to 300 s, clamped 1..300 s, and a read command's TTL is at most 300 s (#1059 `ttl_seconds`) |
| P3 F5 (codes contradict the schema) | §5 lists submission checks in pipeline order with one code each; a non-`none` effect and a read payload on a non-read kind fail the schema first and are `invalid_document`; `ErrPayloadTooLarge` is added to `errors.go` |
| P3 F6 (stale #1059 names) | Vendored set uses the #1059 file names (`read-command.schema.json`, `read-result.schema.json`, `approval-basket.schema.json`, fixtures, vectors); the column is `operation_kind` |
| P3 F7 (T7b impossible) | T7b is scoped to `bridge_commands.result`, `bridge_read_results`, transitions, logs and audit; `bridge_commands.lease_token` stores the lease token by design (`store.go:97`) |
| P3 F8 (unspecified row details) | `request_id` equality is checked at submission; read rows use `intent_hash` = the `payload_digest` of the command params, `operation_key` = `"read:"+rdq_`, `sequence` = 1, `approval_ref` = `''`; a non-`succeeded` outcome maps to `ErrReadUnavailable` |
| P3 F9 (weak negative tests, no lock order) | T15 diffs the full route, MCP tool and Temporal registration lists; T16 uses the statement log. Reads take only L5 of #957 §6b on `bridge_commands`, and `bridge_read_results` is never locked together with L1-L4 |

## Amendment 2026-11-09 (b)

Resolves the independent review of digest
`sha256:f8935e57eb1164201307d742878624c2562817d76b99e15c75cec57633d379ab` (mctl-api#986,
2 P1, 5 P2, 6 P3) and records owner decisions B and A of 2026-11-09 (b). Code references
were re-checked at mctl-api `origin/main` `ceac9ed`. This proposal was rewritten; no
older passage survives that contradicts this section.

**Owner decision B.** The read contract moves to **mctlhq/mctl-agents#1059** (bridge
`v1alpha2`: canonical schemas, golden fixtures, RFC 8785 digest vectors), which gets its
own proposal, review and approval and lands **before** this slice is implemented. This
issue becomes the mctl-api **store/serve slice**: ReadBridge in process, no public
retrieval route, reads are history, preview and basket only (prepare stays a #957
write), no Temporal signal for reads, raw bytes stored and re-verified on fetch, binding,
TTL, revocation and `glovo:read` re-checked in process for the #957 handlers, idempotent
schema changes, and the connection check wired to #957's named mechanism. `v1alpha1`
stays unchanged.

**Owner decision A.** The connection store (#959) is in the same physical database as
the bridge, so the connection check is a live read with no cross-database window.

| Review finding | Fix in this proposal |
|---|---|
| P1-1 nobody starts a read; the v1alpha2 command keeps `order_ref`/`we_`/`wi_`/`workflow_id`; reads write a signal-outbox row | The in-process `bridge.ReadClient` (§3) enqueues read commands and waits on the store with a deadline. Read commands carry the #1059 read binding set (no order, `we_`, `wi_` or workflow fields); a kind-conditional CHECK requires `''` there for read kinds (amended (c): no NOT NULL is relaxed). Read kinds write no `bridge_signal_outbox` row and store `''` as `workflow_id` (§4, amended (c)). Task 4 implements the `ReadClient`; #957 A12 wires it behind its `ReadBridge` interface |
| P1-2 public `GET /api/v1/glovo/read-results/{ref}` and a `glovoAudienceRoutes` entry bypass #957's checks | Dropped. No route and no `glovoAudienceRoutes` change. `Store.FetchReadResult` is in process only and is called by the `ReadClient` on behalf of #957's handlers after their own checks; it re-checks binding, TTL, revocation and `glovo:read` as defence in depth (§5). T15 asserts no route is added |
| P2-1 `read_prepare` contradicts the merged contract | Dropped. Read kinds are `read_history`, `read_preview`, `read_basket` (names from #1059). Prepare is the #957 `/orders:prepare` write, which consumes the preview/basket read; open question 3 is closed by #957 D5 |
| P2-2 digest over Go struct order; JSONB re-orders keys | The digest is sha256 over the RFC 8785 (JCS) canonical form, defined by #1059 with vendored test vectors. mctl-api stores the canonical bytes as `BYTEA`, recomputes `sha256(stored) == data_digest` on every fetch and fails closed on a mismatch. Round-trip test T9 |
| P2-3 contract-first split half there; fixtures local | The contract slice is mctl-agents#1059. This slice vendors its schemas, fixtures and digest vectors by sha256 (task 1); T2/T3 use the vendored fixtures only. The provider-side vendoring is an extension of mctl-telegram#1262 (OPEN-986-2) |
| P2-4 `ADD CONSTRAINT bridge_commands_read_wire_chk` fails on the second boot; drop/re-add takes ACCESS EXCLUSIVE every boot | Every schema change is guarded by a catalog check in one `DO` block (`pg_constraint`, `pg_attribute`), constraints are added `NOT VALID` and validated once, and nothing is dropped and re-added on a normal boot (§4). Task 3 DoD and T16 apply the schema twice and on a populated v1alpha1 database |
| P2-5 connection checker undecided | `ConnectionChecker` is the #959 live connection read on the same database, `LiveConnection(ctx, glovo.Owner)` (amended (c), #957 §6d.4). The fail-closed default stays; task 5 wires it |
| P3 `SubmitResult` hard-refuses non-v1alpha1 (`store.go:745`), `validate()` (`store.go:229-256`), `projection()` (`store.go:334`) | Tasks 2-4 name all three |
| P3 checker-unavailable sentinel falls through `bridgeStatus` (`handlers_bridge.go:95-113`) | No HTTP route uses it any more; the sentinel stays in process and #957 maps it. `bridgeStatus` gains an explicit case anyway so a future caller cannot fall through to 409 |
| P3 `provenance: "synthetic"` is self-declared | Bounded field shapes come from #1059 (item codes in the `FAKE-n` catalogue pattern, no name/address/phone/person fields, coarse timestamps); mctl-api validates against the vendored schema |
| P3 rows kept forever after the data is erased | Hard delete 24 h after `expires_at` in the same sweep |
| P3 digest in the query string | Gone with the route |
| P3 rollback order | Cancel or expire open read-kind commands **before** the code revert |
| Alignment with the #1059 review (mctl-agents#1059 comment 6745621467), same PR | The cap is the transport's: body ≤ 16384 B (`bridgeMaxBody`), `JCS(payload)` ≤ 12288 B (§5). The result carries no binding refs: bindings come only from the stored command row, and a result that adds any is invalid. Raw-bytes pre-check before parsing (§5 step 3). `lease_token` is never persisted. Read kinds are leased only to v1alpha2-capable providers, and the claim response is versioned (§2). The approval-basket fingerprint is #1059's, computed by #957/#988, not here |

Skipped P3s: none.

## Current state

- `internal/bridge/schema.go` embeds the v1alpha1 `command.schema.json`,
  `result.schema.json` and `PROVENANCE`, vendored from mctl-agents#1045 and pinned by
  `TestVendoredSchemasMatchProvenance`. `SchemaVersion = "bridge.mctl.ai/v1alpha1"`.
- The v1alpha1 command requires `execution_id`, `work_item_id` and `order_ref`;
  `validate()` checks them and `workflow_id` (`store.go:229-256`); `bridge_commands.
  workflow_id` is `NOT NULL` (`store.go:73`). `kind` is closed to `quote`,
  `place_order_fake`, `cancel_order_fake`, `read_status`. The result has only an
  optional `result_ref`.
- `SubmitResult` refuses any `schema_version` other than v1alpha1 (`store.go:745`).
  `submitTx` writes a `bridge_signal_outbox` row to the command's `workflow_id` for every
  completed command (`store.go:800-801`). `projection()` hard-codes `SchemaVersion`
  (`store.go:334`).
- `bridgeSchema` is applied at every start (`store.go:66-67`, `:374`).
- `IssueWritePermit` returns `ErrNotMutating` for non-mutating kinds (`permit.go:98`).
- `bridgeStatus` maps bridge codes (`handlers_bridge.go:95-113`);
  `bridge_unavailable` is written only by `bridgeReady` (`:137`). `bridgeMaxBody` is
  16 KiB (`:42`).
- `glovoAudienceRoutes` is empty (`glovo_audience_gate.go:29-32`); #961 owns the facade
  entries.
- #957 (merged design, ae9101d6) makes `ReadBridge` an in-process interface,
  `Read(ctx, GlovoReadRequest) (GlovoReadResult, error)`, kinds `history|preview|basket`,
  whose transport implementation is this slice (#957 design §5).

## Proposed solution

### 1. Contract (vendored from mctl-agents#1059)
- Task 1 vendors, byte for byte, the #1059 v1alpha2 `read-command.schema.json`,
  `read-result.schema.json` (the per-kind shapes are definitions inside it), the valid and
  invalid fixtures and the RFC 8785 digest vectors into `internal/bridge/schema/v1alpha2/`.
  The basket files (`approval-basket.schema.json`, the basket-fingerprint vectors,
  `must-reject.json`, `pattern-parity.json`) are vendored once by #988 in
  `internal/glovo/basket/contract/` (round 4, N3); the read-result schema reaches the
  approval-basket schema by `$ref`, and a test pins the sha256 of #988's copy. Both have a
  `PROVENANCE` file (repo, PR, merge commit, sha256 per file). It does not author or edit
  any of them. If #1059 is not merged, the task stops.
- Read kinds: `read_history`, `read_preview`, `read_basket` (final names from #1059).
  Read commands carry the #1059 read binding set (tenant, principal, connection and
  install-revision ref (`irv_`, wire only) and the decimal revision, the read idempotency key `request_id` (`rdq_`) and per-kind
  `params`) and no `order_ref`,
  `execution_id`, `work_item_id` or workflow fields.
- The single M1 basket fingerprint is defined in #1059 over the **approval basket**
  projection (`approval-basket.schema.json`) that the preview and basket payloads embed.
  This slice does not compute it. It only stores and serves the read result; #957 and
  #988 compute the fingerprint from the embedded approval basket. `payload_digest` is
  transport integrity only.
- v1alpha1 files, digests, projections and result digests are not touched.

### 2. Code changes for versioning (`schema.go`, `store.go`)
- `compileSchemas()` compiles both URL sets; `ParseResult` reads `schema_version` first
  and validates against the matching schema.
- `SubmitResult` (`store.go:745`) accepts `v1alpha2` only for a read-kind command, else
  `binding_mismatch`. Round 4 (R3-3): the wire version is derived from `operation_kind` in
  the shared paths (a write kind is v1alpha1), so `cmdCols` and `scanCmd` are unchanged; the
  stored `wire_version` is read only by the read-kind paths (§4a).
- `validate()` (`store.go:229-256`) gets a read-kind branch: read binding set required,
  order/`we_`/`wi_`/workflow fields forbidden.
- `projection()` (`store.go:334`) emits `bridge.mctl.ai/v1alpha1` for write kinds, exactly as
  today, and for read kinds the #1059 read projection, built from the row plus the extras of
  §4a (`wire_version`, `read_request_id`, `install_revision_ref`; round 4, R3-1).
- Versioning (#1059 §Versioning):
  - `BridgeProviderConfig` gains a server-side `SupportedVersions` list, default
    `[v1alpha1]`;
  - `Claim` leases a read-kind (v1alpha2) command only to a provider whose list contains
    `bridge.mctl.ai/v1alpha2`, and never trusts a provider-side filter;
  - the claim response (`handlers_bridge.go:200`, today a hard-coded v1alpha1 envelope)
    gets an envelope version, and each command keeps its own `schema_version`;
  - a read command no capable provider claims before `expires_at` expires as `expired`.
  Whether this lands here or in a separate slice is OPEN-1059-2; this proposal plans it
  here (task 2).

### 3. In-process read client (`internal/bridge/readclient.go`)

```go
type ReadRequest struct {
    Kind ReadKind // history | preview | basket
    Tenant, OwnerPrincipalID string        // private
    TenantRef, PrincipalRef, ConnectionRef string // tnr_, prr_, gcn_
    InstallRevision string    // decimal #959 revision: stored on the result row and compared on fetch (round 3, X-2)
    InstallRevisionRef string // irv_ ref minted by #957: written only to the command's install_revision_ref; EnqueueRead refuses either empty
    Scopes []string                         // from the verified subject token, for the glovo:read re-check
    Params json.RawMessage                  // bounded, validated against the #1059 command schema
    Deadline time.Time
}
type ReadResult struct{ Kind ReadKind; ResultRef, Digest string; Data []byte /* canonical bytes */ ; ExpiresAt time.Time }
func (c *ReadClient) Read(ctx context.Context, r ReadRequest) (*ReadResult, error)
```

`Read`:
1. In one transaction on the bridge pool: `EnqueueRead` inserts a read-kind command with
   a server-minted `request_id` (`rdq_`, the idempotency key) and no workflow. Commit.
2. Wait on the store until the command completes, with the request deadline (bounded
   poll with backoff; default 10 s, never longer than the #957 handler deadline). On
   deadline: `Store.Cancel` the command and return `ErrReadUnavailable`.
3. Call `Store.FetchReadResult` (§5) with the caller's tenant, principal, connection,
   install revision and scopes, and return the canonical bytes.

Only #957's handlers call `ReadClient.Read`, through #957's `ReadBridge` interface
(#957 task A12 owns the adapter). Amended (c): #957 passes every `ReadRequest` field
(design §5 there): the verified owner principal id, the `tnr_`/`prr_`/`gcn_` refs, the
decimal install revision, its `irv_` ref (both from one #959 read) and the subject token's scopes. #986 never resolves an `irv_`. `FetchReadResult` is the
authoritative binding check for reads. `EnqueueRead` sets the command TTL to
`min(Deadline - now, 300 s)`, `intent_hash` to the params digest, `operation_key` to
`"read:"+rdq_`, `sequence` to 1 and `approval_ref` to `''`. `execution_id` is `''` for every read, so the existing non-partial `UNIQUE (execution_id, sequence)` would admit one read in the whole database; §4 replaces it. The `pho_` and cursor origin check (#1059 consumer MUST 10) is not done here: #957 owns it (§5a there). No HTTP route, MCP tool, Temporal workflow or
signal is involved.

### 4. Storage (in `bridge.ApplySchema`, idempotent; amended (c))

These changes are owned here as `bridge.ApplyReadSchemaTx(ctx, tx pgx.Tx, runtimeRole string)
error` (round 4, X-3). #985's `bridge.ApplySchema` calls it inside its own transaction under
the migration role, with the grants of mctl-api#957 design §6d.1 for the objects below; the
runtime role never runs them. The function refuses to run unless `bridge_commands` is owned
by `current_user`, and is tested standalone on a database built from today's `bridgeSchema`. All changes
run in one `DO $$ … $$` block whose steps each test the catalog first, so a
second and every later boot is a no-op and takes no ACCESS EXCLUSIVE lock (round 5, F1: this is observed through `pg_locks` on the caller's still-open transaction, never through `log_statement`, which does not log statements nested in a `DO` block; an unguarded `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` takes the lock even when it changes nothing, so the test goes red on it):
- add `wire_version TEXT NOT NULL DEFAULT 'bridge.mctl.ai/v1alpha1'`,
  `read_request_id TEXT` (holds the #1059 `request_id`) and `install_revision_ref TEXT`
  (the `irv_` wire ref, NULL for write kinds; round 4, R3-1), each `ADD COLUMN IF NOT EXISTS`;
- (amended (c)) no NOT NULL is dropped; read rows store `''` in `workflow_id`,
  `run_id`, `execution_id`, `work_item_id` and `order_ref`;
- add, only if absent in `pg_constraint`, `NOT VALID`, then `VALIDATE CONSTRAINT` once
  in the same guarded step:
  - `bridge_commands_kind_v2_chk`: `operation_kind` in the v1alpha1 kinds plus the three read kinds
    (the old `bridge_commands_kind_chk` is dropped in the same guarded step, which runs
    exactly once);
  - `bridge_commands_read_shape_chk`: a read kind has `wire_version` v1alpha2, a
    non-null `read_request_id`, a non-null `install_revision_ref` matching `^irv_[A-Za-z0-9]{16,40}$`
    and `''` in workflow/order/`we_`/`wi_`; every other kind has a NULL `install_revision_ref` and
    all of those non-empty (which `validate()` already guarantees for v1alpha1 rows,
    `store.go:228-256`);
- (round 3, N1) `bridge_commands_sequence` (origin/main `store.go:115-116`, non-partial
  `UNIQUE (execution_id, sequence)`) is replaced by the same-named partial index
  `... WHERE operation_kind NOT IN ('read_history','read_preview','read_basket')`. The guarded
  step reads `pg_indexes.indexdef`; only when the definition has no such predicate does it
  `DROP INDEX` and `CREATE UNIQUE INDEX` once. `bridge.ApplySchema`'s copy of `bridgeSchema`
  carries the partial form, so its `CREATE UNIQUE INDEX IF NOT EXISTS` never re-creates the
  old one. `claimTx`'s `p.sequence < c.sequence` predicate needs no change: all reads have
  sequence 1, so reads never wait on each other, and a v1alpha1 execution's ordering is
  unchanged;
- `CREATE UNIQUE INDEX IF NOT EXISTS bridge_commands_read_request ON bridge_commands
  (tenant, read_request_id) WHERE read_request_id IS NOT NULL`;
- table `bridge_read_results` (`CREATE TABLE IF NOT EXISTS`):
  `result_ref` (server-minted `res_`, PK), `command_id` UNIQUE, `read_kind`, `tenant`,
  `owner_principal_id`, `tenant_ref`, `principal_ref`, `connection_ref`,
  `install_revision`, `data BYTEA` (canonical bytes; NULL after erase), `data_digest`,
  `size_bytes`, `created_at`, `expires_at`, `erased_at`; index on `expires_at`;
- table `bridge_read_schema_version(level INT NOT NULL)` (single row, written last; `SELECT`
  for the runtime role), the read level of §4a.

#### 4a. Compatibility with a database that never ran the migrator (round 4, R3-3)

- `cmdCols`/`scanCmd` do not change. `claimTx`, `Cancel`, `lockOwned`, `permitTx`, `expireTx`
  and `submitTx` for write kinds run the same SQL as today, so a deployment that never ran
  `ApplySchema` (Glovo off, the supported mode) or runs older code keeps its v1alpha1 bridge.
- The read-kind paths (`EnqueueRead`, the read branch of `claimTx` projection, `submitTx` read
  branch, `FetchReadResult`) read the new columns through one extras query keyed by
  `command_id`, issued only for rows whose `operation_kind` is a read kind. A v1alpha1 row has no
  extras and is wire v1alpha1.
- `bridge.CheckReadLevel(ctx, q Querier) error` reads `bridge_read_schema_version`. `EnqueueRead`
  and `ReadClient.Read` call it and refuse with `ErrReadUnavailable` (#957 maps it to
  `not_ready`) when the table is missing or its level is below the compiled level (1);
  the compiled level is the constant `bridge.ReadSchemaLevel` (= 1, owned here). #985 `NewRuntimeStore` calls it too and answers `not_ready`; that leg, its test and its selector-table row are #985's (round 5, F3). A claim never leases a read kind
  while the level is missing.

Every path that reads or transitions a `bridge_commands` row was checked (amended (c)):
`cmdCols`/`scanCmd`, `claimTx`, `lockOwned` and `Cancel` need no change because no
column becomes nullable; `permitTx` refuses a read kind (no write permit for a read);
`expireTx` adds `operation_kind` to its `RETURNING` and skips the
`bridge_signal_outbox` insert for read kinds. `submitTx` for a read kind writes **no**
`bridge_signal_outbox` row and no transition to a workflow; it inserts the `bridge_read_results` row in the same transaction as the
result CAS. Raw data never enters `bridge_commands.result`, which keeps
`{kind, digest, size_bytes, result_ref}` only.

### 5. Submission and fetch rules
Submission (provider, existing `/api/v1/bridge/commands/{id}/result` route), in this
pipeline order, one code per check (amended (c)):
1. `schema_version` must equal the command's wire version (the stored `wire_version` of a read-kind command, read in this read-only path; v1alpha1 for a write kind), else `binding_mismatch`.
   `request_id` must equal the stored `read_request_id`, else `binding_mismatch`.
2. Read kind: a non-`none` `provider_effect`, a provider-chosen `result_ref`, a payload
   on a non-`succeeded` outcome, or a read payload on a non-read kind all fail the
   vendored schema in step 4 and are `invalid_document` (the schema makes
   `provider_effect` const `none`). A body over 16384 bytes is refused by
   `bridgeMaxBody` before this pipeline. Round 4 (R3-2): the result handler
   (`handlers_bridge.go:216-220`) answers the unchanged 400 `invalid_document` for
   `*http.MaxBytesError` (round 5, F2: the #1059 route contract; `payload_too_large` is only
   the code of the in-Store cap below); the Store never sees that body. The Store's own cap, `JCS(payload)` over 12288 bytes, returns `ErrPayloadTooLarge`
   (`errors.go`). `ErrPayloadTooLarge`, `ErrReadUnavailable` and `ErrReadNotAuthorized` are
   entries of `codedErrors` (`payload_too_large`, `read_unavailable`, `read_not_authorized`)
   with `bridgeStatus` cases 413, 503 and 403.
3. Run the #1059 raw-bytes pre-check (`jcs.Precheck`, #988) on the body before any `json.Unmarshal`. It rejects
   duplicate keys, lone surrogates, `NaN`/`Infinity`, numbers outside ±(2^53-1) and any
   non-integer token in an integer position. Go's `encoding/json` accepts duplicate keys
   and replaces lone surrogates, so this is a token-level scanner, tested against the
   vendored `must-reject.json` (T7). Failure: `invalid_document`.
4. Validate the envelope against the #1059 `read-result.schema.json`, then canonicalize
   `payload` with RFC 8785 (`jcs.Canonicalize`, #988; the vendored #1059 vectors pin the implementation). Failing
   the per-kind schema, or a result that carries any binding ref: `invalid_document`.
   `JCS(payload)` over 12288 bytes: `payload_too_large` (the body itself is already capped
   at 16384 by `bridgeMaxBody`). `"sha256:"+hex(sha256(canonical)) != payload_digest`:
   `binding_mismatch`. Tenant, principal, connection and install revision come only from
   the stored command row; the result carries none of them. `result.kind` must equal the
   stored kind, and the result must arrive before the command's `expires_at`.
5. Store the canonical bytes, mint `res_`, set `expires_at = clock_timestamp() + ReadTTL`. The
   `lease_token` from the result is compared and never persisted, as in v1alpha1.
6. Replay of the same digest returns the same `res_`; a different digest is
   `result_conflict`.

`Store.FetchReadResult(ctx, ReadFetch{ResultRef, Tenant, PrincipalID, ConnectionRef,
InstallRevision, Scopes})`, in process only, checks in this order:

| Check | Sentinel |
|---|---|
| row missing, tenant or owner differs | `ErrCommandNotFound` (identical for all three) |
| `glovo:read` not in `Scopes` | `ErrReadNotAuthorized` |
| `expires_at <= clock_timestamp()` or `data IS NULL` | `ErrCommandExpired` |
| row's connection or install revision differs from the request | `ErrBindingMismatch` |
| #959 `LiveConnection(ctx, glovo.Owner{TenantID, PrincipalID})`: `no_connection`, revoked, expired (including `expires_at` passed), or a connection or install revision other than the row's | `ErrBindingMismatch` with the M1a state attached for #957's mapping |
| checker error | `ErrReadUnavailable` |
| `sha256(data) != data_digest` (constant-time compare) | `ErrReadUnavailable`, logged as an integrity failure |

`ConnectionChecker` is implemented by the #959 store's `LiveConnection` (same database,
owner decision A; amended (c)). A command whose outcome is not `succeeded` answers
`ErrReadUnavailable`. The install revision stored on the result row is the decimal one;
the checker compares it with the live #959 revision and the request's `InstallRevision`, never an `irv_`. Default `DenyConnectionChecker` returns
`ErrReadUnavailable`. #957 maps every sentinel through its §4 table (no bridge code
reaches the Glovo wire); `bridgeStatus` also gains explicit cases for the new sentinels
so they cannot fall through to 409 if ever exposed.

### 6. Expiry and retention
`EraseExpiredReads` sets `data=NULL, erased_at=now()` for expired rows and deletes rows
whose `expires_at` is more than 24 h ago, in bounded `FOR UPDATE SKIP LOCKED` batches
from the existing `Expirer` tick. Metric `mctl_api_bridge_read_results_erased_total`, no
tenant labels. `MCTL_BRIDGE_READ_RESULT_TTL`: default 300 s, clamped 1..300 s
(amended (c); prepare does not re-read, #957 §6d.3).

## Alternatives

1. Data through the Temporal signal or `ReadOutcome`. Rejected: raw user data in Temporal
   history (forbidden by the issue and #1044).
2. A public retrieval route. Rejected (review P1-2): it bypasses #957's kill switch,
   scope, team grant and preview persistence, and exposes bridge codes on the Glovo wire.
3. Authoring the schema here. Rejected (owner decision B): #1059 is the canonical source.
4. JSONB storage. Rejected (review P2-2): JSONB re-orders keys, so the digest cannot be
   re-verified.

## Platform impact

- Migrations: additive, guarded, idempotent (§4), applied by `bridge.ApplySchema` under
  the migration role. Existing v1alpha1 rows satisfy the new CHECKs; no NOT NULL is
  relaxed.
- Backward compatibility: v1alpha1 unchanged and golden-pinned. Providers receive
  v1alpha2 commands only for read kinds, which nobody enqueues until #957 wires the
  client.
- Security: no new route or audience; data reachable only in process after #957's checks
  plus this store's re-checks; providers cannot read data back.
- Resources: ≤ 12 KiB per read row (the #1059 `JCS(payload)` cap of 12288 bytes), erased within 300 s, deleted after
  24 h.
- Locks: reads take only L5 of mctl-api#957 design §6b on `bridge_commands`;
  `bridge_read_results` is never locked together with L1-L4.
- Order (round 4): #1059 approved and merged -> #959 -> #988 (`internal/jcs`) -> #960, #961, #989 -> this slice -> #985 (`bridge.ApplySchema` calls `bridge.ApplyReadSchemaTx`) -> #957 A12 and the mctl-telegram
  provider read path -> #990 tests. Nothing is enabled by this slice.
