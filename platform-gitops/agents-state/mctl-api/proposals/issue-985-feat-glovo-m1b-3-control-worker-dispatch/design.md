# Design: issue-985-feat-glovo-m1b-3-control-worker-dispatch

## Amendment 2026-11-10 (independent review, AMEND)

Where this section and older text disagree, this section wins. Decisions recorded earlier and the owner-only questions (OPEN-985-2, OPEN-985-11, OPEN-985-13) are unchanged.

| Finding | Change here |
|---|---|
| Revocation hook can stay synthetic (`cmd/api/glovo_team_grant.go` installs `syntheticRevocationHook`, a no-op) | §7.3 item 4 and task 9: `main.go` swaps it for `bridge.CancelOpenForConnections`; startup asserts the installed hook IS that function; a test refuses the fence with the synthetic hook; T24 is red with the swap reverted. |
| `MembershipRevocationWired()` is a non-empty label (`internal/glovo/store.go`: `membershipRevoker != ""`), not evidence | §7.3 item 5 defines the positive signal. Until it exists the interim answer is refusing. OPEN-985-2 (who owns the detector) stays an owner question. |
| `Membership.IsMember` has no `ctx` and is a network call under L1-L4 (and in `Fence.Check` under L5) | §5 step 9 and §7.2: `ctx` plus a hard timeout `MembershipTimeout` (2 s, below the 5 s `lock_timeout`); timeout is `unavailable`. `Membership` is a gate, fail closed, not best effort. New T15a. |
| Security tests can pass with the fix reverted | Tasks: a Definition of done clause and one `mutation:` line per security test. |
| `approval_expired` decided too late | §5 step 11: refused before enqueue when `fresh_until - now <= ReservePermitMargin`; boundary tests at 119 s and 121 s (T4a). |
| Stale line references | Re-pinned to mctl-api main `dc55930` (see the lines cited below). |

## Amendment 2026-11-09 (c), round 7 of the AMEND PR

Targeted fixes for two seams the round-6 text left open. Where this section and older text disagree, this section wins.

| Finding | Change here |
|---|---|
| F1, #986 R6-986-1, #1059 R6-1 to R6-3, CROSS X-A (the v1alpha2 `place_order_fake` had no owner in `internal/bridge`) | One owner per responsibility, each stated once (table in #986 design §2a): schema, envelope and result contract in #1059 §Write command; per-command wire version, projection, Claim gating, `SubmitResult` and vendoring in mctl-api in #986; the provider in mctl-telegram#1262. This slice only enqueues with `WireVersion: bridge.WireV1alpha2` (§5 step 11) and calls #986 `EnableWireVersions` from `NewRuntimeStore` (task 4). It vendors nothing; OPEN-985-8 stays closed |
| F2, #957 R6-957-1, #988 X-1, #989 R7-989-1, CROSS X-C (result to order was not total) | §2a: one total table over (command status, `effect_state`) and one function, `reconcileOrder`, that applies it from `read_command_result` and from `Cancel` after `Store.Cancel` for every dispatched order, nil or `ErrAlreadyCompleted` (§6; round 8). `CommandEffect` returns `(status, effectState)`. #957 §3a renders the same keys; #988 needs no new edge |

## Amendment 2026-11-09 (c), round 5 of the AMEND PR

Fold-in of the round-4 findings; simplified, no new mechanism beyond the one named per row. Where this section and older text disagree, this section wins.

| Finding | Change here |
|---|---|
| N3 (`Enqueue` field mapping) | §5 step 11 and T25: `ProviderRef`, `Tenant`, `OwnerPrincipalID`, `InstallRevision`, `TTL` mapped |
| N4 (contract artifact) | §2a and task 8: this slice owns `internal/glovo/control/contract/*.json`; #1044 and #990 are consumers |
| X-4 (cancelled and expired triple) | §2a: the route returns the triple for them; OPEN-985-15 (renumbered round 8) |
| #986 F3 (read-level leg) | §4 selector row and T26 for `bridge_read_schema_version` |

## Amendment 2026-11-09 (c), round 4 of the AMEND PR

Resolves the round-3 findings F2 and F3 and the cross-slice finding X-3. Where this section and older text disagree, this section wins.

