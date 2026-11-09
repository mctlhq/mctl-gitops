# Tasks: issue-989-feat-glovo-m1b-2-single-authoritative-aa

Amended 2026-11-09 (b); design.md has the finding -> fix table. Blocking dependencies:
mctl-agents#1059 merged (approval basket and vectors); the write payload contract
(OPEN-989-6); the ownership move (OPEN-989-1). Until then the code lands dark and
`Ready` fails.

- [ ] 1. `workitems.ApplyGlovoApprovalSchema(ctx, migrationPool)` (design §2): schema
  version row; the widened state CHECK and the exact-kind CHECK (guarded, `NOT VALID`
  then `VALIDATE`); `glovo.approval_bindings` with `UNIQUE (order_ref)`, the partial
  unique index on `command_id` and `install_revision TEXT`; `glovo.aar_guard()`,
  `glovo.approval_bindings_guard()` and the deferred `glovo.aar_binding_required()`
  constraint trigger; column-level grants. Ownership check, version downgrade refusal.
  — DoD: applies twice; fails when an object is owned by another role.
- [ ] 2. Kinds, states, intent: `GlovoActionKinds`, `IsGlovoKind`, the SQL constant
  `glovoKindPredicate`, `ApprovalReserved`, `ApprovalUnknown`, `GlovoBinding`,
  `GlovoIntent`, `GlovoReceiptState` (expiry precedence of design §1), errors. — DoD:
  golden hash for a binding; any field change changes the hash.
- [ ] 2b. (OPEN-989-1, after the owner decides) `workitems.ApplySchema` runs the generic
  `actionApprovalSchema` under the migration role, and `NewStore` only verifies the
  version when `action_approval_requests` is not owned by `current_user`. — DoD:
  generic work-items tests pass with both owners.
- [ ] 3. Store methods of design §4: `CreateGlovoApprovalTx` (binding row, complete
  governance context, #988 `BindApproval` in the same tx), `LockGlovoApprovalTx`,
  `ReserveGlovoApprovalTx` (binding equality, idempotent for the same `cmd_`),
  `ConsumeGlovoApprovalTx`, `RevokeGlovoApprovalTx`, `MarkGlovoApprovalUnknownTx`,
  `DecideGlovoApprovalTx` (aar_ only), `GlovoApprovalStatus`. — DoD: none begins or
  commits; nil collaborators give `not_ready`.
- [ ] 4. Generic paths: `CreateActionApproval` refuses `glovo.` kinds; the four generic
  CAS statements add `AND NOT (glovoKindPredicate)` and map a Glovo row to 409
  `approval_kind_not_spendable_here`. — DoD: existing work-items and receipt-gate tests
  pass unchanged.
- [ ] 5. Governance: `governance.AuthorityBasisResourceOwner`; register
  `glovo.order.owner-approval` v1 in `governance.Policies`; `decisionCapture` records
  `resource_owner` for Glovo kinds.
- [ ] 6. Owner decision (design §5): the non-admin branch with one uniform 403, the
  direct membership read, `isGlovoOwnerDecider`, `DecideGlovoApprovalTx` on a bridge-pool
  transaction, `canSeeActionApproval` owner rule for Glovo kinds, audit without
  `args_digest`. — DoD: existing decide tests pass unchanged.
- [ ] 7. `internal/glovo/receipt`: `Fence` with `PreLock` and `Check` (design §6),
  including the recompute of fingerprint and intent hash from the stored payload; the
  refusal codes of design §10 wrapping `bridge.ErrWriteFenceRefused`; `afr_` ref;
  `Audit(ctx)` for the joint-state table; `Sweeper` (design §7) in the `Expirer` tick.
  `PreLock` itself is added to `bridge.WriteFence` by #985.
- [ ] 8. `receipt.Ready()` with every condition of design §8. #985 task 9 is the only
  `SetFence` caller. — DoD: with today's closed gate and unset URLs, startup is
  unchanged and the fence stays `refusingFence`.
- [ ] 9. Cross-slice notes in package comments: #957 prepare calls `CreateGlovoApprovalTx`
  under L3; #985 uses the `Receipts` methods and calls `MarkGlovoApprovalUnknownTx` on
  cancel without permit; the lock order is #957 §6b; `GlovoControlInput` carries
  `approval_ref` and the fingerprint; the provider writes only the payload's lines
  (OPEN-989-4). Run `go fmt`, `go vet`, `golangci-lint`, `go test ./...`.

## Tests

Postgres tests use `TEST_DATABASE_URL` (skip when unset), a migration role and a
separate runtime role. Fence tests use fakes for `Orders` and `Conns` until #988 and #959
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
  owner, connection, install revision): `intent_mismatch`; the `aar_` stays `reserved`.
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
  recomputed one (`intent_mismatch`). A matching payload gets the permit.
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
  and `ALTER TABLE … DISABLE TRIGGER` are each rejected.
- [ ] T16. Invariant table of design §7 over every lifecycle path; `consumed` iff a
  permit exists.
- [ ] T17. Secrecy: logs and audit rows across T1-T16 contain no basket, `args_digest`,
  lease token or credential.
- [ ] T18. Readiness: each missing URL, a failed `ProveOneDatabase`, a disabled trigger, a
  runtime-owned table, an unregistered policy, and each nil collaborator give
  `not_ready`, and `SetFence` is not called.
- [ ] T19. Governance in strict mode: an owner approve passes `guardDecision` and records
  `authority_basis = resource_owner`; the start-up backfill leaves Glovo rows unchanged.
- [ ] T20. Control worker: `GlovoApprovalStatus` returns only ids and enums, and
  `not_found` outside `tenants`; `RevokeGlovoApprovalTx` moves `approved` to `denied`
  and is refused on `reserved`.
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
