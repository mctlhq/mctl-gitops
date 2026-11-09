# Design: issue-985-feat-glovo-m1b-3-control-worker-dispatch

## Amendment 2026-11-09 (b)

This amendment resolves the independent review of digest
`sha256:a7db8569254a19cfad95ac26d5a437d98591334227a00d857e98705339d45e01` (mctl-api#985:
8 P2, 9 P3). It also records the owner decisions of 2026-11-09 (b). Code references were
re-checked at mctl-api `origin/main` `ceac9ed`. Where this section and older text
disagree, this section wins. Every older passage that contradicted it has been rewritten.

**Owner decision A (connections, option a).**
- The connection store (#959), the order index (#988), the `aar_` receipts (#989) and the
  command bridge live in **one physical Postgres database**. They are used through one
  shared `pgx.Tx`.
- `GLOVO_DB_URL`, `COMMERCE_DB_URL` and `WORK_ITEMS_DB_URL` must all point to that
  database. A startup check proves transaction compatibility. Equal URL strings are not
  proof.
- Stores keep separate schemas and roles with least privilege.
- Revocation and write authorization serialize through locks, with **one documented lock
  order** (§7.1).
- There is no implicit `AUDIT_DB_URL` fallback. A boundary that cannot be proven answers
  `not_ready` and makes zero provider writes.
- One database does **not** make the fake provider's HTTP effect atomic with the
  database. This slice and #990 must still prove revoke-vs-write, timeout and crash
  fencing.

**Owner decision C (#985).** Apply every P2 and the cheap P3s listed below.

| Review finding | Fix in this proposal |
|---|---|
| P2-1 `AUDIT_DB_URL` fallback (old `design.md:147`) | No fallback anywhere. `Ready()` requires `GLOVO_DB_URL`, `COMMERCE_DB_URL` and `WORK_ITEMS_DB_URL` to be set explicitly, plus the §4 proof. The #957 §6b failure-injection test is T20. #987 (drop the bridge fallback) is a listed dependency |
| P2-2 Duplicates the #989 `aar_` machine; the generic `consumed` state is re-armable (`action_approvals.go:1044-1066`) | Old task 2 (`ConsumeActionApprovalTx`) is dropped. §3 consumes #989's tx-scoped methods: reserve at dispatch, consume inside #989's `WriteFence.Check`, revoke on cancel before dispatch, mark `unknown` when a reserved command ends without a permit. Dispatch is `not_ready` until the interface exists. The fence refuses any `aar_` in a generic work-items receipt state |
| P2-3 Route body and codes do not match the merged #1044; there is no `read_command_result` route | The dispatch body is `{approval_ref, fingerprint}`, and a fingerprint mismatch is `basket_changed`. One closed refusal table (§2b) maps to #1044 M10 and the #959 enum. Absent or foreign orders are `not_found`. `read_command_result` and `read_approval` routes are added under the same gate (§2a) |
| P2-4 Lock-order inversion between the permit and the revoker (`lockOwned` runs first, `permit.go:87`) | One global lock order, canonical in #957 design §6b (§7.1 here). `WriteFence` gains `PreLock`, which `permitTx` calls **before** `lockOwned` (`store.go:659`). The #959 revokers take their advisory keys before any command lock and cancel commands `ORDER BY command_id`. Deterministic deadlock test: T21 |
| P2-5 The fence can be installed without the membership precondition | `SetFence` has three explicit preconditions (§7.3). The third is the capability of a hook that turns a membership removal into a connection revocation. T17 asserts that `SetFence` is not called without it. The owner's acceptance of the residual risk is an OPEN item |
| P2-6 The connection-store topology conflicts with #957 §6b and #959 | Owner decision A. #959 and #957 §6b are amended in the same PR: the store lives in the one database, and the #959 revokers cancel open bridge commands in the same transaction (§7.2). It is listed as a blocking dependency in `tasks.md` |
| P2-7 Cancel records `cancelled` while the effect is `unknown` | The order becomes `cancelled` only when the bridge effect is `none`. Otherwise it becomes `unknown`, and the response carries `effect_state` (§6). T7 asserts this |
| P2-8 The credential has no production verifier and no tenant bound; T16 is incomplete | The credential is test-only until the issuer decision mctl-gitops#2506. It reuses the `PinClaims` pattern (`bridge_provider.go:155`), a required `Tenants` upper bound like `BridgeProviderConfig.Tenants` (`:68`), and a per-tenant rate limit. T16 adds the #961 Glovo worker and the orchestrator-DevLoop principal |
| P3 The step order contradicts itself | One order, written once in §5 and referenced by task 5 |
| P3 `EnqueueInput.Sequence` is unspecified (`store.go:115-116`) | Allocated explicitly under the order lock (§5 step 10) |
| P3 `Enqueue` returns `created=false` while the order is still undispatched | Refused as an invariant violation with `unavailable`; nothing is committed (§5 step 11) |
| P3 Cancel before dispatch leaves the `aar_` `approved` | Cancel before dispatch calls #989 `RevokeGlovoApprovalTx` (`pending|approved -> refused`) |
| P3 `ProveColocated` gaps (physical standbys share `system_identifier`; EXECUTE on `pg_control_system`) | Replaced by a nonce written in one transaction and read back through every pool, plus privilege and `to_regclass` checks (§4). `pg_control_system` is no longer used |
| P3 The partial unique index is applied on every boot | Kept in `bridgeSchema`. The runtime role owns `bridge_commands` and already creates `bridge_commands_sequence` the same way at every start (`store.go:66-67`, `:115-116`), so `CREATE UNIQUE INDEX IF NOT EXISTS` is idempotent and permitted. Verified; no change |
| P3 Crash after commit but before the response | T22: the retry returns the same `cmd_` |
| P3 `glovo.Default` is a `var` (`gate.go:24`) | `ControlDefault` is backed by an unexported `const controlGateOpen = false` |
| P3 `in_flight` is called an effective state | Corrected: it is a stored state (`action_approvals.go:215-232`) |

Skipped P3s: none.

**Alignment with the #989 amendment (same PR, coordinator scope extension).** The
receipt interface of §3 now uses #989's method names and states. The write fence is
#989's `receipt.Fence`; this slice keeps only the bridge hook (`PreLock`), the revoker
function and the `SetFence` wiring. The canonical lock order moved to #957 design §6b;
§7.1 references it. Dispatch enqueues the order's final approval basket as the command
payload, so the fence can recompute the fingerprint from what is actually written (#989
review P1).

## Current state

The bridge (mctl-api#962, #968) lives in `internal/bridge/`:
- `Store.Enqueue(ctx, tx pgx.Tx, in EnqueueInput) (commandID, created, err)`
  (`store.go:478`) inserts a `pending` row in the caller's transaction.
  - It is idempotent on `(tenant, execution_id, operation_key)`, and it returns an
    existing id without comparing fields (`store.go:483-486`).
  - `validate()` (`store.go:229-256`) requires an `aar_` for `place_order_fake` and
    `cancel_order_fake`.
  - `bridge_commands_sequence` is unique on `(execution_id, sequence)`
    (`store.go:115-116`).
- `Store.Cancel(ctx, tx, commandID, actor)` (`store.go:815-834`) locks the row
  `FOR UPDATE`. It sets `cancelled` and `cancel_requested=true`, and moves
  `effect_state` from `permitted` to `unknown`. A repeat on a cancelled row is a no-op.
  A completed or expired row returns `ErrAlreadyCompleted`.
- `ReadOutcome` (`store.go:847`) reads the status, the effect state and the stored
  result. Nothing calls it today.
- `Store.Pool()` (`store.go:414`) exposes the pool for the caller's transaction. Nothing
  calls `Enqueue` from a route today.
- `permitTx` (`permit.go:86`) calls `lockOwned` first (`store.go:659`, `FOR UPDATE`).
  It then checks the lease, the kind, `cancel_requested` and `effect_state`, and finally
  calls `currentFence().Check(ctx, tx, FenceBinding{...})` in the same transaction. The
  default `refusingFence` returns `ErrWriteFenceUnavailable`. The `WriteFence` doc names
  "reserve/consume/record-outcome" (`permit.go:43-49`).
- `cmd/api/main.go:1019-1021`: the bridge uses `COMMERCE_DB_URL`, and falls back to
  `AUDIT_DB_URL`. Removing that fallback is tracked in mctl-api#987.

Approvals (`aar_`) live in `internal/workitems/action_approvals.go`:
- The stored states are `pending`, `approved`, `denied`, `consumed`, `in_flight` and
  `executed`, plus the effective state `expired`. `in_flight` is a stored state, added
  for mctl-api#772 (`:215-232`).
- `ReserveActionApproval` and `SettleActionApproval` move
  `consumed -> in_flight -> consumed | executed`, "so a failed call leaves the human
  approval usable for a retry" (`:1044-1066`).
- The generic `consumed` state can therefore be re-armed, so it cannot serve as a
  single-use Glovo receipt. The single authoritative Glovo receipt machine is
  mctl-api#989 (M1b/2).

Glovo gate (`internal/glovo/gate.go`):
- `Gate{Open}`. `Default = Gate{Open: false}` is a package `var` (`:24`).
- Codes live in `internal/glovo/errors.go`. #959 extends them to the closed
  joint-contract enum.

Principals:
- `internal/auth/bridge_provider.go`: `service:bridge-provider:<ref>`, exact audience,
  `Tenants` upper bound (`:68`), `PinClaims` (`:155`). The production verifier waits on
  the issuer decision mctl-gitops#2506.
- `internal/auth/orchestrator_devloop.go`: `service:mctl-orchestrator-devloop`.
- The #961 Glovo worker (`auth.IsGlovoWorker()`) is reserved and is built by #961.

Tenant membership comes from GitOps (`checkTenantRoleByPrincipal`,
`gitops.PrincipalMembership`). It is not a Postgres row, so it cannot be locked.

Deployed state:
- `bootstrap/templates/mctl-platform/mctl-api.yaml` sets `AUDIT_DB_URL`, which points at
  database `mctl-api` on `shared-pg-rw.platform-db.svc`.
- It sets none of `COMMERCE_DB_URL`, `WORK_ITEMS_DB_URL`, `GLOVO_DB_URL` or
  `MCTL_BRIDGE_ENABLED`. So every store currently falls back to one database, and the
  bridge is dark.
- The live pod env was not observed.

## Proposed solution

### 1. Dedicated control-worker principal (`internal/auth/glovo_control_worker.go`)
- Principal id `service:glovo-control-worker`, with permission
  `glovo:control-dispatch`. It is not an admin and has no tenant of its own.
- Config is `MCTL_GLOVO_CONTROL_WORKER`, JSON `{issuer, subject, audience, tenants}`,
  with the exact audience `mctl-api-glovo-control`.
  - `tenants` is a **required, non-empty** upper bound, like
    `BridgeProviderConfig.Tenants`. An order or command outside it is `not_found`.
  - A half-configured or reserved value disables the mapping and logs once.
- Claims are checked with the `PinClaims` pattern: issuer, audience, subject, `exp` and
  `nbf`. Any missing value fails closed.
- **The verifier is test-only until mctl-gitops#2506**, as for the bridge provider. This
  slice wires no production verifier: the static test verifier exists only in the test
  build. In production every route answers 403 to this principal until the issuer
  decision lands and a follow-up wires its verifier.
- `User.IsGlovoControlWorker()` is false for every other principal type: users, admins,
  the Glovo facade (`IsGlovoAudience`), bridge providers, the #961 Glovo worker, the
  orchestrator-DevLoop principal, agents, CI and surfaces.

### 2. Confinement and routes (`internal/api/handlers_glovo_control.go`, `router.go`)
- `glovoControlWorkerGate` sits in the authenticated group, next to
  `bridgeProviderGate`. A control-worker principal gets 403 on everything except the
  routes in §2a.
- `requireGlovoControlWorker` on the route group refuses every other principal with 403
  `not_authorized` before any store call.
- Routes are mounted only when two things hold: `glovo.ControlDefault.Open` is true (it
  is const-backed and `false`), and `MCTL_GLOVO_CONTROL_ENABLED=true`. When the routes
  are absent the answer is 404. When they are mounted but not ready it is 503
  `not_ready`.
- Rate limit: one `httprate` bucket keyed by (principal, tenant of the addressed order or
  command). One tenant therefore cannot exhaust the worker's budget for another.
- Bodies are strict (`readStrictJSON`, `handlers_bridge.go:150`), so unknown fields give
  400 `invalid_request`. There is no payload, basket, endpoint or credential field. The
  provider payload is built from the order index (#988), never from the caller.

#### 2a. Route table (the #1044 `ControlApiPort` contract)

| #1044 call | Route | Body | 200 body |
|---|---|---|---|
| `dispatch_order(order_ref, approval_ref, fingerprint)` | `POST /api/v1/internal/glovo/orders/{order_ref}/dispatch` | `{"approval_ref":"aar_…","fingerprint":"sha256:…"}` | `{command_id, order_state, effect_state}` |
| `cancel_order(order_ref)` | `POST /api/v1/internal/glovo/orders/{order_ref}/cancel` | `{}` | `{command_id?, order_state, effect_state}` |
| `read_command_result(command_id)` | `GET /api/v1/internal/glovo/commands/{command_id}` | none | `{command_id, order_ref, status, effect_state, outcome?, provider_effect?, error_code?, result_digest?}` |
| `read_approval` (poll) | `GET /api/v1/internal/glovo/approvals/{approval_ref}` | none | `{approval_ref, order_ref, state, expires_at}` |

- No body carries `execution_id` any more. It is derived from the locked order row
  (`Order.ExecutionID`, #988).
- A replayed dispatch returns the original body byte for byte, with the header
  `Idempotent-Replayed: true` (the #957 M4 convention). The body has no `replayed` field.
- `read_command_result` returns ids, enums and the digest only, never the stored result
  body or a payload. It answers only for Glovo `place_order_fake`/`cancel_order_fake`
  commands whose order is inside the `tenants` bound. Anything else is `not_found`.
- `revalidate_scope` and `resolve_connection` from #1044's `ControlApiPort` are not
  added here. Their owner is an OPEN item.

#### 2b. Closed refusal table

Every refusal uses the #959 `glovo.WriteError` body `{"error","error_description"}`
with fixed text. Codes come only from #1044 M10 and the #959 closed enum; nothing else is
sent. The internal reason goes to audit only.

| Condition | HTTP | `error` | #1044 M10 |
|---|---|---|---|
| The caller is not the control worker, or a control worker calls another route | 403 | `not_authorized` | terminal |
| Gate closed after mount, missing config, failed proof, or a missing collaborator | 503 | `not_ready` | `provider_disabled` (mapped on the #1044 side) |
| Store I/O error, `lock_timeout` | 503 | `unavailable` | retryable |
| Lock contention on the tenant beyond the retry budget | 409 | `tenant_busy` | `tenant_busy` |
| Malformed ref, unknown or duplicate field | 400 | `invalid_request` | terminal |
| Order, command or approval is absent, foreign, or outside `tenants` | 404 | `not_found` | terminal |
| The `aar_` is not `approved` (`pending`, `refused`, `unknown`, `consumed` without this command) or is not a Glovo-kind `aar_` | 409 | `approval_invalid` | `approval_invalid` |
| The `aar_` is past `expires_at` or its freshness bound | 409 | `approval_expired` | `approval_expired` |
| The `aar_` is already reserved or consumed for another command, or a different `aar_` names a dispatched order | 409 | `approval_replayed` | `approval_replayed` |
| A binding differs: tenant, owner, `we_`, order, connection, install revision or intent hash | 409 | `intent_mismatch` | `intent_mismatch` |
| The body fingerprint differs from the order's final fingerprint or the `aar_` binding | 409 | `basket_changed` | `basket_changed` |
| The owner is no longer a tenant member | 403 | `no_tenant` | terminal |
| No live connection / connection revoked / connection expired | 404 / 409 / 409 | `no_connection` / `connection_revoked` / `connection_expired` | terminal |
| The install revision moved | 409 | `stale_install` | terminal |
| Dispatch of an order that is `cancelled`, `unknown` or `closed` | 409 | `invalid_transition` | terminal |
| Rate limit | 429 (+ `Retry-After`) | `rate_limited` | retryable |

Cancelling a command that is already `completed` or `expired` is **not** a refusal. It
answers 200 with the current `order_state` and `effect_state`, and changes nothing.

It is an OPEN item whether #1044 already maps the #959 codes in this table: `no_tenant`,
`no_connection`, `connection_revoked`, `connection_expired`, `stale_install`,
`invalid_transition`, `not_found` and `unavailable`. If it does not, #1044 is amended in
the same wave.

### 3. Store seam (`internal/glovo/control/`)

```go
type OrderIndex interface { // #988 (M1b/1), tx-scoped, control path
    PeekOrderScope(ctx context.Context, q Querier, orderRef string, tenants []string) (tenant, owner string, err error) // unlocked read of write-once columns
    LockOrderForControl(ctx context.Context, tx pgx.Tx, orderRef string, tenants []string) (*orders.Order, error) // L3, FOR UPDATE; scope derived from the row
    MarkDispatched(ctx context.Context, tx pgx.Tx, o *orders.Order, commandID string, actor orders.Actor) error // finalized -> dispatched, command_id write-once
    MarkCancelled(ctx context.Context, tx pgx.Tx, o *orders.Order, actor orders.Actor) error  // only when no effect is possible
    MarkUnknown(ctx context.Context, tx pgx.Tx, o *orders.Order, actor orders.Actor) error    // the effect may have happened
}
type Receipts interface { // provided by #989 (internal/workitems, glovo_approvals.go); tx-scoped; #985 never writes action_approval_requests itself
    LockGlovoApprovalTx(ctx context.Context, tx pgx.Tx, id string) (*workitems.ActionApprovalRequest, *workitems.GlovoBinding, error) // L4, FOR UPDATE
    ReserveGlovoApprovalTx(ctx context.Context, tx pgx.Tx, id string, cmd workitems.ReserveCommand) (replayed bool, err error) // approved -> reserved; idempotent for the same cmd_
    RevokeGlovoApprovalTx(ctx context.Context, tx pgx.Tx, id string, actor string) error // pending|approved -> refused (cancel before dispatch)
    MarkGlovoApprovalUnknownTx(ctx context.Context, tx pgx.Tx, id, commandID string) error // reserved -> unknown (command ended without a permit)
    GlovoApprovalStatus(ctx context.Context, tenants []string, id string) (*workitems.GlovoApprovalStatus, error) // tx-free; ids and enums only; read_approval
}
type Connections interface { // #959, tx-scoped, on the shared tx
    LockOwnerShared(ctx context.Context, tx pgx.Tx, tenant, principal string) error // L1 shared + L2 shared, the #959 withLocks order
    LiveConnectionTx(ctx context.Context, tx pgx.Tx, owner glovo.Owner) (*glovo.Connection, error) // no row lock; L1/L2 already held
    RevocationHook() bool // true only when a membership removal revokes connections (§7.3)
}
type Membership interface{ IsMember(tenant, principalID string) (bool, error) } // GitOps, best effort
type Dispatcher struct {
    Bridge *bridge.Store; Orders OrderIndex; Receipts Receipts; Conns Connections
    Members Membership; Ready func() error
}
```

- The receipt states are #989's: `pending -> approved -> reserved -> consumed | unknown`,
  plus `refused` (stored `denied`) and `expired` (derived). `consumed` is written only
  by #989's fence inside the permit transaction, never by this slice.
- An `aar_` that #989 does not manage, or one in a generic work-items state (`consumed`,
  `in_flight` or `executed` of the generic machine), is `approval_invalid`.
- Nil collaborators make `Ready()` return `not_ready`. Dispatch stays `not_ready` until
  the #989 `Receipts` implementation exists.

### 4. One-database proof (owner decision A)
- Required config: `GLOVO_DB_URL`, `COMMERCE_DB_URL` and `WORK_ITEMS_DB_URL`, each set
  explicitly. A missing value is `not_ready`. None of them falls back to `AUDIT_DB_URL`
  or to another one.
- `control.ProveOneDatabase(ctx, bridgePool, workItemsPool, glovoPool)` runs at startup:
  1. In one transaction on the bridge pool, insert a fresh 128-bit nonce into
     `bridge_colocation_probe` and commit. The table is created idempotently in
     `bridgeSchema`.
  2. Read the nonce back through the work-items pool and the Glovo pool. If either does
     not find it, the proof fails. This proves one database, not merely one cluster. It
     does not depend on `system_identifier` (physical standbys share it) or on EXECUTE
     rights on `pg_control_system()`.
  3. Each pool must report `pg_is_in_recovery() = false`.
  4. From the bridge pool, `to_regclass` must find every participating table:
     `bridge_commands`, the #988 order tables, the #989 receipt table, and the #959
     `glovo.glovo_installs` and `glovo.glovo_connections`. `has_table_privilege` must
     show exactly the grants in the role table of #959's amendment: SELECT on the #959
     tables, and no UPDATE or DELETE on them.
  5. Delete the nonce.
- Any failure sets `Ready()` to `not_ready` for the life of the process. It logs once,
  with no URL, and leaves the fence as `refusingFence`.
- CI proves the transaction boundary (#957 §6b) in T20. The test runs the #957 prepare
  writes and this slice's dispatch in one `pgx.Tx`, injects a failure after the last
  statement, and asserts that nothing from either side committed.

### 5. Dispatch transaction (`Dispatcher.Dispatch`)
This is the only step order. Task 5 implements exactly this.
1. Check `Ready()`, else `not_ready`. Begin `tx` on the bridge pool at READ COMMITTED,
   with `SET LOCAL lock_timeout = '5s'`.
2. `Orders.PeekOrderScope(order_ref, tenants)` reads the order's write-once tenant and
   owner without a lock. Absent, foreign or outside the bound: `not_found`.
3. `Conns.LockOwnerShared(tenant, owner)` takes L1 shared, then L2 shared.
4. `Orders.LockOrderForControl(order_ref, tenants)` takes L3. It re-checks that the
   tenant and owner equal those from step 2. They are write-once, so a difference is an
   invariant violation and answers `unavailable`.
5. Replay check, before any receipt check. If `order.state == dispatched`, the order's
   `approval_ref` equals the body's and the fingerprint matches, commit and return the
   stored `command_id` with `Idempotent-Replayed: true`. A reserved or consumed receipt
   therefore replays and is not refused. Otherwise:
   - a different `aar_` on a dispatched order is `approval_replayed`;
   - `cancelled`, `unknown` or `closed` is `invalid_transition`;
   - any state other than `finalized` is `invalid_transition`.
6. `body.fingerprint` must equal `order.final_basket_fingerprint`, else
   `basket_changed`. The value is the single M1 basket fingerprint defined in
   mctl-agents#1059 (see #988). mctl-api computed it; the caller's copy is only compared.
7. `Receipts.LockGlovoApprovalTx(aar)` takes L4. Its state is checked as in §2b. Then the binding:
   tenant, owner, `we_`, order, connection, install revision, fingerprint and intent hash
   must equal the locked order row. Any difference is `intent_mismatch`, except the
   fingerprint, which is `basket_changed`.
8. `Conns.LiveConnectionTx(owner)`:
   - no connection is `no_connection`;
   - revoked or expired gives the matching code;
   - a connection or install revision that differs from the order's is `stale_install`.
9. `Members.IsMember(tenant, owner)`: false is `no_tenant`; an error is `unavailable`.
10. Compute `sequence = coalesce(max(sequence), 0) + 1` over `bridge_commands` for this
    `execution_id`, read under L3. Every command of this `we_` is created under this
    order lock.
11. Read the order's final snapshot (`final_snapshot_seq`) and require
    `basket.Fingerprint(snapshot) == order.final_basket_fingerprint`. Call
    `bridge.Store.Enqueue(ctx, tx, EnqueueInput{Kind: KindPlaceOrderFake,
    OperationKey: "glovo-dispatch:"+order_ref, Sequence: sequence, ApprovalRef: aar,
    IntentHash: <the aar_ row's intent_hash>, Payload: <the snapshot's approval basket>,
    Attempt: 1, …})`. Every field comes from the locked rows. The payload shape is the
    #1059 approval basket for a Glovo `place_order_fake` command (OPEN-985-8); until that
    contract exists, dispatch is `not_ready`. `created=false` at this
    point (the order is still `finalized`) is an invariant violation: roll back, audit
    it, and answer `unavailable`.
12. `Receipts.ReserveGlovoApprovalTx(aar, {cmd_, tenant, owner, we_, order, connection,
    install revision, intent hash})`. #989 re-checks the binding against these command
    fields and is idempotent for the same `cmd_`.
13. `Orders.MarkDispatched(order, cmd_, Actor{Kind: control_worker})`.
14. Commit. Any error rolls back everything.

A backstop index goes in `bridgeSchema`: `CREATE UNIQUE INDEX IF NOT EXISTS
bridge_commands_mutating_approval ON bridge_commands (approval_ref) WHERE
operation_kind='place_order_fake'`.

### 6. Cancel transaction (`Dispatcher.Cancel`)
Locks are taken in the same order as §5: L1/L2 shared, L3, L4, L5.
- `finalized` (not dispatched): call `Receipts.RevokeGlovoApprovalTx(aar, actor)` and
  `MarkCancelled`. `effect_state` is `none`.
- `dispatched`: call `bridge.Store.Cancel(ctx, tx, cmd_, "service:glovo-control-worker")`,
  then read the command's `effect_state` on the same tx:
  - `none` (pending, or leased without a permit): call
    `Receipts.MarkGlovoApprovalUnknownTx(aar, cmd_)` (the reserved receipt can never be
    spent again) and `MarkCancelled`.
  - `unknown` (a permit was issued, and `Cancel` turned `permitted` into `unknown`): the
    `aar_` is already `consumed` and is not touched (the outcome lives only in
    `effect_state`, #989). Call `MarkUnknown`. The order is **never** `cancelled` in this
    case.
  - `ErrAlreadyCompleted`: change nothing and answer 200 with the command's current
    `effect_state`. The result path reconciles the order. Who owns the transition from a
    result to order `closed` is an OPEN item.
- `cancelled` or `unknown`: no-op, 200 with the current state.
- No path ever returns an `aar_` to `approved`.

### 7. Revocation and the actual write

#### 7.1 Global lock order

The canonical lock order L1..L6 for every Glovo write path is defined once, in #957
design §6b. This slice takes:
- dispatch and cancel: L1 shared, L2 shared, L3 (order), L4 (`aar_`), L5 (commands);
- permit (through `WriteFence.PreLock`, then `lockOwned`): L1 shared, L2 shared, L3, L4,
  then L5;
- `bridge_cancel_open_for_connections` (called by the #959 revokers after L1/L2): L5
  only, `ORDER BY command_id`.

The provider claim, result and expiry paths take only L5.

#### 7.2 Write fence (#989 `receipt.Fence`, a `bridge.WriteFence`)
- `bridge.WriteFence` gains `PreLock(ctx, tx, commandID) error`. `permitTx` calls it
  **before** `lockOwned`. This is a change to `permit.go:86`, owned by this slice. The
  default `refusingFence.PreLock` is a no-op.
- #989's `receipt.Fence.PreLock` reads the command's immutable binding without a lock (tenant,
  owner, order, `aar_`). It then takes L1 shared, L2 shared, L3 and L4.
- `permitTx` then takes L5 (`lockOwned`). #989's `Check` re-verifies that the binding
  read in `PreLock` is unchanged, recomputes the fingerprint and intent hash from the
  stored command payload, checks the connection, the install revision, membership and
  the receipt state (`reserved` for this `cmd_`), and consumes the `aar_` (#989 design
  §6). That is the single-use point at the physical write.
- The #959 revokers are `Revoke` (including reason `membership_removed`),
  `RevokeInstall` and `Reinstall`. Each one:
  1. takes L1 and L2 as today;
  2. updates the connection rows;
  3. in the **same transaction**, cancels the open bridge commands of every ended
     connection through `bridge.CancelOpenForConnections(ctx, tx, gcnIDs, actor)`. That
     call locks the commands `ORDER BY command_id FOR UPDATE` and applies the semantics
     of `Store.Cancel`.
- Race outcomes:
  - If the revoke commits first, a dispatch or permit waiting on L2 then sees the
    revoked connection or `cancel_requested`, and refuses.
  - If the dispatch or permit commits first, the revoker waits on L2 and then cancels the
    command. A command without a permit can then never get one (`cancel_requested`), and
    a permitted one becomes `unknown`.
- One database does not make the provider's HTTP call atomic with any of this. Timeout
  and crash fencing are proven by T13, T14 and T22 here, and by #990.

#### 7.3 When the fence is installed
`main.go` (task 9 here, the single installer) calls
`bridgeStore.SetFence(receipt.NewFence(...))` (#989) only when all three of these hold:
1. `glovo.ControlDefault.Open` is true, and the owner has lifted hold
   mctl-gitops#2457.
2. The §4 one-database proof passed.
3. `Conns.RevocationHook()` is true. That means the component that observes a GitOps
   membership removal revokes the member's connection (`Revoke` with reason
   `membership_removed`). Who builds that detector is an OPEN item. Until it exists, the
   fence stays `refusingFence`.

A residual window remains between the GitOps membership removal and the hook's
revocation. The owner must accept it explicitly; this is an OPEN item.

### 8. Logging and audit
- `h.logAudit` records:
  - the operation (`glovo.control.dispatch`, `cancel`, `read_command` or
    `read_approval`);
  - the `ordr_`, `aar_` and `cmd_`;
  - the code and the internal reason;
  - whether the call replayed.
- Order-index events record `Actor{Kind: control_worker, ID:
  service:glovo-control-worker}`, never the owner.
- No payload, nonce, lease token or connection secret is logged.

## Alternatives

- **An HTTP enqueue route on the bridge for the worker.** Rejected by owner decision
  M7 = (b).
- **Two phases: consume, then enqueue, across databases.** Rejected: it reopens the
  #954 point 3 TOCTOU. Owner decision A puts every store in one database instead.
- **The generic work-items `consumed` state as the single-use receipt.** Rejected
  (review P2-2): `SettleActionApproval` re-arms it. #989 owns the receipt.
- **SERIALIZABLE instead of explicit locks.** Rejected: it causes retry storms under
  concurrent dispatch and does not help the revoker path.
- **Reuse the orchestrator-DevLoop principal.** Rejected: the issue requires a principal
  that can do nothing else.

## Platform impact

- **Migrations.** These go in `bridgeSchema`, applied by the runtime role, idempotently,
  in the same pattern as `bridge_commands_sequence`:
  - the partial unique index `bridge_commands_mutating_approval`;
  - the table `bridge_colocation_probe(nonce TEXT PRIMARY KEY, created_at TIMESTAMPTZ)`;
  - the `SECURITY DEFINER` function `bridge_cancel_open_for_connections(text[], text)`.
    It uses `CREATE OR REPLACE` and a fixed `search_path`. EXECUTE is revoked from
    PUBLIC and granted only to the Glovo runtime role named in config. If that grantee
    is not configured, the #959 hook is unavailable and the fence stays refusing.
- **Backward compatibility.** The routes are absent unless the const and the env flag
  are both on. `refusingFence.PreLock` is a no-op, so the default permit path is
  unchanged.
- **Resources.** One short transaction per call. With two replicas, the advisory and row
  locks serialize across both.
- **Risks and mitigations:**
  - The database is split: the proof fails closed.
  - Membership changes are invisible to Postgres: the fence needs the hook, and the
    owner accepts the residual.
  - Lock waits: a 5 s `lock_timeout` maps to `unavailable`.
  - Token confusion: exact audience, a confining gate and the `tenants` bound.
- **Dependencies (blocking).** If any of these is missing, the routes answer
  `not_ready`:
  - the amended #959 store (one database, tx-scoped reads, revokers that cancel
    commands);
  - the #988 order index;
  - the #989 methods of §3 and its `receipt.Fence`;
  - the #1059 approval-basket payload for Glovo `place_order_fake` (OPEN-985-8);
  - #987, the fallback removal;
  - mctl-gitops#2506, for a production verifier.

## Open questions

See requirements.md.
