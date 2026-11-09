# Design: issue-959-feat-glovo-m1a-2-tenant-principal-connec

## Amendment 2026-11-09 (c), round 4 of the AMEND PR

Resolves the round-3 findings that land here. Where this section and older text disagree, this section wins.

| Finding | Change here |
|---|---|
| F1 (`now()` is the transaction start time) | Every expiry comparison of this slice uses `clock_timestamp()` (`LiveConnectionTx`, `LiveConnection`, the `Reconnect` terminal branch, `endConnection`, `ActivateTx`). `ActivateInput.ExpiresAt` (a Go `time.Time`) is replaced by `ExpiresIn time.Duration`, and SQL computes `clock_timestamp() + ExpiresIn`. New test T21: a transaction that begins before `expires_at` and reads after it |
| F2 (`endConnection` purged a #961 table) | Option (b): `endConnection` names no #961 table. `WithEndPurger(EndPurger)` is installed by #961; `Ready` reports `end_purger_missing` when `WithEndPurgerRequired(true)` was passed and none is installed. T15 proves the purge both ways, T20 runs with and without the #961 tables |
| F3 (grant paragraph vs table) | The body no longer lists grants: `ApplySchema` issues exactly the #959 rows of #957 §6d.1. T12 and T16 read the same rows |
| #961 N1 (worker has no owner) | New `GetConnectionForWorker(ctx, id)` (worker-only read), see Store API |
| #961 N3 (`Ready` and the #961 tables) | `Ready` checks the grants of every table that exists in schema `glovo` against `glovo.expectedGrants`, the Go mirror of the `glovo.*` rows of #957 §6d.1 to which each slice adds its own rows in its own PR; a table with no row is `not_ready`, a row whose table is absent is skipped unless required |
| X-2 (`ApplySchema` signature) | `ApplySchema(ctx, migrationConnStr, runtimeRole string)` everywhere (task 4 was missing `runtimeRole`) |

## Amendment 2026-11-09 (c), round 2 of the AMEND PR

Re-review of the AMEND PR head `dc1fe6e5` against mctl-api `ceac9ed`. The cross-slice
seams (roles and grants, interfaces, refusal codes) now have one owner, mctl-api#957
design §6d and §4; this slice references them and no longer restates them. Where this
section and older text disagree, this section wins; the older passages are edited.

| Finding | Change |
|---|---|
| F1 (consumers use names #959 does not have) | The #959 interface is listed once in #957 §6d.4 and below, verbatim: `LockOwnerShared(ctx, tx, tenant, principal)`, `LiveConnectionTx(ctx, tx, owner glovo.Owner) (*glovo.Connection, error)`, `RevocationHook`, `WithRevocationHook`, `Ready`. #985 and #988 cite exactly these. "Membership detector exists" is a separate signal, `WithMembershipRevoker(name)` / `MembershipRevocationWired()`, not an overload of the hook |
| F2 (Reconnect supersede skips the hook) | Every path that ends a connection goes through `endConnection`, which calls the hook in the same transaction; that includes `Reconnect` (`superseded`). T17 drives it |
| F3 (expiry not fenced by `expires_at`) | `LiveConnectionTx` and `LiveConnection` treat `expires_at <= clock_timestamp()` (database clock, evaluated at the statement, never the transaction start; round 4) as `connection_expired` before any `Transition` ran. T17 has the case |
| F4 (one shared role "is the union") | Withdrawn. One dedicated Glovo runtime role for `GLOVO_DB_URL` and the bridge pool, a separate migration role, and no Glovo grant for the work-items role: #957 §6d.1 (owner-confirmed 2026-11-09, `glovo_runtime` / `glovo_migrator`). `ApplySchema(ctx, migrationConnStr, runtimeRole)`; `Ready` and T16 check the §6d.1 grants exactly |
| F5 (`glovo.Status` disagrees with #957 §4) | The joint contract's HTTP status row now equals #957 §4.1 (`no_connection` 404, `stale_install` 403); the enum row lists the codes the sibling slices add. Same edit in #960 and #961, whose joint contract text stays identical |
| F7 (A11 depends on #985's real hook; dependency cycle) | T17 uses a fake hook only. The end-to-end revoke-then-permit and expiry-then-permit proof is #985 T24, a #985 gate; #959 no longer depends on #985 |
| F8 (Reconnect conflicts with the #961 route) | `Reconnect` has two branches (below). The #961 route exposes only the terminal branch and refuses a live prior with `connection_exists`; #961 is edited to say so |
| Round 3 (X-3, N1) | `NewStore(ctx, pool, runtimeRole, opts...)`, `Pool()` and `WithExplicitURL`: #959 opens no second pool, so the R5 same-pool check can pass |
| Round 3 (N2) | `Ready` gains the role-attribute and `current_user` checks; A12 gets T19, a negative matrix proven both ways |
| Round 3 (#961 F1, F4, F6) | `ActivateTx`, `ConnectInput.AfterLocks`, `ConnectInput.TerminalOnly` and `AppendRefusal`, so #961 adds no store primitive of its own |
| P3 F6, F9, F10 | Schema-safety requirement rewritten (`ApplySchema` is the only DDL path); every query is `glovo.`-qualified, with an A10 test under the runtime role's default `search_path`; `*Refusal` replaced by `*glovo.Error`; the lock prose points to #957 §6b; the handoff-refs grant is #961's, to the same runtime role; the explicit-URL check is an input to `Ready` from the wiring slice (#957 A9) |

## Amendment 2026-11-09 (b) — owner decision A, companion to #985/#988/#989

Owner decision A (2026-11-09): connections, orders, `aar_` and the bridge live in **one
physical Postgres database** and share one `pgx.Tx`. This section supersedes every
earlier text in this proposal that leaves the database URL open or lets the store fall
back to `AUDIT_DB_URL`. It is the #959 side of the #985 review P2-4/P2-6 and the #989
review P2-3/P2-6 fixes in the same PR.

| Driver | Change in this slice |
|---|---|
| Decision A: one physical database, explicit URLs | The store lives in the Postgres schema `glovo` (`glovo.glovo_installs`, `glovo.glovo_connections`, …) of the same database as the bridge, the work items and the #988 orders. `GLOVO_DB_URL` must be set explicitly; there is no `AUDIT_DB_URL` fallback. Same-database is proven by #985 `control.ProveOneDatabase`, not by URL equality |
| Least privilege across pools | Amended (c): the role and grant table is mctl-api#957 design §6d.1 only. The migration role owns every `glovo` object; the one Glovo runtime role (also the bridge pool's role) holds the listed DML; the work-items role has no Glovo grant |
| #985/#988/#989 need tx-scoped reads on their transaction | `LockOwnerShared(ctx, tx, tenant, principal)` (L1 shared, L2 shared) and `LiveConnectionTx(ctx, tx, owner)` (no row lock; valid because every writer holds L2 exclusive). Neither begins or commits |
| One lock order | L1 and L2 here are levels L1 and L2 of the canonical order in #957 design §6b. Readers on the Glovo write path take both shared; every connection write takes L1 shared (L1 exclusive for install changes) and L2 exclusive |
| Revocation must fence open bridge commands (#985 review P2-4) | Every path that ends a connection (`Revoke`, including reason `membership_removed`, `RevokeInstall`, `Reinstall`, `Reconnect` with reason `superseded`, and terminal `Transition`s) goes through `endConnection`, which calls the installed `RevocationHook` in the **same transaction**, after L1/L2 and the row updates, with the ended `gcn_` ids. #985 installs `bridge.CancelOpenForConnections`, a plain Go function on that transaction (L5, `ORDER BY command_id`; amended (c): no `SECURITY DEFINER` function) |
| Membership loss | New reason `membership_removed` and `RevokeForMembership(ctx, tenant, principal, actor)`. Who detects membership removal and calls it is an OPEN item |
| Timeout fencing must still be proven | `expired` through `Transition` is a revoker too, so the hook runs; independently, `LiveConnectionTx` answers `connection_expired` once `expires_at <= clock_timestamp()` (amended (c), round 4). T17 covers both with a fake hook; the end-to-end permit proof is #985 T24 |

### Roles (owner decision A; amended (c))

The role and grant table moved to mctl-api#957 design §6d.1, the only copy. For this
slice: the migration role owns every object in schema `glovo` and runs
`ApplySchema(ctx, migrationConnStr, runtimeRole)`, which grants the named runtime role
`USAGE` on `glovo` and the #959 rows of that table, nothing else. No runtime role owns a
`glovo` object, so none can `ALTER`, `DROP` or `DISABLE TRIGGER`. The work-items role
gets no grant. `Ready` checks the grants of the #959 rows exactly and that the runtime
role is not a member of the owner role.

### Tx-scoped API and revocation hook

```go
// EndPurger (round 4): endConnection calls it on the path's own transaction, after the
// connection rows are ended and before the RevocationHook, with the ended ids. #961
// installs the handoff-ref purge. #959 never names a #961 table, so it merges and runs
// without them; an error rolls the ending back, like a hook error.
type EndPurger func(ctx context.Context, tx pgx.Tx, ended []string) error
func WithEndPurger(p EndPurger) Option
func WithEndPurgerRequired(required bool) Option // wiring slice (#985 task 9) passes true when the #961 handoff routes are mounted
func (s *Store) EndPurgerInstalled() bool
// LockOwnerShared takes L1 (install key) shared, then L2 (owner key) shared, on tx.
func (s *Store) LockOwnerShared(ctx context.Context, tx pgx.Tx, tenant, principal string) error
// LiveConnectionTx reads the owner's live connection on tx without a row lock.
// The caller must hold L2 (shared or exclusive). A connection whose expires_at is
// at or before clock_timestamp() (database clock at statement time; now() is the
// transaction start and is never used, round 4) is connection_expired even if no
// Transition has run yet (amended (c)).
func (s *Store) LiveConnectionTx(ctx context.Context, tx pgx.Tx, owner Owner) (*Connection, error)
// RevocationHook is called by every path that ends a connection (endConnection),
// on that path's transaction, after the connection rows are ended, with the ended ids.
type RevocationHook func(ctx context.Context, tx pgx.Tx, ended []string, actor string) error
func WithRevocationHook(h RevocationHook) Option
// WithMembershipRevoker registers the slice that detects membership removal and
// calls RevokeForMembership (OPEN-985-2); MembershipRevocationWired reports it.
func WithMembershipRevoker(name string) Option
func (s *Store) MembershipRevocationWired() bool
func (s *Store) RevokeForMembership(ctx context.Context, tenant, principal, actor string) ([]Connection, error)
func (s *Store) Ready(ctx context.Context) error
```

- A hook error rolls the revoker back: no connection is ended without its commands
  being cancelled.
- Without an `EndPurger`, revokers still work and purge only `secret_ref`; `Ready` reports
  `end_purger_missing` only when `WithEndPurgerRequired(true)` was given and none is installed
  (round 4). A purger error is a failed read of the purge, never "nothing to purge": the
  ending rolls back.
- Without a hook, revokers still work (the M1a store stays usable), but `Ready` reports
  `revocation_hook_missing`. #985 and #989 treat that as `not_ready`, so no Glovo
  write can be dispatched or permitted.
- `Ready` also checks (round 3, the full #957 §6d.1 list that #959 owns):
  - the explicit-URL fact (`WithExplicitURL(true)`, an input from the wiring slice, #957 A9);
  - `current_user` equals the `runtimeRole` given to `NewStore`;
  - `rolsuper`, `rolcreaterole`, `rolcreatedb` and `rolbypassrls` of `current_user` are false;
  - the schema version, and the grants of every table that exists in schema `glovo` against `glovo.expectedGrants`, the Go mirror of the `glovo.*` rows of #957 §6d.1 (round 4: each slice adds its own rows in its own PR, and a golden test compares the mirror with §6d.1). A `glovo` table with no row, extra or missing rights, `CREATE`, `TRUNCATE`, `TRIGGER` or `REFERENCES` is `not_ready`; a row whose table does not exist yet is skipped unless required (`glovo_handoff_refs` when `WithEndPurgerRequired(true)`);
  - `current_user` owns no `glovo` object and is not a member of any owner role;
  - the audit and no-delete triggers are enabled (`tgenabled = 'O'`);
  - a `RevocationHook` is installed (`revocation_hook_missing` otherwise);
  - an `EndPurger` is installed when `WithEndPurgerRequired(true)` (`end_purger_missing` otherwise).


## Amendment 2026-11-09 — joint 959/960/961 AMEND

Independent review of digest `sha256:718181577b889372ffec9eb565489b3cf53130b7e9a3b2545f0de65198467651` (mctl-api#959, comment of 2026-11-09) required one joint amendment across #959, #960 and #961. Finding -> change in this slice:

| Finding | Change |
|---|---|
| P2 runtime role is not the table owner, but `NewStore` runs DDL with the runtime `connStr` | DDL moves to `ApplySchema(ctx, migrationConnStr, runtimeRole)` under a migration role; `NewStore` runs no DDL and checks the schema version; runtime grants are DML only; tests T14 prove the runtime role cannot `ALTER`, `DROP` or `DISABLE TRIGGER` (task 4, A5) |
| P3 "No Glovo code exists" is stale; #977 ships `internal/glovo` | Current state corrected; this slice extends `internal/glovo` and reuses `glovo.Code`/`glovo.Error` instead of a parallel `RefusalCode`/`Refusal` (task 1) |
| P3 open question still offers store-configurable retention | Open question replaced: retention is the documented 400-day obligation, enforced only by a future privileged maintenance design |
| P3 T7 races `Reinstall` but not `RevokeInstall` | T7 now also races `Connect` against `RevokeInstall` |
| P3 carry-over from mctl-telegram#1258: only revoke/cancel purge state | Per-terminal-state retention and purge table added (section "Terminal-state purge"); T15 drives every terminal path |
| Cross-slice: #961 needs `expires_at`, audit `actor_kind`; #960 task 0 needs the allowlist DDL and the refusal enum from this slice | `glovo_connections.expires_at`, `glovo_audit_events.actor_kind`, the `glovo_pilot_allowlist` DDL with `IsAllowlisted`, and the full closed refusal enum are added here |

### Joint contract frozen for #959, #960 and #961 (identical text in all three)

Verified against mctl-api main `a9ca5814` (#977 merged) and the merged #968 bridge (`docs/bridge.md`). Where an earlier section of this document disagrees, this contract wins.

| Item | Frozen value | Owner slice |
|---|---|---|
| Consent-time team selection, claims `tgr`/`stn`, `User.TeamGrant()`, `scope.Resolver` | `/oauth/consent` selection, the claims `tgr` (grant id) and `stn` (selected tenant), `User.TeamGrant() (grantID, tenant string, ok bool)` and `scope.Resolver.Resolve(ctx, *auth.User) (Scope, *glovo.Error)`. No other slice selects a team, mints a tenant claim or reads a tenant header as input; #957 consumes these (round 3: it mints no `mctl_tenant`). The `scope_ref` binding key of #957 section 2b is the grant's `refresh_family_id` (`oauth_team_grants`), read through `User.TeamGrant()` plus `teamgrant.Check`. Eligibility = membership ∩ allowlist minus `GLOVO_NON_SELECTABLE_TENANTS`; the current install is not part of it (a selected team without a current install is refused at use with `no_install` by #959) | #960 (sole owner) |
| Go package | extend the existing `internal/glovo` from #977 (`glovo.Code`, `glovo.Error`, `glovo.Gate`, `glovo.WriteError`); no parallel `RefusalCode`/`Refusal` type | #959 adds the codes |
| Tables | `glovo_installs`, `glovo_connections`, `glovo_connect_requests`, `glovo_audit_events`, `glovo_pilot_allowlist` | #959 (DDL) |
| | `glovo_handoff_refs`, `glovo_rate_counters` | #961 (DDL) |
| | `oauth_team_grants`, `oauth_refresh_tokens.team_grant_id` (refresh-store database) | #960 |
| Columns | reconnect link `supersedes_id`; `glovo_connections.expires_at TIMESTAMPTZ NULL`; `glovo_audit_events.actor_kind` (`user`, `owner`, `admin`, `worker`, `system`) | #959 |
| Store API | `Install`, `GetInstall`, `RevokeInstall`, `Reinstall`, `Connect`, `Reconnect`, `Transition`, `Revoke`, `GetConnection`, `LiveConnection`, `ListAudit`, `IsAllowlisted` | #959 |
| Store states | `pending_handoff`, `pending_provider`, `active`, `expired`, `failed`, `revoked`; wire `PublicState`: both `pending_*` -> `pending`, the rest unchanged | #959 states, #961 mapping |
| Refusal enum (closed, `glovo.Code`) | `not_ready`, `unavailable`, `not_authorized`, `invalid_request`, `not_found`, `no_install`, `ambiguous_tenant`, `no_tenant`, `scope_unsupported`, `not_in_pilot`, `stale_install`, `stale_version`, `no_connection`, `connection_exists`, `connection_revoked`, `connection_expired`, `invalid_transition`, `idempotency_key_reused`, `rate_limited`; since 2026-11-09 (c) also `fingerprint_changed`, `approval_invalid`, `approval_expired`, `approval_replayed`, `intent_mismatch`, `basket_changed`, `tenant_busy`. The one closed set, with every status and wire value, is mctl-api#957 design §4.1 | #959 adds the M1a codes; #985, #988 and #989 add theirs through #957 §4.1 |
| HTTP status | Amended 2026-11-09 (c) to equal mctl-api#957 design §4.1: 503: `not_ready`, `unavailable`; 401/403: `not_authorized` (401 only when no valid token); 400: `invalid_request`; 404: `not_found`, `no_connection`; 403: `no_install`, `ambiguous_tenant`, `no_tenant`, `scope_unsupported`, `not_in_pilot`, `stale_install`; 429: `rate_limited`; 409: every other code. One function, `glovo.Status(code)`; the #957 A6 golden test checks it against §4.1 for every code | #959 |
| Membership lost | `no_tenant` everywhere (resolver, facade, worker check); `not_authorized` only for a wrong audience or identity kind | all |
| Refusal body | #977's `glovo.WriteError` shape `{"error": <code>, "error_description": <fixed text per code>}`. No `schema`/`refusal` envelope on refusals; success bodies keep their `schema` field. This is the shape mctl-api#957 and mctl-telegram#1235 vendor | all |
| Kill switch | one name, `GLOVO_ENABLED`, default `false`, read once in `cmd/api/main.go`. Open only when `GLOVO_ENABLED=true` **and** every readiness dependency is configured and healthy. `GLOVO_MCP_RESOURCE` alone never opens anything. `GLOVO_OAUTH_ENABLED` and `GLOVO_DISABLED` are withdrawn | #960 introduces, #961 reuses |
| DDL role | DDL runs only through `glovo.ApplySchema(ctx, migrationConnStr, runtimeRole)` with a dedicated migration role that owns the objects; the one Glovo runtime role and its grants are mctl-api#957 design §6d.1 (amended (c)). `NewStore(ctx, pool *pgxpool.Pool, runtimeRole string, opts ...Option)` (round 3) takes the one shared `GLOVO_DB_URL` pool that the wiring slice opened and that the bridge store also uses (#957 §6d.1 R4), opens no pool of its own and runs no DDL: it pings and checks the recorded schema version, failing closed on a mismatch. The runtime role gets only the DML it needs (no UPDATE/DELETE on `glovo_audit_events`, no DELETE on `glovo_connections`), so it cannot `ALTER`, `DROP` or `DISABLE TRIGGER`. A test proves each of the three refusals | #959 builds it, #961 extends it |
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
  opens a pool with `pgshared.Open` (the Glovo store deliberately departs from this in
  round 3: the wiring slice opens the one `GLOVO_DB_URL` pool with `pgshared.Open` and
  passes it in) (`internal/pgshared/pool.go`), pings,
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
migrationConnStr, runtimeRole)`, executed by a dedicated migration role that owns every
`glovo_*` object. It ends by issuing the runtime grants, which are exactly the #959 rows of
mctl-api#957 design §6d.1 and nothing else (the one copy of the grant table; this
body does not list rights, round 4). The writes to `glovo_pilot_allowlist` are
reachable only through #960's admin routes; #960 has no DDL role and issues no grant of
its own. `NewStore`
uses the runtime connection, runs **no DDL**, and fails closed when
`glovo_schema_version` is missing or differs from the compiled version. This
departs from the DDL-in-`NewStore` convention of other mctl-api stores
deliberately: a role that creates a table owns it and could disable the audit
trigger.

### Terminal-state purge

| Terminal event | Purged in the same transaction | Retained |
|---|---|---|
| connection `expired`, `failed`, `revoked` (any reason, incl. `superseded`, `install_revoked`, `install_reinstalled`) | `secret_ref` set to NULL and returned for release; whatever the installed `EndPurger` removes for the ended ids (#961 installs the purge of the connection's unconsumed `glovo_handoff_refs` rows; this slice names no #961 table, round 4) | connection row (id never reused), audit events |
| install `uninstalled` / reinstall | the above for every live connection of the old revision | install row, audit events |
| idempotency rows | not on terminal transition; removed after 24 h by the #961 `Sweep` (bounded `DELETE` on `glovo_connect_requests`, `glovo_handoff_refs` and `glovo_rate_counters`; the matching `DELETE` rights are in #957 §6d.1) | none |

Every terminal path goes through one `endConnection` helper, so no path can
skip the purge (the gap found in the fake worker of mctl-telegram#1258).

### Locking (revoke-vs-connect safety)

Amended (c): the canonical order is #957 design §6b; this section gives only the #959
rows. Two advisory keys, always taken in this order inside one transaction:

1. Tenant install key `glovo-install/v1|<tenant>`. Taken **shared**
   (`pg_advisory_xact_lock_shared`) by `Connect`, `Reconnect`,
   connection `Transition` and the Glovo write-path readers of #957 §6b. Taken
   **exclusive** by `Install`,
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
  by the owner key. Whichever commits second sees the other's result, and a
  `Reconnect` that then finds its prior connection terminal takes the terminal
  branch below.
- `Reconnect` (amended (c)) has two branches, chosen under L2 exclusive from the
  prior connection's state. Prior live (`pending_*`, `active`, `expires_at` not
  passed): it is ended through `endConnection` with reason `superseded` (purge and
  `RevocationHook` included) and a new `gcn_` is created with `supersedes_id`. Prior
  terminal (`expired`, `failed`, `revoked`, or `expires_at` passed): a new `gcn_` is
  created with `supersedes_id` and nothing is ended (an expired-by-clock prior is first
  moved to `expired` through `endConnection`). A prior that is not the owner's is
  `ErrNotFound`. The #961 route exposes only the terminal branch.
- The partial unique index `glovo_connections_one_live` is the last line
  of defense. A unique violation on it maps to `connection_exists` and
  never to a 500.

### Store API (`store.go`)

All methods take an `Owner` or a tenant plus an actor `prn_`, and they
return `*glovo.Error` for domain refusals and wrapped errors for I/O
(`fmt.Errorf("glovo: ...: %w", err)`).

```go
func ApplySchema(ctx context.Context, migrationConnStr, runtimeRole string) error // migration role only; grants per #957 §6d.1
func NewStore(ctx context.Context, pool *pgxpool.Pool, runtimeRole string, opts ...Option) (*Store, error) // round 3: shared GLOVO_DB_URL pool, no DDL, opens no pool of its own
func (s *Store) Pool() *pgxpool.Pool // the pool NewStore was given; #985 ProveOneDatabase compares it with bridge.Store.Pool() (same pointer)
// Option: WithExplicitURL(bool): the wiring slice (#985 task 9) passes true only when GLOVO_DB_URL was set explicitly (never AUDIT_DB_URL); false makes Ready answer not_ready
// Option: WithClock(func() time.Time); audit retention is a future privileged maintenance slice
func (s *Store) Close() // releases nothing it does not own: the shared pool is closed by the wiring slice

func (s *Store) Install(ctx, tenantID, actor string) (*Install, error)          // idempotent if already installed
func (s *Store) RevokeInstall(ctx, tenantID, actor, reason string, expectedRevision int64) (*Install, []Connection, error)
func (s *Store) Reinstall(ctx, tenantID, actor string, expectedRevision int64) (*Install, []Connection, error)
func (s *Store) GetInstall(ctx, tenantID string) (*Install, error)               // no_install

type ConnectInput struct {
    Owner Owner; ExpectedInstallRevision int64; IdempotencyKey string
    TerminalOnly bool                                // Reconnect only (round 3): a live prior is refused connection_exists under L2, no supersede; a prior terminal by state or by expires_at <= clock_timestamp() (database clock) takes the terminal branch
    AfterLocks func(ctx context.Context, tx pgx.Tx) error // round 3, for #961: runs on the mutation's own tx after L1/L2 and before the insert; an error aborts and is returned as is (e.g. rate_limited)
}
func (s *Store) Connect(ctx, in ConnectInput) (*ConnectResult, error)           // {Connection, Replayed}
func (s *Store) Reconnect(ctx, in ConnectInput, priorConnectionID string) (*ConnectResult, error)
// ActivateTx (round 3, for #961): on the caller's tx it takes L1 shared then L2 exclusive,
// runs in.AfterLocks (the handoff-ref consume, level L2b of #957 §6b), then steps
// pending_handoff -> pending_provider -> active (two audited transitions, the edge table
// is unchanged) with expires_at = clock_timestamp() + in.ExpiresIn, computed in SQL
// (round 4: no Go time.Time crosses the boundary, so it cannot be in the past or drift
// from the database clock; ExpiresIn <= 0 or above MaxConnectionTTL (24 h) is invalid_request).
// It checks ExpectedVersion and ExpectedInstallRevision (stale_version / stale_install).
// It begins and commits nothing. LiveConnectionTx then reports connection_expired once
// expires_at has passed.
type ActivateInput struct { Owner Owner; ConnectionID string; ExpectedVersion, ExpectedInstallRevision int64; ExpiresIn time.Duration; Actor string; AfterLocks func(ctx context.Context, tx pgx.Tx) error }
func (s *Store) ActivateTx(ctx context.Context, tx pgx.Tx, in ActivateInput) (*Connection, error)
// AppendRefusal (round 3, for #961): appends one glovo_audit_events row (event 'refused',
// reason_code = the refusal code, to_state = from_state = the entity's current state) for a
// refusal that names an existing install or connection. Pre-scope refusals have no entity
// and are not audited here (slog and metrics only).
func (s *Store) AppendRefusal(ctx context.Context, ev RefusalEvent) error
func (s *Store) Transition(ctx, owner Owner, connectionID string, to ConnectionState,
                           expectedVersion int64, reason string, ref *SecretRef) (*Connection, error)
func (s *Store) Revoke(ctx, owner Owner, connectionID, reason string) (*Connection, error)
func (s *Store) GetConnection(ctx, owner Owner, connectionID string) (*Connection, error) // ErrNotFound
// GetConnectionForWorker (round 4, for #961's worker routes): the one read by id with no
// owner predicate. It returns the connection with its write-once Owner (tenant, principal),
// state, version, install revision and expires_at; ErrNotFound for an absent id. Only the
// worker handlers behind glovoWorkerGate call it (a source-scan test fails on any other
// caller). It takes no lock and is not an authority: check/activate/expire then call
// LockOwnerShared, ActivateTx or Revoke with the returned Owner, and ExpectedVersion is the
// version read here, re-checked by ActivateTx under L1/L2 (a change in between is
// stale_version and commits nothing).
func (s *Store) GetConnectionForWorker(ctx context.Context, connectionID string) (*Connection, error)
func (s *Store) LiveConnection(ctx, owner Owner) (*Connection, error)                    // no_connection
func (s *Store) ListAudit(ctx, tenantID, entityID string) ([]AuditEvent, error)
func (s *Store) IsAllowlisted(ctx, tenantID, principalID string) (bool, error) // read only
// Audit retention deletion is OUT OF SCOPE for M1; no SweepAudit API is exposed.
```

The returned `[]Connection` from revoke/reinstall are the connections the
call ended, so a later slice can propagate revocation (Temporal signal) and
release secret references after commit.

Every query names its table schema-qualified (`glovo.glovo_connections`, …), because
the tx-scoped reads run on the bridge pool's transaction, whose `search_path` does not
include `glovo` (amended (c)). Every connection query has the form
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
