# Design: issue-985-feat-glovo-m1b-3-control-worker-dispatch

## Current state

Bridge (mctl-api#962, #968), `internal/bridge/`:
- `store.go`: `Store.Enqueue(ctx, tx pgx.Tx, in EnqueueInput) (commandID, created, err)`
  inserts a `pending` row in the caller's transaction. It is idempotent on the unique
  index `bridge_commands_operation_key (tenant, execution_id, operation_key)` and
  issues `cmd_` + 26 base62. `EnqueueInput` already carries `OrderRef`,
  `ConnectionRef`, `InstallRevision`, `IntentHash`, `ApprovalRef`, `OwnerPrincipalID`.
  `validate()` requires an `aar_` `approval_ref` (`^aar_[A-Za-z0-9]{16,40}$`) for
  `place_order_fake` / `cancel_order_fake`, and the table has the CHECK
  `bridge_commands_approval_chk`.
- `Store.Cancel(ctx, tx, commandID, actor)` locks the row `FOR UPDATE` and sets
  `cancelled`, `cancel_requested=true`, and `effect_state permitted -> unknown`.
  A repeat on a cancelled row is a no-op, and a completed or expired row returns
  `ErrAlreadyCompleted`.
- `Store.Pool()` exposes the pool "so a control-plane caller can open the
  transaction it passes to Enqueue". Nothing in the tree calls `Enqueue` from a
  route today. There is no HTTP enqueue route, only `/bridge/commands/claim`,
  `/result` and `/write-permit` (`internal/api/router.go`, bridge-provider only via
  `requireBridgeProvider` / `bridgeProviderGate` in `internal/api/handlers_bridge.go`).
- `permit.go`: `IssueWritePermit` -> `permitTx` locks the command and checks lease,
  kind, `cancel_requested` and `effect_state == none`. It then calls
  `currentFence().Check(ctx, tx, FenceBinding{...})` in the same transaction before
  inserting `bridge_write_permits`. The default `refusingFence` returns
  `ErrWriteFenceUnavailable`, so no permit is ever issued today.
  `SetFence(WriteFence)` installs the #954 fence.
- `cmd/api/main.go` (~L1012): the bridge is dark unless `MCTL_BRIDGE_ENABLED=true`.
  It uses `COMMERCE_DB_URL`, else `AUDIT_DB_URL`.

Approvals (`aar_`), `internal/workitems/action_approvals.go`:
- Table `action_approval_requests` (`id, execution_id, action_kind, target,
  args_digest, intent_hash, state, expires_at, fresh_until, consumed_at, ...`), states
  `pending/approved/denied/consumed/executed` plus the effective `expired` and
  `in_flight`.
- `ConsumeActionApproval(ctx, id, intentHash)` is one CAS
  `approved -> consumed` on `s.pool` (its own implicit transaction, not a caller
  `pgx.Tx`). `ConsumeStateRefusal` maps states to errors.
- There are no tenant, owner, order, connection, install-revision or
  basket-fingerprint binding columns. Those are M1b/2.
- The store uses `WORK_ITEMS_DB_URL`, else `AUDIT_DB_URL` (`workItemsStoreSource`).

Glovo, `internal/glovo/gate.go`: `Gate{Open}`, `Default = Gate{Open: false}` as a
build constant. Codes `not_ready` / `not_authorized` are in `internal/glovo/errors.go`.
`internal/api/glovo_audience_gate.go` lets a Glovo-audience token reach no route.

Dedicated principals: `internal/auth/bridge_provider.go` (`service:bridge-provider:<ref>`,
permission `bridge:provide`, workload token with an exact audience, configured by
`MCTL_BRIDGE_PROVIDERS`) and `internal/auth/orchestrator_devloop.go`
(`service:mctl-orchestrator-devloop`, confined by `orchestratorDevLoopGate`). Each
dedicated principal has a confining middleware in the authenticated group of
`router.go` (`usageWriterGate`, `bridgeProviderGate`, `ciPrincipalGate`, ...).

Tenant membership comes from GitOps: `checkTenantRoleByPrincipal` in
`internal/api/tenant_role.go` and `principalSet` in `tenant_authz_shadow.go`
(`gitops.PrincipalMembership`). It is not a Postgres row.

There is no order index and no connection or revocation store in the clone
(`grep` finds nothing for orders, connections or basket fingerprints). Those land
in M1b/1 and #959/#960.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml`: `AUDIT_DB_URL`
  points at database `mctl-api` on `shared-pg-rw.platform-db.svc`, and
  `LIFECYCLE_DB_URL` at `mctl-lifecycle`. No `COMMERCE_DB_URL`, `WORK_ITEMS_DB_URL`
  or `SURFACE_IDENTITY_DB_URL` appears in that file, so the bridge, work-items and
  identity stores currently fall back to the same `mctl-api` database.
  `MCTL_BRIDGE_ENABLED` does not appear, so the bridge is dark. The comment at L16
  says two replicas.
- `$MCTL_GITOPS_ROOT/infra-components/data/cnpg/shared/databases.yaml`: the
  `mctl-api-db` Database backs the AUDIT_DB_URL-initialised stores.
- `$MCTL_GITOPS_ROOT/services/`: holds only tenant services (admins, karabu, labs,
  namax66). mctl-api is a platform component, not a tenant service, so
  `mctl_get_service_config` was not applicable. MCP tools were not called. The
  env list above comes from the bootstrap template only. The live pod env was not
  observed (see Open questions).

## Proposed solution

### 1. Dedicated control-worker principal (`internal/auth/glovo_control_worker.go`)
- Principal id `service:glovo-control-worker`, permission `glovo:control-dispatch`,
  no tenant, not an admin.
- It authenticates like a bridge provider: a workload token verified against
  `MCTL_GLOVO_CONTROL_WORKER` (JSON `{issuer, subject, audience}`), with the exact
  audience `mctl-api-glovo-control`.
- A half-configured or reserved value disables the mapping and logs once, as
  `orchestratorDevLoopIdentity` does.
- `User.IsGlovoControlWorker()` is false for every other principal type.
- The identity is distinct from user, Glovo facade (`IsGlovoAudience`) and bridge
  provider (`BridgeProviderRef`). Exact-audience matching stops a token minted for
  one from verifying as another.

### 2. Confinement and routes (`internal/api/handlers_glovo_control.go`, `router.go`)
- `glovoControlWorkerGate` sits in the authenticated group next to
  `bridgeProviderGate`. A control-worker principal gets 403 on anything except
  `POST /api/v1/internal/glovo/orders/{order_ref}/{dispatch|cancel}`.
- `requireGlovoControlWorker` on the route group refuses every other principal with
  403 `not_authorized`, which covers users, admins, facade, provider, agent and
  surface tokens.
- The routes are mounted only when the build constant `glovo.ControlDefault.Open`
  is true (new, `false`) and the env `MCTL_GLOVO_CONTROL_ENABLED=true`. When they
  are absent the path answers 404, and when mounted but not ready it answers 503
  `not_ready`.
- `glovoAudienceGate` already denies facade tokens, so the path stays unreachable
  for them.
- The routes have their own `httprate` bucket keyed by principal.
- Body (strict, `readStrictJSON`): `{"approval_ref":"aar_...","execution_id":"we_..."}`
  for dispatch, and `{"execution_id":"we_..."}` for cancel. Unknown fields give 400.
  No payload, basket, endpoint or credential field exists. The provider payload
  comes from the order index row (M1b/1), never from the caller.
- Response: `{"command_id":"cmd_...","order_state":"dispatched","replayed":bool}`.
  Cancel adds `effect_state` from the bridge. Nothing else is returned.

### 3. Store seam (`internal/glovo/control/`)
New package `control` with:
```go
type OrderIndex interface { // M1b/1
    LockOrder(ctx, tx pgx.Tx, orderRef string) (*Order, error)          // SELECT ... FOR UPDATE
    CASOrder(ctx, tx pgx.Tx, orderRef string, fromVersion int64, to OrderState, cmdID, aar string) error
}
type Approvals interface { // M1b/2, tx-scoped
    LockApproval(ctx, tx pgx.Tx, id string) (*workitems.ActionApprovalRequest, *ApprovalBinding, error) // FOR UPDATE
    ConsumeApprovalTx(ctx, tx pgx.Tx, id, intentHash string) error    // same CAS as ConsumeActionApproval, on tx
}
type Connections interface { // #959/#960
    LockConnectionShared(ctx, tx pgx.Tx, connectionRef string) (*Connection, error) // FOR SHARE
}
type Membership interface { IsMember(tenant, principalID string) (bool, error) } // gitops-backed
type Dispatcher struct { Bridge *bridge.Store; Orders OrderIndex; Approvals Approvals; Conns Connections; Members Membership; Ready func() error }
```
- `workitems` gains `ConsumeActionApprovalTx(ctx, tx, id, intentHash)`, which is
  the existing CAS SQL run on a caller `pgx.Tx`. `ConsumeActionApproval` delegates
  to it, so behaviour does not change.
- Nil collaborators make `Ready()` return `not_ready`.

### 4. Co-location proof (fixes the TOCTOU of #954 comment 2026-11-08 point 3)
- The transaction is opened on `bridge.Store.Pool()`, and every lock is taken on
  that same `tx`. That only fences the race if `action_approval_requests`, the
  order index, the connection table and `bridge_commands` live in one database.
- At startup, `control.ProveColocated(ctx, pools...)` runs
  `SELECT system_identifier FROM pg_control_system(), current_database()` on each
  store's pool and requires them all to be equal. It also requires the tables to be
  visible from the bridge pool (`to_regclass` for the four tables).
- Any mismatch or error sets `Ready()` to `not_ready` permanently for the process,
  logs once (no URL), and leaves the fence `refusingFence`.
- Today's deployment falls back to `AUDIT_DB_URL` for all of them, so the proof
  passes. A future split of `WORK_ITEMS_DB_URL` fails closed instead of opening a
  race.

### 5. Dispatch transaction (`Dispatcher.Dispatch`)
1. `Ready()`, else `not_ready`. Begin `tx` on the bridge pool.
2. `LockOrder(order_ref)` `FOR UPDATE`. A missing order, or one whose
   `execution_id` differs from the body, gives `order_not_found`. All dispatches
   of one order serialize here, which gives concurrent-dispatch safety.
3. If `order.state == dispatched`: when `order.approval_ref == body.approval_ref`,
   commit and return `order.command_id` with `replayed=true`. This happens before
   any `aar_` state check, so a consumed receipt replays and is not refused.
   Otherwise return `order_already_dispatched`. `cancelled` gives `order_cancelled`.
   Any state other than `approved` gives `order_state_conflict`.
4. `LockApproval(aar)` `FOR UPDATE`.
   - `ConsumeStateRefusal` maps the state: consumed or in flight gives
     `approval_consumed`, and expired or stale gives `approval_expired`.
   - Binding: tenant, owner, `execution_id`, `order_ref`, `connection_ref`,
     install revision, basket fingerprint and intent hash must equal the locked
     order row. Otherwise `approval_binding_mismatch`, or `order_not_found` for a
     foreign tenant or owner.
5. `LockConnectionShared(connection_ref)` `FOR SHARE`. Revoked, or a current
   revision different from the bound one, gives `connection_revoked`.
6. `Members.IsMember(tenant, owner)`. False or error gives `membership_revoked` /
   `not_ready`.
7. `ConsumeApprovalTx`, then `CASOrder(version, dispatched, cmd, aar)` after the
   enqueue returns the id. The order is: enqueue, then CAS, then consume, all in
   the tx.
8. Enqueue with `bridge.Store.Enqueue(ctx, tx, EnqueueInput{Kind: KindPlaceOrderFake,
   OperationKey: "glovo-dispatch:"+order_ref, ApprovalRef: aar, Attempt: 1, ...})`.
   All fields come from the locked rows. `OperationKey` is per order, so the
   bridge's own unique index is a second idempotency backstop.
9. Additive backstop index:
   `CREATE UNIQUE INDEX IF NOT EXISTS bridge_commands_mutating_approval ON
   bridge_commands (approval_ref) WHERE operation_kind='place_order_fake'`. It
   makes one `aar_` yield at most one command even if a caller bypasses step 3.
10. Commit. Any error rolls back everything (`finish` pattern).

### 6. Cancel transaction (`Dispatcher.Cancel`)
- Lock the order. `approved` CASes to `cancelled`; the `aar_` stays unconsumed, and
  the order state alone prevents it from dispatching.
- `dispatched` calls `bridge.Store.Cancel(ctx, tx, order.command_id,
  "service:glovo-control-worker")` and CASes the order to `cancelled`. The bridge
  sets `permitted -> unknown` and fences a leased command.
  `ErrAlreadyCompleted` maps to 409 `already_completed`, and the order row is left
  for the result path.
- `cancelled` is a no-op that returns 200.
- No path ever writes `approved` back to `action_approval_requests`.

### 7. Revocation race at the actual write
- Dispatch is not the write. The write is `IssueWritePermit`.
- This slice implements `control.Fence` (a `bridge.WriteFence`) with the same
  check function as steps 4-6. It re-locks the `aar_` (`FOR UPDATE`), requires
  state `consumed` bound to this command, re-locks the connection `FOR SHARE`, and
  re-checks membership.
- `main.go` installs it with `bridgeStore.SetFence` only when
  `glovo.ControlDefault.Open` is true and the co-location proof passed. It stays
  `refusingFence` while hold mctl-gitops#2457 is ON.
- The contract required of the #959/#960 revocation writer (documented in
  `docs/glovo-control.md` and asserted by tests through a fake connection store):
  `UPDATE connections SET revoked_at=now(), revision=revision+1` takes the
  exclusive row lock, and in the same transaction it calls `bridge.Store.Cancel`
  for each open command of the connection.
