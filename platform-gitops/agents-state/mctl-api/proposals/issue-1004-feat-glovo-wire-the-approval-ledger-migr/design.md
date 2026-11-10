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
   `READ ONLY` transaction. It observes, for the selected steps: every relation, sequence,
   function and the schema `glovo` whose owner is not `current_user`; that the named roles
   (`glovo_runtime`, the work-items role) exist; that `current_user` equals the expected
   migrator and is not a superuser; that `current_user` holds CREATE on the database (needed
   for `CREATE SCHEMA glovo`) and CREATE on schema `public` (needed to create
   `work_items_schema_version` and the bridge tables). The expected migrator comes from the
   flag `-migrator-role` (default `glovo_migrator`, validated by `roleNameRE`; no env
   override). Exit codes: 1 = any read failed or returned a malformed result (outranks
   everything else: a state that could not be observed is never reported as a foreign owner
   or as clean); 3 = observed but wrong: connecting role is not the expected migrator, a named
   role is missing, or a CREATE privilege is absent; 2 = observed foreign-owned objects (the
   operator transfer text is printed). Precedence when several apply: 1, then 3, then 2.
   None issues DDL.
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

The binary never performs an ownership transfer and no flag exists to do so. Steps
`-with-glovo`, `-with-bridge`, `-with-orders`, `-with-join` run the other `ApplySchema`
functions in dependency order (glovo, bridge, orders, join, then approval schema; the bridge
step passes `bridge.WithWorkItemsRole(<work-items role>)`). They default off so that a
partial run is possible, but they are NOT optional for activation (D2 step 4): verified in
`internal/glovo/control/prove.go` (L39, L78-88) that `ProveOneDatabase` inserts a nonce into
`bridge_colocation_probe` on the bridge pool and reads it back through the work-items pool, so
the bridge step with the work-items grant on that table is required, and `receipt.Ready`
needs `GlovoStoreReady` and the orders store (`ready.go`, see Current state), hence the glovo
and orders steps. The activation checklist therefore requires a run with all four flags, and
the verifier (section 8) must report the full set `ok` before step 4. The pre-check covers
whatever is selected.

Read-only mode. `cmd/glovo-migrate -verify` runs the section 8 verifier and the pre-check
in a `READ ONLY` transaction, issues no DDL and needs no `-confirm` (it changes nothing).
Its credential is `GLOVO_MIGRATION_DB_URL`, the operator-held `glovo_migrator` login (the
catalog reads it needs are available to any login; it is never mounted into the API pod).
The Dockerfile gains the binary next to `bridge-scrub`. Nothing is applied by this change.

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
| `glovo_migrator` | runs `cmd/glovo-migrate` | owner of the migrated objects; CREATE on the database (for `CREATE SCHEMA glovo`) and CREATE on schema `public` (for the version table and bridge tables) | superuser, CREATEROLE, CREATEDB, BYPASSRLS, replication; no use by the API pod |
| `glovo_runtime` | Glovo and bridge runtime | the rows of `RuntimeGrants()` and `glovoPublicGrants`, column-level UPDATE on `action_approval_requests` | DDL, ownership |
| `mctl_api_workitems` | work-items store (`WORK_ITEMS_DB_URL`) | exactly `genericGrants`, USAGE on `work_item_intents_id_seq`, SELECT on `bridge_colocation_probe` | DDL, ownership, any right in schema `glovo`, the attributes above |

