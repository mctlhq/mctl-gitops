# Design: issue-988-feat-glovo-m1b-1-owner-scoped-order-inde

## Current state

- `internal/glovo/` has only the closed feature gate: `gate.go` (`Gate{Open bool}`,
  `Default = Gate{Open: false}`, `Authorize`) and `errors.go` (`Code` with
  `not_ready`/`not_authorized`, `WriteError`). It has no store, table or order code.
- `internal/bridge/store.go` is the command outbox (#962):
  - It already carries the order's identity columns on `bridge_commands`:
    `tenant`, `owner_principal_id`, `order_ref`, `connection_ref` and
    `install_revision`.
  - `refPatterns` pins the external ref formats: `ordr_`, `tnr_`, `prr_`, `gcn_`, `aar_`
    and `we_`, each `[A-Za-z0-9]{16,40}`.
  - `randAlnum(n)` generates the base62 suffixes from `crypto/rand`.
  - `Enqueue(ctx, tx, EnqueueInput)` writes on a caller-supplied `pgx.Tx`.
  - `Store.Pool()` exposes the pool, so a caller can open that transaction.
  - `NewStore` runs `bridgeSchema` DDL on every start.
  - `OpenExistingStore` is the existing precedent for a no-DDL opener: it checks
    `to_regclass('bridge_commands')` and fails if the table is missing.
- `cmd/api/main.go` (around lines 1016-1030) opens the bridge only when
  `MCTL_BRIDGE_ENABLED=true`. It resolves the URL from `COMMERCE_DB_URL` and falls back
  to `AUDIT_DB_URL`. That fallback conflicts with owner decision D2 (#957 §6b), and
  mctl-api#987 tracks its removal.
- Every other store also runs DDL at startup: `internal/commerce/store.go`,
  `internal/workitems/store.go` and the bridge. This slice's no-DDL rule is a deliberate
  departure, as in the #959 proposal.
- Immutability precedent: `internal/decisions/store.go` defines
  `decision_records_immutable()`, a `BEFORE UPDATE` trigger function that raises. Schema
  serialization precedent: `internal/principals/store.go:133` uses
  `pg_advisory_xact_lock(hashtext('principals-schema'))`.
- Hash precedent: `workitems.IntentHash` (`internal/workitems/action_approvals.go:334`)
  is a versioned, length-prefixed `key:len:value\n` encoding hashed to
  `sha256:<hex>`.
- `we_` ids come from `internal/workitems` (`ExecutionIDPrefix = "we_"` in
  `types.go:27`). `Store.ExecutionByID` and `ResolveExecution` resolve an execution to
  its work item and tenant. There is no tx-aware variant yet: the store only has a
  private `withTx` (`store.go:266`).
- `internal/pgshared` provides `Open`/`Release` for the shared pool.
- Postgres tests use `TEST_DATABASE_URL` and skip when it is unset
  (`internal/bridge/outbox_pg_test.go:38`).
- The #959 connection store (`glovo_installs`, `glovo_connections`,
  `glovo.ApplySchema`, `NewStore` with no DDL, `LiveConnection(ctx, owner)`) is not in
  the clone. Issue #959 is OPEN, and its proposal is `status: proposed`. This slice
  depends on it only through an interface.

Deployed state checked:

- `mctl_get_service_config(team=admins, service=mctl-api)` returned
  "service not found: admins/mctl-api". mctl-api is not a tenant catalogue service, so
  its live env (`COMMERCE_DB_URL`, `WORK_ITEMS_DB_URL`, `MCTL_BRIDGE_ENABLED`) was **not
  observed**.
- `$MCTL_GITOPS_ROOT/services/` lists `admins`, `karabu`, `labs` and `namax66`. None of
  them has an `mctl-api` directory, so no deployed mctl-api values were read there.
- `helm/` in the clone has no `COMMERCE_DB_URL`, `GLOVO_*` or `BRIDGE` entries (grep
  found nothing).
- Read for cross-slice alignment, not deployed state: the proposals under
  `agents-state/mctl-api/proposals/` for issue-959 (schema, `ApplySchema`, grants),
  issue-954 (earlier `provider_orders` model), issue-957 (§2a refs, §6b one transaction)
  and issue-985 (`OrderIndex` interface). All four are `proposed` or under amendment, not
  merged.
- Gap: whether the bridge currently runs on an explicit `COMMERCE_DB_URL` or on the
  `AUDIT_DB_URL` fallback is unknown. See Open questions in requirements.md.

## Proposed solution

### Package and wiring

There is one new package, `internal/glovo/orders`. It has no route, no MCP tool and no
`cmd/api/main.go` change, so the server's behaviour and the MCP tool count do not change.
#957 and #985 construct the store from `bridge.Store.Pool()` when they wire their routes.

```go
func ApplySchema(ctx context.Context, migrationConnStr, runtimeRole string) error // migration role only
func NewStore(ctx context.Context, pool *pgxpool.Pool, conns Connections, execs Executions, opts ...Option) (*Store, error) // no DDL
func (s *Store) Ready(ctx context.Context) error // version + to_regclass re-check

type Scope struct{ Tenant, PrincipalID string } // from the verified caller, never a body
type Connections interface { // satisfied by the #959 store (adapter)
    LiveConnection(ctx context.Context, tenant, principalID string) (*LiveConn, error) // ErrNoConnection
}
type LiveConn struct{ ConnectionID, InstallID string; InstallRevision int64 }
type Executions interface { // tx-aware; #957 supplies the workitems adapter
    ExecutionTenantTx(ctx context.Context, tx pgx.Tx, executionID string) (tenant string, err error)
}

type CreateInput struct{ Scope Scope; IdempotencyKey string; Basket Basket }
func (s *Store) Create(ctx, tx pgx.Tx, in CreateInput) (*Order, bool /*replayed*/, error)
func (s *Store) AppendSnapshot(ctx, tx pgx.Tx, sc Scope, orderRef string, expectedVersion int64, b Basket) (*Snapshot, error)
func (s *Store) Finalize(ctx, tx pgx.Tx, sc Scope, orderRef string, expectedVersion int64) (*Order, error)
func (s *Store) Get(ctx, q Querier, sc Scope, orderRef string) (*Order, error)
func (s *Store) LockOrder(ctx, tx pgx.Tx, sc Scope, orderRef string) (*Order, error) // FOR UPDATE
func (s *Store) Transition(ctx, tx pgx.Tx, sc Scope, orderRef string, expectedVersion int64, to State, refs TransitionRefs) (*Order, error)
func (s *Store) RecordEffect(ctx, tx pgx.Tx, sc Scope, orderRef string, kind EffectKind, executionID, idempotencyKey string) (*Effect, bool, error)
func (s *Store) Snapshot(ctx, q Querier, sc Scope, orderRef string, seq int) (*Snapshot, error)
func Fingerprint(b Basket) (string, error) // pure
```

Every write method takes the caller's `pgx.Tx` and never begins, commits or rolls it
back. That is #957 §6b: one transaction on the bridge pool for the order, the `we_`, the
`aar_` and (in #985) `bridge_commands`. `NewStore` accepts a pool, not a URL, so the
store cannot fall back to `AUDIT_DB_URL` by itself. The pool's provenance stays a wiring
concern of #957/#987.

`NewStore` with a nil `Connections` or `Executions` returns a store whose `Ready`
reports `not_ready` and whose every write method refuses with `not_ready`.

### Schema (`schema.go`, applied only by `ApplySchema`)

```sql
CREATE TABLE IF NOT EXISTS glovo_join_refs (
  kind TEXT NOT NULL, ref TEXT NOT NULL, tenant TEXT NOT NULL,
  principal_id TEXT NOT NULL DEFAULT '', subject_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (kind, ref), UNIQUE (kind, tenant, subject_id));
CREATE TABLE IF NOT EXISTS glovo_orders (
  order_id TEXT PRIMARY KEY,               -- pord_ + 26 base62, internal only
  order_ref TEXT NOT NULL UNIQUE,          -- ordr_ + 26 base62, external
  tenant TEXT NOT NULL, owner_principal_id TEXT NOT NULL,      -- prn_
  connection_id TEXT NOT NULL, install_id TEXT NOT NULL,       -- gcn_, gin_
  install_revision BIGINT NOT NULL,
  provider TEXT NOT NULL DEFAULT 'fake',
  state TEXT NOT NULL DEFAULT 'open',
  final_basket_fingerprint TEXT NOT NULL DEFAULT '',
  final_snapshot_seq INTEGER NOT NULL DEFAULT 0,
  approval_ref TEXT NOT NULL DEFAULT '', command_id TEXT NOT NULL DEFAULT '',
  idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL,
  version BIGINT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE (tenant, owner_principal_id, idempotency_key));
CREATE INDEX IF NOT EXISTS glovo_orders_owner_key
  ON glovo_orders (tenant, owner_principal_id, connection_id, install_revision);
CREATE TABLE IF NOT EXISTS glovo_order_snapshots (
  order_id TEXT NOT NULL REFERENCES glovo_orders (order_id), seq INTEGER NOT NULL,
  basket_fingerprint TEXT NOT NULL, fingerprint_version TEXT NOT NULL,
  basket_canonical BYTEA NOT NULL, line_count INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL, PRIMARY KEY (order_id, seq));
CREATE TABLE IF NOT EXISTS glovo_order_effects (
  effect_id TEXT PRIMARY KEY,              -- pef_
  order_id TEXT NOT NULL REFERENCES glovo_orders (order_id),
  tenant TEXT NOT NULL, owner_principal_id TEXT NOT NULL,
  effect_kind TEXT NOT NULL,               -- place_order_fake | cancel_order_fake
  execution_id TEXT NOT NULL UNIQUE,       -- we_: one execution per effect
  basket_fingerprint TEXT NOT NULL,
  idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  UNIQUE (tenant, owner_principal_id, idempotency_key));
CREATE TABLE IF NOT EXISTS glovo_order_events (
  id BIGSERIAL PRIMARY KEY, tenant TEXT NOT NULL, order_ref TEXT NOT NULL,
  actor_principal_id TEXT NOT NULL, event TEXT NOT NULL,
  from_state TEXT NOT NULL DEFAULT '', to_state TEXT NOT NULL DEFAULT '',
  snapshot_seq INTEGER NOT NULL DEFAULT 0, recorded_at TIMESTAMPTZ NOT NULL);
CREATE INDEX IF NOT EXISTS glovo_order_events_order ON glovo_order_events (tenant, order_ref, id);
CREATE TABLE IF NOT EXISTS glovo_orders_schema_version (version INT NOT NULL);
```

A `DO $$` block in the `internal/commerce` style adds named CHECKs:

- `provider = 'fake'`
- `state IN ('open','finalized','approved','dispatched','cancelled','closed')`
- the prefix checks (`order_id LIKE 'pord\_%'`, `order_ref ~ '^ordr_[A-Za-z0-9]{26}$'`,
  `owner_principal_id LIKE 'prn\_%'`, `execution_id ~ '^we_[A-Za-z0-9]{16,40}$'`)
- `kind IN ('tenant','principal','order')`
- `effect_kind IN ('place_order_fake','cancel_order_fake')`
- `state = 'open' OR final_basket_fingerprint <> ''`
- `state <> 'approved' OR approval_ref LIKE 'aar\_%'`
- `state NOT IN ('dispatched','closed') OR command_id LIKE 'cmd\_%'`

Triggers are created behind a `pg_trigger` existence test:

- `glovo_orders_immutable_rows()` on snapshots, effects, events and join refs refuses
  `BEFORE UPDATE OR DELETE` unconditionally.
- `glovo_orders_guard()` on `glovo_orders` refuses `DELETE`. On `UPDATE` it refuses any
  change to `order_id`, `order_ref`, `tenant`, `owner_principal_id`, `connection_id`,
  `install_id`, `install_revision`, `provider`, `idempotency_key` or `request_hash`. It
  also refuses any change to `final_basket_fingerprint` or `final_snapshot_seq` once they
  are non-empty or non-zero.
- No GUC escape hatch exists, consistent with the rejection in the #959 proposal.

`ApplySchema` opens its own connection with `migrationConnStr` and runs everything in one
transaction under `pg_advisory_xact_lock(hashtext('glovo-orders-schema'))`. It upserts
the schema version, then issues the runtime grants to `pgx.Identifier{runtimeRole}`
(validated `^[a-z_][a-z0-9_]{0,62}$`):

- `SELECT, INSERT, UPDATE` on `glovo_orders`
- `SELECT, INSERT` on `glovo_order_snapshots`, `glovo_order_effects`,
  `glovo_order_events` and `glovo_join_refs`
- `USAGE` on the events sequence
- `SELECT` on `glovo_orders_schema_version`

The migration role owns every object, so the runtime role cannot `ALTER`, `DROP` or
`DISABLE TRIGGER`.

### Owner scoping and the closed refusal set (`refusal.go`)

- `type Refusal struct{ Code Code }` uses the codes listed in requirements.md. It has no
  free-text description that could carry an id. I/O errors are wrapped with
  `fmt.Errorf("glovo/orders: ...: %w", err)` and are never refusals.
- Every order lookup is one statement:
  `SELECT ... FROM glovo_orders WHERE order_ref=$1 AND tenant=$2 AND owner_principal_id=$3`.
  `LockOrder` adds `FOR UPDATE`. A miss is `order_not_found`, with no second probe that
  could tell "foreign" from "missing", so the query count and the response are identical.
- A ref that fails `^ordr_[A-Za-z0-9]{26}$` is also `order_not_found`. It still runs the
  same statement (it will match nothing), so the malformed path takes the same work as a
  well-formed miss.
- Refs are random and never derived from a raw id. Error values never include an id.
  `Order` has an exported `OrderRef` and keeps `order_id` unexported (used only for
  joins inside the package).

### Connection and install revision binding

`Create` calls `Connections.LiveConnection(tenant, principal)`:

- `ErrNoConnection` (absent or revoked) maps to `connection_revoked`.
- Any other error maps to `not_ready`.
- On success, the live `connection_id`, `install_id` and `install_revision` are stored on
  the order.

Every mutation (`AppendSnapshot`, `Finalize`, `Transition`, `RecordEffect`) runs the same
check after `LockOrder`:

- no live connection: `connection_revoked`
- live connection id differs from the order's: `connection_revoked` (a reconnect mints a
  new `gcn_` in #959)
- live install revision differs: `install_revision_stale`

`Get` and `Snapshot` return an order and its snapshots even after revocation, so the
owner can still inspect them. Writes are refused.

### Snapshots and fingerprint (`basket.go`)

`Basket{StoreRef, Currency string; Items []Item{SKU string; Quantity int}}` is validated
as follows:

- 1 to 100 items
- unique SKUs
- quantity 1 to 99
- `Currency` matches `^[A-Z]{3}$`
- `SKU` and `StoreRef` match `^[A-Za-z0-9._-]{1,64}$`
- anything else is `invalid_basket`

Canonical encoding: items are sorted by SKU, then written as
`mctl-basket/v1\n`, `store_ref:<len>:<v>\n`, `currency:<len>:<v>\n` and
`items:<n>\n`, followed by `sku:<len>:<v>\nquantity:<len>:<v>\n` per item. This is the
`IntentHash` style with its own version tag, so it can never collide with an action
intent hash. `Fingerprint` is `sha256:<hex>` of those bytes. The encoding is stored in
`basket_canonical`, so a reader can re-verify `Fingerprint == sha256(basket_canonical)`.

`AppendSnapshot`:

1. Lock the order.
2. Require `state='open'` and `version = expectedVersion`, otherwise
   `order_finalized` or `order_state_conflict`.
3. Insert at `seq = max+1`.
4. Bump the version and append an event.

`Finalize` runs
`UPDATE ... SET state='finalized', final_basket_fingerprint=$fp, final_snapshot_seq=$seq, version=version+1 WHERE order_id=$1 AND state='open' AND version=$v AND final_basket_fingerprint=''`
from the latest snapshot. A finalize with no snapshot is `invalid_basket`. A changed
basket after finalization needs a new order. The old snapshot rows stay untouched, and
the triggers guarantee that even for raw SQL.

### State machine

`Transition` enforces this table in Go:

| From | Allowed targets |
|---|---|
| `open` | `cancelled` (`finalized` only through `Finalize`) |
| `finalized` | `approved` (requires an `aar_` in refs), `cancelled` |
| `approved` | `dispatched` (requires a `cmd_`), `cancelled` |
| `dispatched` | `closed`, `cancelled` |

The database CHECKs back the same table. Any other move is `order_state_conflict`. This
slice calls none of `approved`, `dispatched` or `closed` itself; M1b/2 and #985 do.

### One `we_` per effect

`RecordEffect`:

1. Lock the order and require `finalized` or later.
2. Call `Executions.ExecutionTenantTx(tx, we)` and require the result to equal
   `Scope.Tenant`. A miss or foreign tenant is `order_not_found`.
3. Insert with `ON CONFLICT DO NOTHING`.

Conflict handling:

- A conflict on `(tenant, owner, idempotency_key)` with the same request hash replays.
  With a different hash it is `idempotency_key_reused`.
- A conflict on `execution_id` is `execution_already_bound`.

The effect copies the order's `final_basket_fingerprint`.

### Idempotent concurrent create

The request hash is a length-prefixed sha256 of (tenant, principal, idempotency key,
basket fingerprint). `Create` runs:

```
INSERT INTO glovo_orders (...) VALUES (...)
ON CONFLICT (tenant, owner_principal_id, idempotency_key) DO NOTHING
RETURNING order_ref
```

If no row is returned, it selects the existing row and compares `request_hash`. A second
concurrent transaction blocks on the unique index until the first commits, then sees the
row and replays. If the first rolls back, the second inserts. The `glovo_join_refs` row
and the first snapshot (seq 1) are written in the same transaction.

### Audit

Each mutation appends one `glovo_order_events` row on the same transaction. The row holds
only the `ordr_`, actor `prn_`, event, from/to state and snapshot sequence. It holds no
fingerprint (a low-entropy basket could be brute-forced from it), no basket and no
provider data. `slog` lines from the package log only refusal codes and `ordr_` refs.

## Alternatives

1. **`CREATE TABLE IF NOT EXISTS` in `NewStore`, like the bridge and commerce.**
   Dropped. The issue and the #959 owner decision require DDL only under a migration
   role. A runtime role that owns the tables could disable the immutability triggers.
2. **A separate `GLOVO_ORDERS_DB_URL` with its own pool and its own transactions, like
   #954's earlier `provider_orders` design.** Dropped. #957 §6b (owner D2) requires the
   order writes to share the bridge's `pgx.Tx`, and an own-URL store reintroduces the
   fallback and TOCTOU questions. Taking a pool closes both.
3. **Store only the fingerprint and keep the basket with the worker (#954's earlier
   model).** Not chosen, but kept as an open question. #985 builds the provider payload
   from the order index, and re-verifying the fingerprint needs the canonical bytes. The
   bytes are synthetic, in a private column, and never appear in events.
4. **Extend #959's `glovo_audit_events` (`entity_kind IN (install, connection)`) for
   order events.** Dropped. That would alter another slice's CHECK and schema version
   before it merges. A separate append-only table keeps the slices independent.

## Platform impact

- **Migrations:** five new tables, one version table, CHECKs and two trigger functions.
  All are additive and applied only by `orders.ApplySchema`. No existing table changes.
  Nothing runs at startup because nothing constructs the store in this slice.
- **Backward compatibility:** no route, MCP tool, env var or `main.go` change. The MCP
  tool count in `internal/mcp/server_test.go` is unchanged. `glovo.Default` stays
  closed.
- **Resources:** none at runtime until a later slice wires the store. When it is wired,
  each mutation is a few indexed statements on the existing bridge pool.
- **Risks and mitigations:**
  - *Cross-tenant enumeration.* Mitigated by single-statement owner-scoped lookups,
    random refs, id-free refusals and tests that compare query counts and responses for
    foreign and missing refs.
  - *Snapshot mutation after approval.* Mitigated by database triggers plus CAS on
    `state='open'`, tested with raw SQL under the runtime role.
  - *Connection revoked in another database (`GLOVO_DB_URL`).* Mitigated by a re-check
    on every mutation. The remaining window is the #957 §6b TOCTOU test's
    responsibility, and the write fence stays refusing until it passes.
  - *The bridge pool coming from the `AUDIT_DB_URL` fallback.* Out of this slice's
    control. It is noted for #987 and #957 readiness.
  - *Fingerprint version drift.* The version tag is part of the hash and stored per
    snapshot. A new encoding needs a new tag.
- **Dependencies:** #959 for the real `Connections` implementation. Until it lands, tests
  use a fake, and readiness stays `not_ready`. This slice blocks M1b/2, #985 and M1b/4.
  Hold mctlhq/mctl-gitops#2457 stays ON.