- Race orders:
  - (a) Revoke commits first: the dispatch or permit `FOR SHARE` read sees the
    revoked row and refuses.
  - (b) Dispatch or permit commits first: the revoke's `UPDATE` blocks on the share
    lock until commit. It then cancels the command, so an unpermitted command can
    never get a permit (`cancel_requested`) and a permitted one becomes `unknown`.
  Postgres row locks make these the only two orders.
- Membership is GitOps-backed and cannot be row-locked. That residual is listed in
  Open questions. Until the membership-removal path writes a connection
  revocation, the fence stays refusing.

### 8. Logging and audit
`h.logAudit` records the operation (`glovo.control.dispatch|cancel`), `order_ref`,
`aar_`, `cmd_`, the code and `replayed`. It never records a payload, nonce, lease
token or connection secret, mirroring `auditBridge`. Errors map through one
`glovoControlStatus` table.

## Alternatives

- **HTTP enqueue route on the bridge for the worker.** Rejected by owner decision
  M7=(b) and the issue: it creates a generic write path and splits the `aar_`
  consume from the enqueue across two transactions.
- **Two-phase: consume the `aar_` in the work-items DB, then enqueue in the bridge
  DB, with a compensating outbox.** Rejected: it reopens exactly the TOCTOU from #954
  point 3, and a crash between the phases either loses the approval or double-spends
  it. The co-location proof plus one transaction is simpler and fails closed.
