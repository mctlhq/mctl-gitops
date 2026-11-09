# Design: issue-989-feat-glovo-m1b-2-single-authoritative-aa

## Current state

Clone at `ceac9ed` (Merge #984).

### Generic `aar_` machine (`internal/workitems/action_approvals.go`)

- `ActionApprovalIDPrefix = "aar_"`. The table `action_approval_requests` is created
  inline in `actionApprovalSchema`. Its stored states are
  `pending, approved, denied, consumed, in_flight, executed`, enforced by
  `action_approval_requests_state_check`, which is replaced with the "replace-once"
  `DO $$` pattern. `expired` is never stored: `effectiveState` derives it for pending or
  approved rows past `expires_at`.
- `IntentHash(ActionIntent)` is a length-prefixed sha256 over `execution_id`,
  `action_kind`, `target`, `args_digest`, `policy_rule_id`, `policy_version`,
  `artifact_hash` and `work_item_id`.
- `DecideActionApproval` runs in `withTx` (`internal/workitems/store.go:266`), locks
  `FOR UPDATE`, refuses `ErrApprovalSelfDecision`, and moves `pending -> approved|denied`
  with `WHERE state='pending'`. Concurrent approve and refuse therefore already
  serialize.
- `ConsumeActionApproval` is a CAS `approved -> consumed` on `s.pool`.
  `ReserveActionApproval` and `SettleActionApproval` implement the MCP receipt gate
  (mctl-api#772): `consumed -> in_flight -> executed | consumed`. **A failed call
  returns the receipt to `consumed`, which is reusable.** A Glovo receipt must never do
  that.
- There is no tenant, owner, order, connection, install-revision or fingerprint column.
  The only tenant link is `work_item_id`. There is no tx-aware create, reserve or
  consume. Everything runs on the store's own pool or `withTx`.

### Decision authorization (`internal/api/handlers_action_approvals.go`)

- `DecideActionApproval` (around line 652) refuses anyone who is not `isHumanAdmin(u)`
  (admin, not service, not relayed, not surface) with `aarCodeDeciderForbidden`. It then
  runs the binding gate (`approval_binding.go:115` `bindingGate`) and `guardDecision`
  (governance context digest), and then the store decide.
- `devLoopApprovalKind = "mctl-agents-approve"` shows the existing precedent for
  per-kind rules in this handler (`isAgentExecutionGrant`, `isPinnedAgentGrant`).
- WorkItem visibility is `canSeeWorkItem` (`handlers_work_items.go:135`). Live tenant
  roles go through `requireTenantRole` / `checkTenantRole`
  (`internal/api/tenant_role.go:235`).
- `human_input_vs_action_approval_test.go` already proves that the approval path writes
  nothing to the `hir_` ledger. The reverse direction (a `hir_` answer causes no `aar_`
  or bridge change) has no Glovo-specific test.

### Bridge (`internal/bridge/`)

- `permit.go`: `FenceBinding{CommandID, ExecutionID, WorkItemID, Tenant,
  OwnerPrincipalID, ConnectionRef, InstallRevision, IntentHash, ApprovalRef,
  OperationKey, LeaseEpoch}`. The `WriteFence` interface has
  `Check(ctx, tx, b) (fenceRef, error)`, and its comment states the contract this slice
  must satisfy: "locks the aar_ approval row and verifies human approval, current tenant
  membership, owner, connection, install revision, basket fingerprint,
  unexpired/unrevoked state and equal IntentHash ... The bridge keeps no second grant or
  receipt state machine". The default is `refusingFence`, which returns
  `ErrWriteFenceUnavailable`.
- `permitTx` locks the command, checks the lease, the kind (`place_order_fake` or
  `cancel_order_fake`), a non-empty `ApprovalRef` and `effect_state='none'`. It calls
  `Check` on the same tx, inserts `bridge_write_permits` (unique) and sets
  `effect_state='permitted'`.
- `store.go` effect states are `none, permitted, succeeded, failed, not_performed,
  unknown`. `effectFor` maps a result. `Cancel` turns `permitted` into `unknown`.
  `ExpireDue` expires commands. `SetFence` (`store.go:416`) installs the fence, and
  `Pool()` (`store.go:414`) exposes the pool. The command row stores `tenant` (name),
  `owner_principal_id`, `order_ref` (`ordr_`), `connection_ref` (`gcn_`),
  `install_revision`, `approval_ref` (`aar_`) and `intent_hash`.
- `FenceBinding` carries no basket fingerprint. The fence must read it from the order
  (#988 `glovo_orders.final_basket_fingerprint`), never from the command or the request.

### Glovo gate and wiring

- `internal/glovo/gate.go`: `Default = Gate{Open: false}`, a build constant.
  `errors.go`: codes `not_ready` and `not_authorized`.
- `cmd/api/main.go`: the work items use `WORK_ITEMS_DB_URL`, falling back to
  `AUDIT_DB_URL` (`workItemsStoreSource`, line 2769). The bridge uses `COMMERCE_DB_URL`,
  falling back to `AUDIT_DB_URL` (lines 1019-1021), and is gated by
  `MCTL_BRIDGE_ENABLED`. Nothing calls `SetFence` today.

### Sibling proposals (agents-state, not yet in the clone)

- #988 (M1b/1): `glovo_orders` with `final_basket_fingerprint`, `approval_ref` and
  `command_id`, with the `Transition` table `finalized -> approved` ("requires an `aar_`
  in refs"). Its tx-only write methods take a caller `pgx.Tx`. Its design says M1b/2
  performs the `approved` transition.
- #957 §6/§6b: prepare creates `pord_` + `we_` + pending `aar_` in one `pgx.Tx` opened on
  `bridge.Store.Pool()`. Only the owner decides, through
  `POST /api/v1/action-approvals/{id}/decision`, which the facade cannot reach.
- #985 (M1b/3): defines `control.Approvals{LockApproval, ConsumeApprovalTx}`, the
  dispatch transaction and `ProveColocated`. In this proposal, the reserve step of that
  transaction is `ReserveGlovoApprovalTx`, and the consume moves to the fence (see
  "Alternatives").

### Deployed state checked

- `mcp__mctl__mctl_get_service_config(team=admins, service=mctl-api)`: error
  "service not found: admins/mctl-api". mctl-api is not a catalogue service under that
  name. This is an observation gap, not proof of absence.
- `$MCTL_GITOPS_ROOT/services/*/`: no `mctl-api` directory. Only `tenants/erpact/values.yaml`
  mentions `mctl-api`. Not read further, because it is a different tenant and not this
  service's config.
- `agents-state/mctl-api/proposals/issue-957-*`, `issue-985-*`, `issue-988-*` and
  `issue-960-*`: read for the contracts cited above. All are `status: proposed`, not
  merged.
- The deployed values of `COMMERCE_DB_URL`, `WORK_ITEMS_DB_URL` and
  `MCTL_BRIDGE_ENABLED` for mctl-api were **not observed** (see Open questions in
  requirements.md). The design does not depend on them, because co-location is proven
  at runtime by #985's `ProveColocated`.

## Proposed solution

### 1. One row, one state column

The authoritative object is the existing `action_approval_requests` row, with no second
state table. Glovo adds:

- **Action kinds** `glovo.place_order_fake` and `glovo.cancel_order_fake`
  (`workitems.GlovoActionKinds`, plus `IsGlovoKind(kind)`).
- **Two stored states**, `reserved` and `unknown`, added to the state CHECK with the
  existing replace-once `DO $$` pattern, keyed on `'reserved'`. A second CHECK,
  `action_approval_requests_glovo_states_chk`, enforces both directions:
  - `state IN ('reserved','unknown')` requires `action_kind LIKE 'glovo.%'`;
  - `action_kind LIKE 'glovo.%'` requires `state NOT IN ('in_flight','executed')`.
- **Lazy expiry extended**: `effectiveState` also reads a `reserved` row past
  `expires_at` as `expired`. The stored state stays `reserved` for forensics. The fence
  refuses on the stored expiry, and an expired row can never move again.
- **Exposed vocabulary** (`GlovoReceiptState(a)`): `pending`, `approved`, `reserved`,
  `consumed`, `unknown`, `refused` (stored `denied`) and `expired` (derived).

### 2. Immutable binding table

```sql
CREATE TABLE IF NOT EXISTS glovo_approval_bindings (
  approval_id        TEXT PRIMARY KEY REFERENCES action_approval_requests (id),
  tenant             TEXT NOT NULL,
  owner_principal_id TEXT NOT NULL CHECK (owner_principal_id LIKE 'prn\_%'),
  execution_id       TEXT NOT NULL,          -- we_, equals the aar_ row's
  work_item_id       TEXT NOT NULL,
  order_ref          TEXT NOT NULL CHECK (order_ref ~ '^ordr_[A-Za-z0-9]{16,40}$'),
  connection_ref     TEXT NOT NULL CHECK (connection_ref ~ '^gcn_[A-Za-z0-9]{16,40}$'),
  install_id         TEXT NOT NULL,
  install_revision   BIGINT NOT NULL,
  basket_fingerprint TEXT NOT NULL,          -- digest only, never basket bytes
  provider           TEXT NOT NULL,
  command_id         TEXT NOT NULL DEFAULT '',
  created_at         TIMESTAMPTZ NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS glovo_approval_bindings_command
  ON glovo_approval_bindings (command_id) WHERE command_id <> '';
```

- The trigger `glovo_approval_bindings_immutable()` (`BEFORE UPDATE OR DELETE`) refuses
  every change except setting `command_id` from `''` to a `cmd_` value.
- "One live `aar_` per order" is enforced in `CreateGlovoApprovalTx`: lock the order
  through #988's `LockOrder`, then refuse if `glovo_orders.approval_ref` is non-empty.
  A partial unique index cannot be used, because it cannot join the state. #988's own
  `approval_ref` column holds the single link.
- The DDL runs in the work-items `ApplySchema` path next to `actionApprovalSchema`,
  because `REFERENCES` needs the same database. Co-location with the bridge and order
  tables is proven by #985.

### 3. Intent hash

`GlovoIntent(b Binding, kind) workitems.ActionIntent` sets:

- `Target = "glovo:v1:" + len-prefixed(tenant, owner, order_ref, connection_ref,
  install_id, install_revision, provider)`;
- `ArgsDigest = basket_fingerprint`;
- `ExecutionID = we_`, `WorkItemID = wi_`, `PolicyRuleID = "glovo.order.owner-approval"`
  and `PolicyVersion = "1"`.

`intent_hash = IntentHash(...)`, so the existing hash covers every binding. #957 stores
that same hash on the bridge command, which `FenceBinding.IntentHash` checks.

### 4. Tx-aware store API (`internal/workitems/glovo_approvals.go`)

None of these methods begins, commits or rolls back a transaction:

```go
func (s *Store) CreateGlovoApprovalTx(ctx, tx pgx.Tx, in GlovoApprovalInput) (*ActionApprovalRequest, bool, error)
func (s *Store) LockGlovoApprovalTx(ctx, tx pgx.Tx, id string) (*ActionApprovalRequest, *GlovoBinding, error) // FOR UPDATE
func (s *Store) ReserveGlovoApprovalTx(ctx, tx pgx.Tx, id, intentHash, commandID string) (*ActionApprovalRequest, error)
func (s *Store) ConsumeGlovoApprovalTx(ctx, tx pgx.Tx, id, commandID string) (*ActionApprovalRequest, error)
func (s *Store) MarkGlovoApprovalUnknownTx(ctx, tx pgx.Tx, id, commandID string) error
```

- **Create** inserts the `aar_` row (`requested_by = "service:glovo-prepare"`,
  `subject_principal_id = owner`, `risk_level=high`, `side_effect=write`) and the binding
  row. It is idempotent on `(requested_by, idempotency_key)` exactly like
  `CreateActionApproval`. Because the requester is the server actor and never the owner,
  the existing `ErrApprovalSelfDecision` still holds for every other caller.
- **Reserve** runs one CAS:

  ```
  UPDATE action_approval_requests SET state='reserved', reserved_at=$now
  WHERE id=$1 AND state='approved' AND action_kind LIKE 'glovo.%'
    AND intent_hash=$2 AND expires_at > $now
    AND (fresh_until IS NULL OR fresh_until > $now)
  ```

  In the same tx it sets the binding's `command_id` (the trigger allows exactly one
  write). A refusal reads back and maps the state, reusing `ConsumeStateRefusal` plus
  the new `ErrApprovalReserved`.
- **Consume** runs a CAS `reserved -> consumed`, guarded by the binding's `command_id`
  and an unexpired state. It is called only by the fence.
- **MarkUnknown** runs a CAS `reserved -> unknown`, guarded by `command_id`.
- **Generic paths refuse Glovo kinds.** `ConsumeActionApproval`,
  `ReserveActionApproval`, `SettleActionApproval` and `MarkActionApprovalExecuted` add
  `AND action_kind NOT LIKE 'glovo.%'` to their CAS. On a miss they return the new
  `ErrApprovalKindNotSpendable`, which the HTTP layer maps to 409
  `approval_kind_not_spendable_here`. The agent receipt gate
  (`internal/api/agent_receipt_gate.go`) inherits the refusal.

### 5. Owner-decider limited to the Glovo kinds (`handlers_action_approvals.go`)

`DecideActionApproval` moves the `isHumanAdmin` check after the pre-read and branches
on the kind:

```go
if workitems.IsGlovoKind(cur.ActionKind) {
    if !h.isGlovoOwnerDecider(r, user, cur) { /* 403 or 404, audited */ }
} else if !isHumanAdmin(user) { /* unchanged 403 */ }
```

To keep the existing refusal order for every non-Glovo kind, a caller that is not an
admin gets the same 403 before any body parsing, unless the id belongs to a Glovo kind.
The pre-read reveals nothing, because a non-visible row answers 404 either way.

`isGlovoOwnerDecider` requires all of the following:

- `user.PrincipalID() != ""` and `!user.PrincipalUnresolved()`;
- `!user.IsService()`, `!user.IsAgent()`, `!user.IsCI()` and `!user.IsGlovoAudience()`,
  with no `ViaPrincipalID` and no surface. These are the same exclusions as
  `glovo.Gate.Authorize`, except that a Glovo-audience token is *refused*, so the facade
  and the model can never decide;
- `binding.OwnerPrincipalID == user.PrincipalID()`;
- `checkTenantRole(user, binding.Tenant, RoleDeveloper)` succeeds. Without any role on
  the tenant, the answer is 404 `approval_not_found` (no leak). A role that is too low
  gets 403;
- `glovo.Default.Open` and the Glovo approvals readiness are true. Otherwise the answer
  is 503 `not_ready`.

For a Glovo kind, the store decide runs as `DecideGlovoApprovalTx(ctx, tx, in)` on a
transaction opened on the shared (bridge) pool. It applies the same
`FOR UPDATE ... WHERE state='pending'` CAS as `DecideActionApproval`. In the same
transaction it calls #988's `Transition`: `finalized -> approved` on approve (the order
row's `approval_ref` must equal the `aar_` id) and `finalized -> cancelled` on refuse.
The order state is a projection of the decision, written atomically, and never a second
authority.

Admins get no override for Glovo kinds. A non-owner admin gets 403
`approval_decider_forbidden`. The binding gate, `guardDecision` and the store's
`FOR UPDATE ... WHERE state='pending'` stay unchanged, so concurrent approve and refuse
still yield exactly one winner. Read access (`canSeeActionApproval`) gains the same
owner rule for Glovo kinds only.

### 6. The fence (`internal/glovo/receipt/fence.go`)

`receipt.Fence` implements `bridge.WriteFence` with the collaborators
`Approvals` (the workitems store), `Orders` (#988 `LockOrder`), `Connections`
(#959/#960 `LockConnectionShared`) and `Membership` (live tenant role). Its
`Check(ctx, tx, b)` does the following, all on the bridge's `tx`:

1. `LockGlovoApprovalTx(b.ApprovalRef)`. A missing row or a non-Glovo kind is refused
   with `approval_not_found`.
2. It requires the stored state to be `reserved` and `binding.command_id == b.CommandID`
   (refused with `approval_not_reserved` or `approval_command_mismatch`).
3. It requires equality on `b.ExecutionID`, `b.WorkItemID`, `b.Tenant`,
   `b.OwnerPrincipalID`, `b.ConnectionRef`, `b.InstallRevision` and `b.IntentHash`
   (refused with `approval_binding_mismatch`). This covers an `aar_` from another `we_`
   or another intent.
4. It requires `expires_at` and `fresh_until` to lie in the future (refused with
   `approval_expired`).
5. It requires `Membership.IsMember(tenant, owner)` (refused with `owner_not_member`).
6. It takes `LockConnectionShared(connection_ref)` and requires the connection to be
   active with `install_revision` equal to the bound revision (refused with
   `connection_changed`). This is what makes a reconnect fail: the new `gcn_` or
   revision never equals the binding.
7. It takes `Orders.LockOrder(order_ref)` and requires `state == dispatched`, the
   order's `command_id == b.CommandID` and
   `final_basket_fingerprint == binding.basket_fingerprint` (refused with
   `fingerprint_changed`).
8. It calls `ConsumeGlovoApprovalTx` and returns
   `fenceRef = "afr_" + base32(sha256(aar_id|cmd_id|lease_epoch))[:26]`. The value is
   opaque: no token and no fingerprint.

Every refusal wraps `bridge.ErrWriteFenceRefused` with its code, so `permitTx` rolls the
whole transaction back. The lock order is approval, then connection, then order. #985's
dispatch transaction must take the same order (approval before order), which is
recorded as a cross-slice contract in tasks.

### 7. Recording the outcome: composition with `effect_state`

The bridge gains one optional interface in `permit.go`:

```go
// OutcomeRecorder is implemented by a fence that must observe a command ending
// without a permit. Called in the same tx as the command's terminal transition.
type OutcomeRecorder interface {
    CommandEndedWithoutPermit(ctx context.Context, tx pgx.Tx, b FenceBinding) error
}
```

`submitTx`, `Cancel` and `ExpireDue` call it (through a type assertion on
`currentFence()`) for a mutating command whose `effect_state` was not `permitted` when
it reached a terminal status. `receipt.Fence` implements it as
`MarkGlovoApprovalUnknownTx`. If that call errors, the bridge transaction rolls back,
which is fail-closed.

The resulting ownership of facts:

| Fact | Single source of truth |
|---|---|
| Human authorized this exact intent | `aar_` state `approved` (`decided_by_principal_id`) |
| Authorization bound to one command | `aar_` `reserved` + `glovo_approval_bindings.command_id` |
| Authorization spent | `aar_` `consumed` <=> `bridge_write_permits` row (same tx) |
| What the provider did | `bridge_commands.effect_state` only |
| Order progress | `glovo_orders.state` (#988) |

The joint states that are allowed:

| `aar_` | bridge `effect_state` | Meaning |
|---|---|---|
| pending / approved / refused / expired | no command | not dispatched |
| reserved | `none` | dispatched, permit not yet requested |
| consumed | `permitted` / `succeeded` / `failed` / `not_performed` / `unknown` | permit issued; the outcome is the bridge's |
| unknown | `none` / `not_performed` (terminal command) | reserved, command ended with no permit |

Any other pair is an invariant violation. Test T16 asserts the table, and
`receipt.Audit(ctx)` reports violations as a readiness failure.

### 8. Wiring and readiness

`cmd/api/main.go` calls `bridgeStore.SetFence(receipt.NewFence(...))` only when all of
the following hold: `glovo.Default.Open`, a non-nil work-items store, the bridge store,
#988's order store and #959's connection store, and #985's `ProveColocated` succeeding.
Otherwise the fence stays `refusingFence`, and the Glovo approval methods return
`glovo.CodeNotReady`. Because `Default` is a closed build constant, nothing changes in
production behaviour when this merges.

### 9. Secrecy

- Audit entries (`auditActionApproval`) for Glovo kinds add only `order_ref`,
  `command_id` and the receipt state. `target` (which contains the length-prefixed
  refs) is already logged today. The fingerprint is never added. The `Target` string
  holds refs only, never the fingerprint, which goes only into `args_digest`.
  `auditActionApproval` must therefore omit `args_digest` for Glovo kinds (a
  low-entropy basket could be brute-forced, as #988 notes).
- The fence and the store log only codes and ids. `fenceRef` is a hash of ids.
- This slice adds no Temporal input or signal. The cross-slice contract with #957/#985
  is that `GlovoControlInput` carries `approval_ref` (an id, not a bearer token) and
  never the fingerprint. Test T17 scans the inputs built by the #957 helper when it is
  present, and is skipped with a recorded reason otherwise.

## Alternatives

1. **A separate `glovo_receipts` table with its own state machine, linked to the
   `aar_`.** Dropped: it creates two authorities (the `aar_` state and the receipt
   state) that can disagree, which is exactly what the issue forbids, and #954 point 2
   asks for one.
2. **Consume at #985 dispatch (`ConsumeApprovalTx`, as the #985 draft has it) and let the
   fence only re-check.** Dropped: a consumed receipt would then precede the permit by
   an arbitrary queue delay, during which revocation, reconnect or a fingerprint change
   are checked only by a read. Making the fence the consume point puts every check and
   the single-use spend inside the one permit transaction that `bridge_write_permits`
   already fences (`permit.go` comment: "single canonical reserve/consume/record-outcome
   fence"). #985 reserves instead, which still prevents one `aar_` from reaching two
   commands. This changes #985's `Approvals` interface. See tasks for the cross-slice
   note.
3. **Mirror the provider outcome onto the `aar_` (`consumed` = applied, `unknown` =
   provider unknown).** Dropped: it duplicates `effect_state`, and the two could diverge
   after a cancel (`permitted -> unknown`) that does not touch the `aar_`. Recorded as an
   open question for the reviewer.
4. **Reuse the generic `in_flight` reservation for Glovo.** Dropped: `SettleActionApproval`
   with `succeeded=false` returns the receipt to `consumed`, so it can be used again.

## Platform impact

- **Migrations:** additive.
  - `action_approval_requests` gets the widened state CHECK (adding `reserved` and
    `unknown`) with the replace-once pattern, plus a new kind/state CHECK. Both hold
    trivially for existing rows, which have no `glovo.%` kind.
  - New table `glovo_approval_bindings`, with its trigger and partial unique index.
  - No backfill. Restart is idempotent.
- **Backward compatibility:** non-Glovo kinds keep their exact decision, consume,
  reserve and settle behaviour. The generic CAS statements gain one extra predicate
  that is always true for them. The decide handler's refusal order for non-admins on
  non-Glovo ids is unchanged. One pre-read happens before the 403, and it answers 404
  for an unknown id exactly as before.
- **Bridge:** one optional interface, plus three call sites in `store.go`. When the fence
  is `refusingFence`, the type assertion fails and nothing changes.
- **Resources:** one extra row per Glovo order and a few indexed lookups per permit.
  Negligible.
- **Risks and mitigations:**
  - Lock-order deadlock between dispatch and fence. Mitigation: a documented lock order
    (approval, then connection, then order) that #985 also follows, plus a race test.
  - Cross-database transaction. Mitigation: the fence is installed only after #985's
    `ProveColocated`. Otherwise it stays `not_ready`.
  - Admins lose the ability to decide Glovo kinds. This is intended and documented.
  - Sibling slices are not merged. This slice codes against interfaces, keeps nil
    collaborators `not_ready`, and runs the fence integration tests with in-package
    fakes of `Orders` and `Connections` until #988 and #959 land.
