# Design: issue-1004-feat-glovo-wire-the-approval-ledger-migr

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
  `agents-state/`: no hits. mctl-gitops#2563 (draft) is not on the checked-out `main` and
  was not observed.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-api/proposals/issue-989-.../closure-decision.md`:
  read for context (verified against `675dff75`).
- mctl MCP tools were not used; the gitops checkout answered the questions above.

## Proposed solution

Six slices, all inside the existing dark switches. None changes a const gate.

### 1. Migration entry point: `cmd/glovo-migrate`

A new one-shot binary modelled on `cmd/bridge-scrub` (`run(ctx, args, getenv, out)` for
testability). Flags/env:
- `-confirm=apply-glovo-approval-schema` (required),
- `GLOVO_MIGRATION_DB_URL` (connection as `glovo_migrator`; required; no fallback),
- `-glovo-runtime-role` (default `glovo_runtime`), `-work-items-role` (required, no default).

It calls `workitems.ApplyGlovoApprovalSchema(ctx, dsn, glovoRuntimeRole,
workitems.WithWorkItemsRole(workItemsRole))`, which runs `workitems.ApplySchema` first in
the same role. An ownership refusal is printed with the operator step
(`ALTER TABLE ... OWNER TO glovo_migrator` for the listed relations) and exits 2; the binary
never performs the transfer. Optional flags `-with-glovo`, `-with-bridge`, `-with-orders`,
`-with-join` run the other `ApplySchema` functions in dependency order (glovo, bridge,
orders, join, then approval schema) so one job can migrate the whole M1 database; they
default off. The Dockerfile gains the binary next to `bridge-scrub`, so the inert,
suspended job in mctl-gitops#2563 can invoke it. Nothing is applied by this change.

Role name: the repo-wide role rule refuses `mctl-api`. Rather than widening five regexes
used to build unquoted DDL, the design records `mctl_api_workitems` as the work-items role
(a new login role, granted DML by this migration, used through an explicit
`WORK_ITEMS_DB_URL` on database `mctl-api`). This is pending the clarification in Open
questions; the code takes the role as a flag, so the decision is configuration only.

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

## Alternatives

- Run migrations at API startup (like other stores' `CREATE TABLE IF NOT EXISTS`).
  Rejected: the #989 design requires the runtime role to own nothing and
  `ApplySchema` refuses relations owned by another role; startup DDL would need the
  migrator credential in the long-running pod.
- Extend `bridge.Expirer` to also sweep approvals. Rejected by the owner decision in the
  issue (a second collaborator), and it would couple the bridge package to `workitems`.
- Admit hyphenated role names (`mctl-api`) by quoting identifiers everywhere. Viable but
  touches five packages' DDL builders and their tests; deferred to the clarification. A
  dedicated underscore role also gives the work-items store an explicit
  `WORK_ITEMS_DB_URL`, which `receipt.Ready` requires regardless.
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
  - Moving work-items store construction order in `main.go`: covered by the existing
    `cmd/api` tests plus a new wiring test.