- **SERIALIZABLE isolation instead of explicit row locks.** Rejected: it gives
  retry-driven serialization failures under concurrent dispatch, and does nothing
  for the revocation writer, which is in another code path. Explicit `FOR UPDATE` /
  `FOR SHARE` gives deterministic orders that tests can force.
- **Reuse the orchestrator-DevLoop OIDC principal.** Rejected: the issue requires a
  principal that can do nothing else.

## Platform impact

- **Migrations:** one additive partial unique index on `bridge_commands`, with
  `CREATE ... IF NOT EXISTS` in `bridgeSchema`. If an existing deployment has
  duplicate `place_order_fake` rows for one `approval_ref`, the index creation
  fails. None can exist because no route enqueues today. The
  `ConsumeActionApprovalTx` refactor changes no SQL.
- **Backward compatibility:** the routes are absent unless both the build constant
  and the env flag are on. `ConsumeActionApproval` behaviour is unchanged. The
  default fence is unchanged.
- **Resources:** one short transaction per call holding 3 row locks; negligible.
  With two replicas, row locks serialize across both.
- **Risks:**
  - The DB split silently breaks atomicity. Mitigation: startup proof that fails
    closed.
  - A membership change is invisible to Postgres. Mitigation: fence stays
    refusing, plus an open question.
  - A long lock held by a revocation writer stalls dispatch. Mitigation: the
    30s request timeout, plus `SET LOCAL lock_timeout = '5s'` in the tx, mapping to
    503 `busy`.
  - Token confusion. Mitigation: exact audience and a confining gate.
- **Dependencies:** this can merge before M1b/1 and M1b/2 with nil collaborators
  (`not_ready`). It becomes functional only once they land.

## Open questions

- Live pod env of mctl-api was not observed (MCP tools not used; only the bootstrap
  template was read). Whether a `WORK_ITEMS_DB_URL` or `COMMERCE_DB_URL` override
  exists elsewhere (secret or overlay) is unknown. The startup proof covers it
  either way.
- Membership fencing (see requirements). Fence ownership between M1b/1 and this
  slice. The worker authentication form. The compensating `cancel_order_fake`. The
  M1b/1 and M1b/2 schema names.
