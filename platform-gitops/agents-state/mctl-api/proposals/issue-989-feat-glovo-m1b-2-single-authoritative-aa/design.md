# Design: issue-989-feat-glovo-m1b-2-single-authoritative-aa

## Amendment 2026-11-09 (c), round 4 of the AMEND PR

Resolves the round-3 findings F1 and F2 and the cross-slice finding X-2. Where this section and older text disagree, this section wins.

| Finding | Change here |
|---|---|
| F1 (a Glovo `aar_` has an empty `artifact_hash`, so the decision binding gate can never pass) | §3 and §4: `CreateGlovoApprovalTx` sets `artifact_hash` to the basket fingerprint (`sha256:<hex>`), which is also the `ArgsDigest` of `GlovoIntent`, so it is bound to the order. The INSERT guard requires it to match `^sha256:[0-9a-f]{64}$`, the deferred `aar_binding_required` trigger requires it to equal `binding.basket_fingerprint`, and `aar_guard` adds `artifact_hash` to the immutable columns. The `GET` of the `aar_` therefore returns a non-empty `artifact_hash`, and a binding copied from it has `content_digest == artifact_hash`. §5: under `MCTL_APPROVAL_BINDING=enforce`, `missingFields` and `guardDecision` pass for a complete binding and give `context_changed` for a stale `content_digest`. T15 (immutable subtest), T19 (both enforce cases) |
| F2 (`GlovoApprovalInput` undefined; no source for the expiry or freshness window) | §4: `GlovoApprovalInput{Tenant, OwnerPrincipalID, WorkItemID, ExecutionID, OrderRef, ConnectionRef, InstallID, InstallRevision, BasketFingerprint, Provider string; ExpiresIn time.Duration}` defined once. The TTL is chosen by #957 prepare (the named constant `GlovoApprovalTTL`, at most `MaxApprovalTTL`, OPEN-957-10) and passed as `ExpiresIn`; SQL stores `expires_at = clock_timestamp() + ExpiresIn` and the same stored value is the prepare response `expires_at` and the bound of #1044's approval wait. `ExpiresIn <= 0` or `> MaxApprovalTTL` is `invalid_request`. Freshness: `fresh_until` (set by `decisionCapture` as decision time plus `maxDecisionAge`) is checked in the Reserve CAS with a margin (`ReservePermitMargin`, OPEN-989-7) and again by the fence (§6 step 3); T7b |
| X-2 (`ApplyGlovoApprovalSchema` signature) | `workitems.ApplyGlovoApprovalSchema(ctx, migrationConnStr, runtimeRole string) error`, the shape of every `ApplySchema` (#957 §6d.4); it needs `runtimeRole` for the `aar_guard` literal and the grants, and runs `workitems.ApplySchema(ctx, migrationConnStr, runtimeRole)` (the generic DDL, task 2b) first |
| Class sweep (#959 F1) | `expires_at` and `fresh_until` comparisons in Reserve, Consume and the fence use `clock_timestamp()`, not `now()` (the transaction start time) |

## Amendment 2026-11-09 (c), round 2 of the AMEND PR

Re-review of the AMEND PR head `dc1fe6e5`; code references re-checked at mctl-api
`ceac9ed`. Cross-slice seams are owned by mctl-api#957 design §6d (roles and grants,
execution binding, approval-basket source, interface list) and §4 (refusal codes).
Where this section and older text disagree, this section wins; the older passages are
edited.

| Finding | Change |
|---|---|
| X-1, #957 F1/F5, #988 F1/F2 (no tx-aware `wi_`/`we_` create; nobody owns the execution binding) | This slice owns `CreateGlovoExecutionTx` and `ExecutionBindingTx` (#957 §6d.2), §4. Ids are `wi_`/`we_` plus 26 `randAlnum` characters; no own transaction, no `withTx` advisory lock |
| F1, X-2 (the fence fingerprints only one member of the payload; #985 and #989 disagree on the shape) | The write payload **is** the approval basket (#957 §6d.3). Fence step 4 runs #988 `basket.Parse` on the whole `bridge_commands.payload`: an extra top-level field, a wrapper, a missing field or any other shape is `basket_changed`. `basket.Fingerprint` is taken over the canonical bytes `Parse` returns. T10 gains the cases |
| F3 (`glovo.cancel_order_fake` can be created but never spent; binding undefined) | Dropped from M1. The only Glovo kind is `glovo.place_order_fake`; the kind CHECK admits only it, and `CreateGlovoApprovalTx` refuses any other kind (T15). Cancel before dispatch revokes the existing `aar_`; cancel after dispatch needs no approval (#985 §6). #1044's cancel row is unreachable in M1 |
| F4 (the lifecycle guard misses INSERT) | `glovo.aar_guard()` is `BEFORE INSERT OR UPDATE OR DELETE`. A Glovo row is inserted only as `pending`, with every `decided_*` field empty, `requested_by='service:glovo-prepare'` and a complete policy context. `pending→approved` additionally needs `decided_by_principal_id` = the binding's owner and `authority_basis='resource_owner'`; the fence re-checks both. T15 INSERT cases |
| F5, X-4 (grants go to an unnamed role; writes run as the bridge role) | One Glovo runtime role (#957 §6d.1) serves the bridge and Glovo pools, and every Glovo approval write runs on it. Its grants on `action_approval_requests` and `glovo.approval_bindings` are in the #957 §6d.1 table; this design only points there. The work-items role keeps its generic grants and gets nothing in schema `glovo`; a Glovo-kind write by any role other than `glovo_runtime` is refused by `glovo.aar_guard()`. Owner-confirmed 2026-11-09 |
| P3 F2 (ReserveCommand fields) | `ReserveCommand` is published once in §4 with every field required; an empty field is a refusal, never a skip. #985 §5 step 12 passes every field. T-case per field |
| P3 F6 (no tenant membership table) | The owner decider calls `decideWrittenRole` with `PrincipalMembership.MemberRolesForPrincipal` directly (`internal/api/tenant_role.go:148-151`, `:185`) and skips `roleGate`. The fence's membership check is the #985 `Membership` read (GitOps, best effort, outside the transaction); the transactional guarantee is #985 §7.3 (the revocation hook plus L2) |
| P3 F7 (intent recompute sources) | §6 step 5 lists them: `tenant`, `owner_principal_id`, `order_ref`, `connection_ref`, `install_revision` and `provider_ref` come from the command row, `install_id` from the binding. `command.provider_ref == binding.provider` and `command.order_ref == binding.order_ref` are required. T6 subtests |
| P3 F8 (gate and installer disagree with #985) | §8 uses the #985 §7.3 list: `glovo.ControlDefault.Open` and `receipt.Ready(ctx) == nil` |
| P3 F9, X-9 (idempotency key unspecified) | `idempotency_key = "glovo-prepare:" + ordr_`, set server-side, never from client input (§4) |
| P3 F10 (negative tests) | T15 per immutable column and raw INSERT of `glovo.other`; Reserve mismatch per field; T20 revoke from `pending` |
| #985 consistency (Revoke and MarkUnknown idempotency) | `RevokeGlovoApprovalTx` on a row already `denied` for this order succeeds; `MarkGlovoApprovalUnknownTx` on a row already `unknown` for this `cmd_` succeeds (§4), as #985 §3 states |
| P2-4 row of (b) said "the owner cancels through #957" | Corrected: an unapproved order is closed by #985 cancel (which revokes the `aar_`) or by expiry of its `aar_`; #957 exposes no cancel |

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
| P2-4 order `approved` state is a second authority | Dropped. The decision writes only the `aar_`. `CreateGlovoApprovalTx` calls #988 `BindApproval` in the same transaction. A refusal does not cancel the order; an unapproved order is closed by #985 cancel, which calls `RevokeGlovoApprovalTx`, or by expiry of its `aar_` (§4, §5; corrected in (c)) |
| P2-5 owner decision recorded as `platform_admin`; policy unregistered; context incomplete | `governance.AuthorityBasisResourceOwner = "resource_owner"`, recorded for Glovo kinds. The rule `glovo.order.owner-approval` v1 is registered in `governance.Policies`. `CreateGlovoApprovalTx` writes a complete context (`intent_source = execution:<we_>`, `policy_decision`, `policy_reasons`), so the start-up backfill never touches it. T19 runs strict mode (§5) |
| P2-6 readiness ignores D2 and decision A | `GLOVO_DB_URL`, `COMMERCE_DB_URL` and `WORK_ITEMS_DB_URL` set explicitly, no fallback; #985 `ProveOneDatabase` passes; schema version, triggers enabled and table owners checked; policy registered; every collaborator non-nil. Otherwise no `SetFence` and every Glovo approval method answers `not_ready`. The connection read is #959 `LiveConnectionTx` under L2; `LockConnectionShared` is gone (§8) |
| P2-7 contract gaps with #957/#1044 | `GlovoControlInput` carries `approval_ref` **and** the fingerprint, as the merged #957 §6c and #1044 M10 say (§9). New: `GlovoApprovalStatus` for the control worker's `read_approval`, `RevokeGlovoApprovalTx`, an idempotent `ReserveGlovoApprovalTx` that also checks the binding against the command fields, and one refusal table to the seven M10 reasons and #957 §4 (§10) |
| P3 generic create can mint Glovo kinds; `IsGlovoKind` vs `LIKE` | The generic create refuses any `glovo.` kind. One predicate: a DB `CHECK` that a `glovo.`-prefixed kind is one of the exact list, so `LIKE 'glovo.%'` and `IsGlovoKind` agree (§1) |
| P3 invariant table misses `unknown` + effect `unknown` | Added (§7) |
| P3 expired vs `MarkUnknown` | `unknown` wins for forensics: a stored `reserved` row past `expires_at` can only become `unknown`, never `consumed`. `expired` is a reading of `pending`, `approved` or `reserved` only (§1) |
| P3 admins skip the live role check | For Glovo kinds the decider's membership is read through `PrincipalMembership` with no admin pass (§5; see (c) P3 F6) |
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
  `MCTL_BRIDGE_ENABLED` for mctl-api were **not observed**. The design requires
  `GLOVO_DB_URL` and `WORK_ITEMS_DB_URL` to be set explicitly (#957 §6d.1 R4) and #985's `ProveOneDatabase` to pass (§8).

## Proposed solution

### 1. One row, one state column

The authoritative object is the existing `action_approval_requests` row. Glovo adds:

- **Action kind** `glovo.place_order_fake` only (`workitems.GlovoActionKinds`,
  `IsGlovoKind`). M1 has no `glovo.cancel_order_fake`: cancel before dispatch revokes
  the existing `aar_`, and cancel after dispatch needs no approval (#985 §6). One
  predicate everywhere: the CHECK `action_approval_requests_glovo_kind_chk`
  `action_kind NOT LIKE 'glovo.%' OR action_kind = 'glovo.place_order_fake'`
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

`workitems.ApplyGlovoApprovalSchema(ctx, migrationConnStr, runtimeRole string) error` is the only path that creates
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
- `glovo.aar_guard()` (`BEFORE INSERT OR UPDATE OR DELETE` on
  `action_approval_requests`):
  - INSERT of a Glovo-kind row: only `state='pending'`, every `decided_*` column and
    `authority_basis` empty, `consumed_at`/`reserved_at`/`executed_at` null,
    `requested_by='service:glovo-prepare'`, and a complete policy context
    (`intent_source`, `policy_rule_id='glovo.order.owner-approval'`,
    `policy_version='1'`, `policy_decision`, `policy_reasons` non-empty) and `artifact_hash` matching
    `^sha256:[0-9a-f]{64}$` (round 4, F1);
  - `pending→approved` additionally needs `NEW.decided_by_principal_id` equal to the
    binding's `owner_principal_id` and `NEW.authority_basis='resource_owner'`;
  - a row whose `OLD.action_kind` or `NEW.action_kind` is a Glovo kind may not change
    `action_kind`, `intent_hash`, `expires_at`, `execution_id`, `work_item_id`,
    `subject_principal_id`, `requested_by`, `artifact_hash` or `policy_rule_id`/`policy_version`;
  - its state may move only `pending→approved`, `pending→denied`, `approved→reserved`,
    `approved→denied` (revoke before dispatch), `reserved→consumed`,
    `reserved→unknown`; `consumed`, `unknown` and `denied` are final;
  - `DELETE` of a Glovo row is refused.
- `glovo.aar_binding_required()`: a `CONSTRAINT TRIGGER … DEFERRABLE INITIALLY
  DEFERRED` `AFTER INSERT` on `action_approval_requests`. A Glovo-kind row must have its
  binding row by commit, and its `artifact_hash` must equal `binding.basket_fingerprint`
  (round 4, F1).
- The widened state CHECK and the kind CHECK are added here too (guarded, `NOT VALID`
  then `VALIDATE`), not in the runtime `actionApprovalSchema`.
- Grants: every Glovo approval write runs on the one Glovo runtime role of #957 §6d.1
  (the bridge pool). Its rights on `glovo.approval_bindings` (`SELECT, INSERT, UPDATE
  (command_id)`) and on `action_approval_requests` (the exact column list is the one row of #957 design §6d.1 and is not restated here, round 3; no `DELETE`,
  `TRUNCATE` or `TRIGGER`) are listed in that table and nowhere else; this slice's
  `ApplyGlovoApprovalSchema` issues them. The work-items role keeps its generic rights
  and gets nothing in schema `glovo` (#957 §6d.1 "existing consumers").
- `glovo.aar_guard()` refuses any INSERT or UPDATE of a Glovo-kind row whose
  `current_user` is not the `runtimeRole` given to `ApplyGlovoApprovalSchema` (written
  into the function body as a literal at apply time), so no other role can mint or move
  a Glovo receipt. Grants govern service access only; the owner, membership, connection
  and `aar_` checks of §5 and §6 still run on every decision and permit.
- **Ownership of `action_approval_requests`.** A trigger on a table owned by the
  runtime role can be disabled by that role. The table must therefore be owned by the
  migration role, and `actionApprovalSchema` must stop running DDL on the runtime pool
  for it (`workitems/store.go:243`). Because that changes the generic work-items
  startup, it is an owner decision (OPEN-989-1). This slice plans it as task 2b: move
  the generic DDL into `workitems.ApplySchema(ctx, migrationConnStr, runtimeRole string)` under the migration role, and have
  `NewStore` only verify the schema version when the table is not owned by
  `current_user`. Until the move happens, Glovo `Ready` fails and every Glovo approval
  method answers `not_ready`; generic work items are unchanged.
- `Ready` checks: schema version; both guard triggers and the constraint trigger exist
  with `tgenabled = 'O'`; `NOT pg_has_role(current_user, relowner, 'MEMBER')` for
  `action_approval_requests` and `glovo.approval_bindings`; the runtime role's
  privileges equal the #957 §6d.1 rows (checked by #985 `ProveOneDatabase`).

### 3. Intent hash

`GlovoIntent(b Binding, kind) workitems.ActionIntent` sets:
- `Target = "glovo:v1:" + len-prefixed(tenant, owner, order_ref, connection_ref,
  install_id, install_revision, provider)`;
- `ArgsDigest = basket_fingerprint` (the #1059 approval-basket fingerprint); `CreateGlovoApprovalTx` also stores the same value as the row's `artifact_hash` (round 4, F1: the decision binding gate compares `content_digest` with `artifact_hash`, and an empty value can never pass it);
- `ExecutionID = we_`, `WorkItemID = wi_`, `PolicyRuleID = "glovo.order.owner-approval"`,
  `PolicyVersion = "1"`.

`intent_hash = IntentHash(...)`. The fence recomputes it from the command row (§6), so a
caller-supplied hash is only ever compared.

### 4. Tx-aware store API (`internal/workitems/glovo_approvals.go`)

None of these methods begins, commits or rolls back a transaction, and none takes an
advisory lock. The names match #957 design §6d.4 and the `Receipts` interface in #985
design §3.

```go
func (s *Store) CreateGlovoExecutionTx(ctx, tx pgx.Tx, in GlovoExecutionInput) (workItemID, executionID string, err error)
func (s *Store) ExecutionBindingTx(ctx, q Querier, executionID string) (tenant, ownerPrincipalID, workItemID, workflowID string, err error)
func (s *Store) CreateGlovoApprovalTx(ctx, tx pgx.Tx, in GlovoApprovalInput) (*ActionApprovalRequest, bool, error)
func (s *Store) LockGlovoApprovalTx(ctx, tx pgx.Tx, id string) (*ActionApprovalRequest, *GlovoBinding, error) // L4
func (s *Store) ReserveGlovoApprovalTx(ctx, tx pgx.Tx, id string, cmd ReserveCommand) (replayed bool, err error)
func (s *Store) ConsumeGlovoApprovalTx(ctx, tx pgx.Tx, id, commandID string) error      // fence only
func (s *Store) RevokeGlovoApprovalTx(ctx, tx pgx.Tx, id, actor string) error
func (s *Store) MarkGlovoApprovalUnknownTx(ctx, tx pgx.Tx, id, commandID string) error
func (s *Store) DecideGlovoApprovalTx(ctx, tx pgx.Tx, in ActionDecisionInput) (*ActionApprovalRequest, error)
func (s *Store) GlovoApprovalStatus(ctx, q Querier, tenants []string, id string) (*GlovoApprovalStatus, error)  // round 3: q is the glovo_runtime pool or the caller's tx, never the work-items pool
func (s *Store) GlovoApprovalForDecision(ctx, q Querier, id string) (*ActionApprovalRequest, *GlovoBinding, error) // round 3: Glovo-kind pre-read for the decision route and canSeeActionApproval
```

```go
type GlovoExecutionInput struct{ Tenant, OwnerPrincipalID, WorkflowID, Actor string }
type GlovoApprovalInput struct { // round 4, F2; every field required
    Tenant, OwnerPrincipalID, WorkItemID, ExecutionID, OrderRef, ConnectionRef string
    InstallID, InstallRevision, BasketFingerprint, Provider string
    ExpiresIn time.Duration // chosen by #957 prepare (GlovoApprovalTTL); 0 < ExpiresIn <= MaxApprovalTTL, else invalid_request; SQL: expires_at = clock_timestamp() + ExpiresIn
}
type ReserveCommand struct { // every field required; an empty field is ErrReserveIncomplete (intent_mismatch), never a skip
    CommandID, Tenant, OwnerPrincipalID, ExecutionID, OrderRef, ConnectionRef string
    InstallRevision, IntentHash, BasketFingerprint string
}
```

- **CreateGlovoExecutionTx** (#957 prepare, #957 §6d.2): one `work_items` row (owner
  = the principal, origin surface `glovo`), one creation event and one
  `work_item_executions` row (engine `temporal`, `engine_ref = WorkflowID`, attempt 1)
  on the caller's transaction. Ids are `wi_`/`we_` plus 26 characters of the bridge
  `randAlnum` alphabet, matching `internal/bridge/store.go:164-165`; the generic
  hyphenated UUID ids (`internal/workitems/store.go:395`, `:676`) never would. The
  generic `withTx` advisory lock (`store.go:266-272`) is not taken.
- **ExecutionBindingTx**: the #988 `Executions` collaborator and the #985 workflow-id
  source; `not_found` for an id it did not create.
- **Create** (called by #957 prepare, which already holds L3 on the order): inserts the
  `aar_` row and the binding, and calls #988 `BindApproval(tx, order_ref, aar_)` in the
  same transaction. `requested_by = "service:glovo-prepare"`, `subject_principal_id =
  owner`, `risk_level = high`, `side_effect = write`, and a complete governance
  context: `intent_source = "execution:" + we_`, `policy_rule_id`/`policy_version` of
  §3, `policy_decision = "require_approval"`, `policy_reasons =
  ["glovo.order.owner-approval"]`. `idempotency_key = "glovo-prepare:" + order_ref`,
  set here and never taken from client input, so the global `UNIQUE (requested_by,
  idempotency_key)` (`action_approvals.go:152`) is per order. Any kind other than
  `glovo.place_order_fake` is refused. It calls `BindApproval` with
  `Scope{Tenant, PrincipalID: owner}` and `Actor{Kind: system, ID:
  "service:glovo-prepare"}`. Idempotent on that key. A
  second `aar_` for the same order hits `UNIQUE (order_ref)` and is `approval_replayed`.
- **Reserve** (#985 dispatch, under L3+L4): every `ReserveCommand` field is required
  and must equal the binding (else
  `intent_mismatch`, or `basket_changed` for the fingerprint). If the row is already
  `reserved` with `command_id == cmd.CommandID`, it returns `replayed = true` and
  changes nothing (crash-retry). Otherwise one CAS `approved → reserved` (`expires_at > clock_timestamp()` and
  `fresh_until > clock_timestamp() + ReservePermitMargin`, Glovo kind; round 4, F2: a dispatch
  that is already too stale to be permitted is refused with `approval_expired` while the
  `aar_` is still `approved`, so nothing is burned; a `fresh_until` that passes between
  reserve and permit is refused by the fence and the sweeper marks the row `unknown`) and the binding's `command_id` write, in the same transaction.
- **Consume** (fence only): CAS `reserved → consumed` guarded by `command_id` and
  `expires_at > clock_timestamp()`.
- **Revoke** (#985 cancel before dispatch): CAS `pending|approved → denied`, recording
  the actor and reason `order_cancelled`. Exposed as `refused`. A row already `denied`
  for this order is success (idempotent retry); any other state is `invalid_transition`.
- **MarkUnknown**: CAS `reserved → unknown` guarded by `command_id`; allowed past expiry.
  A row already `unknown` for the same `command_id` is success.
- **Decide**: `FOR UPDATE … WHERE state='pending'` on the `aar_` only (L4). It writes no
  order row.
- **GlovoApprovalStatus** (round 3: a read on the caller's `Querier`, which is the Glovo pool as `glovo_runtime` or the caller's `pgx.Tx`; the work-items role has no privilege on schema `glovo`, #957 §6d.1 R3, so this read never runs on its pool; used by #985 `read_approval`, `glovo_order_status` and the prepare replay): returns
  `approval_ref`, exposed state, `expires_at`, `order_ref` and `command_id` (ids and
  enums only). Missing, non-Glovo or outside `tenants` is one `not_found`.
- **Generic paths refuse Glovo kinds.** `CreateActionApproval` refuses any `glovo.`
  kind with 400 `approval_kind_not_creatable_here`. `ConsumeActionApproval`,
  `ReserveActionApproval`, `SettleActionApproval` and `MarkActionApprovalExecuted` add
  `AND NOT (glovoKindPredicate)` to their CAS and return `ErrApprovalKindNotSpendable`
  (409 `approval_kind_not_spendable_here`) on a Glovo row. The trigger backs this up.

### 5. Owner decision (`handlers_action_approvals.go`)

`DecideActionApproval` gains one branch before the admin check:
1. Non-admin caller: pre-read the generic `aar_` row through the work-items pool (kind and state only, as today). Only when it is a Glovo kind, read the binding with `GlovoApprovalForDecision` on the **Glovo pool** (round 3: the owner and tenant live in `glovo.approval_bindings`, which the work-items role cannot read); an absent binding is the same uniform 403. The pre-read is advisory: `DecideGlovoApprovalTx` re-checks the binding and the state under L4. If it is a Glovo kind and every check below
   passes, continue. Otherwise answer the same 403 `approval_decider_forbidden` that a
   non-admin gets today, whether the id is unknown, non-Glovo, someone else's or
   undecidable. No oracle.
2. Admin caller on a Glovo kind: the same checks; an admin who is not the owner gets
   403 `approval_decider_forbidden`. Admin on a non-Glovo kind: unchanged.

`isGlovoOwnerDecider` requires:
- a resolved principal; not a service, agent, CI, relayed or surface caller; not a
  Glovo-audience token (the facade and the model never decide);
- `binding.owner_principal_id == user.PrincipalID()`;
- live membership for `binding.tenant` with at least the minimum role (proposed
  `developer`, OPEN-989-3): `decideWrittenRole` (`internal/api/tenant_role.go:185`)
  over `PrincipalMembership.MemberRolesForPrincipal` (`:148-151`), called directly so
  `roleGate` (`:157`) gives admins no pass. Membership is a GitOps checkout, not a
  Postgres table;
- `glovo.Default.Open` and Glovo approvals readiness (§8), else 503 `not_ready`.

Governance:
- `governance.AuthorityBasisResourceOwner = "resource_owner"`. `decisionCapture`
  records it for Glovo kinds, and `platform_admin` stays for every other kind.
- `governance.Policies` registers `glovo.order.owner-approval` version `1`, so
  `Admit(…, RequireRegisteredPolicy)` passes in strict mode.
- `guardDecision` and the binding gate run unchanged (round 4, F1: with a non-empty
  `artifact_hash` a complete binding passes under `MCTL_APPROVAL_BINDING=enforce`, and a
  stale `content_digest` is `context_changed`). The context is complete from
  create, so the start-up backfill does not rewrite Glovo rows.

The decision runs as `DecideGlovoApprovalTx` on a transaction from the bridge pool (one
database). It touches only the `aar_`. The route keeps its existing `writeErrorCode`
body; owner decision C1 applies to the #957/#985 Glovo routes, not this one. Read
access (`canSeeActionApproval`) gains the same owner rule for Glovo kinds only, reading the binding through `GlovoApprovalForDecision` on the Glovo pool (it takes the `aar_` row and a binding looked up by the caller, never from the work-items pool).

### 6. The fence (`internal/glovo/receipt/fence.go`)

`receipt.Fence` implements `bridge.WriteFence`, including the `PreLock` hook that #985
adds to `permitTx`. Collaborators: `Approvals` (this store), `Orders` (#988), `Conns`
(#959 `LockOwnerShared`, `LiveConnectionTx`) and `Membership` (#985 §3: GitOps, best
effort, read outside any row lock; the transactional guarantee is #985 §7.3). The lock
levels are the canonical ones of #957 design §6b.

`PreLock(ctx, tx pgx.Tx, c bridge.Caller, commandID string) error` (the #957 §6d.4
signature, round 3), before `lockOwned`:
0. Scope first. Read the command row **without a lock** and apply the same provider and
   tenants predicate as `lockOwned` (`internal/bridge/store.go:659-668`, `c.allowsTenant`
   and the provider). An absent id and a foreign tenant or provider both answer
   `ErrCommandNotFound`, before any lock and with no order or `aar_` specific error. A
   command whose kind is not `place_order_fake` (a read, `cancel_order_fake`, an empty
   `order_ref`) returns nil without any lock; `permitTx`'s own kind refusal then applies.
1. Read, without a lock, the command's immutable binding columns: `tenant`,
   `owner_principal_id`, `order_ref`, `approval_ref`.
2. `Conns.LockOwnerShared(tenant, owner)`: L1 shared, L2 shared.
3. `Orders.LockOrderForControl(ctx, tx, order_ref, []string{tenant})`: L3.
4. `Approvals.LockGlovoApprovalTx(approval_ref)`: L4.

`permitTx` then takes L5 (`lockOwned`) and calls `Check(ctx, tx, b)`:
1. Re-read the command row (now locked). Its `tenant`, `owner_principal_id`,
   `order_ref` and `approval_ref` must equal what `PreLock` read; they are immutable
   after `Enqueue`, so a difference is an invariant violation.
2. The `aar_` is a Glovo kind in stored state `reserved` with `binding.command_id ==
   b.CommandID`. Otherwise `approval_invalid`, or `approval_replayed` when it is bound
   to another command.
3. `expires_at` and `fresh_until` are in the future by `clock_timestamp()` (statement time, not the permit transaction's start), else `approval_expired`.
4. **Recompute from the written content.** Read `bridge_commands.payload` from the
   locked row and run #988 `basket.Parse(payload)` on the **whole** payload (#957
   §6d.3: the payload is exactly the approval basket, no wrapper, no other top-level
   field; the #1059 rules: closed schema, sorted unique `item_code`, arithmetic). Then
   `fp = basket.Fingerprint(canonical)`. `fp` must equal `binding.basket_fingerprint`
   and the order's `final_basket_fingerprint`, else `basket_changed`. An extra or
   missing field, a wrapper object or any other shape fails `Parse` and is
   `basket_changed`.
5. Recompute `ih = IntentHash(GlovoIntent(..., fp))`. From the command row: `tenant`,
   `owner_principal_id`, `order_ref`, `connection_ref`, `install_revision` and
   `provider_ref`; from the binding: `install_id`. `command.provider_ref` must equal
   `binding.provider` and `command.order_ref` must equal `binding.order_ref`, else
   `intent_mismatch`. The `aar_` must also carry `decided_by_principal_id ==
   binding.owner_principal_id` and `authority_basis = 'resource_owner'`, else
   `approval_invalid`.
   `ih` must equal the `aar_` `intent_hash` and `b.IntentHash`, else `intent_mismatch`.
   The same check covers `b.ExecutionID`, `b.WorkItemID`, `b.Tenant`,
   `b.OwnerPrincipalID`, `b.ConnectionRef` and `b.InstallRevision`.
6. `Membership.IsMember(tenant, owner)` (#985 §3, best effort): false is `no_tenant`;
   a read error is `unavailable`.
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

`receipt.Ready(ctx)` is nil only when all of the following hold:
- `GLOVO_DB_URL` and `WORK_ITEMS_DB_URL` are each set explicitly, with no
  `AUDIT_DB_URL` fallback, and `current_user` on the Glovo pool is `glovo_runtime`;
- #985 `control.ProveOneDatabase` passed (one physical database, owner decision A);
- `ApplyGlovoApprovalSchema`'s version matches, the triggers are enabled, the runtime
  role is not a member of the table owners, and its grants equal #957 §6d.1 (§2);
- `glovo.order.owner-approval` v1 is registered;
- the work-items, bridge, #988 order and #959 connection stores are non-nil;
- the #1059 approval basket is vendored and the write payload contract exists
  (OPEN-985-8, OPEN-1059-1).

Only #985 task 9 calls `bridgeStore.SetFence(receipt.NewFence(...))`, and only when
all six #985 §7.3 preconditions hold, among them `glovo.ControlDefault.Open` and
`receipt.Ready(ctx) == nil`. Otherwise the fence stays
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

| Internal condition | #1044 M10 reason | #957 §4.1 / #985 wire (status equals the §4.1 row; amended (c)) |
|---|---|---|
| `aar_` missing, not a Glovo kind, or outside `tenants` (control read) | — | 404 `not_found` |
| state `pending`, `refused` or `unknown`; `consumed`/`reserved` without this command at the fence; decider is not the bound owner or `authority_basis` is not `resource_owner` | `approval_invalid` | 409 `approval_invalid` |
| reserved or consumed for another `cmd_`; a second `aar_` for the order | `approval_replayed` | 409 `approval_replayed` |
| past `expires_at` or `fresh_until` | `approval_expired` | 409 `approval_expired` |
| binding differs (tenant, owner, `we_`, order, connection, install revision, provider), a `ReserveCommand` field is empty, or recomputed intent hash differs | `intent_mismatch` | 409 `intent_mismatch` |
| fingerprint differs (body, order, or recomputed from the payload), or the payload is not exactly an approval basket (`basket.Parse` fails) | `basket_changed` | 409 `basket_changed` |
| `lock_timeout` (55P03) on any §6b lock | `tenant_busy` | 409 `tenant_busy` |
| not configured, proof failed, gate closed | `provider_disabled` | 503 `not_ready` |
| owner no longer a member | terminal | 403 `no_tenant` |
| connection absent / revoked / expired; revision moved | terminal | 404 `no_connection` / 409 `connection_revoked` / 409 `connection_expired` / 403 `stale_install` |
| I/O error, or a membership read error | retryable | 503 `unavailable` |
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

- **Migrations:** additive, only through `ApplyGlovoApprovalSchema` under
  `glovo_migrator`: the bindings table, three triggers, two CHECKs, the widened state
  CHECK and the #957 §6d.1 grants. No backfill. The ownership move of
  `action_approval_requests` and `work_items*` is OPEN-989-1 (extended).
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
