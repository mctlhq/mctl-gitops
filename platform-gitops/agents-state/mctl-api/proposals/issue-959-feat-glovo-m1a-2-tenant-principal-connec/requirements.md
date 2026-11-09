# Glovo M1a slice 2: tenant/principal connection model, audited Postgres store and atomic revoke

## Context

Issue mctlhq/mctl-api#959 is slice 2 of 4 carved out of the over-wide parent
mctlhq/mctl-api#953 (synthetic, tenant-bound Glovo connections). Slice 1
(#958) owns the OAuth resource audience and fail-closed auth gates. Slice 3
(#960) owns human-selected team grant and the per-user allowlist. Slice 4
(#961) owns handlers, worker scope checks and end-to-end tests. This slice
provides only the durable domain and store underneath them: typed
install and connection states, server-minted `tenant_id` / `principal_id` /
`install_id` + `install_revision` / `gcn_` connection IDs, Postgres schema
with uniqueness and lifecycle constraints, an immutable audit trail with
retention, and concurrency-safe connect / reconnect / revoke / reinstall.

This slice matters because every later slice decides authorization by
looking up this store. If two tenants, or two users in one team, could
reach each other's connection, or if a revoke that races a connect could
leave a live connection behind, later slices would be unsafe no matter how
good their auth gates are. Everything stays synthetic. No real Glovo
session, cookie or `session.json` exists. Secrets appear only as an opaque
reference abstraction.

## AMEND 2026-11-08 — DB test cleanup and immutable audit security (P1/P2)

This proposal must **not** use `SET LOCAL session_replication_role = replica` in tests: that bypasses triggers/constraints, typically requires database superuser privileges, and is unsuitable for MCTL's ordinary CI/RDS role. Each test must isolate its fixtures in a disposable, separately named schema/database (with a dedicated connection/search_path) or use deterministic transaction rollbacks with no trigger bypass. Cleanup is allowed only in that test-owned schema/database, never on shared production tables.

The proposed `glovo.retention_sweep` user-defined GUC is **not an authorization boundary**: an application DB role can normally `SET LOCAL` a custom GUC and forge the exception to the audit DELETE trigger. For M1, audit rows must be append-only: deny UPDATE/DELETE unconditionally for the application role, with no custom-GUC bypass. Defer physical retention deletion to a separate security-reviewed, privileged maintenance design with a distinct DB role or tightly controlled SECURITY DEFINER, explicit ownership and retention gate. `SweepAudit` must not be exposed to the API role in M1.

Prove tests with a **non-superuser** DB role that attempts arbitrary `SET LOCAL glovo.retention_sweep=on`, UPDATE/DELETE and fake role changes and confirms they cannot tamper with audit rows. No broadening of identity or real Glovo scope; implementation needs independent digest approval.

## User stories

- AS a later-slice handler author I WANT a Go store API where the owner
  (tenant + principal) is a required argument of every read and write SO
  THAT I cannot write a lookup by connection ID alone.
- AS a team member I WANT my Glovo connection to be invisible to another
  member of my team and to every other tenant SO THAT nobody else can act
  through my connection.
- AS a tenant administrator I WANT revoking or reinstalling the tenant's
  Glovo install to atomically end every connection bound to the old
  revision SO THAT no stale connection stays live.
- AS a security reviewer I WANT every state change recorded as an
  immutable, retention-bounded audit event without secrets or PII SO THAT
  I can reconstruct what happened.
- AS an operator I WANT the schema to be additive and transaction-safe SO
  THAT deploying it cannot damage existing mctl-api tables.

## Acceptance criteria (EARS)

Identity and ownership
- WHEN the store creates an install THE SYSTEM SHALL mint `install_id` as
  `gin_<ULID>` server-side with `install_revision` 1, and SHALL NOT accept
  an install ID or revision chosen by the caller.
- WHEN the store creates a connection THE SYSTEM SHALL mint
  `connection_id` as `gcn_<ULID>` server-side and SHALL bind it to exactly
  one (`tenant_id`, `principal_id`, `install_id`, `install_revision`).
- THE SYSTEM SHALL require `tenant_id` and a `prn_`-prefixed `principal_id`
  on every store method that reads or changes a connection, and SHALL
  refuse (`invalid_request`) an empty tenant or a principal ID without the
  `prn_` prefix.
- WHILE a (`tenant_id`, `principal_id`) pair has a connection in a live
  state (`pending_handoff`, `pending_provider`, `active`) THE SYSTEM SHALL
  hold at most one such connection, enforced by a partial unique index.
- THE SYSTEM SHALL keep a unique key on (`tenant_id`, `principal_id`,
  `connection_id`, `install_revision`), and at most one install row per
  `tenant_id`.

Lifecycle
- THE SYSTEM SHALL allow only these connection transitions:
  `pending_handoff -> pending_provider|failed|expired|revoked`,
  `pending_provider -> active|failed|expired|revoked`,
  `active -> expired|failed|revoked`. `expired`, `failed` and `revoked`
  are terminal.
- IF a transition is not in that table THEN THE SYSTEM SHALL refuse it with
  `invalid_transition` and change nothing.
- IF a transition names an `expected_version` that differs from the stored
  version THEN THE SYSTEM SHALL refuse it with `stale_version` and change
  nothing.
- THE SYSTEM SHALL enforce the state vocabulary with named CHECK
  constraints in the database as well as in Go.

Connect, reconnect, idempotency
- WHEN `Connect` runs for an owner whose tenant has no installed install
  THE SYSTEM SHALL refuse with `no_install`.
- WHEN `Connect` or `Reconnect` names an `expected_install_revision` other
  than the tenant's current revision THE SYSTEM SHALL refuse with
  `stale_install`.
- WHEN `Connect` runs for an owner who already has a live connection THE
  SYSTEM SHALL refuse with `connection_exists`, unless the call replays an
  earlier idempotency key.
- WHEN `Connect` repeats an idempotency key with identical arguments THE
  SYSTEM SHALL return the original connection with `replayed=true` and
  create nothing. IF the same key arrives with different arguments THEN THE
  SYSTEM SHALL refuse with `idempotency_key_reused`.
- WHEN `Reconnect` runs THE SYSTEM SHALL, in one transaction, revoke the
  owner's current connection (reason `superseded`) and create a connection
  with a NEW `gcn_` ID. THE SYSTEM SHALL never reuse a connection ID.

Revoke and reinstall atomicity
- WHEN a connection is revoked THE SYSTEM SHALL set state `revoked`,
  `ended_at`, `end_reason`, clear its secret reference, and append the
  audit event in the same transaction.
- WHEN an install is revoked (uninstalled) or reinstalled THE SYSTEM SHALL,
  in one transaction, raise `install_revision` by one (on reinstall) or set
  state `uninstalled` (on revoke), and move every live connection of that
  tenant bound to an older revision to `revoked` with reason
  `install_revoked` or `install_reinstalled`.
- WHEN any revoker ends a connection (`Revoke`, including reason
  `membership_removed`, `RevokeInstall`, `Reinstall`, or a `Transition` to a terminal
  state) THE SYSTEM SHALL call the installed `RevocationHook` with the ended ids in the
  same transaction, after taking L1 and L2, and SHALL roll back if the hook fails.
- WHILE no `RevocationHook` is installed THE SYSTEM SHALL report
  `revocation_hook_missing` from `Ready`.
- WHEN `LockOwnerShared` or `LiveConnectionTx` is called THE SYSTEM SHALL run on the
  caller's transaction and SHALL NOT begin or commit one.
- WHILE `GLOVO_DB_URL` is not set explicitly THE SYSTEM SHALL report `not_ready`; it
  SHALL NOT fall back to `AUDIT_DB_URL`.
- THE SYSTEM SHALL create every object in the Postgres schema `glovo`, owned by the
  migration role, and SHALL grant the bridge and work-items runtime roles only `USAGE`
  on the schema and `SELECT` on `glovo_installs` and `glovo_connections`.
- WHILE a `Connect` races a connection revoke or an install
  revoke/reinstall for the same tenant THE SYSTEM SHALL serialize them so
  that after both commit no live connection references a revoked install
  or a non-current install revision.
- IF any statement in a store transaction fails THEN THE SYSTEM SHALL roll
  back every row and audit event written by that transaction.

Not-found indistinguishability
- IF a caller reads or changes a connection ID that does not exist, that
  belongs to another principal in the same tenant, or that belongs to
  another tenant THEN THE SYSTEM SHALL return the same `not_found` error
  (same sentinel, same message, no timing-relevant extra query) in all
  three cases.
- IF a caller reads a connection of its own that is terminal THEN THE
  SYSTEM SHALL return it with its state so that a later slice can answer
  `connection_revoked` / `connection_expired`. A lookup with no live
  connection for the owner returns `no_connection`.

Audit
- WHEN any install or connection state changes THE SYSTEM SHALL append
  one audit event with a server-minted immutable `gae_<ULID>` event ID,
  tenant, subject principal, actor principal, entity, from/to state,
  install revision, reason code and timestamp.
- THE SYSTEM SHALL refuse **every** UPDATE or DELETE of an audit event by the runtime application DB role, even if it sets a custom GUC.
- THE SYSTEM SHALL document the audit retention obligation (400 days target) but SHALL NOT expose an application-side sweep in M1. Future privileged maintenance requires a separate reviewed schema/DB-role policy; install and connection rows remain non-deletable.
- THE SYSTEM SHALL NOT store in any table, audit event or log line a
  provider session, cookie, token, password, email address, phone number
  or delivery address. The only secret-related value stored is an opaque
  `gsr_` reference ID.

Secret reference
- THE SYSTEM SHALL expose a `SecretRefs` interface (opaque reference ID
  only) and SHALL ship only a refusing implementation in this slice.
- THE SYSTEM SHALL NOT describe a future per-connection DEK / independent
  KEK design as "crypto-shredding" in code or docs.

Schema safety
- WHEN the store starts THE SYSTEM SHALL apply its schema idempotently
  under a schema advisory lock, creating only new `glovo_*` objects and
  never altering or dropping an existing non-`glovo_*` table.

## Out of scope

- OAuth resource/audience handling, grants or selected-team inference
  (slices 1 and 3).
- Any public HTTP route or MCP tool; the MCP tool count in
  `internal/mcp/server_test.go` stays unchanged (slice 4).
- Wiring the store into `cmd/api/main.go` for production startup (slice 4).
- Temporal namespace, worker or workflow propagation of revocation.
- Real provider access, real Glovo sessions or cookies, hosted
  `session.json`, an actual secret backend or KMS.
- Approval / `aar_` receipts, orders, payment (M1b, #954).
- Quota and rate ceilings (parent #953; deferred to slice 4).

## Open questions

- Install cardinality: the issue does not say whether an install is
  per-tenant or per-principal. This proposal assumes one install per
  tenant (a team installs Glovo once), with per-principal connections
  under it. A later slice can add per-principal installs additively.
- Reinstall semantics: this proposal keeps the same `install_id` and
  raises `install_revision` by one. Reinstalling after an uninstall also
  raises the revision. The alternative (new `install_id` per reinstall)
  is listed in design.md.
- Audit retention: the 400-day target is a documented obligation only.
  Nothing in the store deletes or expires audit rows; deletion needs a
  separate privileged maintenance design. Install and connection rows are
  kept indefinitely. (Amended 2026-11-09: the store-configurable option is
  withdrawn.)
- Production wiring: the store is not constructed in `cmd/api/main.go` in
  this slice, so no schema reaches production until slice 4 wires it
  behind a feature flag. If the owner wants the schema deployed earlier,
  that is a one-line follow-up.
- The deployed mctl-api configuration could not be observed (see
  design.md, Deployed state checked). Resolved by owner decision A
  (2026-11-09 (b)): `GLOVO_DB_URL` is required, names the same physical
  database as the bridge and the work items, and never falls back to
  `AUDIT_DB_URL`.
- OPEN-959-1. Who detects that an owner lost tenant membership and calls
  `RevokeForMembership` (a membership-change hook in the tenant role store,
  or a sweeper). Until it exists, the #989 fence's live membership read is
  the only guard.
- OPEN-959-2. Provisioning of the migration and runtime roles (shared with
  OPEN-985-6, OPEN-988-3, OPEN-989-2).
