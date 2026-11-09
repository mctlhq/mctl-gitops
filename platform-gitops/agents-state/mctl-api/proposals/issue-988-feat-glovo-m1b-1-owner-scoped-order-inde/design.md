# Design: issue-988-feat-glovo-m1b-1-owner-scoped-order-inde

## Amendment 2026-11-09 (c), round 5 of the AMEND PR

Fold-in of the round-4 findings; simplified, no new mechanism beyond the one named per row. Where this section and older text disagree, this section wins.

| Finding | Change here |
|---|---|
| F1, X-1 (types and merge order) | #959 merges first; no fake `Connections`; task 1 adds no `glovo.Code` |
| F2 (registry rows) | `glovo.RegisterGrants` for the #988 rows; `Ready` reuses the registry; T14 |
| F3 (`Querier`) | The local `Querier` is deleted; `dbq.Querier` (#957 §6d.4) |
| F5 (vector vendoring) | Task 2a vendors `jcs-digest.json` and `must-reject.json` from a pinned #1059 commit into `internal/jcs/testdata`; task 2 vendors the other three; no cycle |

## Amendment 2026-11-09 (c), round 4 of the AMEND PR

Resolves the round-3 findings N1-N4 and the cross-slice finding X-3 (merge order). Where this section and older text disagree, this section wins.

| Finding | Change here |
|---|---|
| N1 (`orders.execution_id` is not unique; two orders can bind one `we_`) | §2: `CREATE UNIQUE INDEX orders_execution ON glovo.orders (execution_id) WHERE execution_id <> ''`. §7: SQLSTATE `23505` on `orders_execution`, `orders_approval` or `orders_command` is `invalid_transition` (an invariant: the caller never reuses an id); on `order_ref` it is `invalid_request`. Tests: T12 (second order with the same `we_` is refused by the index), T17 (raw-SQL insert of a second order for an owner's `we_`) |
| N2 (which writes re-read the live connection) | §6, new table "Connection re-check per method": `Create`, `AppendSnapshot`, `Finalize` and `BindApproval` call `LiveConnectionTx` on the caller's transaction; `MarkDispatched`, `MarkCancelled` and `MarkUnknown` never do (cancel must succeed after a revoke; dispatch re-checks the connection in #985 itself). T4 gains the revoke case |
| N3 (no owner for the Go RFC 8785 implementation) | Owner: this slice, task 2. A neutral package `internal/jcs` (`Canonicalize(raw []byte) ([]byte, error)`, `Precheck(raw []byte) error`) reproduces the #1059 `vectors/` byte for byte, including the UTF-16 key order and number-form vectors. #986 imports it (its `rawcheck.go` becomes a wrapper over `jcs.Precheck`), so this slice depends on #1059 only, never on #986. The #1059 files this slice needs (`approval-basket.schema.json`, `basket-fingerprint.json`, `must-reject.json`, `pattern-parity.json`) are vendored here under `internal/glovo/basket/contract/` by sha256; #986 vendors the read-command and read-result schemas and references this copy for the basket files |
| N4 (`NewStore`/`Ready` have no role names; surface missing from #957 §6d.4) | §1: `NewStore(ctx, pool, runtimeRole, migrationRole string, conns, execs)`; `Ready` compares the owner of schema `glovo`, every table and every trigger function with exactly `migrationRole`. `Querier`, `JoinKind`, `ActorKind` and `Snapshot` are defined in §1. #957 §6d.4 lists `NewStore`, `Ready`, `ApplySchema`, `AppendSnapshot`, `Get`, `LockOrder`, `ScopeFromRefs` and these types |
| X-3 (merge order) | Merge order of the Glovo M1 slices, no cycle: #1059, #959, #988 (with `internal/jcs`), #960, #961, #989, #986, #985, then the #957 read routes (round 5: #959 first, #957 §6d.1). This slice has no dependency on #986 or #985 |

## Amendment 2026-11-09 (c), round 2 of the AMEND PR

Re-review of the AMEND PR head `dc1fe6e5`; code references re-checked at mctl-api
`ceac9ed`. Cross-slice seams are owned by mctl-api#957 design §6d (roles and grants,
execution binding, approval-basket source, interface list) and §4 (refusal codes).
Where this section and older text disagree, this section wins; the older passages are
edited.

| Finding | Change |
|---|---|
| F1, X-1 (`Order.ExecutionID` only via a `RecordEffect` #957 forbids) | The `we_` is bound at `Create`: `CreateInput.ExecutionID` (from #989 `CreateGlovoExecutionTx`, #957 §6d.2), checked through `ExecutionBindingTx` (tenant **and** owner) and written once at insert. `RecordEffect` is withdrawn; `MarkDispatched` writes the `place_order_fake` effect row. The `Executions` collaborator is #989's `ExecutionBindingTx`, not an adapter written by #957 |
| F2 (CHECK rejects real `we_` ids) | The CHECK stays `^we_[A-Za-z0-9]{16,40}$`, equal to the bridge pattern (`internal/bridge/store.go:164`). Glovo `we_` ids come only from #989 `CreateGlovoExecutionTx` (alphanumeric); a generic `we_`+UUID (`internal/workitems/store.go:676`) is refused, and T9 uses an id from the real generic store to prove it |
| F3, X-6 (signatures drift) | `Connections` is #959's `LiveConnectionTx(ctx, tx, owner glovo.Owner) (*glovo.Connection, error)`; `PeekOrderScope` returns `Scope` (#985 now copies it); #989 calls `BindApproval` with `Scope{Tenant, PrincipalID: owner}` and `Actor{system, "service:glovo-prepare"}`; the #989 fence passes `[]string{command tenant}` to `LockOrderForControl`. All in #957 §6d.4 |
| F4 (no raw-bytes entry point) | `basket.Parse(raw []byte) (Approval, []byte, error)` runs the shared raw-bytes pre-check (`internal/jcs.Precheck`, round 4), the vendored `approval-basket.schema.json` (`additionalProperties: false`) and `Validate`, and returns the JCS bytes; `basket.Fingerprint(canonical []byte)` hashes them. These are the only entry points; the #1059 basket files are vendored once, here, in `internal/glovo/basket/contract/` (round 4, N3) |
| F5 (`invalid_transition` maps to no §4 row) | §7 maps through #957 §4: on the facade prepare route it is an invariant failure (`unavailable`; a replay never reaches a write), on the #985 control routes it is 409 `invalid_transition` |
| F6, #957 F5 (refs, workflow id, run id) | `LookupJoinRefTx` (read-only) is added; the order row carries only `ordr_`, `we_`, fingerprint and `aar_`. #985 reads `tnr_`/`prr_` here, the workflow id from #989 `ExecutionBindingTx` and the run id from #957 `ControlStartTx` |
| F7 (readiness only checks `relowner <> current_user`) | `Ready` and `ApplySchema` require `NOT pg_has_role(current_user, owner, 'MEMBER')` for every table, trigger function and schema `glovo`, and that schema `glovo` is owned by the migration role. T14 adds an inherited-membership case and a runtime-owned schema |
| Round 3 (X-1, F-A) | `CreateInput.OrderRef` and `NewOrderRef()`; read-only `LookupByIdempotencyKey`; the `order` join kind is dropped (the ref is the order's own column) |
| Round 3 (F-B) | `glovo.orders_insert_guard()` and `glovo.order_effects_insert_guard()` close the raw-`INSERT` gap |
| Round 3 (F-C) | `lock_timeout` (55P03) maps to `tenant_busy` |
| Round 3 (F-D) | one `triggerInventory` constant (eight triggers, five functions) shared by `ApplySchema` and `Ready` |
| X-5 (`irv_`) | `glovo.join_refs.kind` gains `install_revision` (`irv_`), subject `install_id@revision` |
| X-4 (grants) | The grant list in §3 equals the #988 rows of #957 §6d.1; `execution_id` leaves the column `UPDATE` list (it is written at insert) |
| P3 F8, F9, F10 | Row P2-3 below now quotes the body's CHECK and cites T11/T12; `order_snapshots` gains `CHECK (basket_fingerprint = 'sha256:' \|\| encode(sha256(basket_canonical), 'hex'))` and a `BEFORE INSERT` trigger that refuses a snapshot unless the order is `open`; `CreateInput` is defined; the owner `Cancel` is dropped (no caller; prepare commits a finalized order in one transaction, so no `open` order is ever visible); a downgrade test is added |
| #989 F3 (`cancel_order_fake`) | `order_effects.effect_kind` is `place_order_fake` only |

## Amendment 2026-11-09 (b)

Resolves the independent review of digest
`sha256:dcacb4dcc5f6f22aaa8dddc05e4bdef538cee846a225b18b8b2aa7e402b81f40` (mctl-api#988
comment 6745210743: 1 P1, 7 P2, 5 P3; each re-verified at mctl-api `ceac9ed`) and
applies the coordinator direction and owner decision A of 2026-11-09 (b). This proposal
was rewritten; no older passage survives that contradicts this section.

| Review finding | Fix in this proposal |
|---|---|
| P1 own `mctl-basket/v1` over an invented `{store_ref, sku}` schema; prices excluded; differs from the preview fingerprint `aar_` binds | Dropped. There is **one** basket fingerprint in M1: `"sha256:" + hex(sha256(JCS(approval_basket)))`, where the **approval basket** projection (`approval-basket.schema.json`: store ref, lines sorted by unique `item_code` with quantity and unit price in integer minor units, currency, fees, total; no display or time fields) and its golden vectors are defined by the mctl-agents#1059 amendment in this PR (RFC 8785, **prices included**). It replaces `mctl-basket/v1`. #957 preview and prepare, #988, #985 dispatch, the #989 fence and #1044 all use it. This slice implements it once in `internal/glovo/basket` against the vendored #1059 vectors and invents no basket schema (§4). `Create` and `Finalize` take an `ExpectedFingerprint` and refuse `fingerprint_changed` |
| P2-2 order `approved` state is a second approval authority; cannot carry the pending `aar_` | `approved` is dropped. `approval_ref` is a write-once binding set by `BindApproval` while `finalized`, called by #989 `CreateGlovoApprovalTx` in the prepare transaction. Approval state lives only on the #989 `aar_` row (§6) |
| P2-3 CHECKs cannot see `OLD`; `approval_ref`/`command_id` swappable; table-wide `UPDATE`; `open -> cancelled` CHECK bug | `glovo.orders_guard()` enforces the transition matrix over `OLD.state`/`NEW.state`, makes `approval_ref`, `command_id` and `execution_id` write-once, and requires `final_basket_fingerprint` to equal the final snapshot's. The runtime grant is column-level `UPDATE`. The fingerprint CHECK reads `state IN ('open','cancelled') OR final_basket_fingerprint ~ '^sha256:[0-9a-f]{64}$'`. T11 and T12 assert trigger rejection under the runtime role (§3, §6; amended (c)) |
| P2-4 refusals not mapped to #957 §4; absent and revoked conflated; I/O mapped to `not_ready` | One table maps every refusal to the #957 §4 wire code (§7). Absent is `no_connection`; revoked and expired stay distinct. I/O errors are `dependency_unavailable`; `not_ready` means not configured. The package extends `glovo.Code` instead of a third vocabulary |
| P2-5 `Scope` cannot serve #985; events attribute dispatch to the owner; no `ExecutionID` | Control path `PeekOrderScope` / `LockOrderForControl` derives tenant and owner from the order row inside the worker's `tenants` bound, plus `ScopeFromRefs` over `glovo_join_refs`. Every write takes an `Actor{Kind owner|control_worker|system, ID}` recorded in events with a CHECK. `Order.ExecutionID` is a write-once column (§5, §8) |
| P2-6 `RecordEffect` checks the execution's tenant only | `Executions.ExecutionBindingTx` returns `(tenant, owner_principal_id, work_item_id)`; both tenant and owner must match. T9 adds the same-tenant, other-owner `we_` |
| P2-7 `glovo_join_refs` has two owners; `ApplySchema` trusts existing objects | #988 owns `glovo_join_refs` and its minting helper; #957 A7 is amended to call it. `ApplySchema` fails on any object not owned by the migration role, uses `CREATE OR REPLACE FUNCTION`, and refuses a schema-version downgrade. `NewStore`/`Ready` require every guard trigger to exist with `tgenabled='O'` and `relowner` not the current role (§3) |
| P2-8 fingerprint not pinned | Pinned by the #1059 golden vectors, vendored by sha256; T7 asserts them byte for byte, including a permuted-input vector and a single-price change |
| P3 duplicate error vocabulary | Extends `glovo.Code` (`internal/glovo/errors.go:24-44`) |
| P3 T10 too broad; `search_path` shadowing | Tables live in the Postgres schema `glovo`, owned by the migration role, and every statement is schema-qualified. T10 is scoped to the order tables |
| P3 naming gap with #957 `providerorders.Service`; `pord_` on the wire | #957 drops `providerorders` and calls this store and #989 directly (#957 task 8). #957 is amended so `order_id` on the wire carries the `ordr_`, and its T6 uses `ordr_` |
| P3 idempotent create needs READ COMMITTED | `Create` refuses a caller transaction that is not READ COMMITTED (`dependency_unavailable`, logged) |
| P3 retention before G3 | Recorded as a precondition before any G3 or real-data use (OPEN-988-4) |

Skipped P3s: none.

**Owner decision A.** The order tables live in the one physical database shared with the
bridge, the work items, the `aar_` rows and the #959 connection store, and every write
uses the caller's one `pgx.Tx`. Locks follow the canonical order of #957 design §6b.

## Current state

- `internal/glovo/` has `gate.go` (`Gate{Open bool}`, `var Default = Gate{Open: false}`
  at `gate.go:24`, `Authorize`) and `errors.go` (`Code`, `WriteError`). No store.
- `internal/bridge/store.go`: `bridge_commands` already carries `tenant`,
  `owner_principal_id`, `order_ref`, `connection_ref`, `install_revision`; `refPatterns`
  pins `ordr_`, `tnr_`, `prr_`, `gcn_`, `aar_`, `we_`; `randAlnum` (`crypto/rand`);
  `Enqueue(ctx, tx, ...)`; `Pool()` (`store.go:414`); `NewStore` runs `bridgeSchema`
  every start (`store.go:374`).
- Immutability precedent: `internal/decisions/store.go` `decision_records_immutable()`.
  Schema serialization precedent: `internal/principals/store.go:133`.
- `we_` ids: `internal/workitems/types.go:27`; `work_items.owner_principal_id`
  (`internal/workitems/store.go:139`). No tx-aware execution lookup exists yet
  (`withTx`, `store.go:266`).
- The #959 connection store and the #989 `aar_` extension are proposals, amended in the
  same wave as this one.
- The live mctl-api env was not observed (`mctl_get_service_config` returns "service not
  found: admins/mctl-api"). The #985 startup proof covers the topology either way.

## Proposed solution

### 1. Package and wiring

New packages `internal/glovo/orders` and `internal/glovo/basket`. No route, no MCP tool,
no `main.go` change. #957 and #985 construct the store from `bridge.Store.Pool()` only
after #985's `ProveOneDatabase` passed.

```go
func ApplySchema(ctx context.Context, migrationConnStr, runtimeRole string) error
func NewStore(ctx context.Context, pool *pgxpool.Pool, runtimeRole, migrationRole string, conns Connections, execs Executions) (*Store, error) // no DDL; round 4 (N4): both role names are checked by Ready
func (s *Store) Ready(ctx context.Context) error

// Querier below is dbq.Querier (internal/glovo/dbq, created by #959; round 5, F3: one definition, #957 §6d.4). This slice defines no Querier of its own.
type JoinKind string                                           // JoinTenant "tenant", JoinPrincipal "principal", JoinInstallRevision "install_revision"
type ActorKind string                                          // ActorOwner "owner", ActorControlWorker "control_worker", ActorSystem "system"
type Snapshot struct {                                         // one row of order_snapshots
    OrderRef string; Seq, LineCount int; Fingerprint string; Canonical []byte; CreatedAt time.Time
}
type Scope struct{ Tenant, PrincipalID string }              // owner path: from the verified caller
type Actor struct{ Kind ActorKind; ID string }               // owner | control_worker | system
type Connections interface {                                  // #959 (merged first, round 5: glovo.Owner and glovo.Connection exist), tx-scoped (#957 §6d.4)
    LiveConnectionTx(ctx context.Context, tx pgx.Tx, owner glovo.Owner) (*glovo.Connection, error)
}
type Executions interface {                                   // provided by #989 workitems (#957 §6d.2)
    ExecutionBindingTx(ctx context.Context, q Querier, executionID string) (tenant, ownerPrincipalID, workItemID, workflowID string, err error)
}
type CreateInput struct {                                     // amended (c)
    Scope Scope; Actor Actor
    IdempotencyKey, RequestHash string                        // client key and hash, per (tenant, owner)
    ConnectionID, InstallID string; ExpectedInstallRevision int64
    ApprovalBasket []byte                                     // JCS bytes stored with the #957 preview
    ExpectedFingerprint string                                // the preview's fingerprint
    ExecutionID string                                        // we_ from #989 CreateGlovoExecutionTx
    OrderRef string                                           // ordr_, minted by #957 with NewOrderRef() before the workflow id is derived (round 3, X-1)
}
func NewOrderRef() string                                     // "ordr_" + 26 base62 from crypto/rand (the bridge randAlnum); the only minting entry point

// owner path (#957)
func (s *Store) Create(ctx, tx, in CreateInput) (*Order, bool /*replayed*/, error)
func (s *Store) LookupByIdempotencyKey(ctx, q Querier, sc Scope, key string) (*Order, error) // read-only, one statement on (tenant, owner, key); not_found on a miss (round 3)
func (s *Store) AppendSnapshot(ctx, tx, sc Scope, a Actor, orderRef string, expectedVersion int64, b basket.Approval, expectedFP string) (*Snapshot, error)
func (s *Store) Finalize(ctx, tx, sc Scope, a Actor, orderRef string, expectedVersion int64, expectedFP string) (*Order, error)
func (s *Store) BindApproval(ctx, tx, sc Scope, a Actor, orderRef, approvalRef string) error // #989 only
func (s *Store) Get(ctx, q Querier, sc Scope, orderRef string) (*Order, error)
func (s *Store) LockOrder(ctx, tx, sc Scope, orderRef string) (*Order, error)               // FOR UPDATE
func (s *Store) Snapshot(ctx, q Querier, sc Scope, orderRef string, seq int) (*Snapshot, error)

// control path (#985), scope derived server-side from the order row
func (s *Store) PeekOrderScope(ctx, q Querier, orderRef string, tenants []string) (Scope, error)
func (s *Store) LockOrderForControl(ctx, tx, orderRef string, tenants []string) (*Order, error)
func (s *Store) ScopeFromRefs(ctx, q Querier, tenantRef, principalRef string) (Scope, error)
func (s *Store) MarkDispatched(ctx, tx, o *Order, commandID string, a Actor) error // also writes the place_order_fake effect row
func (s *Store) MarkCancelled(ctx, tx, o *Order, a Actor) error
func (s *Store) MarkUnknown(ctx, tx, o *Order, a Actor) error
func (s *Store) MarkClosed(ctx, tx, o *Order, a Actor) error // dispatched -> closed only (round 6, G2)

// join refs (owned here; #957 calls it)
func (s *Store) MintJoinRefTx(ctx, tx, kind JoinKind, tenant, principalID, subjectID string) (string, error)   // insert-or-read
func (s *Store) LookupJoinRefTx(ctx, q Querier, kind JoinKind, tenant, principalID, subjectID string) (string, error) // read-only; not_found if never minted
```

Every signature here is the one listed in mctl-api#957 design §6d.4 (amended (c)).

`Create` requires `in.OrderRef` to match `^ordr_[A-Za-z0-9]{16,40}$` (else `invalid_request`)
and inserts it as `order_ref`; the order's own column is therefore the only `ordr_`, and
the workflow id, `engine_ref`, the `aar_` key and `glovo.control_starts` all embed the one
value #957 minted (round 3). On an idempotency conflict `Create` writes nothing and
returns the stored order with `replayed=true`, whatever `OrderRef` and `ExecutionID` the
caller passed; a caller that sees `replayed=true` after it already wrote other rows in
its transaction must roll the whole transaction back (#957 §6 step 1b).
`LookupByIdempotencyKey` lets #957 answer a replay before any write.

`Order` exports `RequestHash`, `OrderRef`, `Tenant`, `OwnerPrincipalID`, `ConnectionID`,
`InstallRevision`, `State`, `FinalBasketFingerprint`, `FinalSnapshotSeq`,
`ApprovalRef`, `CommandID`, `ExecutionID` and `Version`. `order_id`
(`pord_`) stays unexported. No write method begins, commits or rolls back a transaction.
With a nil collaborator every method returns `not_ready`.

### 2. Tables (Postgres schema `glovo`, applied only by `ApplySchema`)

```sql
CREATE SCHEMA IF NOT EXISTS glovo;   -- owned by the migration role; every ApplySchema runs this (#957 §6d.1)
CREATE TABLE IF NOT EXISTS glovo.join_refs (
  kind TEXT NOT NULL CHECK (kind IN ('tenant','principal','install_revision')), -- irv_, amended (c); no 'order' kind (round 3): ordr_ is the order's own order_ref column, never a join row
  ref TEXT NOT NULL, tenant TEXT NOT NULL, principal_id TEXT NOT NULL DEFAULT '',
  subject_id TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (kind, ref), UNIQUE (kind, tenant, subject_id));
CREATE TABLE IF NOT EXISTS glovo.orders (
  order_id TEXT PRIMARY KEY,                       -- pord_, internal only
  order_ref TEXT NOT NULL UNIQUE,                  -- ordr_ + 26 base62, supplied by #957 through CreateInput.OrderRef (NewOrderRef), written once
  tenant TEXT NOT NULL, owner_principal_id TEXT NOT NULL,
  connection_id TEXT NOT NULL, install_id TEXT NOT NULL, install_revision BIGINT NOT NULL,
  provider TEXT NOT NULL DEFAULT 'fake' CHECK (provider = 'fake'),
  state TEXT NOT NULL DEFAULT 'open'
    CHECK (state IN ('open','finalized','dispatched','cancelled','unknown','closed')),
  final_basket_fingerprint TEXT NOT NULL DEFAULT '',
  final_snapshot_seq INTEGER NOT NULL DEFAULT 0,
  approval_ref TEXT NOT NULL DEFAULT '', command_id TEXT NOT NULL DEFAULT '',
  execution_id TEXT NOT NULL DEFAULT '',
  idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL,
  version BIGINT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE (tenant, owner_principal_id, idempotency_key),
  CHECK (state IN ('open','cancelled') OR final_basket_fingerprint ~ '^sha256:[0-9a-f]{64}$'),
  CHECK (state NOT IN ('dispatched','unknown','closed') OR command_id ~ '^cmd_[A-Za-z0-9]{26}$'),
  CHECK (approval_ref = '' OR approval_ref ~ '^aar_[A-Za-z0-9]{16,40}$'),
  CHECK (execution_id = '' OR execution_id ~ '^we_[A-Za-z0-9]{16,40}$'));
CREATE UNIQUE INDEX IF NOT EXISTS orders_approval ON glovo.orders (approval_ref) WHERE approval_ref <> '';
CREATE UNIQUE INDEX IF NOT EXISTS orders_command  ON glovo.orders (command_id)   WHERE command_id <> '';
CREATE UNIQUE INDEX IF NOT EXISTS orders_execution ON glovo.orders (execution_id) WHERE execution_id <> '';   -- round 4 (N1): one `we_` binds at most one order
CREATE TABLE IF NOT EXISTS glovo.order_snapshots (
  order_id TEXT NOT NULL REFERENCES glovo.orders (order_id), seq INTEGER NOT NULL,
  basket_fingerprint TEXT NOT NULL, basket_canonical BYTEA NOT NULL,   -- JCS bytes
  line_count INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL, PRIMARY KEY (order_id, seq),
  CHECK (basket_fingerprint = 'sha256:' || encode(sha256(basket_canonical), 'hex')));
CREATE TABLE IF NOT EXISTS glovo.order_effects (
  effect_id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES glovo.orders (order_id),
  tenant TEXT NOT NULL, owner_principal_id TEXT NOT NULL,
  effect_kind TEXT NOT NULL CHECK (effect_kind = 'place_order_fake'),   -- amended (c)
  execution_id TEXT NOT NULL UNIQUE, basket_fingerprint TEXT NOT NULL,
  idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
  UNIQUE (tenant, owner_principal_id, idempotency_key));
CREATE TABLE IF NOT EXISTS glovo.order_events (
  id BIGSERIAL PRIMARY KEY, tenant TEXT NOT NULL, order_ref TEXT NOT NULL,
  actor_kind TEXT NOT NULL CHECK (actor_kind IN ('owner','control_worker','system')),
  actor_id TEXT NOT NULL, event TEXT NOT NULL,
  from_state TEXT NOT NULL DEFAULT '', to_state TEXT NOT NULL DEFAULT '',
  snapshot_seq INTEGER NOT NULL DEFAULT 0, recorded_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS glovo.orders_schema_version (version INT NOT NULL);
```

### 3. Triggers, roles and schema application

Trigger inventory (round 3). One list per function; the exact set below is a single
constant `triggerInventory` (table, trigger name, function, timing, event) shared by
`ApplySchema` and `Ready`, so they cannot drift:

| Function | Attached to | Timing and event |
|---|---|---|
| `glovo.orders_immutable_rows()` | `join_refs`, `order_snapshots`, `order_effects`, `order_events` (four triggers) | `BEFORE UPDATE OR DELETE` |
| `glovo.orders_guard()` | `orders` | `BEFORE UPDATE OR DELETE` |
| `glovo.orders_insert_guard()` | `orders` | `BEFORE INSERT` |
| `glovo.order_snapshots_guard()` | `order_snapshots` | `BEFORE INSERT` |
| `glovo.order_effects_insert_guard()` | `order_effects` | `BEFORE INSERT` |

That is eight triggers and five functions.

- `glovo.orders_immutable_rows()` refuses `UPDATE` and `DELETE` on the four tables above.
- `glovo.orders_guard()` (`BEFORE UPDATE OR DELETE` on `glovo.orders`):
  - refuses `DELETE`;
  - refuses a change to any identity column (`order_id`, `order_ref`, `tenant`,
    `owner_principal_id`, `connection_id`, `install_id`, `install_revision`, `provider`,
    `idempotency_key`, `request_hash`, and since (c) `execution_id`, set at insert);
  - allows only these `(OLD.state, NEW.state)` pairs, plus same-state updates that only
    set a write-once column:
    `open->finalized`, `open->cancelled`, `finalized->dispatched`,
    `finalized->cancelled`, `dispatched->cancelled`, `dispatched->unknown`,
    `dispatched->closed`, `unknown->closed`. `cancelled` and `closed` are final;
  - `final_basket_fingerprint`, `final_snapshot_seq`, `approval_ref` and `command_id`
    are write-once (empty/zero to a value, never changed after);
  - `approval_ref` may be set only while `finalized`; `command_id` only on
    `finalized->dispatched`, and only when `approval_ref` is set;
  - on `open->finalized`, `NEW.final_basket_fingerprint` must equal the
    `basket_fingerprint` of the snapshot at `NEW.final_snapshot_seq`.
- `glovo.orders_insert_guard()` (`BEFORE INSERT` on `glovo.orders`, round 3) refuses an
  insert unless `state = 'open'`, `final_basket_fingerprint`, `approval_ref`,
  `command_id` are empty, `final_snapshot_seq = 0`, `version = 1`, `execution_id` is
  non-empty and resolves, through the same join as #989 `ExecutionBindingTx`
  (`work_item_executions` to `work_items`), to the order's `tenant` and
  `owner_principal_id`. It runs as the invoker and needs only the `SELECT` on those
  tables that #957 §6d.1 grants through #989 task 2b. Until #989 lands, `Ready` reports
  `not_ready` (it checks `has_table_privilege(runtimeRole, 'public.work_items' and
  'public.work_item_executions', 'SELECT')`), so `Create` is never reachable without
  the guard's inputs (round 6, G3). Without it the runtime role, which holds
  `INSERT`, could create an order already `dispatched`, with a fingerprint that matches
  no snapshot or an execution of another owner, and the update guards would never run.
- `glovo.order_snapshots_guard()` (`BEFORE INSERT` on `glovo.order_snapshots`, amended
  (c)) refuses a snapshot unless its order is `open` in the same transaction.
- `glovo.order_effects_insert_guard()` (`BEFORE INSERT` on `glovo.order_effects`, round 3)
  refuses an insert unless the order row exists in state `finalized` in the same
  transaction, and the effect's `tenant`, `owner_principal_id`, `execution_id` and
  `basket_fingerprint` equal the order's `tenant`, `owner_principal_id`, `execution_id`
  and `final_basket_fingerprint`. `MarkDispatched` therefore inserts the effect row
  first, then CASes the order `finalized -> dispatched`, in one transaction.
- `ApplySchema` runs in one transaction under the migration role with
  `pg_advisory_xact_lock(hashtext('glovo-orders-schema'))`:
  - fails if any existing object in this list is not owned by the migration role;
  - uses `CREATE OR REPLACE FUNCTION` for every function of the trigger inventory (all
    five), and creates each trigger of `triggerInventory` only if absent in `pg_trigger`;
  - refuses to run if the stored version is newer than the code's;
  - round 5 (F2): calls `glovo.RegisterGrants` from this package's `init` with exactly the rows below, which are also the #988 rows of `internal/glovo/testdata/grants.golden` (#959 owns the registry, merged first);
  - grants the runtime role (`^[a-z_][a-z0-9_]{0,62}$`): `USAGE` on schema `glovo`;
    `SELECT, INSERT` on `orders` plus column-level
    `UPDATE (state, final_basket_fingerprint, final_snapshot_seq, approval_ref,
    command_id, version, updated_at)` (amended (c): exactly the #988 rows of
    mctl-api#957 design §6d.1); `SELECT, INSERT` on the four
    append-only tables; `USAGE` on the events sequence; `SELECT` on the version table. No
    `DELETE`, `TRUNCATE`, `REFERENCES` or `TRIGGER`.
- `NewStore` and `Ready` require: the version matches; every table resolves through
  `to_regclass('glovo.…')`; `Ready` compares `pg_trigger` with `triggerInventory` exactly:
  every listed trigger is present, `tgenabled = 'O'`, its `tgfoid` is the expected
  function, the function is owned by the migration role, and no unlisted trigger exists on
  these tables; for
  every table, trigger function and schema `glovo`,
  `NOT pg_has_role(current_user, <owner>, 'MEMBER')` (amended (c); covers inherited
  membership, not only `relowner <> current_user`); schema `glovo` is owned by exactly
  the `migrationRole` argument (round 4, N4: every table, trigger function and the schema
  are compared with that one name, so an object owned by any other role, including another
  non-superuser, fails); and the grants of the #988 tables equal the rows this slice registered with #959's `glovo.RegisterGrants` (round 5, F2: `Ready` reuses the registry, it hand-codes no copy).
  Otherwise `not_ready`.

### 4. One basket fingerprint (`internal/glovo/basket`)

- `basket.Approval` is the Go mirror of the #1059 `approval-basket.schema.json`. This
  slice does not define its fields; it vendors the #1059 schema, `basket-fingerprint.json`
  and `must-reject.json` by sha256 (as #986 task 1 does) and fails to build without them.
  `basket.Validate` enforces what the schema cannot: lines sorted by unique `item_code`
  (unsorted input is rejected, never re-sorted) and the subtotal and total arithmetic.
  The read payload (`payload_digest`) is never a fingerprint input.
- Amended (c): the only entry points are `basket.Parse(raw []byte) (Approval, []byte,
  error)` and `basket.Fingerprint(canonical []byte) string`. `Parse` runs the #1059
  raw-bytes pre-check (shared with #986 through `internal/jcs.Precheck`), validates
  against the vendored `approval-basket.schema.json` with `additionalProperties: false`
  (so an extra field such as `item_name`, or `quantity: 1.0`, is refused), runs
  `Validate`, and returns the RFC 8785 bytes of the validated input. The #1059 basket files are
  vendored once, here, in `internal/glovo/basket/contract/` (#986 and #985 pin the same
  sha256 and do not copy them). The write command schema that wraps this basket by `$ref`
  is #1059's `command-place-order-fake.schema.json`, vendored and gated by #986 §2a (round 7; #985 only enqueues it).
- `basket.Fingerprint(canonical) = "sha256:" + hex(sha256(canonical))`, with RFC 8785 from the
  `internal/jcs.Canonicalize` of this slice (round 4, N3; #986 imports it). Prices and amounts are part of `t`, so
  a price change changes the fingerprint.
- mctl-api computes it itself at preview (#957), at prepare (`Create`/`Finalize` here),
  at dispatch (#985 compares) and at the write fence (#989 recomputes from the stored
  command payload). A provider- or caller-supplied fingerprint is only ever compared
  against a value mctl-api computed, never stored as truth.
- The snapshot stores `JCS(t)` in `basket_canonical`, so any reader can re-verify
  `Fingerprint == sha256(basket_canonical)`.

### 5. Owner scoping and the control path

- Owner path: every lookup is one statement on `(order_ref, tenant, owner_principal_id)`,
  `FOR UPDATE` when locking. A miss, a foreign row and a malformed ref run the same
  statement and return the same `not_found`.
- Control path (#985): `PeekOrderScope` reads `tenant, owner_principal_id` by
  `order_ref` with `tenant = ANY($tenants)`, no lock. `LockOrderForControl` re-reads the
  row `FOR UPDATE` under the same predicate. A miss is `not_found`. `ScopeFromRefs`
  resolves a `tnr_`/`prr_` pair through `glovo.join_refs` and requires both to map to
  the same tenant; a miss is `not_found`.
- Locks: the order row is level L3 of the canonical order in #957 design §6b. The
  connection read (`LiveConnectionTx`) takes no row lock; callers hold the #959 owner
  advisory key (L2 shared) before calling.

### 6. Lifecycle

| From | To | Method | Caller |
|---|---|---|---|
| (new) | `open` | `Create` (writes snapshot 1 from `CreateInput.ApprovalBasket`, write-once `execution_id`) | #957 prepare |
| `open` | `open` | `AppendSnapshot` | #957 |
| `open` | `finalized` | `Finalize(expectedFP)` | #957 prepare |
| `finalized` | `finalized` | `BindApproval` (write-once `approval_ref`) | #989 `CreateGlovoApprovalTx` |
| `open`, `finalized` | `cancelled` | `MarkCancelled` | #985 |
| `finalized` | `dispatched` | `MarkDispatched(cmd_)` (writes the effect row) | #985 |
| `dispatched` | `cancelled` | `MarkCancelled` (a `cancelled` or `expired` command with effect `none`) | #985 `reconcileOrder` |
| `dispatched` | `unknown` | `MarkUnknown` (a terminal command, `completed`, `cancelled` or `expired`, whose effect is `unknown`) | #985 `reconcileOrder` |
| `dispatched` | `closed` | `MarkClosed` (a `completed` command with effect `succeeded`, `failed`, `not_performed` or `none`) | #985 `reconcileOrder`, one function with the total table of #985 §2a (rounds 6 and 7; this slice needs no new edge; the `unknown -> closed` edge stays in the trigger matrix but has no caller) |

Every write CASes on `version` and `state`; the trigger enforces the same matrix for raw
SQL. Approval state is never stored on the order.

Connection re-check per method (round 4, N2). A method that can start or extend work for
the owner re-reads the live connection on the caller's transaction; a method that only
records a terminal fact never does, so cancellation and recording still succeed after a
revoke.

| Method | `LiveConnectionTx` on the caller's tx | Why |
|---|---|---|
| `Create`, `AppendSnapshot`, `Finalize`, `BindApproval` | yes (L2 held by the caller; revoked, expired, no connection and a moved install revision are refused) | each commits the owner to a basket or an approval |
| `MarkDispatched` | no | #985 re-reads the connection itself in dispatch step 8, before `Enqueue`; this method only records the command id and the effect row |
| `MarkCancelled`, `MarkUnknown`, `MarkClosed` | no, and must not | a revoked connection is exactly when these run (the revoker cancels open commands); refusing them would strand the order |
| `Get`, `Snapshot`, `LockOrder`, control-path reads | no | reads work after revoke (T4) |

### 7. Refusal map (extends `glovo.Code`)

Amended (c): the codes are internal `glovo.Code` values; status and wire value come only
from mctl-api#957 design §4.1.

| Store condition | Code | #957 §4 wire |
|---|---|---|
| order missing, foreign, malformed ref, outside `tenants` | `not_found` | 404 `not_found` |
| no connection | `no_connection` | 404 `no_connection` |
| connection revoked / reconnected (`gcn_` differs) | `connection_revoked` | 409 `connection_revoked` |
| connection expired | `connection_expired` | 409 `connection_expired` |
| install revision moved | `stale_install` | 403 `stale_install` |
| basket invalid or empty at create or finalize | `invalid_request` | 400 `invalid_arguments` (facade) |
| expected fingerprint differs | `fingerprint_changed` | 409 `fingerprint_changed` |
| idempotency key reused with another request hash | `idempotency_key_reused` | 409 `idempotency_key_reused` |
| version or state CAS miss, write-once column already set, or SQLSTATE `23505` on `orders_execution`, `orders_approval` or `orders_command` (round 4, N1) | `invalid_transition` | facade prepare route: invariant, 503 `dependency_unavailable` (#957 §4.2; a replay is answered before any write); #985 control routes: 409 `invalid_transition` |
| `ExecutionID` bound to another tenant or owner, or not a Glovo `we_` | `not_found` | 404 `not_found` (control) / invariant `unavailable` (prepare) |
| SQLSTATE `23505` on `orders_order_ref_key` (a `Create` with an `ordr_` that already exists under another key) | `invalid_request` | 400 `invalid_arguments` (facade) |
| `lock_timeout` (SQLSTATE `55P03`) on `LockOrder`, `LockOrderForControl` or any CAS `UPDATE` (round 3) | `tenant_busy` | #957 §4.1: facade 503 `dependency_unavailable`, control 409 `tenant_busy` |
| any other collaborator or database error, wrong isolation level | `unavailable` | 503 `dependency_unavailable` (facade) / `unavailable` (control) |
| collaborator nil, schema not ready | `not_ready` | 503 `not_ready` |

`order_finalized`, `order_state_conflict` and `execution_already_bound` are folded into
`invalid_transition`. Refusals carry no text and no id.

### 8. Effects, idempotency, audit

- Amended (c): `RecordEffect` is withdrawn. `Create` calls `ExecutionBindingTx` for
  `CreateInput.ExecutionID` and requires tenant **and** owner to equal the order's (a
  mismatch is `not_found`), then writes `execution_id` once at insert.
  `MarkDispatched` writes the one `place_order_fake` row of `glovo.order_effects`
  (idempotency key `glovo-dispatch:`+`ordr_`, `execution_id` the order's, the final
  fingerprint) in the same statement group as the state change.
- `Create` (round 3): `in.OrderRef` is validated and inserted as `order_ref`; #957 calls
  `LookupByIdempotencyKey` first and `Create` only on a miss. `Create` with an existing
  key and the same `request_hash` returns the stored order with `replayed=true` and
  writes nothing (it never mints a second `ordr_`); another hash is
  `idempotency_key_reused`.
- `Create`: requires READ COMMITTED; checks `LiveConnectionTx` and
  `ExpectedInstallRevision`; runs `basket.Parse` on `CreateInput.ApprovalBasket`,
  computes the fingerprint of the first snapshot and compares `ExpectedFingerprint`; inserts with
  `ON CONFLICT (tenant, owner_principal_id, idempotency_key) DO NOTHING`, then reads back
  and compares `request_hash`.
- Every write appends one `glovo.order_events` row with `actor_kind`/`actor_id`, the
  `ordr_`, the event and the from/to state. No fingerprint, basket or provider data.

## Alternatives

1. A fingerprint of its own (`mctl-basket/v1` over `{store_ref, sku}`). Rejected
   (review P1): two fingerprints of one basket, and prices excluded.
2. An order `approved` state. Rejected (review P2-2): a second approval authority.
3. DDL in `NewStore`. Rejected: the runtime role would own the guard triggers.
4. A separate `GLOVO_DB_URL` database for orders. Rejected by owner decision A.

## Platform impact

- Migrations: additive, in schema `glovo`, only through `ApplySchema`.
- Backward compatibility: no route, MCP tool, env var or `main.go` change.
- Dependencies: mctl-agents#1059 (approval basket and vectors), #959 (`LiveConnectionTx`),
  #989 (`BindApproval` caller and `ExecutionBindingTx`), #985 (control-path caller),
  #957 (prepare caller). #986 and #985 depend on this slice (`internal/jcs`, round 4), never the reverse. Until then `not_ready`. Hold mctl-gitops#2457 stays ON.
