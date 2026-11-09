# Tasks: issue-989-feat-glovo-m1b-2-single-authoritative-aa

Amended 2026-11-09 (b); design.md has the finding -> fix table. Blocking dependencies:
mctl-agents#1059 merged (approval basket and vectors); the write payload contract
(OPEN-989-6); the ownership move (OPEN-989-1). Until then the code lands dark and
`Ready` fails.

Amended 2026-11-09 (c): new task 0 (execution binding, #957 §6d.2); kind list is
`glovo.place_order_fake` only; guard covers INSERT and foreign roles; grants follow the
owner-confirmed role model of #957 §6d.1.

- [ ] 0. `CreateGlovoExecutionTx` and `ExecutionBindingTx` (design §4, #957 §6d.2):
  `wi_`/`we_` + 26 `randAlnum` characters, one `work_items` row, one creation event, one
  `work_item_executions` row (engine `temporal`, `engine_ref = WorkflowID`), on the
  caller's tx, no `withTx` advisory lock. — DoD: ids match
  `internal/bridge/store.go:164-165`; an id from the generic store (`store.go:395`,
  `:676`) is `not_found` in `ExecutionBindingTx`; a rollback leaves no row.

- [ ] 1. `workitems.ApplyGlovoApprovalSchema(ctx, migrationPool)` (design §2): schema
  version row; the widened state CHECK and the exact-kind CHECK (guarded, `NOT VALID`
  then `VALIDATE`); `glovo.approval_bindings` with `UNIQUE (order_ref)`, the partial
  unique index on `command_id` and `install_revision TEXT`; `glovo.aar_guard()`,
  `glovo.approval_bindings_guard()` and the deferred `glovo.aar_binding_required()`
  constraint trigger (the guard is `BEFORE INSERT OR UPDATE OR DELETE` and refuses a
  Glovo-kind write by any role other than `runtimeRole`); the `glovo_runtime` and
  work-items grants of #957 §6d.1, nothing else. Ownership check, version downgrade
  refusal.
  — DoD: applies twice; fails when an object is owned by another role.
- [ ] 2. Kinds, states, intent: `GlovoActionKinds` (`glovo.place_order_fake` only), `IsGlovoKind`, the SQL constant
  `glovoKindPredicate`, `ApprovalReserved`, `ApprovalUnknown`, `GlovoBinding`,
  `GlovoIntent`, `GlovoReceiptState` (expiry precedence of design §1), errors. — DoD:
  golden hash for a binding; any field change changes the hash.
- [ ] 2b. (OPEN-989-1, after the owner decides) `workitems.ApplySchema` runs the generic
  `actionApprovalSchema` and the `work_items*` DDL under `glovo_migrator`, which grants
  the work-items role its existing DML explicitly (#957 §6d.1 "existing consumers"), and
  `NewStore` only verifies the version when it does not own the tables. — DoD: generic
  work-items tests pass with both owners; T15b.
- [ ] 3. Store methods of design §4: `CreateGlovoApprovalTx` (binding row, complete
  governance context, `idempotency_key = "glovo-prepare:" + order_ref`, kinds other than
  `glovo.place_order_fake` refused, #988 `BindApproval` with the §4 Scope and Actor in
  the same tx), `LockGlovoApprovalTx`,
  `ReserveGlovoApprovalTx` (the one `ReserveCommand` struct, every field required,
  binding equality, idempotent for the same `cmd_`), `ConsumeGlovoApprovalTx`,
  `RevokeGlovoApprovalTx` and `MarkGlovoApprovalUnknownTx` (both idempotent as #985 §3),
  `DecideGlovoApprovalTx` (aar_ only), `GlovoApprovalStatus(ctx, q Querier, ...)` and `GlovoApprovalForDecision(ctx, q Querier, id)` (both on the Glovo pool, never the work-items pool). — DoD: none begins or
  commits; nil collaborators give `not_ready`.
- [ ] 4. Generic paths: `CreateActionApproval` refuses `glovo.` kinds; the four generic
  CAS statements add `AND NOT (glovoKindPredicate)` and map a Glovo row to 409
  `approval_kind_not_spendable_here`. — DoD: existing work-items and receipt-gate tests
  pass unchanged.
- [ ] 5. Governance: `governance.AuthorityBasisResourceOwner`; register
  `glovo.order.owner-approval` v1 in `governance.Policies`; `decisionCapture` records
  `resource_owner` for Glovo kinds.
- [ ] 6. Owner decision (design §5): the non-admin branch with one uniform 403, the
  membership read through `decideWrittenRole` + `PrincipalMembership` without
  `roleGate`, `isGlovoOwnerDecider`, `DecideGlovoApprovalTx` on a bridge-pool
  transaction, `canSeeActionApproval` owner rule for Glovo kinds (binding read through `GlovoApprovalForDecision` on the Glovo pool after the generic pre-read), audit without
  `args_digest`. — DoD: existing decide tests pass unchanged.
- [ ] 7. `internal/glovo/receipt`: `Fence` with `PreLock(ctx, tx, c bridge.Caller, commandID)` (step 0: provider/tenants predicate and kind refusal before any lock) and `Check` (design §6),
  including `basket.Parse` on the whole stored payload, the recompute of fingerprint and
  intent hash (command-row and binding sources of design §6 step 5), the decider and
  `authority_basis` re-check, `LockOrderForControl(..., []string{tenant})`; the
  refusal codes of design §10 wrapping `bridge.ErrWriteFenceRefused`; `afr_` ref;
  `Audit(ctx)` for the joint-state table; `Sweeper` (design §7) in the `Expirer` tick.
  `PreLock` itself is added to `bridge.WriteFence` by #985.
- [ ] 8. `receipt.Ready(ctx)` with every condition of design §8. #985 task 9 is the only
  `SetFence` caller, after all six #985 §7.3 preconditions. — DoD: with today's closed gate and unset URLs, startup is
  unchanged and the fence stays `refusingFence`.
- [ ] 9. Cross-slice notes in package comments: #957 prepare calls `CreateGlovoApprovalTx`
  under L3; #985 uses the `Receipts` methods and calls `MarkGlovoApprovalUnknownTx` on
  cancel without permit; the lock order is #957 §6b; `GlovoControlInput` carries
  `approval_ref` and the fingerprint; the provider writes only the payload's lines
  (OPEN-989-4). Run `go fmt`, `go vet`, `golangci-lint`, `go test ./...`.

## Tests

Postgres tests use `TEST_DATABASE_URL` (skip when unset), `glovo_migrator`, a separate
`glovo_runtime` and a work-items role. Fence tests use fakes for `Orders` and `Conns` until #988 and #959
merge.

- [ ] T1. A `hir_` answer alone changes no `aar_`, order or bridge row, and
  `IssueWritePermit` is refused.
- [ ] T2. Wrong decider: another tenant member, a non-owner admin, a Glovo-audience token
  for the owner, an agent, a service, CI, a relayed and a surface caller are each
  refused.
- [ ] T3. Scope: an owner cannot decide a non-Glovo `aar_`; `mctl-agents-approve` stays
  admin-only.
- [ ] T4. No oracle: a non-admin caller gets byte-identical 403 bodies for an unknown id,
  a non-Glovo id and someone else's Glovo id.
- [ ] T5. 20 concurrent approve/refuse pairs: one winner per `aar_`; no order row is
  written by the decision.
- [ ] T6. Binding mismatch at the fence, one subtest per field (`we_`, `wi_`, tenant,
  owner, connection, install revision, `provider_ref` vs binding `provider`,
  `order_ref` vs binding `order_ref`, `install_id`): `intent_mismatch`; the `aar_` stays
  `reserved`. Reserve: one subtest per `ReserveCommand` field changed, and one per field
  empty, is refused and the `aar_` stays `approved`.
- [ ] T7. Expiry: decide, reserve and fence past `expires_at` or `fresh_until` are refused
  with `approval_expired`; a reserved row past expiry can become `unknown` but never
  `consumed`; `consumed`/`unknown`/`denied` never read as `expired`.
- [ ] T8. Replay: a second permit for the same command gets `ErrPermitExists`; reserve
  with the same `cmd_` returns `replayed=true` and changes nothing; reserve with another
  `cmd_` is `approval_replayed`; a second `aar_` for the same order is refused by
  `UNIQUE (order_ref)`.
- [ ] T9. Final states: a `consumed`, `unknown` or `denied` `aar_` cannot be decided,
  reserved, consumed or revoked; the generic routes answer
  `approval_kind_not_spendable_here` for every Glovo state; the generic create refuses
  `glovo.place_order_fake` and `glovo.other`.
- [ ] T10. **Written content differs.** Enqueue a real bridge command whose payload's
  approval basket differs from the approved one by one unit price, carrying the approved
  `intent_hash`: the permit is refused `basket_changed`, no `bridge_write_permits` row
  exists and `effect_state` stays `none`. A second case changes the payload's
  `item_code` set; a third stores a command `intent_hash` that differs from the
  recomputed one (`intent_mismatch`). Amended (c): a payload that is the approved basket
  plus one extra top-level field, the basket wrapped in `{"approval_basket": …}`, and a
  payload missing `lines` are each `basket_changed`. A matching payload gets the permit.
- [ ] T11. Reconnect after approval: a new `gcn_` or install revision makes the fence
  refuse (`connection_revoked` / `stale_install`); nothing moves the `aar_` back.
- [ ] T12. Owner removed from the tenant after approval: `no_tenant`.
- [ ] T13. Ending without a permit: #985 cancel moves the `aar_` to `unknown` in its own
  transaction; the sweeper moves a reserved `aar_` whose command expired or completed
  without a permit to `unknown`; a command with provider-reported `unknown` and no permit
  gives the `unknown`/`unknown` pair.
- [ ] T14. Atomicity: a failure injected after `ConsumeGlovoApprovalTx` inside
  `permitTx` leaves the `aar_` `reserved`, no permit row and `effect_state` `none`.
- [ ] T15. Database enforcement under the runtime role, raw SQL: every forbidden
  transition (including `consumed→approved`, `reserved→approved`, `denied→approved`,
  `unknown→reserved`), a change of `action_kind` into or out of a Glovo kind, a change of
  `intent_hash`, `expires_at` or `subject_principal_id`, `DELETE`, a binding column
  update other than the first `command_id`, a Glovo `aar_` committed without a binding,
  and `ALTER TABLE … DISABLE TRIGGER` are each rejected. Amended (c): one subtest per
  immutable column (`action_kind`, `intent_hash`, `expires_at`, `execution_id`,
  `work_item_id`, `subject_principal_id`, `requested_by`, `policy_rule_id`,
  `policy_version`); raw `INSERT` of a Glovo row in `approved`, `reserved` or
  `consumed`, with a `decided_*` field set, with another `requested_by`, or with an
  incomplete policy context; raw `INSERT` of `glovo.other` and of
  `glovo.cancel_order_fake`; `pending→approved` with a decider other than the owner or
  an `authority_basis` other than `resource_owner`.
- [ ] T15b. Foreign roles and existing consumers (#957 §6d.1 R3/R5): the work-items
  role is refused a Glovo-kind `aar_` insert or update by `glovo.aar_guard()` and gets
  `permission denied` on `glovo.approval_bindings`; the runtime role's `UPDATE` on `action_approval_requests` is exactly the column list of #957 §6d.1 (`has_column_privilege` per column, startup proof as the oracle; a table-wide `UPDATE` or a missing column makes `ProveOneDatabase` fail and the dispatcher `not_ready`); with `glovo_migrator` owning the
  tables, the existing generic work-items and action-approvals suites pass unchanged
  under the work-items role, and `workitems.NewStore` sends no DDL.
- [ ] T15c. Foreign permit scope (round 3, X-6): a permit for a `cmd_` of another tenant, another provider or an absent id returns the same `ErrCommandNotFound` and takes no L1-L4 lock (lock-wait probe from a second connection shows none held); a read-kind or `cancel_order_fake` command or an empty `order_ref` takes no lock before `permitTx`'s kind refusal.
- [ ] T15d. Decision pre-read (round 3, X-4): with the role split in force, the owner's decision on a Glovo `aar_` succeeds (binding read on the Glovo pool) and a non-owner gets the uniform 403; the generic pre-read never selects from `glovo.*` on the work-items pool.
- [ ] T16. Invariant table of design §7 over every lifecycle path; `consumed` iff a
  permit exists.
- [ ] T17. Secrecy: logs and audit rows across T1-T16 contain no basket, `args_digest`,
  lease token or credential.
- [ ] T18. Readiness: each missing URL, a failed `ProveOneDatabase`, a disabled trigger, a
  runtime-owned table, an unregistered policy, and each nil collaborator give
  `not_ready`, and `SetFence` is not called.
- [ ] T19. Governance in strict mode: an owner approve passes `guardDecision` and records
  `authority_basis = resource_owner`; the start-up backfill leaves Glovo rows unchanged.
- [ ] T20. Control worker: run with the real role split (round 3): `GlovoApprovalStatus` and `GlovoApprovalForDecision` on the `glovo_runtime` pool succeed, and the same read on the work-items pool gets `permission denied for schema glovo`, so no code path uses it; `GlovoApprovalStatus` returns only ids and enums, and
  `not_found` outside `tenants`; `RevokeGlovoApprovalTx` moves `pending` and `approved`
  to `denied`, succeeds again on a row already `denied` for that order, and is refused
  on `reserved`; `MarkGlovoApprovalUnknownTx` succeeds again on a row already `unknown`
  for the same `cmd_`.
- [ ] T21. Deadlocks, deterministic with two connections and advisory barriers:
  permit vs #985 cancel, permit vs decide, dispatch vs decide, permit vs #959 revoke,
  sweeper vs permit. No `40P01` in any pair; the outcome matches the design §6 and
  #985 §7.2 race table.
- [ ] T22. Refusal map: every row of design §10 produces its M10 reason and wire code.

## Rollback

- The feature is inert while `glovo.Default` is closed and the fence is not installed.
  Revert the PR, or leave the gate closed; the bridge keeps `refusingFence`.
- The schema is additive. The widened CHECK admits more states and is harmless to
  generic code. `glovo.approval_bindings` and the triggers can be dropped by the
  migration role after confirming no Glovo-kind rows exist. The trigger functions act
  only on Glovo-kind rows, so leaving them in place changes nothing for generic kinds.
- If task 2b ran, the table ownership can stay with the migration role; reverting
  `NewStore`'s verify-only mode requires moving ownership back first.
