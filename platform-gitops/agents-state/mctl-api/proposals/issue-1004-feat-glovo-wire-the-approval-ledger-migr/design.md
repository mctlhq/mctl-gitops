# Design: issue-1004-feat-glovo-wire-the-approval-ledger-migr

Amended 2026-11-10 for owner decisions D1 and D2 (see requirements.md). This amendment
approves no implementation. Claims marked UNVERIFIED were not confirmed against code or
GitOps. Verified against mctl-api `main` at `081bd6b7` and the mctl-gitops#2563 branch
`feat/glovo-m1-a15-db-env` at `6464978210cb`.

## Current state

Code read in the clone (`main` at `081bd6b`, which contains `675dff75`):

- `cmd/api/main.go` ~L1173-1190: the only `installWriteFence` call. `Gate` is
  `glovo.ControlDefault.Open`, `HoldLifted` is `glovoWriteFenceHoldLifted`, `Proof` calls
  `controlProof(ctx, os.LookupEnv, bridgeStore, glovoStore, nil)` (work-items pool is
  `nil`, so precondition 3 is always false), and `Build` always returns the error "the
  receipt fence collaborators are not constructed in this build".
- `cmd/api/glovo_bridge.go`: `const glovoWriteFenceHoldLifted = false`;
  `controlEnvReady` demands explicit `GLOVO_DB_URL` and `WORK_ITEMS_DB_URL`;
  `installWriteFence` computes `glovoFencePreconditions` and calls `Set` only when
  `pre.All()`.
- `cmd/api/glovo_control.go`: `fenceHookReady`, `fenceMembershipObserved`
  (`s.MembershipRevocationWired()`), `glovoFencePreconditions.All()` (six booleans);
  `configureGlovoControl` explicitly attaches no Dispatcher because "the orders index, the
  receipts and the join and execution stores are not constructed in this binary yet".
- `cmd/api/glovo_team_grant.go`: `configureGlovoTeamGrants` opens the `GLOVO_DB_URL` pool
  with `GLOVO_DB_RUNTIME_ROLE` / `GLOVO_DB_MIGRATION_ROLE`; `glovoStoreOptions` installs
  `bridge.CancelOpenForConnections` as the revocation hook when control is enabled, but no
  `WithMembershipRevocationProbe`.
- `cmd/api/main.go` ~L666-700: work-items store from `workItemsStoreSource()`
  (`WORK_ITEMS_DB_URL`, else `AUDIT_DB_URL`), built with `WithClock` and
  `WithQueueWhileActive` only, no `WithGlovoOrders`. `api.Options.GlovoApprovals`
  (`internal/api/router.go` L269-272) is never set.
- `cmd/api/main.go` ~L1060-1150: bridge store, `bridge.Expirer` and `bridge.Dispatcher`
  goroutines; no `receipt.Sweeper`.
- `internal/glovo/receipt/ready.go`: `receipt.Ready(ctx, Deps)` checks explicit URLs, five
  collaborators (`WorkItems, Bridge, Orders, Conns, Members`), `GlovoStoreReady`,
  `ProveOneDatabase`, `workitems.VerifyGlovoApprovalSchema`, policy admission,
  basket contract, `WireVersionsEnabled`, and the joint-state `Audit`.
- `internal/glovo/receipt/fence.go`: `NewFence(Approvals, Orders, Conns, Membership)`.
- `internal/glovo/receipt/sweeper.go`: `Sweeper{Begin, Approvals}` with `Sweep` and
  `Run(ctx, interval, onErr)`; doc says #985 task 9 owns the goroutine (OPEN-989-8).
