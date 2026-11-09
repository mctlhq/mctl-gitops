# Design: issue-959-feat-glovo-m1a-2-tenant-principal-connec

## Amendment 2026-11-09 (b) — owner decision A, companion to #985/#988/#989

Owner decision A (2026-11-09): connections, orders, `aar_` and the bridge live in **one
physical Postgres database** and share one `pgx.Tx`. This section supersedes every
earlier text in this proposal that leaves the database URL open or lets the store fall
back to `AUDIT_DB_URL`. It is the #959 side of the #985 review P2-4/P2-6 and the #989
review P2-3/P2-6 fixes in the same PR.

| Driver | Change in this slice |
|---|---|
| Decision A: one physical database, explicit URLs | The store lives in the Postgres schema `glovo` (`glovo.glovo_installs`, `glovo.glovo_connections`, …) of the same database as the bridge, the work items and the #988 orders. `GLOVO_DB_URL` must be set explicitly; there is no `AUDIT_DB_URL` fallback. Same-database is proven by #985 `control.ProveOneDatabase`, not by URL equality |
| Least privilege across pools | Role table below: the migration role owns every `glovo` object; the Glovo runtime role keeps its DML; the bridge and work-items runtime roles get `USAGE` on schema `glovo` and `SELECT` on `glovo_installs` and `glovo_connections` only |
| #985/#988/#989 need tx-scoped reads on their transaction | `LockOwnerShared(ctx, tx, tenant, principal)` (L1 shared, L2 shared) and `LiveConnectionTx(ctx, tx, owner)` (no row lock; valid because every writer holds L2 exclusive). Neither begins or commits |
| One lock order | L1 and L2 here are levels L1 and L2 of the canonical order in #957 design §6b. Readers on the Glovo write path take both shared; every connection write takes L1 shared (L1 exclusive for install changes) and L2 exclusive |
| Revocation must fence open bridge commands (#985 review P2-4) | Every revoker (`Revoke`, including reason `membership_removed`, `RevokeInstall`, `Reinstall`, and terminal `Transition`s) calls the installed `RevocationHook` in the **same transaction**, after L1/L2 and the row updates, with the ended `gcn_` ids. #985 installs `bridge.CancelOpenForConnections`, which runs the `SECURITY DEFINER` function `bridge_cancel_open_for_connections(text[], text)` (L5, `ORDER BY command_id`) |
| Membership loss | New reason `membership_removed` and `RevokeForMembership(ctx, tenant, principal, actor)`. Who detects membership removal and calls it is an OPEN item |
| Timeout fencing must still be proven | `expired` through `Transition` is a revoker too, so the hook runs; T17 covers revoke-after-approval-before-permit and expiry-before-permit |

### Role table (owner decision A)

| Role | Objects | Rights |
|---|---|---|
| migration role | every object in schema `glovo` | owner; runs `ApplySchema` only |
| Glovo runtime role (`GLOVO_DB_URL`) | `glovo_installs`, `glovo_connections`, `glovo_connect_requests` | `SELECT, INSERT, UPDATE` |
| | `glovo_audit_events` | `SELECT, INSERT` |
| | `glovo_pilot_allowlist` | `SELECT, INSERT, DELETE` |
| | `bridge_cancel_open_for_connections(text[], text)` | `EXECUTE` (granted by #985's bridge DDL) |
| bridge runtime role (`COMMERCE_DB_URL`), work-items runtime role (`WORK_ITEMS_DB_URL`) | schema `glovo` | `USAGE` |
| | `glovo_installs`, `glovo_connections` | `SELECT` only |

No role other than the migration role owns a `glovo` object, so no runtime role can
`ALTER`, `DROP` or `DISABLE TRIGGER`. If the three URLs resolve to the same role, the
rights are the union and the ownership rule still holds; `Ready` checks ownership,
not role names.

### Tx-scoped API and revocation hook

```go
// LockOwnerShared takes L1 (install key) shared, then L2 (owner key) shared, on tx.
func (s *Store) LockOwnerShared(ctx context.Context, tx pgx.Tx, tenant, principal string) error
// LiveConnectionTx reads the owner's live connection on tx without a row lock.
// The caller must hold L2 (shared or exclusive).
func (s *Store) LiveConnectionTx(ctx context.Context, tx pgx.Tx, owner Owner) (*Connection, error)
// RevocationHook is called by every revoker in its own transaction, after the
// connection rows are ended, with the ended connection ids.
type RevocationHook func(ctx context.Context, tx pgx.Tx, ended []string, actor string) error
func WithRevocationHook(h RevocationHook) Option
func (s *Store) RevokeForMembership(ctx context.Context, tenant, principal, actor string) ([]Connection, error)
func (s *Store) Ready(ctx context.Context) error
```

- A hook error rolls the revoker back: no connection is ended without its commands
  being cancelled.
- Without a hook, revokers still work (the M1a store stays usable), but `Ready` reports
  `revocation_hook_missing`. #985 and #989 treat that as `not_ready`, so no Glovo
  write can be dispatched or permitted.
- `Ready` also checks: `GLOVO_DB_URL` set explicitly, the schema version, table owners
  are not `current_user`, and the audit and no-delete triggers are enabled.


## Amendment 2026-11-09 — joint 959/960/961 AMEND

Independent review of digest `sha256:718181577b889372ffec9eb565489b3cf53130b7e9a3b2545f0de65198467651` (mctl-api#959, comment of 2026-11-09) required one joint amendment across #959, #960 and #961. Finding -> change in this slice:

| Finding | Change |
|---|---|
| P2 runtime role is not the table owner, but `NewStore` runs DDL with the runtime `connStr` | DDL moves to `ApplySchema(ctx, migrationConnStr)` under a migration role; `NewStore` runs no DDL and checks the schema version; runtime grants are DML only; tests T14 prove the runtime role cannot `ALTER`, `DROP` or `DISABLE TRIGGER` (task 4, A5) |
| P3 "No Glovo code exists" is stale; #977 ships `internal/glovo` | Current state corrected; this slice extends `internal/glovo` and reuses `glovo.Code`/`glovo.Error` instead of a parallel `RefusalCode`/`Refusal` (task 1) |
| P3 open question still offers store-configurable retention | Open question replaced: retention is the documented 400-day obligation, enforced only by a future privileged maintenance design |
| P3 T7 races `Reinstall` but not `RevokeInstall` | T7 now also races `Connect` against `RevokeInstall` |
| P3 carry-over from mctl-telegram#1258: only revoke/cancel purge state | Per-terminal-state retention and purge table added (section "Terminal-state purge"); T15 drives every terminal path |
| Cross-slice: #961 needs `expires_at`, audit `actor_kind`; #960 task 0 needs the allowlist DDL and the refusal enum from this slice | `glovo_connections.expires_at`, `glovo_audit_events.actor_kind`, the `glovo_pilot_allowlist` DDL with `IsAllowlisted`, and the full closed refusal enum are added here |

### Joint contract frozen for #959, #960 and #961 (identical text in all three)

Verified against mctl-api main `a9ca5814` (#977 merged) and the merged #968 bridge (`docs/bridge.md`). Where an earlier section of this document disagrees, this contract wins.

| Item | Frozen value | Owner slice |
|---|---|---|
| Go package | extend the existing `internal/glovo` from #977 (`glovo.Code`, `glovo.Error`, `glovo.Gate`, `glovo.WriteError`); no parallel `RefusalCode`/`Refusal` type | #959 adds the codes |
| Tables | `glovo_installs`, `glovo_connections`, `glovo_connect_requests`, `glovo_audit_events`, `glovo_pilot_allowlist` | #959 (DDL) |
| | `glovo_handoff_refs`, `glovo_rate_counters` | #961 (DDL) |
| | `oauth_team_grants`, `oauth_refresh_tokens.team_grant_id` (refresh-store database) | #960 |
| Columns | reconnect link `supersedes_id`; `glovo_connections.expires_at TIMESTAMPTZ NULL`; `glovo_audit_events.actor_kind` (`user`, `owner`, `admin`, `worker`, `system`) | #959 |
| Store API | `Install`, `GetInstall`, `RevokeInstall`, `Reinstall`, `Connect`, `Reconnect`, `Transition`, `Revoke`, `GetConnection`, `LiveConnection`, `ListAudit`, `IsAllowlisted` | #959 |
| Store states | `pending_handoff`, `pending_provider`, `active`, `expired`, `failed`, `revoked`; wire `PublicState`: both `pending_*` -> `pending`, the rest unchanged | #959 states, #961 mapping |
| Refusal enum (closed, `glovo.Code`) | `not_ready`, `unavailable`, `not_authorized`, `invalid_request`, `not_found`, `no_install`, `ambiguous_tenant`, `no_tenant`, `scope_unsupported`, `not_in_pilot`, `stale_install`, `stale_version`, `no_connection`, `connection_exists`, `connection_revoked`, `connection_expired`, `invalid_transition`, `idempotency_key_reused`, `rate_limited` | #959 |
| HTTP status | 503: `not_ready`, `unavailable`; 401/403: `not_authorized` (401 only when no valid token); 400: `invalid_request`; 404: `not_found`; 403: `no_install`, `ambiguous_tenant`, `no_tenant`, `scope_unsupported`, `not_in_pilot`; 429: `rate_limited`; 409: every other code. One function, `glovo.Status(code)` | #959 |
| Membership lost | `no_tenant` everywhere (resolver, facade, worker check); `not_authorized` only for a wrong audience or identity kind | all |
| Refusal body | #977's `glovo.WriteError` shape `{"error": <code>, "error_description": <fixed text per code>}`. No `schema`/`refusal` envelope on refusals; success bodies keep their `schema` field. This is the shape mctl-api#957 and mctl-telegram#1235 vendor | all |
| Kill switch | one name, `GLOVO_ENABLED`, default `false`, read once in `cmd/api/main.go`. Open only when `GLOVO_ENABLED=true` **and** every readiness dependency is configured and healthy. `GLOVO_MCP_RESOURCE` alone never opens anything. `GLOVO_OAUTH_ENABLED` and `GLOVO_DISABLED` are withdrawn | #960 introduces, #961 reuses |
| DDL role | DDL runs only through `glovo.ApplySchema(ctx, migrationConnStr)` with a dedicated migration role that owns the objects. `NewStore(ctx, runtimeConnStr)` runs no DDL: it pings and checks the recorded schema version, failing closed on a mismatch. The runtime role gets only the DML it needs (no UPDATE/DELETE on `glovo_audit_events`, no DELETE on `glovo_connections`), so it cannot `ALTER`, `DROP` or `DISABLE TRIGGER`. A test proves each of the three refusals | #959 builds it, #961 extends it |
| Worker identity | none exists today: `auth.IsGlovoWorker()` is the reserved stub (`internal/auth/oidc.go`, always false). #961 builds it, default OFF. It is distinct from the #968 bridge provider (`service:bridge-provider:<ref>`, `bridge:provide`): the Glovo worker is refused on `/api/v1/bridge/*` and the bridge provider on `/api/v1/glovo/*`, tested both ways. Its credential is test-only until the issuer decision (mctl-gitops#2506 / #2540) | #961 |
| Facade routes | `/api/v1/glovo/facade/*` is added to #977's empty `glovoAudienceRoutes` by #961 (the only slice that adds those routes) | #961 |
| Allowlist routes | `PUT\|DELETE /api/v1/glovo/pilot/{tenant}/principals/{principal_id}` are defined only in #960 | #960 |

## Current state

- mctl-api#977 (merged `a9ca5814`) ships `internal/glovo` with `glovo.Code`
  (`not_ready`, `not_authorized`), `glovo.Error`, `glovo.WriteError` and the
  closed `glovo.Gate`. It has no store, table or connection code. This slice
  extends that package.
- Every durable store follows one pattern: its own package under
  `internal/<name>/store.go`. A `const <name>Schema` string holds idempotent
  DDL (`CREATE TABLE IF NOT EXISTS`, `CREATE ... INDEX IF NOT EXISTS`,
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`). `NewStore(ctx, connStr)`
  opens a pool with `pgshared.Open` (`internal/pgshared/pool.go`), pings,
  executes the schema, and returns the store. See
  `internal/commerce/store.go` (`commerceSchema`, `NewStore`, `withTx`)
  and `internal/lifecycle/store.go` (`lifecycleSchema`). There is no
  migration framework and no `.sql` files. "Migrations" are additive DDL
  applied on start.
- Named CHECK constraints are added outside `CREATE TABLE` in a `DO $$`
  loop that tests `pg_constraint` and handles `duplicate_object`. This
  covers tables created by earlier builds and two pods cold-starting at
  once. See `internal/commerce/store.go` around the
  `commerce_invocations_phase_check` block.
- Write serialization uses `pg_advisory_xact_lock(hashtext($1))` inside
  the transaction: `commerce.Store.withTx`, `workitems/store.go:272`,
  `principals/link.go:98`, `lifecycle/store.go:1468`. Schema application
  is serialized the same way in `principals/store.go:133` and
  `auth/clientstore/postgres.go:86`.
- Immutable rows are enforced with a `BEFORE UPDATE` trigger that raises.
  See `decision_records_immutable()` in `internal/decisions/store.go`
  (lines ~114-131), and `internal/evidence/store.go` and
  `internal/deployplan/store.go`.
- IDs: canonical principals are `prn_<ULID>` (`principals.PrincipalIDPrefix`
  in `internal/principals/ulid.go`). `commerce.newULID` is a local copy of
  the ULID minting, kept local "so this package does not depend on the
  principals store". Tenants are referenced by their name as `TEXT`
  (`work_items.tenant`, `commerce_*.tenant_id`).
- Scoped reads return a package `ErrNotFound` (e.g.
  `principals.ErrNotFound`). Commerce scopes every read by `tenant_id`, so a
  foreign ID is a plain miss (`GetQuote(ctx, tenantID, quoteID)`).
- Audit-shaped tables are append-only event tables keyed by `BIGSERIAL`:
  `lifecycle_events`, `commerce_invocation_transitions`,
  `work_item_events`. Retention that drops content but keeps the row exists
  for `work_item_intents.text`.
- `internal/secretscan.Scan(content []byte) (pattern string, found bool)`
  detects secret-shaped values. It is reusable for a "no secrets in
  fixtures/audit" test.
- DB tests use `TEST_DATABASE_URL` and `t.Skip` when it is unset
  (`internal/commerce/store_test.go:newTestStore`). CI provides
  `postgres:16` in `.github/workflows/validate.yml`. Concurrency tests
  exist (`TestConcurrentAcceptsOfOneKeyYieldOneRow`).
- Stores are wired in `cmd/api/main.go` through `initStore(...)` with an
  env DB URL that falls back to `AUDIT_DB_URL` (commerce at ~line 556). The Glovo store
  does **not** follow that fallback: `GLOVO_DB_URL` is required (Amendment (b)).

Deployed state checked:
- `mctl_get_service_config(team=admins, service=mctl-api)` returned
  `service not found: admins/mctl-api`. mctl-api is not a catalogue
  tenant service, so its deployed env (DB URLs) could not be observed.
- `$MCTL_GITOPS_ROOT/services/*/`: no `mctl-api/values.yaml` exists under
  `admins`, `karabu`, `labs` or `namax66`. Grepping `services/` for
  `glovo` returned nothing. Not observed, so this design assumes nothing
  about the deployed DB URL and does not wire production startup (see
  Open questions in requirements.md).
- Sibling issues read with `gh`: #953 (parent), #958, #960, #961, #954
  exist and are OPEN. This slice's scope was cut against them.

## AMEND 2026-11-08 — mandatory corrections to original schema/test draft

The previously proposed `glovo_audit_immutable()` exception based on `current_setting('glovo.retention_sweep', true)` is **REJECTED** because caller-controlled custom settings do not prove privileged maintenance identity. The M1 trigger must always `RAISE EXCEPTION` for UPDATE or DELETE against audit events under the API role; no `SET LOCAL` flag or callable `SweepAudit` may bypass it. Retention is a documented obligation and a future **separately approved** maintenance service/DB-role design, not a runtime task in this slice. A dedicated migration role owns the schema; deny UPDATE/DELETE for runtime DB roles and verify GRANTs explicitly.

The old cleanup helper's `session_replication_role = replica` is also **REJECTED**. Build DB tests with a disposable per-test schema/database and set search_path only on test-owned connections, using an actual limited non-superuser role; after a test, drop the isolated schema/database through the CI test-owner connection. Never disable triggers or mutate shared production fixtures. All lock concurrency tests must operate on an isolated owned test schema and still execute the real triggers.

These amendments supersede the audit retention GUC bypass, the original `SweepAudit` design and the session_replication_role cleanup in subsequent sections. No live migration/production deploy is allowed by proposal approval.

## Proposed solution

Extend the existing package `internal/glovo` from #977 (still no imports from
`internal/api`, `internal/mcp` or `internal/principals`). This slice adds
no route, no MCP tool and no `main.go` wiring.

### Files

- `internal/glovo/types.go`: states, transitions, IDs, refusal codes,
  inputs/outputs.
- `internal/glovo/ids.go`: `newPrefixedID(prefix, now)`, a copy of the
  ULID minting (same reason as `commerce.newULID`). Prefixes: `gin_`
  install, `gcn_` connection, `gae_` audit event, `gsr_` secret reference.
- `internal/glovo/schema.go`: `const glovoSchema` (DDL below).
- `internal/glovo/store.go`: `Store`, `NewStore`, `withTx`, and the
  methods below.
- `internal/glovo/secretref.go`: the `SecretRefs` interface and
  `RefusingSecretRefs`.
- `internal/glovo/*_test.go`: unit tests (no DB) and DB tests
  (`TEST_DATABASE_URL`).
- `internal/glovo/fixtures_test.go`: synthetic fixtures.
- `docs/glovo-connections.md`: data model, state machine, lock order,
  refusal codes, retention, manual down-migration.

### Types (`types.go`)

```go
type InstallState string    // "installed", "uninstalled"
type ConnectionState string // "pending_handoff","pending_provider","active","expired","failed","revoked"

var transitions = map[ConnectionState][]ConnectionState{
    PendingHandoff:  {PendingProvider, Failed, Expired, Revoked},
    PendingProvider: {Active, Failed, Expired, Revoked},
    Active:          {Expired, Failed, Revoked},
}
func (s ConnectionState) Live() bool
func CanTransition(from, to ConnectionState) bool

type Owner struct{ TenantID, PrincipalID string } // validate(): non-empty tenant, "prn_" principal

// Codes are added to #977's glovo.Code; the closed enum is the joint
// contract above. No parallel RefusalCode/Refusal type.
func refuse(c Code) *Error                 // fixed Description per code, no IDs
var ErrNotFound = refuse(CodeNotFound)     // one value for missing AND foreign
func Status(c Code) int                    // the single HTTP mapping (joint contract)
```

A refusal (`*glovo.Error`) carries no IDs or owner data in its message. This keeps a
foreign-ID miss byte-identical to a true miss. The codes match the parent
#953 vocabulary so slice 4 can map them to HTTP without translation.

### Schema (`glovoSchema`)

```sql
CREATE TABLE IF NOT EXISTS glovo_installs (
  install_id       TEXT PRIMARY KEY,                 -- gin_
  tenant_id        TEXT NOT NULL UNIQUE,             -- one install per tenant
  install_revision BIGINT NOT NULL CHECK (install_revision >= 1),
  state            TEXT NOT NULL,
  installed_by     TEXT NOT NULL,                    -- prn_
  created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
  version          BIGINT NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS glovo_connections (
  connection_id    TEXT PRIMARY KEY,                 -- gcn_
  tenant_id        TEXT NOT NULL,
  principal_id     TEXT NOT NULL,
  install_id       TEXT NOT NULL REFERENCES glovo_installs (install_id),
  install_revision BIGINT NOT NULL,
  state            TEXT NOT NULL,
  secret_ref       TEXT,                             -- gsr_ or NULL
  supersedes_id    TEXT NOT NULL DEFAULT '',         -- prior gcn_ on reconnect
  end_reason       TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
  ended_at         TIMESTAMPTZ,
  expires_at       TIMESTAMPTZ,                      -- synthetic expiry, set on activation (#961)
  version          BIGINT NOT NULL DEFAULT 1,
  UNIQUE (tenant_id, principal_id, connection_id, install_revision)
);
CREATE UNIQUE INDEX IF NOT EXISTS glovo_connections_one_live
  ON glovo_connections (tenant_id, principal_id)
  WHERE state IN ('pending_handoff','pending_provider','active');
CREATE INDEX IF NOT EXISTS glovo_connections_tenant_live
  ON glovo_connections (tenant_id, install_revision)
  WHERE state IN ('pending_handoff','pending_provider','active');
CREATE TABLE IF NOT EXISTS glovo_connect_requests (
  tenant_id TEXT NOT NULL, principal_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
  request_hash TEXT NOT NULL, connection_id TEXT NOT NULL REFERENCES glovo_connections,
  created_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (tenant_id, principal_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS glovo_audit_events (
  event_id TEXT PRIMARY KEY,                         -- gae_
  tenant_id TEXT NOT NULL, subject_principal_id TEXT NOT NULL DEFAULT '',
  actor_principal_id TEXT NOT NULL,
  actor_kind TEXT NOT NULL,                          -- user | owner | admin | worker | system
  entity_kind TEXT NOT NULL,                         -- install | connection
  entity_id TEXT NOT NULL, event TEXT NOT NULL,
  from_state TEXT NOT NULL DEFAULT '', to_state TEXT NOT NULL,
  install_revision BIGINT NOT NULL, reason_code TEXT NOT NULL DEFAULT '',
  recorded_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS glovo_audit_events_entity ON glovo_audit_events (tenant_id, entity_id, recorded_at);
CREATE INDEX IF NOT EXISTS glovo_audit_events_recorded ON glovo_audit_events (recorded_at);
CREATE TABLE IF NOT EXISTS glovo_pilot_allowlist (            -- read here, written by #960
  tenant_id TEXT NOT NULL, principal_id TEXT NOT NULL,
  added_by TEXT NOT NULL, added_at TIMESTAMPTZ NOT NULL,
  UNIQUE (tenant_id, principal_id)
);
CREATE TABLE IF NOT EXISTS glovo_schema_version (version INT NOT NULL);
```

Then comes a `DO $$` block in the commerce style that adds the named
CHECKs: `glovo_installs_state_check`, `glovo_connections_state_check`,
`glovo_connections_principal_check` (`principal_id LIKE 'prn\_%'`),
`glovo_pilot_allowlist_principal_check` (`principal_id LIKE 'prn\_%'`),
`glovo_audit_events_actor_kind_check`,
`glovo_connections_secret_ref_check`
(`secret_ref IS NULL OR secret_ref LIKE 'gsr\_%'`), and
`glovo_connections_terminal_check`
(`state IN (live) OR ended_at IS NOT NULL`). A connection's
`install_revision` must equal the install's current revision at creation.
A cross-table CHECK cannot express that, so Go enforces it under the
locks below.

Immutability uses the `internal/decisions` pattern:
`glovo_audit_immutable()` unconditionally refuses `BEFORE UPDATE` and
`BEFORE DELETE` to the runtime role. It has **no** `glovo.retention_sweep` custom-GUC exception or application-exposed sweep. A separate, privileged and reviewed retention-maintenance design is required before any deletion of audit records. Installs and connections have no DELETE path
in Go. A `BEFORE DELETE` trigger on `glovo_connections` refuses
unconditionally, because connection IDs must stay unique forever (never
reused). Triggers are created with the `pg_trigger` existence test.

The whole schema runs in one transaction under
`pg_advisory_xact_lock(hashtext('glovo-schema'))`, as
`principals/store.go:133` does, but only inside `ApplySchema(ctx,
migrationConnStr)`, executed by a dedicated migration role that owns every
`glovo_*` object. It ends by issuing the runtime grants: `SELECT, INSERT,
UPDATE` on `glovo_installs`, `glovo_connections`, `glovo_connect_requests`;
`SELECT, INSERT` on `glovo_audit_events`; `SELECT, INSERT, DELETE` on
`glovo_pilot_allowlist` (the writes are reachable only through #960's admin
routes; #960 has no DDL role and issues no grant of its own). `NewStore`
uses the runtime connection, runs **no DDL**, and fails closed when
`glovo_schema_version` is missing or differs from the compiled version. This
departs from the DDL-in-`NewStore` convention of other mctl-api stores
deliberately: a role that creates a table owns it and could disable the audit
trigger.

### Terminal-state purge

| Terminal event | Purged in the same transaction | Retained |
|---|---|---|
| connection `expired`, `failed`, `revoked` (any reason, incl. `superseded`, `install_revoked`, `install_reinstalled`) | `secret_ref` set to NULL and returned for release; every unconsumed `glovo_handoff_refs` row of the connection (#961) | connection row (id never reused), audit events |
| install `uninstalled` / reinstall | the above for every live connection of the old revision | install row, audit events |
| idempotency rows | not on terminal transition; removed after 24 h by the #961 cleanup restricted to synthetic tables | none |

Every terminal path goes through one `endConnection` helper, so no path can
skip the purge (the gap found in the fake worker of mctl-telegram#1258).

### Locking (revoke-vs-connect safety)

Two advisory keys, always taken in this order inside one transaction:

1. Tenant install key `glovo-install/v1|<tenant>`. Taken **shared**
   (`pg_advisory_xact_lock_shared`) by `Connect`, `Reconnect` and
   connection `Transition`. Taken **exclusive** by `Install`,
   `RevokeInstall` and `Reinstall`.
2. Owner key `glovo-owner/v1|<tenant>|<principal>`. Taken exclusive by
   every connection write for that owner, and shared by the readers on the Glovo
   write path (`LockOwnerShared`: #985 dispatch and cancel, the #989 permit fence).

These are levels L1 and L2 of the canonical lock order in #957 design §6b. A revoker
holds L1 and L2, ends the rows, then calls the `RevocationHook`, which takes L5 (bridge
commands) only.

Keys are length-prefixed (as `commerce.lengthPrefixed`) so a tenant name
containing `|` cannot collide. Under the shared install lock, `Connect`
re-reads the install row with `SELECT ... FOR SHARE` and checks
`state='installed'` and `install_revision = expected`. This gives the
following:

- A connect racing a reinstall/uninstall either commits first, and its new
  connection is then revoked by the reinstall's sweep because the sweep
  runs after the exclusive lock is granted. Or it commits second, and it
  then sees the new revision/state and refuses with `stale_install` or
  `no_install`. No interleaving leaves a live connection on an old
  revision.
- A connect racing a revoke of the same owner's connection is serialized
  by the owner key. A `Reconnect` that observes the connection already
  revoked refuses `no_connection` rather than creating a second chain.
- The partial unique index `glovo_connections_one_live` is the last line
  of defense. A unique violation on it maps to `connection_exists` and
  never to a 500.

### Store API (`store.go`)

All methods take an `Owner` or a tenant plus an actor `prn_`, and they
return `*Refusal` for domain refusals and wrapped errors for I/O
(`fmt.Errorf("glovo: ...: %w", err)`).

```go
func ApplySchema(ctx context.Context, migrationConnStr string) error // migration role only
func NewStore(ctx context.Context, runtimeConnStr string, opts ...Option) (*Store, error) // no DDL
// Option: WithClock(func() time.Time); audit retention is a future privileged maintenance slice
func (s *Store) Close()

func (s *Store) Install(ctx, tenantID, actor string) (*Install, error)          // idempotent if already installed
func (s *Store) RevokeInstall(ctx, tenantID, actor, reason string, expectedRevision int64) (*Install, []Connection, error)
func (s *Store) Reinstall(ctx, tenantID, actor string, expectedRevision int64) (*Install, []Connection, error)
func (s *Store) GetInstall(ctx, tenantID string) (*Install, error)               // no_install

type ConnectInput struct{ Owner Owner; ExpectedInstallRevision int64; IdempotencyKey string }
func (s *Store) Connect(ctx, in ConnectInput) (*ConnectResult, error)           // {Connection, Replayed}
func (s *Store) Reconnect(ctx, in ConnectInput, priorConnectionID string) (*ConnectResult, error)
func (s *Store) Transition(ctx, owner Owner, connectionID string, to ConnectionState,
                           expectedVersion int64, reason string, ref *SecretRef) (*Connection, error)
func (s *Store) Revoke(ctx, owner Owner, connectionID, reason string) (*Connection, error)
func (s *Store) GetConnection(ctx, owner Owner, connectionID string) (*Connection, error) // ErrNotFound
func (s *Store) LiveConnection(ctx, owner Owner) (*Connection, error)                    // no_connection
func (s *Store) ListAudit(ctx, tenantID, entityID string) ([]AuditEvent, error)
func (s *Store) IsAllowlisted(ctx, tenantID, principalID string) (bool, error) // read only
// Audit retention deletion is OUT OF SCOPE for M1; no SweepAudit API is exposed.
```

The returned `[]Connection` from revoke/reinstall are the connections the
call ended, so a later slice can propagate revocation (Temporal signal) and
release secret references after commit.

Every connection query has the form
`WHERE connection_id=$1 AND tenant_id=$2 AND principal_id=$3`, issued as
one statement. A miss returns `ErrNotFound` with no second probe to tell
"foreign" from "missing", so the response and query count are identical.
`Revoke` of an already-revoked own connection is idempotent (returns it,
no new event). `Revoke` of a foreign or missing one returns `ErrNotFound`.

Idempotency: `request_hash` is `sha256` over a length-prefixed encoding of
(tenant, principal, expected revision, prior connection ID). A replay
returns the stored connection in whatever state it is now. Reconnect uses
the same table, so retrying a reconnect never mints a third ID.

### Secret reference (`secretref.go`)

```go
type SecretRef struct{ ID string } // "gsr_<ULID>", opaque; no bytes
type SecretRefs interface {
    Reserve(ctx context.Context, owner Owner, connectionID string) (SecretRef, error)
    Release(ctx context.Context, ref SecretRef) error
}
type RefusingSecretRefs struct{} // returns ErrSecretBackendUnavailable from both
```

The store records only `secret_ref`. On any terminal transition it sets
`secret_ref = NULL` in the same transaction and returns the old ref to the
caller. No secret material is ever passed to the store. The doc comment and
`docs/glovo-connections.md` describe a possible future envelope (random
per-connection DEK, independent KEK) as a design note only. It is
explicitly not called crypto-shredding, because no evidence for erasure
guarantees exists yet.

### Logging

The store logs no row content. Errors carry codes and wrapped pgx errors
only. `slog` is not called with tenant, principal or connection IDs at
info level.

### Synthetic fixtures (`fixtures_test.go`)

- Tenants `tg959-alpha-<rand>` and `tg959-beta-<rand>`. Principals are
  minted `prn_` IDs: `alpha` gets two principals (A1, A2) and `beta` gets
  one (B1). This gives 2 tenants, and 2 principals in one team.
- Negative inputs: A2 using A1's `gcn_`, B1 using A1's `gcn_`, a random
  well-formed `gcn_` that never existed, a stale `install_revision`
  (current-1), and a stale `expected_version`.
- No emails, names, addresses, tokens or cookies. A test runs
  `secretscan.Scan` over every audit row and connection row serialized as
  JSON, and over captured `slog` output.

## Alternatives

1. **Row locks only (`SELECT ... FOR UPDATE`) without advisory locks.**
   This was dropped. `Connect` for an owner with no existing row has
   nothing to lock, so two first-connects could both pass the check. The
   repo convention (`commerce`, `workitems`, `principals`) is an advisory
   xact lock on a deterministic key. The unique index remains as a
   backstop.
2. **New `install_id` per reinstall instead of a revision counter.** This
   was dropped. The issue and parent ask explicitly for "install
   identity/revision" and a "revision bump". A stable `install_id` also
   keeps audit history for one tenant install in one chain. It is
   recorded as an open question.
3. **A versioned migration framework (golang-migrate, goose) with
   up/down `.sql` files.** This was dropped for consistency. Every
   existing store applies idempotent additive DDL on start, and adding a
   framework for one package would split conventions. Down-migration is
   documented as a manual `DROP` script in `docs/glovo-connections.md`.
4. **Putting connections in the existing `principals` or `workitems`
   packages.** This was dropped. Parent #953 wants a distinct Glovo
   authority, and a separate package keeps the blast radius and the review
   surface small.

## Platform impact

- **Migrations:** six new `glovo_*` tables (incl. `glovo_pilot_allowlist`
  and `glovo_schema_version`), applied only by `ApplySchema` under the
  migration role, indexes, CHECKs, and two
  trigger functions. All are additive and idempotent, and nothing existing
  is altered. Because the store is not constructed in `cmd/api/main.go` in
  this slice, nothing is applied to production databases until slice 4
  wires it. The only database touched is the CI `TEST_DATABASE_URL`.
- **Backward compatibility:** there is no API, MCP or route change. The
  MCP tool count is unchanged. Existing packages are not modified.
- **Resources:** none at runtime in this slice.
- **Risks and mitigations:**
  - *Lock-order deadlock.* The order is install key, then owner key,
    everywhere, and it is enforced by a single `withLocks(tenant,
    principal, installMode)` helper. A test runs 50 interleaved
    connect/reinstall goroutines.
  - *Foreign-ID oracle.* There is one query shape and one sentinel. A
    test asserts `errors.Is(err, ErrNotFound)`, an identical `err.Error()`,
    and an identical returned value (nil) for all three miss cases.
  - *Audit tamper protection.* No caller-writable GUC or runtime sweep exists. With the restricted runtime DB role, both raw UPDATE and DELETE of audit rows always fail, including after forged custom-GUC changes.
  - *Shared database with other stores.* All objects carry the `glovo_`
    prefix, and the trigger function names are unique.
  - *Secret leakage.* No column can hold secret bytes (CHECK on the
    `gsr_` shape), and the secretscan test covers fixtures and logs.