| Finding | Change here |
|---|---|
| F2 (dispatch replay only on `dispatched`; "byte for byte" cannot hold) | §5 step 5: replay on any order state whose `command_id` is non-empty (`dispatched`, `cancelled` after dispatch, `unknown`, `closed`) when the body's `approval_ref` equals the order's and the fingerprint matches. The 200 body carries the same `command_id` with the current `order_state` and `effect_state`, so a late activity retry after a result or a cancel still gets its `cmd_`. §2a is reworded to "the same `command_id`". A different `aar_` on an order with a `command_id` stays `approval_replayed`; an order with no `command_id` that is `cancelled` or `closed` stays `invalid_transition`. T1 and T22 gain the after-result and after-cancel cases |
| F3 (selector reader and outcomes undefined) | §4: the mode is decided once at startup by a probe, `to_regclass('public.bridge_schema_version') IS NOT NULL`, on the `GLOVO_DB_URL` pool when that is set and otherwise on the legacy bridge DSN (`COMMERCE_DB_URL`, as today). `to_regclass` needs no table privilege, so it works for the old bridge role that no longer owns the tables; the version value is read afterwards by `NewRuntimeStore` as `glovo_runtime` (`SELECT` granted by `ApplySchema`). Outcome table in §4: present and `GLOVO_DB_URL` unset is bridge `not_ready`; any probe or version-read error is bridge `not_ready`; neither ever falls back to `NewStore`. T26 adds both cases. OPEN-985-10 records the legacy-DSN probe |
| X-3 (read DDL claimed by #985 and #986) | One owner: #986 `bridge.ApplyReadSchemaTx(ctx, tx, runtimeRole)`. `bridge.ApplySchema` calls it inside its own transaction and depends on #986 task 3; #986 tests it standalone. Merge order: #1059, #959, #988, #960, #961, #989, #986, #985 (#957 §6d.1, round 5). The blocking list names #986 |

## Amendment 2026-11-09 (c), round 2 of the AMEND PR

Re-review of the AMEND PR head `dc1fe6e5`; code references re-checked at mctl-api
`ceac9ed`. The cross-slice seams have one owner each: roles and grants, execution
binding, approval-basket payload and the interface list are mctl-api#957 design §6d; the
closed refusal set is #957 §4. This slice references them. Where this section and older
text disagree, this section wins; the older passages are edited.

| Finding | Change |
|---|---|
| F1, X-6 (hook name collision; `WithRevocationHook` never wired) | `Connections` keeps only `LockOwnerShared` and `LiveConnectionTx` with the #957 §6d.4 signatures. The membership precondition is #959 `MembershipRevocationWired()`, a separate signal. Task 9 constructs the #959 store with `glovo.WithRevocationHook(bridge.CancelOpenForConnections)` |
| F2 (fence preconditions differ) | §7.3 is the single precondition list (six items, including #959 `Ready` and #989 `receipt.Ready`); requirements mirror it verbatim and #989 §8 references it. T17 has one case per item |
| F3 (new DDL by the runtime role; `SECURITY DEFINER`) | New `bridge.ApplySchema(ctx, migrationConnStr, runtimeRole)` under the migration role carries `bridgeSchema`, the partial unique index, `bridge_colocation_probe` and #986's read objects, and grants per #957 §6d.1. With Glovo enabled the bridge opens with `bridge.NewRuntimeStore` (no DDL). The `SECURITY DEFINER` function is withdrawn: `bridge.CancelOpenForConnections` is plain Go on the revoker's transaction. The (b) row "Kept in `bridgeSchema`" is withdrawn |
| F4 (proof does not check the write-path grants) | §4 step 4 checks the full #957 §6d.1 grant table, that the bridge and Glovo pools share the runtime role, that it owns nothing and is not a member of an owner role, and that the work-items role has no `glovo` access. OPEN-985-6 is now true as written |
| X-3, P3 F8 (codes) | §2b statuses now equal #957 §4.1 (`stale_install` 403); `tenant_busy` is defined as `lock_timeout` (SQLSTATE `55P03`) on any §6b lock; other I/O is `unavailable`. The §2b set is a subset of #957 §4.1 |
| P3 F5 (`PreLock` before the scope check) | `PreLock(ctx, tx, c bridge.Caller, commandID)` applies the `lockOwned` provider and tenant check before any lock and answers `ErrCommandNotFound` alike for absent and foreign ids |
| P3 F6 (consumed signatures drift) | §3 copies #988 `PeekOrderScope(...) (orders.Scope, error)` and #989 `ReserveCommand` verbatim; step 12 passes `BasketFingerprint` |
| P3 F7 (cancel vs concurrent receipt transitions) | Cancel treats a receipt already `denied` (for this order) or `unknown` (for this `cmd_`) as success; T7 adds refused-then-cancel and sweeper-then-cancel |
| P3 F8 (test gaps) | T16 adds the surface principal and `PinClaims` negatives (wrong aud, iss, sub; expired; nbf) and a production-build check that no verifier is wired; the revokers list includes `Reconnect` and terminal `Transition` |
| X-1, #957 F5 (workflow id, run id, refs) | `EnqueueInput.WorkflowID` comes from #989 `ExecutionBindingTx`, `RunID` from #957 `glovojoin.ControlStartTx` (may be `''`), `TenantRef`/`PrincipalRef` from #988 `LookupJoinRefTx` (§5 step 11) |
| X-2, X-8 (payload shape) | The `place_order_fake` payload is exactly the order's final approval-basket bytes, no wrapper (#957 §6d.3); the schema is owned by #1059 (`command-place-order-fake.schema.json`, round 6 G1) and, from round 7, vendored and gated by #986 §2a, not here; this slice only enqueues it (OPEN-985-8 closed) |
| #959 F7 (end-to-end revocation proof) | New T24 here: with the real hook and fence, revoke-then-permit and `expires_at`-passed-then-permit give no permit |
| #989 F3 (`cancel_order_fake`) | `read_command_result` answers only for `place_order_fake`; Glovo M1 never enqueues `cancel_order_fake` |

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
- `GLOVO_DB_URL` (the one `glovo_runtime` pool, shared by the #959 store and the bridge store, #957 §6d.1 R4) and `WORK_ITEMS_DB_URL` must both point to that database; `COMMERCE_DB_URL` stays the commerce
  ledger's (amended (c)). A startup check proves transaction compatibility. Equal URL strings are not
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
| P2-4 Lock-order inversion between the permit and the revoker (`lockOwned` runs first, `permit.go:87`) | One global lock order, canonical in #957 design §6b (§7.1 here). `WriteFence` gains `PreLock` (defined by #989 task 7 since 2026-11-10), which `permitTx` calls **before** `lockOwned` (`store.go:659`). The #959 revokers take their advisory keys before any command lock and cancel commands `ORDER BY command_id`. Deterministic deadlock test: T21 |
| P2-5 The fence can be installed without the membership precondition | `SetFence` has three explicit preconditions (§7.3). The third is the capability of a hook that turns a membership removal into a connection revocation. T17 asserts that `SetFence` is not called without it. The owner's acceptance of the residual risk is an OPEN item |
| P2-6 The connection-store topology conflicts with #957 §6b and #959 | Owner decision A. #959 and #957 §6b are amended in the same PR: the store lives in the one database, and the #959 revokers cancel open bridge commands in the same transaction (§7.2). It is listed as a blocking dependency in `tasks.md` |
| P2-7 Cancel records `cancelled` while the effect is `unknown` | The order becomes `cancelled` only when the bridge effect is `none`. Otherwise it becomes `unknown`, and the response carries `effect_state` (§6). T7 asserts this |
| P2-8 The credential has no production verifier and no tenant bound; T16 is incomplete | The credential is test-only until the issuer decision mctl-gitops#2506. It reuses the `PinClaims` pattern (`bridge_provider.go:155`), a required `Tenants` upper bound like `BridgeProviderConfig.Tenants` (`:68`), and a per-tenant rate limit. T16 adds the #961 Glovo worker and the orchestrator-DevLoop principal |
| P3 The step order contradicts itself | One order, written once in §5 and referenced by task 5 |
| P3 `EnqueueInput.Sequence` is unspecified (`store.go:115-116`) | Allocated explicitly under the order lock (§5 step 10) |
| P3 `Enqueue` returns `created=false` while the order is still undispatched | Refused as an invariant violation with `unavailable`; nothing is committed (§5 step 11) |
| P3 Cancel before dispatch leaves the `aar_` `approved` | Cancel before dispatch calls #989 `RevokeGlovoApprovalTx` (`pending|approved -> refused`) |
| P3 `ProveColocated` gaps (physical standbys share `system_identifier`; EXECUTE on `pg_control_system`) | Replaced by a nonce written in one transaction and read back through every pool, plus privilege and `to_regclass` checks (§4). `pg_control_system` is no longer used |
| P3 The partial unique index is applied on every boot | Withdrawn by (c): all bridge DDL moves to `bridge.ApplySchema` under the migration role (§ Platform impact) |
| P3 Crash after commit but before the response | T22: the retry returns the same `cmd_` |
| P3 `glovo.Default` is a `var` (`gate.go:24`) | `ControlDefault` is backed by an unexported `const controlGateOpen = false` in package `internal/glovo` (release file; the fixture twin is §7.4) |
| P3 `in_flight` is called an effective state | Corrected: it is a stored state (`action_approvals.go:215-232`) |

Skipped P3s: none.

**Alignment with the #989 amendment (same PR, coordinator scope extension).** The
receipt interface of §3 now uses #989's method names and states. The write fence is
#989's `receipt.Fence`; this slice keeps only the revoker function and the `SetFence`
wiring (the `PreLock` hook definition moved to #989 task 7 on 2026-11-10, so #989
merges first). The canonical lock order moved to #957 design §6b;
§7.1 references it. Dispatch enqueues the order's final approval basket as the command
payload, so the fence can recompute the fingerprint from what is actually written (#989
review P1).

## Current state

The bridge (mctl-api#962, #968) lives in `internal/bridge/`:
- `Store.Enqueue(ctx, tx pgx.Tx, in EnqueueInput) (commandID, created, err)`
  (`store.go:614`) inserts a `pending` row in the caller's transaction.
  - It is idempotent on `(tenant, execution_id, operation_key)`, and it returns an
    existing id without comparing fields (`store.go:614-660`).
  - `validate()` (`store.go:270`) requires an `aar_` for `place_order_fake` and
    `cancel_order_fake`.
  - `bridge_commands_sequence` is unique on `(execution_id, sequence)`
    (`store.go:115-116`).
- `Store.Cancel(ctx, tx, commandID, actor)` (`store.go:1009`) locks the row
  `FOR UPDATE`. It sets `cancelled` and `cancel_requested=true`, and moves
  `effect_state` from `permitted` to `unknown`. A repeat on a cancelled row is a no-op.
  A completed or expired row returns `ErrAlreadyCompleted`.
- `ReadOutcome` (`store.go:1041`) reads the status, the effect state and the stored
  result. Nothing calls it today.
- `Store.Pool()` (`store.go:550`) exposes the pool for the caller's transaction. Nothing
  calls `Enqueue` from a route today.
- `permitTx` (`permit.go:98`; `PreLock` is declared at `permit.go:60`, `refusingFence.PreLock` is `:67`) calls `lockOwned` (`store.go:836`; since #989 task 7 it runs after `PreLock`, `FOR UPDATE`).
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
| `read_command_result(command_id)` | `GET /api/v1/internal/glovo/commands/{command_id}` | none | `{command_id, order_ref, status, effect_state, outcome?, provider_effect?, error_code?, result_digest?}` (round 5, X-4: see the triple rule below) |
| `read_approval` (poll) | `GET /api/v1/internal/glovo/approvals/{approval_ref}` | none | `{approval_ref, order_ref, state, expires_at}` |

- **Triple for `cancelled` and `expired` commands (round 5, X-4).** The bridge writes no result
  row for them (`Cancel` and `ExpireDue` set only `status` and `effect_state`), but #1044's M9
  table is keyed on (`outcome`, `provider_effect`, `error_code`). So for a terminal
  `cancelled` or `expired` command this route returns the triple itself: `cancelled` gives
  (`cancelled`, `none`, `none`) and `expired` gives (`failed_terminal`, `none`, `expired`) when
  `effect_state` is `none` or `not_performed`; any other `effect_state` gives
  `provider_effect: unknown` (so #1044 maps it to `unknown`). `completed` commands return the
  stored triple. OPEN-985-15 (was the second OPEN-985-9) asks the #1044 AMEND to confirm this mapping.
- **Contract artifact (round 5, N4; the one owner is this slice).** `internal/glovo/control/contract/*.json`
  with a `SHA256SUMS`: for each route of this table its request, its 200 body, every §2b
  refusal body and the `Idempotent-Replayed` header, plus the triple cases above. #1044's
  `ASSISTANTS_API_CONTRACT` pin and the #990 provenance check are consumers of that file
  set, not owners of a second copy.
- No body carries `execution_id` any more. It is derived from the locked order row
  (`Order.ExecutionID`, #988).
- A replayed dispatch returns the same `command_id`, with the header
  `Idempotent-Replayed: true` (the #957 M4 convention), and the current `order_state` and
  `effect_state` (round 4, F2: they change after dispatch, so the body is not byte-identical
  to the first answer). The body has no `replayed` field.
- `read_command_result` returns ids, enums and the digest only, never the stored result
  body or a payload. It answers only for Glovo `place_order_fake`
  commands whose order is inside the `tenants` bound. Anything else is `not_found`.
  (Amended (c): `place_order_fake` only. Glovo M1 never enqueues `cancel_order_fake`;
  cancellation is `bridge.Store.Cancel` on the existing command.)
- **Result to order (round 7, F2; round 8 B1, B2, B6, B7; closes OPEN-985-5; the one owner is this route, and this table is the only copy).**
  One function, `Dispatcher.reconcileOrder(ctx, tx, order, commandID)`, applies the table below. It
  has exactly two callers, and each passes it the pair it read once with `CommandEffect` on its own
  transaction. `read_command_result` takes L1 shared, L2 shared, L3 (`LockOrderForControl`), reads
  the pair (before L4), and takes L4 only for a row whose `aar_` column names a call. `Cancel` (§6)
  holds L1 shared, L2 shared, L6 read, L3, L4 and L5, and reads the pair after `Store.Cancel`. The
  lock list is the same in #957 §6b. `reconcileOrder` first checks that the order is `dispatched` and
  returns without any call otherwise. A terminal command never changes again, so the read made
  before L4 stays valid, and a non-terminal command changes nothing, so a stale read only delays
  the transition. The order calls are not idempotent: each is a CAS on `version` and `state`, so a
  repeat fails, which is why the `dispatched` guard comes first. Only
  `MarkGlovoApprovalUnknownTx` is safe to repeat (#989 §4). The pair is read before `reconcileOrder` is called, so on `read_command_result` a failed or absent `CommandEffect` read is 503 `unavailable` on every order state (a non-`dispatched` order reaches `reconcileOrder` only on that route, because `Cancel` reads a command only on a `dispatched` order, §6, so no `Store.Cancel` commit or rollback question exists on that path); the table lookup is inside `reconcileOrder`, after the `dispatched` guard, so on an order that is not `dispatched` an out-of-table pair makes no call and no write and the control route answers 200 from the stored order state, while the facade (#957 §3a) answers 503 for the same pair on a `dispatched` or `closed` order, because it derives the state from the pair on every such read (for a `cancelled` or `unknown` order the facade state comes from the order alone). `reconcileOrder` derives the order from the (status, `effect_state`) pair alone and never consults the stored result triple: a triple that contradicts `effect_state` does not change the order state.

  | Command `status` | `effect_state` | #988 call on the `dispatched` order | #989 call on the `aar_` | #957 §3a wire `state` |
  |---|---|---|---|---|
  | `pending`, `leased` | `none`, `permitted` | none | none | `dispatched` |
  | `pending`, `leased` | `unknown` (a reclaim turned `permitted` into `unknown`) | none | none | `unknown` |
  | `completed` | `succeeded` | `MarkClosed` | none (the permit consumed it) | `placed` |
  | `completed` | `failed` | `MarkClosed` | none | `failed` |
  | `completed` | `not_performed` (`approval_refused` with no permit) | `MarkClosed` | `MarkGlovoApprovalUnknownTx` | `failed` |
  | `completed` | `unknown` | `MarkUnknown` | none | `unknown` |
  | `completed` | `none` (the provider ended the command before any permit) | `MarkClosed` | `MarkGlovoApprovalUnknownTx` | `failed` |
  | `cancelled`, `expired` | `none`, `not_performed` | `MarkCancelled` | `MarkGlovoApprovalUnknownTx` | `cancelled` |
  | `cancelled`, `expired` | `succeeded`, `failed`, `permitted`, `unknown` (a possible effect is never shown as cancelled) | `MarkUnknown` | none | `unknown` |
  | every other pair: `pending` or `leased` with `succeeded`, `failed` or `not_performed`; `completed` with `permitted` (no read of a command, or a failed read, is in this row too) | | none. An invariant violation, or an unobserved state, never read as "nothing happened". Route, on a `dispatched` order (on any other order state the control route answers 200 from the stored order state, §2a, `reconcileOrder` guard): 503 `unavailable`, audit, the transaction rolls back (nothing is written, `Store.Cancel` included). The facade never renders a state for it (#957 §3a) | none | no state: 503 |

  Every row with a `MarkGlovoApprovalUnknownTx` entry is a command that may have ended with no permit row (the call is a no-op when the receipt is already `consumed`):
  a reserved receipt of it can never be spent, so the order call and the receipt call share the
  transaction, as #989 §7 requires. `MarkGlovoApprovalUnknownTx` is a no-op returning nil when the
  `aar_` is not `reserved` for that command (already `unknown`, or `consumed` because a permit did
  exist, #989 §4), so the order `Mark*` in the same transaction is never rolled back by it; for
  `succeeded` the permit consumed the receipt, and the sweeper covers a command nobody reads (#989
  §7, OPEN-989-8). `bridge.CancelOpenForConnections` (L5 only) never touches the order: the stored
  order catches up on the next `read_command_result` or `cancel`, while the facade `state` does not
  wait, because #957 §3a derives it from the same two inputs on every read.
  `bridge.Store.CommandEffect(ctx, q dbq.Querier, tenants []string, commandID string) (status,
  effectState string, err error)` is the read-only call that this slice adds in task 4 and that
  #957 §3a consumes.
- `revalidate_scope` and `resolve_connection` from #1044's `ControlApiPort` are not
  added here. Their owner is an OPEN item.

#### 2b. Closed refusal table

Every refusal uses the #959 `glovo.WriteError` body `{"error","error_description"}`
with fixed text. Amended (c): every code and status here is a row of the closed set in
mctl-api#957 design §4.1 (control-route column), and nothing else is sent. The internal
reason goes to audit only.

| Condition | HTTP | `error` | #1044 M10 |
|---|---|---|---|
| The caller is not the control worker, or a control worker calls another route | 403 | `not_authorized` | terminal |
| Gate closed after mount, missing config, failed proof, or a missing collaborator | 503 | `not_ready` | `provider_disabled` (mapped on the #1044 side) |
| Store I/O error, a failed or absent `CommandEffect` read, or a pair outside the §2a table on a `dispatched` order (the transaction rolls back; on any other order state the control route answers 200 from the stored order state, §2a, `reconcileOrder` guard) | 503 | `unavailable` | retryable |
| `lock_timeout` (SQLSTATE `55P03`) on any lock of the #957 §6b order | 409 | `tenant_busy` | `tenant_busy` |
| Malformed ref, unknown or duplicate field | 400 | `invalid_request` | terminal |
| Order, command or approval is absent, foreign, or outside `tenants` | 404 | `not_found` | terminal |
| The `aar_` is not `approved` (`pending`, `refused`, `unknown`, `consumed` without this command) or is not a Glovo-kind `aar_` | 409 | `approval_invalid` | `approval_invalid` |
| The `aar_` is past `expires_at` or its freshness bound | 409 | `approval_expired` | `approval_expired` |
| The `aar_` is already reserved or consumed for another command, or a different `aar_` names a dispatched order | 409 | `approval_replayed` | `approval_replayed` |
| A binding differs: tenant, owner, `we_`, order, connection, install revision or intent hash | 409 | `intent_mismatch` | `intent_mismatch` |
| The body fingerprint differs from the order's final fingerprint or the `aar_` binding | 409 | `basket_changed` | `basket_changed` |
| The owner is no longer a tenant member | 403 | `no_tenant` | terminal |
| No live connection / connection revoked / connection expired | 404 / 409 / 409 | `no_connection` / `connection_revoked` / `connection_expired` | terminal |
| The install revision moved | 403 | `stale_install` | terminal |
| Dispatch of an order that is `cancelled`, `unknown` or `closed` | 409 | `invalid_transition` | terminal |
| Rate limit | 429 (+ `Retry-After`) | `rate_limited` | retryable |

Cancelling a command that is already `completed` or `expired` is **not** a refusal. It
answers 200 with the current `order_state` and `effect_state`; the bridge command is unchanged,
and the order moves only through `reconcileOrder` (§2a).

Whether #1044 maps the #959 codes in this table (`no_tenant`, `no_connection`,
`connection_revoked`, `connection_expired`, `stale_install`, `invalid_transition`, `not_found`
and `unavailable`) is closed (round 8): #1044 M10b maps them.

### 3. Store seam (`internal/glovo/control/`)

```go
type OrderIndex interface { // #988 (M1b/1), tx-scoped, control path
    PeekOrderScope(ctx context.Context, q dbq.Querier, orderRef string, tenants []string) (orders.Scope, error) // unlocked read of write-once columns
    LockOrderForControl(ctx context.Context, tx pgx.Tx, orderRef string, tenants []string) (*orders.Order, error) // L3, FOR UPDATE; scope derived from the row
    MarkDispatched(ctx context.Context, tx pgx.Tx, o *orders.Order, commandID string, actor orders.Actor) error // finalized -> dispatched, command_id write-once
    MarkCancelled(ctx context.Context, tx pgx.Tx, o *orders.Order, actor orders.Actor) error  // only when no effect is possible
    MarkUnknown(ctx context.Context, tx pgx.Tx, o *orders.Order, actor orders.Actor) error    // the effect may have happened
    MarkClosed(ctx context.Context, tx pgx.Tx, o *orders.Order, actor orders.Actor) error     // dispatched -> closed only; reconcileOrder (§2a)
}
type Receipts interface { // provided by #989 (internal/workitems, glovo_approvals.go); tx-scoped; #985 never writes action_approval_requests itself
    LockGlovoApprovalTx(ctx context.Context, tx pgx.Tx, id string) (*workitems.ActionApprovalRequest, *workitems.GlovoBinding, error) // L4, FOR UPDATE
    ReserveGlovoApprovalTx(ctx context.Context, tx pgx.Tx, id string, cmd workitems.ReserveCommand) (replayed bool, err error) // approved -> reserved; idempotent for the same cmd_
    RevokeGlovoApprovalTx(ctx context.Context, tx pgx.Tx, id string, actor string) error // pending|approved -> refused (cancel before dispatch); already denied for this order = success
    MarkGlovoApprovalUnknownTx(ctx context.Context, tx pgx.Tx, id, commandID string) error // reserved -> unknown; already unknown for this cmd_ = success
    GlovoApprovalStatus(ctx context.Context, q dbq.Querier, tenants []string, id string) (*workitems.GlovoApprovalStatus, error) // round 3 (X-4): read on the glovo_runtime pool (or the caller's tx), never the work-items pool; ids and enums only; read_approval
}
type Connections interface { // #959, tx-scoped, on the shared tx
    LockOwnerShared(ctx context.Context, tx pgx.Tx, tenant, principal string) error // L1 shared + L2 shared, the #959 withLocks order
    LiveConnectionTx(ctx context.Context, tx pgx.Tx, owner glovo.Owner) (*glovo.Connection, error) // no row lock; L1/L2 already held; expires_at fenced
    MembershipRevocationWired() bool // #959; true only when a membership detector is registered (§7.3, OPEN-985-2)
    Ready(ctx context.Context) error // #959; revocation_hook_missing without a hook
}
// Every signature above is copied from mctl-api#957 design §6d.4 (amended (c)).
type Membership interface{ IsMember(ctx context.Context, tenant, principalID string) (bool, error) } // GitOps; a gate, fail closed; callers bound it with MembershipTimeout (2 s)
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
- Required config: `GLOVO_DB_URL` (the one `glovo_runtime` pool, shared by the #959 store and the bridge store, #957 §6d.1 R4) and `WORK_ITEMS_DB_URL`, each set explicitly. The bridge
  store mode is chosen by one selector (round 3, F2): `bridge_schema_version`, created and
  written by `bridge.ApplySchema`. Round 4 (F3): `main.go` probes
  `to_regclass('public.bridge_schema_version') IS NOT NULL` once at startup, on the
  `GLOVO_DB_URL` pool when it is set and otherwise on the legacy bridge DSN (the only use
  of `COMMERCE_DB_URL` left for the bridge, and read-only). Table present and
  `GLOVO_DB_URL` set: `bridge.NewRuntimeStore` on that pool, whatever any Glovo flag says,
  and it reads the version row as `glovo_runtime`. Table absent: `NewStore` unchanged.

  | Probe result | Bridge |
  |---|---|
  | table present, `GLOVO_DB_URL` set, version row readable and at least the compiled level | `NewRuntimeStore` |
  | table present, `GLOVO_DB_URL` unset | bridge `not_ready` (never `NewStore`) |
  | probe or version-read error, version row missing or older than the compiled level | bridge `not_ready` (never `NewStore`) |
  | table present, but `bridge_read_schema_version` missing or below the compiled read level (`bridge.ReadSchemaLevel`, owned by #986) (round 5, #986 F3) | bridge `not_ready` (`bridge.CheckReadLevel`, never `NewStore`) |
  | table absent | `NewStore`, unchanged |

  Existing bridge consumers therefore never fall into `NewStore`'s `ALTER TABLE` on
  tables they no longer own; an operator who unsets `GLOVO_DB_URL` after `ApplySchema` sees
  an explicit `not_ready`, not a silent switch. Bridge tables created earlier by
  `NewStore` under another owner make `ApplySchema` refuse (OPEN-957-6). A missing value is `not_ready`. None of them falls back to `AUDIT_DB_URL`
  or to another one.
- `control.ProveOneDatabase(ctx, bridgeStore *bridge.Store, glovoStore *glovo.Store, workItemsPool *pgxpool.Pool)` runs at startup (round 3, X-3: it first requires `glovoStore.Pool() == bridgeStore.Pool()`, one pool and one role; the work-items pool is the only other pool):
  1. In one transaction on the bridge pool, insert a fresh 128-bit nonce into
     `bridge_colocation_probe` and commit. The table is created by `bridge.ApplySchema`
     (amended (c)).
  2. Read the nonce back through the work-items pool and the shared Glovo pool. If either does
     not find it, the proof fails. This proves one database, not merely one cluster. It
     does not depend on `system_identifier` (physical standbys share it) or on EXECUTE
     rights on `pg_control_system()`.
  3. Each pool must report `pg_is_in_recovery() = false`.
  4. From the bridge pool, `to_regclass` must find every participating table:
     `bridge_commands`, the #988 order tables, the #989 receipt table, and the #959
     `glovo.glovo_installs` and `glovo.glovo_connections`. Amended (c): from the bridge
     pool, `has_schema_privilege`, `has_table_privilege` and `has_column_privilege`
     reproduce the grant table of mctl-api#957 design §6d.1 exactly, with nothing
     beyond it (this covers every DML right dispatch, cancel, prepare and the revoker
     need); the bridge and Glovo pools report the same `current_user`, which owns no
     object in schema `glovo` and no bridge table, is not a member of any owner role,
     and has `rolsuper`, `rolcreaterole`, `rolcreatedb` and `rolbypassrls` all false
     (`pg_roles WHERE rolname = current_user`; round 3, F1: CREATEROLE would let a runtime
     role grant itself `glovo_migrator`); every guard trigger of every slice's inventory is
     present with `tgenabled = 'O'` (#988 §3 `triggerInventory`, #989 `aar_guard`); the work-items pool reports another
     role, without `USAGE` on `glovo`.
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
5. Replay check, before any receipt check (round 4, F2). If `order.command_id` is non-empty
   (`command_id` is written once, on `finalized -> dispatched`, so it exists in `dispatched`,
   `cancelled` after dispatch, `unknown` and `closed`), the order's `approval_ref` equals
   the body's and the fingerprint matches, commit and return the stored `command_id` with
   the current `order_state` and `effect_state` and `Idempotent-Replayed: true`. A reserved,
   consumed or finished receipt therefore replays and is not refused. Otherwise:
   - a different `aar_` on an order that has a `command_id` is `approval_replayed`;
   - `cancelled` or `closed` without a `command_id` is `invalid_transition`;
   - any state other than `finalized` is `invalid_transition`.
6. `body.fingerprint` must equal `order.final_basket_fingerprint`, else
   `basket_changed`. The value is the single M1 basket fingerprint defined in
   mctl-agents#1059 (see #988). mctl-api computed it; the caller's copy is only compared.
7. `Receipts.LockGlovoApprovalTx(aar)` takes L4. Its state is checked as in §2b. Then the binding:
   tenant, owner, `we_`, order, connection, install revision, fingerprint and intent hash
   must equal the locked order row. Any difference is `intent_mismatch`, except the
   fingerprint, which is `basket_changed`.
8. `Conns.LiveConnectionTx(owner)`:
   - the typed not-live code #959 `LiveConnectionTx` returns (round 8, C-4): `no_connection` (none, or `failed`), `connection_revoked`, `connection_expired`;
   - a live `gcn_` that differs from the order's is `connection_revoked` (decided here, as #988 §6; #959 does not know the order's `gcn_`);
   - an install revision that differs from the order's is `stale_install`.
9. `Members.IsMember(ctx, tenant, owner)` (amended 2026-11-10: it takes a `ctx`; the
   call is a network call made while L1 to L4 are held, so it runs under
   `context.WithTimeout(ctx, MembershipTimeout)`, the named constant `MembershipTimeout`
   = 2 s, below the 5 s `lock_timeout`). `false` is `no_tenant`; an error, a timeout and a
   cancelled context are all `unavailable`, never `no_tenant` and never a pass. A hung
   provider therefore cannot hold L3 or L4 longer than `MembershipTimeout` (T15a).
   `Membership` is a gate at dispatch, and again in #989 `Check`, not best effort: only
   the GitOps lag between a removal and the revoker (the §7.3 residual window) is best
   effort.
10. Compute `sequence = coalesce(max(sequence), 0) + 1` over `bridge_commands` for this
    `execution_id`, read under L3. Every command of this `we_` is created under this
    order lock.
11. Read the order's final snapshot (`final_snapshot_seq`) and require
    `basket.Fingerprint(snapshot) == order.final_basket_fingerprint`. Call
    `bridge.Store.Enqueue(ctx, tx, EnqueueInput{Kind: KindPlaceOrderFake,
    OperationKey: "glovo-dispatch:"+order_ref, Sequence: sequence, ApprovalRef: aar,
    IntentHash: <the aar_ row's intent_hash>, Payload: <the snapshot's JCS approval-basket
    bytes, exactly, no wrapper>, Attempt: 1, …})`. Round 5 (N3), the complete mapping of the
    remaining `EnqueueInput` fields, each also checked by `Enqueue.validate`: `ProviderRef` =
    `binding.provider` from `LockGlovoApprovalTx` (the value #989's fence compares with
    `command.provider_ref`); `Tenant` and `OwnerPrincipalID` from the locked order;
    `InstallRevision` from the binding; `TTL` = the named constant `DispatchCommandTTL` (900 s, §7.4, OPEN-985-13),
    capped at the time left until the `aar_` row's `fresh_until`. Amended 2026-11-10: this
    check runs BEFORE `Enqueue`: when `fresh_until - now <= ReservePermitMargin` (the named
    constant, 120 s, the margin #989 `Check` needs to reserve and issue a permit) the answer is
    409 `approval_expired` and nothing is enqueued, because a command whose TTL is shorter
    than the margin can never be permitted (T4a: 119 s refuses, 121 s enqueues with a TTL
    capped at the time left). Every field comes from the locked rows
    (amended (c), #957 §6d.2): `ExecutionID` and `WorkItemID`/`WorkflowID` from
    `Order.ExecutionID` and #989 `ExecutionBindingTx`; `RunID` from #957
    `glovojoin.ControlStartTx` (empty is valid, `bridge_commands.run_id` defaults to
    `''`, `internal/bridge/store.go:75`); `TenantRef`/`PrincipalRef` from #988
    `LookupJoinRefTx`; `OrderRef` the `ordr_`; `ConnectionRef` the `gcn_`. The payload
    shape is fixed in #957 §6d.3 and the command is defined once by #1059 §Write command.
    Its wire version (`bridge.mctl.ai/v1alpha2`), projection, validation against the schema, Claim
    gating and vendoring are #986 §2a: this step only passes `WireVersion: bridge.WireV1alpha2`.
    `Enqueue` refuses that value while #986 `Store.WireVersionsEnabled()` is false (`ErrReadUnavailable`, which
    dispatch answers as `not_ready`). `created=false` at this
    point (the order is still `finalized`) is an invariant violation: roll back, audit
    it, and answer `unavailable`.
12. `Receipts.ReserveGlovoApprovalTx(aar, workitems.ReserveCommand{CommandID, Tenant,
    OwnerPrincipalID, ExecutionID, OrderRef, ConnectionRef, InstallRevision, IntentHash,
    BasketFingerprint})` (the #989 §4 type, all fields required). #989 re-checks the binding against these command
    fields and is idempotent for the same `cmd_`.
13. `Orders.MarkDispatched(order, cmd_, Actor{Kind: control_worker})`.
14. Commit. Any error rolls back everything.

A backstop index goes in `bridge.ApplySchema` (amended (c)): `CREATE UNIQUE INDEX IF NOT EXISTS
bridge_commands_mutating_approval ON bridge_commands (approval_ref) WHERE
operation_kind='place_order_fake'`.

### 6. Cancel transaction (`Dispatcher.Cancel`)
Locks are taken in the same order as §5: L1 shared, L2 shared, L6 read, L3, L4, L5. The order state
is read under L3 and decides the path; every path answers 200 with the resulting `order_state` and the
command's `effect_state` unless a row says otherwise.
- `open` (no `aar_` and no command exist yet; #988 `open -> cancelled`): `MarkCancelled`, no
  `Revoke`, no bridge call. `command_id` is absent.
- `finalized` (not dispatched): call `Receipts.RevokeGlovoApprovalTx(aar, actor)` and
  `MarkCancelled`. `effect_state` is `none`.
- `dispatched`: call `bridge.Store.Cancel(ctx, tx, cmd_, "service:glovo-control-worker")`; it
  returns nil (a pending or leased command is now `cancelled`, `permitted` turned into `unknown`) or
  `ErrAlreadyCompleted` (`completed` or `expired`, nothing changed). In both cases read the pair
  with `CommandEffect` and call `reconcileOrder` (§2a). The table decides everything: the order is
  never `cancelled` while a permit may have been issued, and never left `dispatched` behind a
  terminal command. This section restates no row.
- `closed`, `cancelled`, `unknown` (terminal): no write and no bridge call, 200 with the current
  state. A repeat of any cancel is therefore a no-op.
- The catch-all row of §2a is 503 `unavailable` for `Cancel` too, with the transaction rolled back
  (a `Store.Cancel` in it included) and an audit event; requirements state the same.

### 7. Revocation and the actual write

#### 7.1 Global lock order

The canonical lock order L1..L6 for every Glovo write path is defined once, in #957
design §6b. This slice takes:
- dispatch and cancel: L1 shared, L2 shared, L6 read, L3 (order), L4 (`aar_`), L5 (commands); `read_command_result` takes L1 shared, L2 shared, L3 and L4 only for the rows that name a receipt call (§2a);
- permit (through `WriteFence.PreLock`, then `lockOwned`): L1 shared, L2 shared, L3, L4,
  then L5;
- `bridge.CancelOpenForConnections` (called by every #959 connection-ending path after
  L1/L2): L5 only, `ORDER BY command_id`.

The provider claim, result and expiry paths take only L5.

#### 7.2 Write fence (#989 `receipt.Fence`, a `bridge.WriteFence`)
- `bridge.WriteFence` gains `PreLock(ctx, tx, c bridge.Caller, commandID) error`.
  `permitTx` calls it **before** `lockOwned`. Since 2026-11-10 the definition, the call
  in `permit.go:98` and the no-op `refusingFence.PreLock` belong to #989 task 7 (they
  break the #985/#989 cycle: #989 merges first and needs nothing from this slice); this
  slice adds no fence code and relies on the hook. Amended (c): the
  fence's `PreLock` first applies the same provider and tenants check as `lockOwned`
  (`internal/bridge/store.go:836-846`, main `dc55930`) to an unlocked read, and answers
  `ErrCommandNotFound` alike for an absent and a foreign id, before taking any lock.
- #989's `receipt.Fence.PreLock(ctx, tx, c bridge.Caller, commandID)` (round 3, X-6: step 0 is the provider/tenants predicate and the `place_order_fake` kind refusal, #989 §6) reads the command's immutable binding without a lock (tenant,
  owner, order, `aar_`). It then takes L1 shared, L2 shared, L3 and L4.
- `permitTx` then takes L5 (`lockOwned`). #989's `Check` re-verifies that the binding
  read in `PreLock` is unchanged, recomputes the fingerprint and intent hash from the
  stored command payload, checks the connection, the install revision, membership (the
  same `MembershipTimeout`, unavailable on timeout; a hung provider cannot hold L5 past it)
  and the receipt state (`reserved` for this `cmd_`), and consumes the `aar_` (#989 design
  §6). That is the single-use point at the physical write.
- The #959 connection-ending paths are `Revoke` (including reason
  `membership_removed`), `RevokeInstall`, `Reinstall`, `Reconnect` (`superseded`) and
  terminal `Transition`s, all through `endConnection` (amended (c)). Each one:
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
`bridgeStore.SetFence(receipt.NewFence(...))` (#989) only when **all six** of these
hold. This is the only copy of the list (amended (c)); the requirements mirror it and
#989 §8 references it.
1. `glovo.ControlDefault.Open` is true.
2. The owner has lifted hold mctl-gitops#2457.
3. The §4 one-database proof passed.
4. #959 `Ready()` returns nil AND the installed revocation hook is
   `bridge.CancelOpenForConnections` (amended 2026-11-10). Today
   `cmd/api/glovo_team_grant.go` installs `syntheticRevocationHook`, which returns nil and
   cancels nothing, and `Ready()` is satisfied by any hook. Task 9 therefore swaps it:
   `glovo.WithRevocationHook(bridge.CancelOpenForConnections)` replaces
   `glovo.WithRevocationHook(syntheticRevocationHook)`, and at startup `main.go` asserts the
   installed hook is that function (the store exposes it for comparison, or the assertion
   is made on the options list `main.go` built: one of the two, chosen in task 9, tested
   either way). A different hook, including the synthetic one, leaves the fence
   `refusingFence` and logs once (T24 cases b and c).
5. #959 `MembershipRevocationWired()` is true on a positive signal (amended 2026-11-10).
   The current implementation returns `membershipRevoker != ""`, a configured label, which
   proves nothing about a running detector. The method must instead be true only when
   there is evidence that the component that observes a GitOps membership removal
   revokes the member's connection (`Revoke` with reason `membership_removed`): either a
   detector heartbeat fresher than a named bound (`MembershipDetectorStale`, default
   5 min) recorded by the detector in the shared database, or a recorded end-to-end
   proof "membership removed, then the connection revoked" younger than a named bound.
   An absent, unreadable or stale signal is false (could not observe is not observed
   present). Interim, until the detector exists: the method is false and the fence stays
   `refusingFence`. Who builds and runs the detector is OPEN-985-2 and stays an owner
   question; this proposal does not decide it. T24 case (d) and T17 cover the two false
   cases (label set but no signal; signal stale).
6. #989 `receipt.Ready(ctx)` returns nil.

Activation precondition, not a fence precondition (round 8, OPEN-986-6): the real provider's
`MCTL_BRIDGE_PROVIDERS` entry must declare `supported_versions` with v1alpha2 (#986 §2). Without it a
dispatched command is never claimed and expires, so the order ends `cancelled` (§2a).

A residual window remains between the GitOps membership removal and the hook's
revocation. The owner must accept it explicitly; this is an OPEN item.

#### 7.4 Fixture build: the gate and the TTL seams (round 8; owner of both seams: this slice)
#990 must drive the real control routes, so a test build needs a way to open the const-closed
gate and to shorten the dispatch TTL. There is one mechanism, the `glovojoin_fixture` build tag
that #957 §8 already uses for `FixtureBridge` (referenced, not duplicated), and it selects
exactly two file pairs, each with a release twin: the gate pair in `internal/glovo` (the package of `glovo.ControlDefault`, so the unexported const is visible to it) and the TTL pair in `internal/glovo/control`:
- `gate_release.go` (`//go:build !glovojoin_fixture`): `const controlGateOpen = false`;
  `gate_fixture.go` (`//go:build glovojoin_fixture`): `const controlGateOpen = true`; both in `internal/glovo`. `glovo.ControlDefault` stays backed by that const.
- in `internal/glovo/control`: `ttl_release.go` (`!glovojoin_fixture`): `const DispatchCommandTTL = 900 * time.Second`;
  `ttl_fixture.go` (`glovojoin_fixture`): `var DispatchCommandTTL = 900 * time.Second` and
  `func SetFixtureDispatchCommandTTL(d time.Duration)`, which a test calls before it starts
  the router. #957 owns the matching pair `internal/glovojoin/ttl_release.go` /
  `ttl_fixture.go` for `GlovoApprovalTTL` and `SetFixtureGlovoApprovalTTL(d)`.
- Opening the const is the only thing the tag does to §7.3. The fixture build still has to
  satisfy items 2 to 6 for real: the `MCTL_GLOVO_CONTROL_ENABLED` route flag, the §4 proof,
  #959 `Ready()`, `MembershipRevocationWired()` and `receipt.Ready`. It must not skip the
  verifier, the revocation hook or `receipt.Ready`; a fixture run that stubs any of them is
  not a #990 pass.
- No injected Go clock is used, so none is the seam. Every expiry decision is made by the
  database (`clock_timestamp()`, #959 F1 and #989 T7b), which a Go clock cannot move. A
  timeout row is therefore driven with a short real duration: the two TTL setters above, and
  for the connection the #959 `ActivateInput.ExpiresIn` (a duration, SQL computes
  `clock_timestamp() + ExpiresIn`) passed by the test with a few seconds, or a direct
  `UPDATE glovo_connections SET expires_at = clock_timestamp() + interval '2 seconds'` in the
  harness database, then a wait. No release-build code path reads a variable.
- DispatchCommandTTL (OPEN-985-13, recommendation 900 s): it is the #1059 `ttl_seconds`
  maximum (1..900) and equals #1044's `settle_timeout_s` default, so the workflow never gives
  up on a command that is still live; the effective value is always capped at the time left
  until the `aar_` `fresh_until` (step 11), so a command can never outlive its approval.

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

- **Migrations (amended (c)).** New `bridge.ApplySchema(ctx, migrationConnStr,
  runtimeRole)`, run under the migration role in the order of mctl-api#957 design
  §6d.1, applies `bridgeSchema` (`internal/bridge/store.go:67-69` onward), then:
  - the partial unique index `bridge_commands_mutating_approval`;
  - the table `bridge_colocation_probe(nonce TEXT PRIMARY KEY, created_at TIMESTAMPTZ)`;
  - #986's read objects, by calling `bridge.ApplyReadSchemaTx(ctx, tx, runtimeRole)` (owned and tested standalone by #986; round 4, X-3) inside this transaction;
  - the grants of the bridge rows of #957 §6d.1 to `runtimeRole`, and `SELECT` on
    `bridge_colocation_probe` to the work-items role for the proof, and `SELECT`,
    `UPDATE (result)` on `bridge_commands` to the bridge maintenance role
    (`cmd/bridge-scrub`), the "existing consumers" rows of #957 §6d.1.
  - the table `bridge_schema_version` (single row), written last, which is the mode
    selector of #957 §6d.1 (round 3, F2).
  Once the row exists the store is always `bridge.NewRuntimeStore` on the shared
  `GLOVO_DB_URL` pool, which runs no DDL and checks the schema version and the grants, in
  the pattern of `OpenExistingStore` (`store.go:520`), whatever the Glovo flags say;
  today `NewStore` runs `bridgeSchema` on every start (`store.go:510`), including an
  `ALTER TABLE` that needs ownership. Without the row (never migrated) `NewStore` is
  unchanged. Bridge tables created earlier under another owner make `ApplySchema` refuse
  with an error naming them (OPEN-957-6, owner decision pending); disabling Glovo after
  `ApplySchema` therefore never changes the bridge's store or database. The runtime role is
  never given `CREATE`, ownership or any other right to make `NewStore` pass (owner
  decision 2026-11-09, #957 §6d.1). There is no
  `SECURITY DEFINER` function: `bridge.CancelOpenForConnections` is a Go function that
  runs on the revoker's transaction with the runtime role's own `bridge_commands`
  rights.
- **Backward compatibility.** The routes are absent unless the const and the env flag
  are both on. `refusingFence.PreLock` is a no-op, so the default permit path is
  unchanged.
- **Resources.** One short transaction per call. With two replicas, the advisory and row
  locks serialize across both.
- **Risks and mitigations:**
  - The database is split: the proof fails closed.
  - Membership changes are invisible to Postgres: the fence needs the hook, and the
    owner accepts the residual.
  - Lock waits: a 5 s `lock_timeout` maps to `tenant_busy` (#957 §4.1).
  - Token confusion: exact audience, a confining gate and the `tenants` bound.
- **Dependencies (blocking).** If any of these is missing, the routes answer
  `not_ready`:
  - #986, for `bridge.ApplyReadSchemaTx` (round 4, X-3: merge order #986 before #985);
  - #957 task A14 (`glovojoin.ControlStartTx`; merge order #957 §6d.1, package direction `control` imports `glovojoin`; round 6, G3);
  - the amended #959 store (one database, tx-scoped reads, revokers that cancel
    commands);
  - the #988 order index;
  - the #989 methods of §3 and its `receipt.Fence` (#989 merges first; it also defines
    `WriteFence.PreLock`, 2026-11-10);
  - the #1059 `command-place-order-fake.schema.json` as vendored by #986 §2a, and the approval basket as vendored by #988 (OPEN-985-8, closed: #1059 owns the schema);
  - #987, the fallback removal;
  - mctl-gitops#2506, for a production verifier.

## Open questions

See requirements.md.
