# Design: issue-989-feat-glovo-m1b-2-single-authoritative-aa

## Amendment 2026-11-09 (b)

Resolves the independent review of digest
`sha256:d394d3d2649fd24c7cc63f2369b70caa3740a15d68ad0c0e9704e92597d722c8`
(mctl-api#989 comment 6745421687: 1 P1, 6 P2, 6 P3) and applies owner decision A (one
physical database) of 2026-11-09 (b). Every cited line was re-checked at mctl-api
`ceac9ed`. The good core is kept: one `aar_` row, spent inside the bridge permit
transaction, the provider outcome only in `effect_state`, and the generic reuse path
closed for Glovo. This proposal was rewritten; no older passage that contradicts this
section survives.

| Review finding | Fix in this proposal |
|---|---|
| P1 the fence compares two values mctl-api wrote itself; a command with the approved `intent_hash` and another payload gets a permit | The fence recomputes from what is written. Under the command lock it reads `bridge_commands.payload`, extracts the #1059 **approval basket**, validates it (sort, uniqueness, arithmetic) and computes `basket_fingerprint`. It then recomputes the intent hash with `GlovoIntent` from the command row's own fields and that fingerprint. Both must equal the `aar_` binding, and the command's stored `intent_hash` must equal the recomputed one. Caller-supplied hashes are never trusted (§6). The provider contract (mctl-telegram#1262) is: write exactly the command payload's lines, never a re-read basket (OPEN-989-4). T10 uses a real command whose payload differs from the approved basket while carrying the approved `intent_hash` |
| P2-2 state machine only in Go; DDL runtime-owned; no `ApplySchema` exists (`workitems/store.go:243`) | `glovo.aar_guard()` (`BEFORE UPDATE OR DELETE` on `action_approval_requests`) allows only `pending→approved|denied`, `approved→reserved|denied`, `reserved→consumed|unknown`; `consumed`, `unknown` and `denied` are final; identity columns are immutable; `DELETE` is refused; no row can move into or out of a Glovo kind. A deferred constraint trigger requires one binding row per Glovo `aar_`. `glovo.approval_bindings` has `UNIQUE (order_ref)`. All of it is created by a new `workitems.ApplyGlovoApprovalSchema` under the migration role; the runtime role gets DML only (column-level `UPDATE (command_id)` on bindings, no `DELETE`, no `TRIGGER`). The ownership of `action_approval_requests` must move to the migration role (OPEN-989-1); until it does, Glovo is `not_ready` (§2) |
| P2-3 no single lock order; the permit already holds the command lock | One global order L1..L6, written once in #957 design §6b. `receipt.Fence.PreLock` runs before `lockOwned` and takes L1 sh, L2 sh, L3, L4; the permit then takes L5. Decide takes L4 only. The in-tx `OutcomeRecorder` is dropped (it would have taken L4 after L5); a sweeper and #985 cancel record `unknown` instead (§6, §7). Deadlock tests T21 |
| P2-4 order `approved` state is a second authority | Dropped. The decision writes only the `aar_`. `CreateGlovoApprovalTx` calls #988 `BindApproval` in the same transaction. A refusal does not cancel the order; the owner cancels through #957, and #985 then calls `RevokeGlovoApprovalTx` (§4, §5) |
| P2-5 owner decision recorded as `platform_admin`; policy unregistered; context incomplete | `governance.AuthorityBasisResourceOwner = "resource_owner"`, recorded for Glovo kinds. The rule `glovo.order.owner-approval` v1 is registered in `governance.Policies`. `CreateGlovoApprovalTx` writes a complete context (`intent_source = execution:<we_>`, `policy_decision`, `policy_reasons`), so the start-up backfill never touches it. T19 runs strict mode (§5) |
| P2-6 readiness ignores D2 and decision A | `GLOVO_DB_URL`, `COMMERCE_DB_URL` and `WORK_ITEMS_DB_URL` set explicitly, no fallback; #985 `ProveOneDatabase` passes; schema version, triggers enabled and table owners checked; policy registered; every collaborator non-nil. Otherwise no `SetFence` and every Glovo approval method answers `not_ready`. The connection read is #959 `LiveConnectionTx` under L2; `LockConnectionShared` is gone (§8) |
| P2-7 contract gaps with #957/#1044 | `GlovoControlInput` carries `approval_ref` **and** the fingerprint, as the merged #957 §6c and #1044 M10 say (§9). New: `GlovoApprovalStatus` for the control worker's `read_approval`, `RevokeGlovoApprovalTx`, an idempotent `ReserveGlovoApprovalTx` that also checks the binding against the command fields, and one refusal table to the seven M10 reasons and #957 §4 (§10) |
| P3 generic create can mint Glovo kinds; `IsGlovoKind` vs `LIKE` | The generic create refuses any `glovo.` kind. One predicate: a DB `CHECK` that a `glovo.`-prefixed kind is one of the exact list, so `LIKE 'glovo.%'` and `IsGlovoKind` agree (§1) |
| P3 invariant table misses `unknown` + effect `unknown` | Added (§7) |
| P3 expired vs `MarkUnknown` | `unknown` wins for forensics: a stored `reserved` row past `expires_at` can only become `unknown`, never `consumed`. `expired` is a reading of `pending`, `approved` or `reserved` only (§1) |
| P3 admins skip the live role check | For Glovo kinds the decider's membership is read directly from the tenant membership table, with no admin pass (§5) |
| P3 refusal oracle | Every non-admin caller who cannot decide gets the same 403 `approval_decider_forbidden`, whether the id is unknown, non-Glovo or someone else's (§5) |
| P3 factual errors | `glovo.Default` is a `var` (`gate.go:24`); `install_revision` is `TEXT` holding the canonical decimal, compared byte for byte with `FenceBinding.InstallRevision`; `SetFence` is `store.go:418`; the decide route keeps its existing `writeErrorCode` body; owner decision C1's `{"error","error_description"}` applies to the #957/#985 Glovo routes |