Verified in code: `ApplySchema` grants the work-items role exactly `genericGrants` (SELECT,
INSERT, UPDATE per table; DELETE only on `agent_run_tokens`) with revoke-then-grant, and
`work_item_intents_id_seq` USAGE (`grantGeneric`); `bridge.WithWorkItemsRole` gives SELECT on
`bridge_colocation_probe`; `ApplyGlovoApprovalSchema` refuses `runtimeRole == workItemsRole`
and gives the work-items role nothing in schema `glovo`. The role-creation SQL itself
(CNPG managed role in #2563, or an operator `CREATE ROLE`) is outside the code.
The CREATE-privilege needs of `glovo_migrator` follow from the DDL the code runs
(`CREATE SCHEMA IF NOT EXISTS glovo`; `CREATE TABLE` in `public`). The PostgreSQL rule that
`ALTER TABLE ... OWNER TO` needs the new owner to hold CREATE on the table's schema and the
operator to be a member of both the current and the new owner role is documented PostgreSQL
behaviour, UNVERIFIED against this server's version here; the runbook (task 14) states it and
the pre-check observes the CREATE privileges. The operator runs the transfer after `SET ROLE`
to a role that is a member of both owners, never as the API's runtime role.

Ownership scope ("strictly necessary"). `ApplySchema` refuses to run unless the migration
role owns every relation in `genericRelations` (13 names) and both functions in
`genericFunctions`. Not all 13 exist in an existing production database: only `ApplySchema`
creates `public.work_items_schema_version` (`CREATE TABLE IF NOT EXISTS`, `apply_schema.go`);
it is not in `genericSchemaBlocks`, and owner-mode `NewStore` runs only those blocks, so
production has at most 12 of the 13 until the version table exists. UNVERIFIED: which of the
13 exist in production and which image version runs (images before `d2cca35` never create the
version table). The scope is therefore the generic relations and functions that already exist
in `public` (read-only evidence: a `pg_class`/`pg_proc` owner listing) plus, per selected
step, only objects that already exist:
- bridge step (required for activation, see section 1): the bridge `ownedRelations`
  (including `bridge_colocation_probe`) and `bridge_command_transitions_id_seq`, only those
  that exist;
- commerce tables: not owned by the migration steps of this proposal. UNVERIFIED which
  commerce or bridge objects exist and who owns them. Required read-only evidence before the
  gate: owner and ACL listing of the relations named in `ownedRelations` and of every table
  the `COMMERCE_DB_URL` store creates. Nothing is guessed; objects that do not exist are
  created by the migrator and owned by it;
- approval schema: schema `glovo` and its objects, only if they exist (UNVERIFIED, expected
  absent).
The transfer is an operator step with its own approval (D2 step 2), run by hand from the
printed pre-check output, never by code. UNVERIFIED: whether a sequence owned by a table
moves with `ALTER TABLE ... OWNER TO`; the pre-check and verifier read `relowner` of
`work_item_intents_id_seq` afterwards, and the transfer text transfers it explicitly when it
did not move.

Compatibility with existing WorkItems and DevLoop. Production today runs the work-items
store as role `mctl-api` through the `AUDIT_DB_URL` fallback (verified in the deployed
Application and `workItemsStoreSource()`). `NewStore` runs DDL only when it owns
`public.work_items` (`ownsTables`); otherwise it reads `work_items_schema_version`
(`verifySchemaVersion`). After an ownership transfer the legacy pod is a non-owner, loses
every owner privilege, and a restart runs `verifySchemaVersion`. Two things must hold before
the transfer or a restart fails: the legacy role keeps its DML, and the version table exists,
holds exactly one row equal to the compiled version (1) and is readable by it. Because only
`ApplySchema` creates that table, a transfer alone leaves two failing windows: before the
migration the relation is missing, and after the migration it exists but is owned by the
migrator with no SELECT for the legacy role.

Chosen approach (REQUIRES owner/operator confirmation; not yet decided by the owner):
pre-create the version table as the legacy owner BEFORE the transfer, in the same operator
step: `CREATE TABLE IF NOT EXISTS public.work_items_schema_version (version INT NOT NULL)`
plus one row `1`, run as `mctl-api`. It then (a) is one of the 13 relations the transfer
moves, so `ApplySchema`'s ownership check passes, (b) is granted SELECT to the legacy role
before the transfer, so there is no window, and (c) is rewritten by `ApplySchema` as the owner
(`DELETE` then `INSERT` of the same version). Rejected alternative: grant SELECT to the legacy
role only right after the migration and define a maintenance window in which no legacy pod
may restart; it leaves a failing window and needs a freeze of restarts and rollouts. If the
operator prefers the window variant, the runbook must state the window and the freeze.
Residual risk of the chosen approach: the pre-created row asserts version 1 before
`ApplySchema` has run; this is harmless because the generic DDL block is what `NewStore`
already ran as owner, and the migration re-records the same value.

Transitional grant to the legacy role `mctl-api`, executed BEFORE the transfer, mirrors what
`grantGeneric` gives the work-items role, without any REVOKE: the `genericGrants` privileges
on each existing generic table (SELECT, INSERT, UPDATE; DELETE on `agent_run_tokens`), SELECT
on `work_items_schema_version`, and USAGE on `public.work_item_intents_id_seq`. UNVERIFIED:
whether the legacy role needs more than `genericGrants` for DevLoop paths (the table is "read
off the statements in this package"); the inventory below must confirm. With this grant and
the pre-created version table the unchanged production DSN keeps working across the transfer
without a deploy. The switch of production to `WORK_ITEMS_DB_URL` as `mctl_api_workitems` is
a separate later action under its own approval, after grants verification (section 8); the
transitional grant is revoked only after that switch is confirmed healthy and only while the
legacy role owns none of the objects. UNVERIFIED: that no other service or role reads or
writes these tables; the read-only inventory (`pg_class` owner and `aclexplode` grantees on
the relations) must precede the transfer, and any unexpected grantee stops the step.

### 8. Grants and ownership verification (read-only)

A verifier (library function in `internal/workitems` and `cmd/glovo-migrate -verify`, which
opens only a `READ ONLY` transaction) reports, per role, the live state against the in-code
tables: ownership of every object of the selected steps, table and column privileges via
`has_table_privilege`/`aclexplode`, sequence privileges, role attributes (`pg_roles`), the
CREATE privileges of `glovo_migrator`, and that `mctl_api_workitems` has no privilege in
schema `glovo`. Output is `ok`, `diverged` (each extra or missing item) or `unknown` (any
failed read); `unknown` never satisfies a check and outranks `diverged`. Entry point and
credential: `cmd/glovo-migrate -verify` with `GLOVO_MIGRATION_DB_URL`, run by the operator or
as a job of the same image; any login can read the catalogs, and the migrator credential is
used only because it is the operator-held one. It runs after the deployment gate (step 2),
after the migration (step 3), and before wiring is enabled (step 4). It is accepted only when
proven both ways: green on a converged database and red after deliberate mutations (an extra
`GRANT`, a missing grant, a runtime-owned table, a superuser role, a missing CREATE
privilege), each mutation confirmed by reverting the check and watching the test fail.

### 9. Rollback per step

- Step 1 (#2563 staging): close the PR or revert; nothing was reconciled.
- Step 2 (roles, grants, version table, transfer): BEFORE the step the operator records the
  catalog state it will change: owner and full ACL (`relacl`, column ACLs, sequence ACL) of
  every object in scope, role existence and attributes, and whether
  `public.work_items_schema_version` and schema `glovo` existed. Rollback restores that
  RECORDED owner and ACL; it is NOT "revoke what was granted". It never runs `REVOKE` against
  a role that is the (restored) owner of the object: if `mctl-api` owns the tables again,
  revoking its transitional grant would strip its owner privileges. Order: restore ownership
  first (`ALTER ... OWNER TO mctl-api`, as an operator with the needed memberships), then reset
  each ACL to the recorded one (`REVOKE ALL ... FROM <grantee>` only for non-owner grantees
  that were absent in the record, then re-`GRANT` the recorded rows). No order is claimed
  safe without the record. Created roles are inert without grants and may stay; dropping one
  needs `DROP OWNED`/`REASSIGN OWNED` and is a separate operator decision.
  If step 3 has already run, rolling back step 2 leaves behind the objects the migration
  created. Disposition (the exact list is produced from the pre-change record plus the
  migration's object lists):
  - `public.work_items_schema_version`: if it did not exist before step 2, keep it (harmless to
    the legacy code, which then reads version 1); drop only after the legacy image no longer
    needs it.
  - schema `glovo`, `glovo.approval_bindings`, `glovo.approval_schema_version`, the three
    trigger functions and the triggers `aar_guard` and `aar_binding_required` on
    `public.action_approval_requests`: the operator drops or disables them BEFORE ownership
    returns to `mctl-api`, because `aar_guard` rejects glovo-kind rows for any role but the
    runtime role and a migrator-owned trigger would otherwise stay on a table `mctl-api` owns.
  - the widened state and kind CHECK constraints on `action_approval_requests`: keep (a
    superset for generic rows); UNVERIFIED that the legacy code never writes `reserved` or
    `unknown`.
  - bridge tables, `bridge_colocation_probe` and `bridge_schema_version` created by the bridge
    step: keep, inert while the bridge flags are off; the `bridge_schema_version` row selects
    `NewRuntimeStore`, so it must be removed if the old `NewStore` path must be restored
    (UNVERIFIED).
- Step 3 (migration): the schemas are additive and idempotent and can stay in place when code
  is reverted. The pre-check makes a refused run change nothing (each apply is one
  transaction under advisory locks).
- Step 4 (wiring enabled): unset the flags (`GLOVO_ENABLED`, `MCTL_BRIDGE_ENABLED`,
  `MCTL_GLOVO_CONTROL_ENABLED`) and the new env; the pod returns to today's path. The write
  fence was never lifted, so no write can have been permitted.
- Production DSN: never changed by this proposal; its later switch rolls back by restoring the
  previous `WORK_ITEMS_DB_URL`/`AUDIT_DB_URL` value.

### 10. Sequence and dependency on mctl-gitops#2563 (D2)

Terminology (owner clarification 2026-11-10). P0/P1: `glovoWriteFenceHoldLifted` stays
`false`, `bridge.Store.SetFence` is NOT called (the bridge keeps its default refusing fence),
all flags are OFF, zero fake effects. P2: a separately authorized activation of a real, ready,
fail-closed `receipt.NewFence` that permits only owner-approved, single-use fake `aar_`
writes. "Write fence on" in D2 step 4 means the P0/P1 state. This proposal covers P0/P1 only.

Each gate is an explicit approval, not a side effect of the previous step.

1. A15 mctl-gitops#2563 (draft). On its branch it stages, inert and outside any Argo CD match:
   ExternalSecrets for `glovo_runtime` and `glovo_migrator`, a suspended migration Job, CNPG
   managed-role fragments (connection limits 16 and 2) with role-specific pg_hba lines for
   those two roles, and env fragments with `GLOVO_DB_URL`. This design needs it extended (it
   is not edited by this proposal): `mctl_api_workitems` (managed role, credential
   ExternalSecret, its own pg_hba line `host mctl-api mctl_api_workitems all scram-sha-256`,
   `WORK_ITEMS_DB_URL`), `GLOVO_DB_RUNTIME_ROLE` and `GLOVO_DB_MIGRATION_ROLE` (required by
   `configureGlovoTeamGrants` when `GLOVO_ENABLED`), the `mctl-api` database name, the CREATE
   privileges of `glovo_migrator`, the pre-created version table, the transitional grant and
   ownership plan as operator text, and the job inputs of `cmd/glovo-migrate`
   (`GLOVO_MIGRATION_DB_URL`, `-work-items-role`, `-migrator-role`, `-with-*`, `-confirm`).
   The Job's `/bin/false` command and `PENDING-985-TASK-4` image tag are to point at this
   proposal's `cmd/glovo-migrate` (mctl-api#1004) once it ships, not at #985 task 4.
   Mismatches are listed in the pull request that carries this amendment.
2. Deployment gate (operator, separate approval): role creation, CREATE privileges, grants
   (including the transitional grant and the pre-created version table), ownership transfer
   limited to section 7, then section 8 verification.
3. `cmd/glovo-migrate` as `glovo_migrator` with the pre-check and explicit `-confirm`, all four
   `-with-*` steps for the activation run. The suspended Job in #2563 stays `suspend: true`
   until this step is approved.
4. Wiring enabled after steps 2 and 3 are verified, flags closed (P0/P1 state). Code that
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