- `internal/workitems/glovo_decisions.go`: `GlovoDecisions{Store, Reader, Begin, ReadyFn}`.
- `internal/workitems/glovo_approvals.go` L27: `WithGlovoOrders(GlovoOrders)`.
- `internal/workitems/apply_schema.go` / `apply_glovo.go`: `ApplySchema` and
  `ApplyGlovoApprovalSchema(ctx, migrationConnStr, runtimeRole, WithWorkItemsRole(..))`;
  the latter runs the former and refuses `runtimeRole == workItemsRole`. Neither has any
  caller outside tests (`grep` over `cmd/` and `internal/`). The same holds for
  `glovo.ApplySchema`, `orders.ApplySchema`, `glovojoin.ApplySchema`, `bridge.ApplySchema`.
- Every `roleNameRE` (`internal/workitems/apply_schema.go` L29, `internal/glovo/store.go`
  L34, `internal/bridge/runtime.go` L53, ...) is `^[a-z_][a-z0-9_]{0,62}$`.
- `internal/glovo/orders/store.go` L239: `orders.NewStore(ctx, pool, runtimeRole,
  migrationRole, conns, execs)`; not constructed in `cmd/api`.
- `internal/glovo/control/prove.go` L62: `ProveOneDatabase(ctx, bs, gs, workItems *pgxpool.Pool)`
  requires the bridge and Glovo stores to share one pool and the work-items pool to reach
  the same database.
- Payload writers: `bridge_commands` is inserted only by `internal/bridge/store.go`
  (`Store.Enqueue`, L616/L671) and `internal/bridge/readstore.go` (`EnqueueRead`, read
  kinds only). The only production `.Enqueue(` call on a bridge store is
  `internal/glovo/control/dispatcher.go` L388, which at "Step 11" reads
  `Orders.Snapshot(..., o.FinalSnapshotSeq)`, re-parses it with `basket.Parse` and refuses
  `CodeBasketChanged` on any fingerprint mismatch before enqueuing the snapshot bytes. The
  schema constraint in `internal/bridge/readschema.go` L141 requires `approval_ref <> ''`
  for `place_order_fake`, and a unique index (`internal/bridge/runtime.go` L56-60) allows
  one `place_order_fake` row per approval.
- `internal/glovo/basket/contract/PROVENANCE` pins the vendored #1059 contract (mctl-agents
  commit `46ccddce...`) by SHA-256; `TestVendoredContractMatchesProvenance` enforces it.
- `cmd/bridge-scrub/main.go`: precedent for a one-shot, `-confirm`-gated maintenance binary
  that the API server never starts.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml` (Application
  `admins-mctl-api`): sets `AUDIT_DB_URL=postgresql://$(DB_USER):$(DB_PASSWORD)@shared-pg-rw.platform-db.svc:5432/mctl-api`
  and `LIFECYCLE_DB_URL`; no `WORK_ITEMS_DB_URL`, `GLOVO_DB_URL`, `COMMERCE_DB_URL`,
  `MCTL_BRIDGE_ENABLED`, `GLOVO_ENABLED` or `GLOVO_DB_*_ROLE` entries were found by grep.
  So the work-items store runs on database `mctl-api` through the fallback.
- `$MCTL_GITOPS_ROOT/infra-components/data/cnpg/shared/databases.yaml`: CNPG `Database`
  `mctl-api` on cluster `shared-pg`, `owner: "mctl-api"`. The actual `DB_USER` value comes
  from a secret that was not read; the owner field indicates the role is `mctl-api`.