Skipped findings: none.

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
  `ExpireDue` expires commands. `SetFence` (`store.go:418`) installs the fence, and
  `Pool()` (`store.go:414`) exposes the pool. The command row stores `tenant` (name),
  `owner_principal_id`, `order_ref` (`ordr_`), `connection_ref` (`gcn_`),
  `install_revision`, `approval_ref` (`aar_`) and `intent_hash`.
- `FenceBinding` carries no basket fingerprint, and `InstallRevision` is a string
  (`permit.go:36`, `bridge_commands.install_revision TEXT`). The command's
  `intent_hash` is supplied by the caller at `Enqueue` (`store.go:218-222`), and nothing
  recomputes it from the stored `payload` (`store.go:86-92`).
- Schema: `workitems.NewStore` runs `actionApprovalSchema` on the runtime pool at every
  start (`internal/workitems/store.go:243`). There is no `ApplySchema` anywhere in
  mctl-api at `ceac9ed`; the runtime role owns `action_approval_requests`.
- Governance: `guardDecision` admits the rule through `approvalPolicies().Admit(…,
  RequireRegisteredPolicy)` (`handlers_approval_governance.go:96`) and requires a
  complete context (`governance.go:248-266`). `decisionCapture` records
  `AuthorityBasisPlatformAdmin` for every approve (`:119-126`). The start-up backfill
  (`action_approvals.go:192-205`) fills a missing `intent_source`.
- `checkTenantRole` lets every admin through `roleGate` (`tenant_role.go:157-160`).
- `CreateActionApproval` (`handlers_action_approvals.go:393`) accepts any kind from a
  direct service or a bound agent (`isApprovalRequester`, `:126-129`).

### Glovo gate and wiring

- `internal/glovo/gate.go:24`: `var Default = Gate{Open: false}`. It is a package `var`
  (its comment calls it a build constant); nothing in this slice sets it.
  `errors.go`: codes `not_ready` and `not_authorized`.