- grep for `glovo_runtime` / `glovo_migrator` under `platform-gitops/` outside
  `agents-state/`: no hits on `main`. mctl-gitops#2563 (draft, staged under
  `deploy/staged/glovo-m1/`, inert) was read on its branch for this amendment; see section 10
  for what it stages and where it differs from this design.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-api/proposals/issue-989-.../closure-decision.md`:
  read for context (verified against `675dff75`).
- mctl MCP tools were not used; the gitops checkout answered the questions above.

## Proposed solution

Six code slices (1 to 6), all inside the existing dark switches, plus the role, verification,
rollback and sequencing sections 7 to 10 (deployment-side; only the section 8 verifier is code). None changes a const gate.

### 1. Migration entry point: `cmd/glovo-migrate`

A new one-shot binary modelled on `cmd/bridge-scrub` (which already refuses to run without
`--confirm=scrub-legacy-results`; `cmd` on `main` holds only `api`, `bridge-scrub`, `mcp`, so
`cmd/glovo-migrate` does not exist yet). `run(ctx, args, getenv, out)` for testability.
Flags/env:
- `-confirm=apply-glovo-approval-schema` (required, no default, not settable from env),
- `GLOVO_MIGRATION_DB_URL` (connection as `glovo_migrator`; required; no fallback),
- `-glovo-runtime-role` (default `glovo_runtime`), `-work-items-role` (required, no default;
  the deployed value is `mctl_api_workitems`).

Control flow, in this order, each stage a hard gate for the next:
1. Validate flags and role names (`roleNameRE`, distinct roles). No connection is opened.
   Wrong or missing `-confirm` exits non-zero here.
2. Connect as the migration role and run the read-only ownership pre-check in a
   `READ ONLY` transaction: for the selected steps, list every relation, sequence,
   function and the schema `glovo` whose owner is not `current_user`; check the named roles
   exist; check `current_user` is not a superuser and is the expected migrator. Any
   foreign-owned object exits 2 and prints the operator step (an `ALTER ... OWNER TO` text
   for the operator to run by hand); any read error exits 1. Neither issues DDL.
   Because the pre-check needs the object lists, `internal/workitems` and
   `internal/bridge` gain small exported read-only helpers (for example
   `workitems.ForeignOwnedObjects(ctx, q)`) built on the same unexported lists
   (`genericRelations`, `genericFunctions`, `glovoApprovalRelations`, bridge
   `ownedRelations`) that `ApplySchema` already uses, so the pre-check and the refusal
   inside `ApplySchema` cannot drift. The refusal inside `ApplySchema`
   (`checkGenericOwnership`, `checkGlovoApprovalOwnership`, before and after the DDL, in one
   transaction) stays as the second line of defence.
3. Only then call `workitems.ApplyGlovoApprovalSchema(ctx, dsn, glovoRuntimeRole,
   workitems.WithWorkItemsRole(workItemsRole))`, which runs `workitems.ApplySchema` first.

The binary never performs an ownership transfer and no flag exists to do so. Optional flags
`-with-glovo`, `-with-bridge`, `-with-orders`, `-with-join` run the other `ApplySchema`
functions in dependency order (glovo, bridge, orders, join, then approval schema; the bridge
step passes `bridge.WithWorkItemsRole`); they default off and the pre-check covers whatever is
selected. The Dockerfile gains the binary next to `bridge-scrub`. Nothing is applied by this
change.

Role name (D1, decided): the work-items role is `mctl_api_workitems`, a new login role
created at the deployment gate, used through an explicit `WORK_ITEMS_DB_URL` on database
`mctl-api`. The code takes the role as a flag and no role-name rule is widened.

### 2. Collaborator construction in `cmd/api` (new file `cmd/api/glovo_receipt.go`)

A pure function `buildGlovoLedger(ctx, glovoLedgerDeps) (*glovoLedger, error)` returning
the orders store, `GlovoDecisions`, the fence builder and the sweeper, so `main.go` only
calls it. Steps:
- Construct `orders.NewStore(ctx, glovoStore.Pool(), runtimeRole, migrationRole, glovoStore, execs)`
  when `glovoStore` and `bridgeStore` exist and the bridge runs on the Glovo pool.
- Move the work-items store construction so it can receive
  `workitems.WithGlovoOrders(ordersStore)` (built before the work-items store; work items
  do not depend on orders' construction order beyond this option).
- Add a `Pool()` accessor on `workitems.Store` (field already exists at
  `internal/workitems/store.go` L207) and pass it to `controlProof` instead of `nil`.
- `GlovoDecisions{Store: workItemsStore, Reader: glovoStore.Pool(), Begin: bridgeStore.Pool().Begin, ReadyFn: readyFn}`
  assigned to `api.Options.GlovoApprovals`.
- `readyFn` closes over `receipt.Deps` filled only with observed values:
  `GlovoURLExplicit`/`WorkItemsURLExplicit` from `controlEnvReady`-style lookups,
  `GlovoStoreReady: glovoStore.Ready`, `ProveOneDatabase: controlProof(...)`,
  `Glovo` and `Audit` = Glovo pool, `Policies` = the registered governance set,
  collaborators = the actual stores and `gitReader`, and
  `WireVersionsEnabled: bridgeStore.WireVersionsEnabled`. A nil collaborator stays nil.
- `Build` in `installWriteFence` becomes: `if err := readyFn(ctx); err != nil { return nil, err }`
  then `receipt.NewFence(workItemsStore, ordersStore, glovoStore, gitReader)`. The reason
  code from `glovo.NotReadyError` is added to the existing "glovo write fence" log line.

Because `installWriteFence` already ANDs all six preconditions and the gate and hold are
const false, the fence still cannot install. `Proof` is still evaluated only behind the
gate; `Build` (and so `receipt.Ready`) is evaluated only when `pre.GateOpen &&
pre.HoldLifted` to avoid DB load in closed-gate releases. That requires a small change in
`installWriteFence`: call `d.Build` only when `d.Gate && d.HoldLifted`, otherwise
`ReceiptReady=false`. This keeps "never observed is false".

### 3. Receipt sweeper

In `buildGlovoLedger`, when the ledger is wired, return
`&receipt.Sweeper{Begin: bridgeStore.Pool().Begin, Approvals: workItemsStore}`. `main.go`
starts `go sweeper.Run(rootCtx, interval, onErr)` with interval from
`MCTL_GLOVO_RECEIPT_SWEEP_INTERVAL` (default 30 s, invalid value warns and uses the
default, same pattern as `MCTL_BRIDGE_EXPIRY_SWEEP_INTERVAL`). `onErr` logs and increments
`mctl_api_glovo_receipt_sweep_errors_total`; a `mctl_api_glovo_receipt_sweep_moved_total`
counter wraps `Sweep` via a small `sweepTick` helper. `bridge.Expirer` is not changed (owner
decision). The sweeper is started regardless of the gate: it only moves `reserved`
approvals whose command already ended, which is safe and needed even while dark.

### 4. Membership-revocation detector (separate slice, `internal/glovo/membershipwatch`)

`Detector{Conns ConnLister, Members Membership, Revoke func(ctx, tenant, principal) error, Interval, Clock}`:
each tick lists distinct (tenant, owner) pairs of live connections, asks `IsMember` with
`glovo.BoundedMembership`, and calls `glovoStore.RevokeForMembership` for non-members. Only
a tick that completed without a read error stores `lastHeartbeat`. `Probe()` returns
`now - lastHeartbeat <= 5m && !lastHeartbeat.IsZero()`. `glovoStoreOptions` gains
`glovo.WithMembershipRevocationProbe(detector.Probe)` and
`WithMembershipRevoker("membershipwatch")`; `main.go` starts `detector.Run(rootCtx)` when
`glovoStore != nil`. A listing method on `glovo.Store` (`LiveOwnersForRevocation`, bounded,
runtime role) is added if absent. Because the store is built before the detector, the
probe is a closure over a detector pointer set after construction (nil detector reads
false).

### 5. Payload ownership test (OPEN-989-4)

`internal/glovo/control/payload_owner_test.go`: a `go/packages`-free AST walk over the
module's non-test Go files that finds every call to `(*bridge.Store).Enqueue` (by method
name on an expression whose type package is `internal/bridge`, using `go/types` from
`golang.org/x/tools/go/packages` if already a dependency, else a syntactic match on
`.Enqueue(` with an `bridge.EnqueueInput` literal) and asserts the set is exactly
`internal/glovo/control/dispatcher.go`. Plus a DB-free unit test of the dispatcher that a
snapshot whose fingerprint differs from `FinalBasketFingerprint` yields
`CodeBasketChanged` and no `Enqueue` (if not already covered; reuse existing fakes).
The client contract stays pinned by `PROVENANCE`; the design cites it.

### 6. Activation-time proof under real roles

`cmd/api/glovo_activation_test.go`, gated on `TEST_DATABASE_URL` like the existing
split-role tests: create `glovo_migrator`, `glovo_runtime`, `mctl_api_workitems`; run
`cmd/glovo-migrate`'s `run` with all schema flags; connect as `glovo_runtime`; assert
`glovoStoreOptions(true)` installs `bridge.CancelOpenForConnections` (via the existing
`assertControlHook`); end a connection and assert its open command is cancelled; assert
`receipt.Ready` is nil when every collaborator is wired and the membership probe true, and
that `installWriteFence` still returns `installed=false` with the const hold false.

### 7. Work-items role, grants, ownership and compatibility (D1, D2 step 2)

Roles (names are defaults and flags; all match `roleNameRE`):

| Role | Purpose | May hold | Must not hold |
| --- | --- | --- | --- |
| `glovo_migrator` | runs `cmd/glovo-migrate` | owner of the migrated objects, DDL | superuser, CREATEROLE, CREATEDB, BYPASSRLS, replication; no use by the API pod |
| `glovo_runtime` | Glovo and bridge runtime | the rows of `RuntimeGrants()` and `glovoPublicGrants`, column-level UPDATE on `action_approval_requests` | DDL, ownership |
| `mctl_api_workitems` | work-items store (`WORK_ITEMS_DB_URL`) | exactly `genericGrants`, USAGE on `work_item_intents_id_seq`, SELECT on `bridge_colocation_probe` | DDL, ownership, any right in schema `glovo`, the attributes above |

Verified in code: `ApplySchema` grants the work-items role exactly `genericGrants` (SELECT,
INSERT, UPDATE per table; DELETE only on `agent_run_tokens`) with revoke-then-grant, and
`work_item_intents_id_seq` USAGE; `bridge.WithWorkItemsRole` gives SELECT on
`bridge_colocation_probe`; `ApplyGlovoApprovalSchema` refuses `runtimeRole == workItemsRole`
and gives the work-items role nothing in schema `glovo`. The role-creation SQL itself
(CNPG managed role in #2563, or an operator `CREATE ROLE`) is outside the code.

Ownership. `ApplySchema` refuses to run unless the migration role owns every relation in
`genericRelations` (13 tables) and both functions in `genericFunctions`, so for the existing
production database the transfer is strictly necessary for those objects, and only for them
plus whatever the selected optional steps check:
- always: the 13 `genericRelations` and the 2 `genericFunctions` in schema `public`;
- with `-with-bridge`: the bridge `ownedRelations` and `bridge_command_transitions_id_seq`,
  only if they exist (UNVERIFIED whether any bridge table exists in production; the bridge
  is off and `COMMERCE_DB_URL` is unset in the deployed Application);
- with the approval schema: schema `glovo` and its relations and functions, only if they
  exist (UNVERIFIED; expected absent, in which case the migrator creates them and owns them).
The transfer is an operator step with its own approval (D2 step 2), run by hand from the
printed pre-check output, never by code. UNVERIFIED: whether sequences owned by a table
move with `ALTER TABLE ... OWNER TO`; the operator runbook must check
`pg_class.relowner` of `work_item_intents_id_seq` afterwards (the pre-check covers it).

Compatibility with existing WorkItems and DevLoop. Production today runs the work-items
store as role `mctl-api` through the `AUDIT_DB_URL` fallback (verified in the deployed
Application and `workItemsStoreSource()`). `NewStore` runs DDL only when it owns
`public.work_items` (`ownsTables`); otherwise it only reads `work_items_schema_version`
(`verifySchemaVersion`). After an ownership transfer that pod would be a non-owner and
would lose every owner privilege, including SELECT on the version table, so a pod restart
would fail. Therefore, before any transfer, the operator step first grants the legacy role
`mctl-api` the same DML as `genericGrants` and SELECT on `work_items_schema_version` (a
transitional grant), so the unchanged production DSN keeps working across the transfer
without a deploy and without a DSN change. The switch of production to `WORK_ITEMS_DB_URL`
as `mctl_api_workitems` is a separate later action under its own approval and happens after
grants verification (section 8). The transitional grant is revoked only after that switch is
confirmed healthy. UNVERIFIED: that no other service or role reads or writes these tables
(DevLoop, agents, other pods); the operator inventory (a read-only `pg_class`/`aclexplode`
listing of grantees on the 13 relations) must precede the transfer and any unexpected grantee
stops the step. UNVERIFIED: which image version production runs, so the transitional-grant
reasoning above is stated for the `NewStore` logic on `main` at `081bd6b7`.

### 8. Grants and ownership verification (read-only)

A verifier (library function in `internal/workitems` plus a read-only mode usable by the
operator; it opens no write transaction) reports, per role, the live state against the
in-code tables: ownership of every object of the selected steps, table and column
privileges via `has_table_privilege`/`aclexplode`, sequence privileges, role attributes
(`pg_roles`), and that `mctl_api_workitems` has no privilege in schema `glovo`. Output is
`ok`, `diverged` (with each extra or missing item) or `unknown` (any failed read); `unknown`
never satisfies a check. It runs: after the deployment gate (step 2), after the migration
(step 3), and before wiring is enabled (step 4). It is accepted only when proven both ways:
green on a converged database and red after deliberate mutations (an extra `GRANT`, a
missing grant, a runtime-owned table, a superuser role), each mutation confirmed by
reverting the check and watching the test fail.

### 9. Rollback per step

- Step 1 (#2563 staging): close the PR or revert; nothing was reconciled.
- Step 2 (roles, grants, transfer): record, before the step, the catalog state it changes
  (owner and ACL of the objects, existence of the roles). Roll back by transferring the
  transferred objects back to `mctl-api` by hand and revoking the new grants; the legacy
  role's transitional grant makes this safe in any order. Created roles are inert without
  grants and may stay; dropping one needs `DROP OWNED`/`REASSIGN OWNED` and is a separate
  operator decision.
- Step 3 (migration): the schemas are additive and idempotent; they can stay in place when
  code is reverted (see Rollback in tasks.md). The ownership pre-check makes a refused run
  change nothing (the apply is one transaction per function under advisory locks).
- Step 4 (wiring enabled): unset the flags (`GLOVO_ENABLED`, `MCTL_BRIDGE_ENABLED`,
  `MCTL_GLOVO_CONTROL_ENABLED`) and the new env; the pod returns to today's path. The write
  fence was never lifted, so no write can have been permitted.
- Production DSN: never changed by this proposal; its later switch rolls back by restoring
  the previous `WORK_ITEMS_DB_URL`/`AUDIT_DB_URL` value.

### 10. Sequence and dependency on mctl-gitops#2563 (D2)

Each gate is an explicit approval, not a side effect of the previous step.

1. A15 mctl-gitops#2563 (draft). On its branch it stages, inert and outside any Argo CD
   match: ExternalSecrets for `glovo_runtime` and `glovo_migrator`, a suspended migration
   Job, CNPG managed-role fragments (connection limits 16 and 2), and env fragments with
   `GLOVO_DB_URL`. This design needs it extended (it is not edited by this proposal):
   `mctl_api_workitems` (managed role, credential ExternalSecret, `WORK_ITEMS_DB_URL`),
   `GLOVO_DB_RUNTIME_ROLE` and `GLOVO_DB_MIGRATION_ROLE` (required by
   `configureGlovoTeamGrants` when `GLOVO_ENABLED`), the `mctl-api` database name, the
   transitional-grant and ownership plan as operator text, and the job inputs of the
   `cmd/glovo-migrate` binary (`GLOVO_MIGRATION_DB_URL`, `-work-items-role`, `-confirm`).
   Mismatches are listed in the pull request that carries this amendment.
2. Deployment gate (operator, separate approval): role creation, grants (including the
   transitional grant), ownership transfer limited to section 7, then section 8 verification.
3. `cmd/glovo-migrate` as `glovo_migrator` with the pre-check and explicit `-confirm`. The
   suspended Job in #2563 stays `suspend: true` until this step is approved; the `/bin/false`
   command and placeholder image tag are replaced only by the activation change.
4. Wiring enabled after steps 2 and 3 are verified, flags closed, write fence on. Code that
   implements the wiring may be merged dark earlier (every path is behind the closed flags).

## Alternatives

- Run migrations at API startup (like other stores' `CREATE TABLE IF NOT EXISTS`).
  Rejected: the #989 design requires the runtime role to own nothing and
  `ApplySchema` refuses relations owned by another role; startup DDL would need the
  migrator credential in the long-running pod.
- Extend `bridge.Expirer` to also sweep approvals. Rejected by the owner decision in the
  issue (a second collaborator), and it would couple the bridge package to `workitems`.
- Admit hyphenated role names (`mctl-api`) by quoting identifiers everywhere. REJECTED by
  owner decision D1: it touches the DDL builders of five packages (every `roleNameRE`) that
  build identifiers today, widens the attack surface of role-name handling, and would keep
  the work-items store on the broad owner role. Kept here only as the rejected alternative;
  the chosen path is the dedicated underscore role with explicit `WORK_ITEMS_DB_URL`.
- Let the migration job transfer ownership itself. REJECTED by owner decision D2: no
  automatic ownership change of existing production tables.
- Keep the legacy owner `mctl-api` as the work-items role and avoid any transfer. Not
  possible: `ApplySchema` refuses relations not owned by the migration role, and the Glovo
  triggers must be owned by a role that is not the runtime role.
- Membership revocation via a GitOps webhook instead of polling. Rejected for now: no
  membership-change event exists in mctl-api; a heartbeat poll fails closed naturally.

## Platform impact

- Migrations: new binary only; no DDL runs from `cmd/api`. Applying is an operator step
  through the mctl-gitops#2563 job, after roles exist and ownership is transferred.
- Backward compatibility: with `GLOVO_ENABLED`, `MCTL_BRIDGE_ENABLED` and
  `MCTL_GLOVO_CONTROL_ENABLED` unset (current production), every new code path is skipped;
  `/api/v1/action-approvals` keeps its generic behaviour because `GlovoApprovals` stays nil.
  Adding `WithGlovoOrders` only when an orders store exists keeps existing work-items
  behaviour unchanged otherwise.
- Resource impact: one sweeper goroutine (one bounded query per 30 s) and one detector
  goroutine (one GitOps membership read per live owner per minute) only when Glovo is
  enabled. `receipt.Ready` is not evaluated in closed-gate builds.
- Risks:
  - Role-name mismatch makes the migration refuse: surfaced early by flag validation, not
    at runtime.
  - One-database proof fails if `GLOVO_DB_URL` and `WORK_ITEMS_DB_URL` point at different
    databases: the fence stays uninstalled (fail closed) and the log names
    `one_database_not_proven`.
  - Membership detector false positive (GitOps read glitch) revoking connections: mitigated
    by treating read errors as "skip and no heartbeat", never as "not a member".
  - Ownership transfer breaks the legacy `mctl-api` pod: mitigated by the transitional grant
    and the operator inventory before the transfer (section 7); the transfer is never
    automatic.
  - Role or grant drift between code tables and the live database: the section 8 verifier,
    green only on a converged database, `unknown` on any failed read.
  - Moving work-items store construction order in `main.go`: covered by the existing
    `cmd/api` tests plus a new wiring test.