- `cmd/api/main.go`: the work items use `WORK_ITEMS_DB_URL`, falling back to
  `AUDIT_DB_URL` (`workItemsStoreSource`, line 2769). The bridge uses `COMMERCE_DB_URL`,
  falling back to `AUDIT_DB_URL` (lines 1019-1021), and is gated by
  `MCTL_BRIDGE_ENABLED`. Nothing calls `SetFence` today.

### Sibling proposals (amended in this same PR)

- #988: no `approved` order state; `BindApproval(tx, …)` sets a write-once
  `approval_ref`; `LockOrderForControl` (L3); `final_basket_fingerprint` over the #1059
  approval basket.
- #985: dispatch and cancel; `WriteFence.PreLock`; `control.ProveOneDatabase`; the
  `Receipts` interface this slice implements (#985 design §3); single `SetFence`
  installer (#985 task 9).
- #957 §6b: one physical database (owner decision A) and the canonical lock order
  L1..L6.
- #959: `LockOwnerShared`, `LiveConnectionTx`, revokers that cancel open commands.
- mctl-agents#1059: `approval-basket.schema.json` and the single fingerprint.

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
- The deployed values of `COMMERCE_DB_URL`, `WORK_ITEMS_DB_URL`, `GLOVO_DB_URL` and
  `MCTL_BRIDGE_ENABLED` for mctl-api were **not observed**. The design requires all
  three URLs to be set explicitly and #985's `ProveOneDatabase` to pass (§8).

## Proposed solution

### 1. One row, one state column

The authoritative object is the existing `action_approval_requests` row. Glovo adds:

- **Action kinds** `glovo.place_order_fake` and `glovo.cancel_order_fake`
  (`workitems.GlovoActionKinds`, `IsGlovoKind`). One predicate everywhere: the CHECK
  `action_approval_requests_glovo_kind_chk`
  `action_kind NOT LIKE 'glovo.%' OR action_kind IN ('glovo.place_order_fake','glovo.cancel_order_fake')`
  makes `LIKE 'glovo.%'` and the exact list equivalent. Go uses the SQL constant
  `glovoKindPredicate` for every query.
- **Two stored states**, `reserved` and `unknown`, added to the state CHECK.
  `action_approval_requests_glovo_states_chk` keeps `reserved`/`unknown` Glovo-only and
  `in_flight`/`executed` non-Glovo.
- **Expiry.** `expired` is never stored. `GlovoReceiptState(a)` reads a `pending`,
  `approved` or `reserved` row past `expires_at` (or past `fresh_until`) as `expired`.
  `consumed`, `unknown` and `denied` are final and are never read as `expired`. A
  `reserved` row past expiry can only move to `unknown` (forensics), never to
  `consumed`: the fence refuses it.
- **Exposed vocabulary:** `pending`, `approved`, `reserved`, `consumed`, `unknown`,
  `refused` (stored `denied`), `expired` (derived).

### 2. Database enforcement, under the migration role

`workitems.ApplyGlovoApprovalSchema(ctx, migrationPool)` is the only path that creates
the objects below. It runs under the migration role, is idempotent (`CREATE … IF NOT
EXISTS`, `CREATE OR REPLACE FUNCTION`, triggers created only if absent in `pg_trigger`),
refuses a stored schema version newer than the code, and refuses if an object exists
but is owned by another role.

```sql
CREATE TABLE IF NOT EXISTS glovo.approval_bindings (
  approval_id        TEXT PRIMARY KEY REFERENCES public.action_approval_requests (id),
  tenant             TEXT NOT NULL,
  owner_principal_id TEXT NOT NULL CHECK (owner_principal_id LIKE 'prn\_%'),
  execution_id       TEXT NOT NULL,
  work_item_id       TEXT NOT NULL,
  order_ref          TEXT NOT NULL UNIQUE CHECK (order_ref ~ '^ordr_[A-Za-z0-9]{16,40}$'),
  connection_ref     TEXT NOT NULL CHECK (connection_ref ~ '^gcn_[A-Za-z0-9]{16,40}$'),
  install_id         TEXT NOT NULL,
  install_revision   TEXT NOT NULL CHECK (install_revision ~ '^[1-9][0-9]{0,18}$'),
  basket_fingerprint TEXT NOT NULL CHECK (basket_fingerprint ~ '^sha256:[0-9a-f]{64}$'),
  provider           TEXT NOT NULL,
  command_id         TEXT NOT NULL DEFAULT '',
  created_at         TIMESTAMPTZ NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS approval_bindings_command
  ON glovo.approval_bindings (command_id) WHERE command_id <> '';
```

- `UNIQUE (order_ref)`: one `aar_` per order (M10). #988's write-once `approval_ref` is
  the other side of the same link.
- `install_revision` holds the canonical decimal string of the #959 revision and is
  compared byte for byte with `FenceBinding.InstallRevision`.
- `glovo.approval_bindings_guard()` (`BEFORE UPDATE OR DELETE`): refuses every change
  except `command_id` from `''` to a `cmd_` value, and refuses `DELETE`.
- `glovo.aar_guard()` (`BEFORE UPDATE OR DELETE` on `action_approval_requests`):
  - a row whose `OLD.action_kind` or `NEW.action_kind` is a Glovo kind may not change
    `action_kind`, `intent_hash`, `expires_at`, `execution_id`, `work_item_id`,
    `subject_principal_id`, `requested_by` or `policy_rule_id`/`policy_version`;
  - its state may move only `pending→approved`, `pending→denied`, `approved→reserved`,
    `approved→denied` (revoke before dispatch), `reserved→consumed`,
    `reserved→unknown`; `consumed`, `unknown` and `denied` are final;
  - `DELETE` of a Glovo row is refused.
- `glovo.aar_binding_required()`: a `CONSTRAINT TRIGGER … DEFERRABLE INITIALLY
  DEFERRED` `AFTER INSERT` on `action_approval_requests`. A Glovo-kind row must have its
  binding row by commit.
- The widened state CHECK and the kind CHECK are added here too (guarded, `NOT VALID`
  then `VALIDATE`), not in the runtime `actionApprovalSchema`.
- Grants to the runtime role: `SELECT, INSERT` on `glovo.approval_bindings`, `UPDATE
  (command_id)` only, no `DELETE`, `TRUNCATE` or `TRIGGER`; `EXECUTE` on no function.
- **Ownership of `action_approval_requests`.** A trigger on a table owned by the
  runtime role can be disabled by that role. The table must therefore be owned by the
  migration role, and `actionApprovalSchema` must stop running DDL on the runtime pool
  for it (`workitems/store.go:243`). Because that changes the generic work-items
  startup, it is an owner decision (OPEN-989-1). This slice plans it as task 2b: move
  the generic DDL into `workitems.ApplySchema` under the migration role, and have
  `NewStore` only verify the schema version when the table is not owned by
  `current_user`. Until the move happens, Glovo `Ready` fails and every Glovo approval
  method answers `not_ready`; generic work items are unchanged.
- `Ready` checks: schema version; both guard triggers and the constraint trigger exist
  with `tgenabled = 'O'`; `relowner` of `action_approval_requests` and
  `glovo.approval_bindings` is not `current_user`.

### 3. Intent hash

`GlovoIntent(b Binding, kind) workitems.ActionIntent` sets:
- `Target = "glovo:v1:" + len-prefixed(tenant, owner, order_ref, connection_ref,
  install_id, install_revision, provider)`;
- `ArgsDigest = basket_fingerprint` (the #1059 approval-basket fingerprint);
- `ExecutionID = we_`, `WorkItemID = wi_`, `PolicyRuleID = "glovo.order.owner-approval"`,
  `PolicyVersion = "1"`.

`intent_hash = IntentHash(...)`. The fence recomputes it from the command row (§6), so a
caller-supplied hash is only ever compared.

### 4. Tx-aware store API (`internal/workitems/glovo_approvals.go`)

None of these methods begins, commits or rolls back a transaction. The names match the
`Receipts` interface in #985 design §3.

```go
func (s *Store) CreateGlovoApprovalTx(ctx, tx pgx.Tx, in GlovoApprovalInput) (*ActionApprovalRequest, bool, error)
func (s *Store) LockGlovoApprovalTx(ctx, tx pgx.Tx, id string) (*ActionApprovalRequest, *GlovoBinding, error) // L4
func (s *Store) ReserveGlovoApprovalTx(ctx, tx pgx.Tx, id string, cmd ReserveCommand) (replayed bool, err error)
func (s *Store) ConsumeGlovoApprovalTx(ctx, tx pgx.Tx, id, commandID string) error      // fence only
func (s *Store) RevokeGlovoApprovalTx(ctx, tx pgx.Tx, id, actor string) error
func (s *Store) MarkGlovoApprovalUnknownTx(ctx, tx pgx.Tx, id, commandID string) error
func (s *Store) DecideGlovoApprovalTx(ctx, tx pgx.Tx, in ActionDecisionInput) (*ActionApprovalRequest, error)
func (s *Store) GlovoApprovalStatus(ctx, tenants []string, id string) (*GlovoApprovalStatus, error)
```

- **Create** (called by #957 prepare, which already holds L3 on the order): inserts the
  `aar_` row and the binding, and calls #988 `BindApproval(tx, order_ref, aar_)` in the
  same transaction. `requested_by = "service:glovo-prepare"`, `subject_principal_id =
  owner`, `risk_level = high`, `side_effect = write`, and a complete governance
  context: `intent_source = "execution:" + we_`, `policy_rule_id`/`policy_version` of
  §3, `policy_decision = "require_approval"`, `policy_reasons =
  ["glovo.order.owner-approval"]`. Idempotent on `(requested_by, idempotency_key)`. A
  second `aar_` for the same order hits `UNIQUE (order_ref)` and is `approval_replayed`.
- **Reserve** (#985 dispatch, under L3+L4): `cmd` carries `CommandID`, `Tenant`,
  `OwnerPrincipalID`, `ExecutionID`, `OrderRef`, `ConnectionRef`, `InstallRevision`,
  `IntentHash` and `BasketFingerprint`. Each must equal the binding (else
  `intent_mismatch`, or `basket_changed` for the fingerprint). If the row is already
  `reserved` with `command_id == cmd.CommandID`, it returns `replayed = true` and
  changes nothing (crash-retry). Otherwise one CAS `approved → reserved` (unexpired,
  Glovo kind) and the binding's `command_id` write, in the same transaction.
- **Consume** (fence only): CAS `reserved → consumed` guarded by `command_id` and
  `expires_at > now()`.
- **Revoke** (#985 cancel before dispatch): CAS `pending|approved → denied`, recording
  the actor and reason `order_cancelled`. Exposed as `refused`.
- **MarkUnknown**: CAS `reserved → unknown` guarded by `command_id`; allowed past expiry.
- **Decide**: `FOR UPDATE … WHERE state='pending'` on the `aar_` only (L4). It writes no
  order row.
- **GlovoApprovalStatus** (tx-free, for the #985 `read_approval` route): returns
  `approval_ref`, exposed state, `expires_at`, `order_ref` and `command_id` (ids and
  enums only). Missing, non-Glovo or outside `tenants` is one `not_found`.
- **Generic paths refuse Glovo kinds.** `CreateActionApproval` refuses any `glovo.`
  kind with 400 `approval_kind_not_creatable_here`. `ConsumeActionApproval`,
  `ReserveActionApproval`, `SettleActionApproval` and `MarkActionApprovalExecuted` add
  `AND NOT (glovoKindPredicate)` to their CAS and return `ErrApprovalKindNotSpendable`
  (409 `approval_kind_not_spendable_here`) on a Glovo row. The trigger backs this up.

### 5. Owner decision (`handlers_action_approvals.go`)

`DecideActionApproval` gains one branch before the admin check:
1. Non-admin caller: pre-read the row. If it is a Glovo kind and every check below
   passes, continue. Otherwise answer the same 403 `approval_decider_forbidden` that a
   non-admin gets today, whether the id is unknown, non-Glovo, someone else's or
   undecidable. No oracle.
2. Admin caller on a Glovo kind: the same checks; an admin who is not the owner gets
   403 `approval_decider_forbidden`. Admin on a non-Glovo kind: unchanged.

`isGlovoOwnerDecider` requires:
- a resolved principal; not a service, agent, CI, relayed or surface caller; not a
  Glovo-audience token (the facade and the model never decide);
- `binding.owner_principal_id == user.PrincipalID()`;
- live membership read **directly** from the tenant membership table for
  `binding.tenant` with at least the minimum role (proposed `developer`, OPEN-989-3).
  Admins get no pass here;
- `glovo.Default.Open` and Glovo approvals readiness (§8), else 503 `not_ready`.

Governance:
- `governance.AuthorityBasisResourceOwner = "resource_owner"`. `decisionCapture`
  records it for Glovo kinds, and `platform_admin` stays for every other kind.
- `governance.Policies` registers `glovo.order.owner-approval` version `1`, so
  `Admit(…, RequireRegisteredPolicy)` passes in strict mode.
- `guardDecision` and the binding gate run unchanged. The context is complete from
  create, so the start-up backfill does not rewrite Glovo rows.

The decision runs as `DecideGlovoApprovalTx` on a transaction from the bridge pool (one
database). It touches only the `aar_`. The route keeps its existing `writeErrorCode`
body; owner decision C1 applies to the #957/#985 Glovo routes, not this one. Read
access (`canSeeActionApproval`) gains the same owner rule for Glovo kinds only.

### 6. The fence (`internal/glovo/receipt/fence.go`)

`receipt.Fence` implements `bridge.WriteFence`, including the `PreLock` hook that #985
adds to `permitTx`. Collaborators: `Approvals` (this store), `Orders` (#988), `Conns`
(#959 `LockOwnerShared`, `LiveConnectionTx`) and `Membership` (direct read). The lock
levels are the canonical ones of #957 design §6b.

`PreLock(ctx, tx, commandID)`, before `lockOwned`:
1. Read, without a lock, the command's immutable binding columns: `tenant`,
   `owner_principal_id`, `order_ref`, `approval_ref`.
2. `Conns.LockOwnerShared(tenant, owner)`: L1 shared, L2 shared.
3. `Orders.LockOrderForControl(order_ref)`: L3.
4. `Approvals.LockGlovoApprovalTx(approval_ref)`: L4.

`permitTx` then takes L5 (`lockOwned`) and calls `Check(ctx, tx, b)`:
1. Re-read the command row (now locked). Its `tenant`, `owner_principal_id`,
   `order_ref` and `approval_ref` must equal what `PreLock` read; they are immutable
   after `Enqueue`, so a difference is an invariant violation.
2. The `aar_` is a Glovo kind in stored state `reserved` with `binding.command_id ==
   b.CommandID`. Otherwise `approval_invalid`, or `approval_replayed` when it is bound
   to another command.
3. `expires_at` and `fresh_until` are in the future, else `approval_expired`.
4. **Recompute from the written content.** Read `bridge_commands.payload` from the
   locked row, extract `approval_basket`, run `basket.Validate` (the #1059 rules: sorted
   unique `item_code`, arithmetic) and compute `fp = basket.Fingerprint(…)`. `fp` must
   equal `binding.basket_fingerprint` and the order's `final_basket_fingerprint`, else
   `basket_changed`. A payload without a valid approval basket is `basket_changed`.
5. Recompute `ih = IntentHash(GlovoIntent(binding fields from the command row, fp))`.
   `ih` must equal the `aar_` `intent_hash` and `b.IntentHash`, else `intent_mismatch`.
   The same check covers `b.ExecutionID`, `b.WorkItemID`, `b.Tenant`,
   `b.OwnerPrincipalID`, `b.ConnectionRef` and `b.InstallRevision`.
6. `Membership`: the owner is still a member of the tenant, else `no_tenant`.
7. `Conns.LiveConnectionTx(owner)`: active, same `gcn_`, same install revision (decimal
   string). Else `no_connection`, `connection_revoked`, `connection_expired` or
   `stale_install`.
8. The order is `dispatched` with `command_id == b.CommandID`, else `invalid_transition`.
9. `ConsumeGlovoApprovalTx`, then return `fenceRef = "afr_" +
   base32(sha256(aar_id|cmd_id|lease_epoch))[:26]`.

Every refusal wraps `bridge.ErrWriteFenceRefused` with its code, and `permitTx` rolls
back. JSONB in `bridge_commands.payload` keeps no duplicate keys and no key order, and
RFC 8785 canonicalizes the parsed value, so recomputing from JSONB is deterministic. The
#1059 number rules (integers only, within ±(2^53-1)) are checked by `basket.Validate`.

The command payload must carry the approval basket. The v1alpha1 `place_order_fake`
payload is `{item_codes, quantity_total, note}`, so this depends on OPEN-985-8
(= mctl-agents OPEN-1059-1). Until that contract exists, `Ready` fails.

### 7. Recording an outcome without a permit

The in-transaction `OutcomeRecorder` of the earlier draft is dropped: it would lock L4
after L5 inside `submitTx`, `Cancel` and `ExpireDue`, which inverts the global order.
Instead:
- #985 cancel holds L3, L4 and L5. When the cancelled command had no permit, it calls
  `MarkGlovoApprovalUnknownTx` itself.
- `receipt.Sweeper`, in the bridge `Expirer` tick: `SELECT … FROM
  action_approval_requests WHERE state='reserved' AND glovoKindPredicate FOR UPDATE SKIP
  LOCKED LIMIT 100` (L4 only), then a plain read of the bound command. A command that
  is terminal (`completed`, `expired`, `cancelled`) with no permit row moves the `aar_`
  to `unknown`. A terminal command never changes again, so the unlocked read is safe.

| Fact | Single source of truth |
|---|---|
| Human authorized this exact intent | `aar_` `approved` (`decided_by_principal_id`, `authority_basis = resource_owner`) |
| Authorization bound to one command | `aar_` `reserved` + `glovo.approval_bindings.command_id` |
| Authorization spent | `aar_` `consumed` <=> `bridge_write_permits` row (same tx) |
| What the provider did | `bridge_commands.effect_state` only |
| Order progress | #988 order state |

| `aar_` | bridge `effect_state` | Meaning |
|---|---|---|
| pending / approved / refused / expired | no command | not dispatched |
| reserved | `none` | dispatched, permit not yet requested |
| consumed | `permitted` / `succeeded` / `failed` / `not_performed` / `unknown` | permit issued; the outcome is the bridge's |
| unknown | `none` / `not_performed` | command ended without a permit |
| unknown | `unknown` | the provider reported `unknown` without a permit (`effectFor`, `store.go:716-722`) |

Any other pair is an invariant violation. T16 asserts the table, and `receipt.Audit`
reports violations as a readiness failure.

### 8. Wiring and readiness

`receipt.Ready()` is nil only when all of the following hold:
- `GLOVO_DB_URL`, `COMMERCE_DB_URL` and `WORK_ITEMS_DB_URL` are each set explicitly, with
  no `AUDIT_DB_URL` fallback;
- #985 `control.ProveOneDatabase` passed (one physical database, owner decision A);
- `ApplyGlovoApprovalSchema`'s version matches, the triggers are enabled and the table
  owners are not the runtime role (§2);
- `glovo.order.owner-approval` v1 is registered;
- the work-items, bridge, #988 order and #959 connection stores are non-nil;
- the #1059 approval basket is vendored and the write payload contract exists
  (OPEN-985-8).

Only #985 task 9 calls `bridgeStore.SetFence(receipt.NewFence(...))`, and only when
`receipt.Ready()` is nil and `glovo.Default.Open` is true. Otherwise the fence stays
`refusingFence` and every Glovo approval method returns `glovo.CodeNotReady`.
`glovo.Default` is a closed package `var`, and nothing in this slice opens it.

### 9. Secrecy

- Audit entries for Glovo kinds add `order_ref`, `command_id` and the receipt state, and
  omit `args_digest`.
- The fence and the store log only codes and ids. `fenceRef` is a hash of ids.
- `GlovoControlInput` carries `approval_ref` and the basket fingerprint, as the merged
  #957 §6c and #1044 M10 specify; dispatch compares the fingerprint and answers
  `basket_changed`. The fingerprint is a digest of a low-entropy fake basket; keeping it
  in Temporal input was accepted by the merged contracts (recorded as OPEN-989-5).
- No Temporal input or signal is added by this slice.

### 10. Refusal map

| Internal condition | #1044 M10 reason | #957 §4 / #985 wire |
|---|---|---|
| `aar_` missing, not a Glovo kind, or outside `tenants` (control read) | — | 404 `not_found` |
| state `pending`, `refused` or `unknown`; or `consumed`/`reserved` without this command at the fence | `approval_invalid` | 409 `approval_invalid` |
| reserved or consumed for another `cmd_`; a second `aar_` for the order | `approval_replayed` | 409 `approval_replayed` |
| past `expires_at` or `fresh_until` | `approval_expired` | 409 `approval_expired` |
| binding differs (tenant, owner, `we_`, order, connection, install revision) or recomputed intent hash differs | `intent_mismatch` | 409 `intent_mismatch` |
| fingerprint differs (body, order, or recomputed from the payload) | `basket_changed` | 409 `basket_changed` |
| lock contention beyond the retry budget | `tenant_busy` | 409 `tenant_busy` |
| not configured, proof failed, gate closed | `provider_disabled` | 503 `not_ready` |
| owner no longer a member | terminal | 403 `no_tenant` |
| connection absent / revoked / expired; revision moved | terminal | `no_connection` / `connection_revoked` / `connection_expired` / `stale_install` |
| I/O error | retryable | 503 `unavailable` |
| generic `aar_` route used on a Glovo row | — | 409 `approval_kind_not_spendable_here` (generic routes only) |

## Alternatives

1. **A separate `glovo_receipts` table with its own state machine.** Dropped: two
   authorities that can disagree.
2. **Consume at #985 dispatch.** Dropped: the spend would precede the permit by an
   arbitrary delay. The fence is the consume point; #985 reserves.
3. **Mirror the provider outcome onto the `aar_`.** Dropped: it duplicates
   `effect_state`.
4. **Reuse the generic `in_flight` reservation.** Dropped: a failed settle re-arms it.
5. **Compare only mctl-api-written fingerprints at the fence.** Dropped (review P1): it
   never checks what is written.
6. **An in-transaction `OutcomeRecorder` in the bridge.** Dropped (review P2-3): it locks
   L4 after L5.
7. **An order `approved` state written by the decision.** Dropped (review P2-4).

## Platform impact

- **Migrations:** additive, only through `ApplyGlovoApprovalSchema` under the migration
  role: the bindings table, three triggers, two CHECKs and the widened state CHECK. No
  backfill. The ownership move of `action_approval_requests` is OPEN-989-1.
- **Backward compatibility:** non-Glovo kinds keep their decision, consume, reserve and
  settle behaviour; the generic CAS statements gain one predicate that is always true
  for them. A non-admin on a non-Glovo id still gets the same 403.
- **Bridge:** no new interface beyond #985's `PreLock`. No call sites added to
  `submitTx`, `Cancel` or `ExpireDue`.
- **Resources:** one binding row per order, a few indexed lookups per permit, one
  bounded sweep per `Expirer` tick.
- **Risks:**
  - Deadlocks: one global order (#957 §6b), deterministic tests T21.
  - Trigger bypass by the table owner: Glovo stays `not_ready` until the owner move
    (OPEN-989-1).
  - Admins lose the ability to decide Glovo kinds: intended.
  - Sibling slices not merged: interfaces only, nil collaborators keep `not_ready`.
