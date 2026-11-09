# Tasks: issue-989-feat-glovo-m1b-2-single-authoritative-aa

- [ ] 1. Schema: in `internal/workitems/action_approvals.go`, widen
  `action_approval_requests_state_check` with the replace-once `DO $$` block keyed on
  `'reserved'`, so it admits `reserved` and `unknown`. Add
  `action_approval_requests_glovo_states_chk`. Add `glovo_approval_bindings`, its
  partial unique index on `command_id`, and the `glovo_approval_bindings_immutable()`
  trigger, which allows only a one-time `command_id` write. — DoD: a restart is a no-op;
  existing rows are unaffected; a raw-SQL UPDATE of any binding column other than the
  first `command_id` write raises.
- [ ] 2. Kinds, states and the intent (depends on 1): in a new
  `internal/workitems/glovo_approvals.go`, add `GlovoActionKinds`, `IsGlovoKind`,
  `ApprovalReserved`, `ApprovalUnknown`, `GlovoBinding`, `GlovoIntent` (canonical
  `Target` plus `ArgsDigest` = fingerprint) and `GlovoReceiptState`. Extend
  `effectiveState` so that `reserved` past `expires_at` reads as `expired`. Add the
  errors `ErrApprovalReserved`, `ErrApprovalKindNotSpendable`,
  `ErrApprovalCommandMismatch` and `ErrApprovalBindingMismatch`. — DoD: unit tests pin
  the hash for a golden binding, and changing any one binding field changes the hash.
- [ ] 3. Tx-aware store methods (depends on 2): `CreateGlovoApprovalTx`,
  `LockGlovoApprovalTx`, `DecideGlovoApprovalTx`, `ReserveGlovoApprovalTx`,
  `ConsumeGlovoApprovalTx` and `MarkGlovoApprovalUnknownTx`. Each is a single CAS on
  the caller's `pgx.Tx`, and none begins or commits. Create takes an `Orders`
  collaborator to lock the order and require an empty `approval_ref`. Decide takes it to
  run the `finalized -> approved | cancelled` transition. — DoD: the methods compile
  against the #988 `orders` interface, or against a local interface when #988 is not
  merged. Nil collaborators return `glovo.CodeNotReady`.
- [ ] 4. Fence the generic paths (depends on 2): add `AND action_kind NOT LIKE 'glovo.%'`
  to the CAS in `ConsumeActionApproval`, `ReserveActionApproval`, `SettleActionApproval`
  and `MarkActionApprovalExecuted`. Map a miss on a Glovo kind to
  `ErrApprovalKindNotSpendable`. Map the error to 409 `approval_kind_not_spendable_here`
  in `writeActionApprovalError`. — DoD: existing tests in
  `internal/workitems/action_approvals_test.go` and `internal/api/agent_receipt_gate_test.go`
  pass unchanged.
- [ ] 5. Owner-decider (depends on 3): in `internal/api/handlers_action_approvals.go`,
  pre-read the `aar_`. For a Glovo kind, run `isGlovoOwnerDecider`: owner principal
  equality, a direct human (no service, agent, CI, relay, surface or Glovo audience),
  `checkTenantRole(..., RoleDeveloper)` with 404 when there is no role, and an open
  gate. Then call `DecideGlovoApprovalTx` on a transaction from the shared pool.
  Non-Glovo kinds keep `isHumanAdmin`. Extend `canSeeActionApproval` with the owner
  rule for Glovo kinds only. Audit Glovo decisions without `args_digest`. — DoD: the
  existing tests in `handlers_action_approvals_test.go`,
  `handlers_devloop_decide_test.go` and `handlers_write_approver_test.go` pass unchanged.
- [ ] 6. Bridge hook (independent of 3-5): in `internal/bridge/permit.go`, add the
  `OutcomeRecorder` interface. Call it from `submitTx`, `Cancel` and `ExpireDue` in
  `internal/bridge/store.go` for mutating commands that reach a terminal status
  without `effect_state='permitted'` ever being set, in the same tx. — DoD: with
  `refusingFence`, all existing bridge tests pass.
- [ ] 7. Fence (depends on 3, 6): add the package `internal/glovo/receipt` with `Fence`
  (`Check` steps 1-8 of design §6, plus `CommandEndedWithoutPermit`), its collaborator
  interfaces (`Orders`, `Connections`, `Membership`), a typed refusal code per check
  wrapping `bridge.ErrWriteFenceRefused`, the opaque `afr_` fence ref, and
  `Audit(ctx)` for the joint-state invariant table. — DoD: no log line contains anything
  other than ids and codes.
- [ ] 8. Wiring (depends on 7, and on #985 `ProveColocated`, #988 and #959 stores): in
  `cmd/api/main.go`, call `bridgeStore.SetFence(receipt.NewFence(...))` only when
  `glovo.Default.Open` holds, every collaborator is non-nil and the co-location proof
  passes. Otherwise log once (no URL) and keep `refusingFence`. — DoD: with today's
  closed gate, startup behaviour is unchanged.
- [ ] 9. Cross-slice contracts (documentation in code comments and the PR description):
  - #957 prepare calls `CreateGlovoApprovalTx` on its shared `pgx.Tx` and stores the
    `aar_` in `glovo_orders.approval_ref`.
  - #985 dispatch calls `ReserveGlovoApprovalTx` (not a consume), locks the approval
    before the order, and passes `cmd_` from `Enqueue`.
  - `GlovoControlInput` carries `approval_ref` only, never a fingerprint or token.

  — DoD: the PR links #957, #985 and #988 and states these interface changes.
- [ ] 10. Docs: update the state-machine comment at the top of `action_approvals.go`
  and the `WriteFence` comment in `permit.go` with the composition table of design §7.
  Run `go fmt`, `go vet` and `golangci-lint`. No MCP tool is added, so the
  `server_test.go` count is unchanged.

## Tests

Postgres-backed tests use the existing store test harness. Fence tests run on one
database with fakes for `Orders` and `Connections` until #988 and #959 merge.

- [ ] T1. A `hir_` alone causes zero effects: answer a human-input request linked to
  the order's work item, then assert that the `aar_` is still `pending`, the order is
  still `finalized`, no bridge command exists and `IssueWritePermit` is refused.
- [ ] T2. Wrong-owner decider: another member of the same tenant gets 403. A platform
  admin who is not the owner gets 403 `approval_decider_forbidden`. A Glovo-audience
  token for the owner, an agent, a service and a relayed or surface caller are each
  refused.
- [ ] T3. Scope does not grow: a tenant `developer` owner cannot decide a non-Glovo
  `aar_` (still 403 `approval_decider_forbidden`), and a `mctl-agents-approve` `aar_`
  stays admin-only.
- [ ] T4. Cross-tenant decision: a caller with no role on the binding's tenant gets 404
  `approval_not_found`, and the audit entry records the refusal.
- [ ] T5. Concurrent approve and refuse: run 20 goroutine pairs. Exactly one decision
  wins per `aar_`, the other gets 409, and the order state matches the winner.
- [ ] T6. An `aar_` from a different `we_` or intent: a fence `Check` with a
  `FenceBinding` whose `ExecutionID`, `IntentHash`, `WorkItemID`, `Tenant`,
  `OwnerPrincipalID`, `ConnectionRef` or `InstallRevision` differs (one subtest per
  field) is refused, and the `aar_` stays `reserved`.
- [ ] T7. Expired: a decision, a reserve and a fence check past `expires_at` are each
  refused, and the state reads `expired`. A `fresh_until` in the past refuses the
  reserve and the fence check.
- [ ] T8. Replayed: a second `IssueWritePermit` for the same command gets
  `ErrPermitExists`. A second `ReserveGlovoApprovalTx` with a different `cmd_` gets
  `ErrApprovalReserved`. A second fence `Check` on a `consumed` `aar_` is refused.
- [ ] T9. Consumed: a `consumed` `aar_` cannot be decided, reserved, consumed or marked
  unknown, and the generic consume, reserve, settle and mark-executed routes return 409
  `approval_kind_not_spendable_here` for every Glovo state.
- [ ] T10. Fingerprint changed: with a fake order whose `final_basket_fingerprint`
  differs, the fence refuses `fingerprint_changed`, no `bridge_write_permits` row
  exists, and `effect_state` stays `none`.
- [ ] T11. Reconnect after approval: after the connection is revoked and a new `gcn_`
  or install revision is active, the fence refuses `connection_changed`. No API path
  moves the old `aar_` back to `approved`.
- [ ] T12. Owner removed from the tenant after approval: the fence refuses
  `owner_not_member`.
- [ ] T13. Ending without a permit: a reserved command that expires (`ExpireDue`), is
  cancelled while leased, or completes with `approval_refused` moves the `aar_` to
  `unknown` in the same tx. After a forced error in `CommandEndedWithoutPermit`, both
  sides roll back.
- [ ] T14. Atomicity: inject a failure after `ConsumeGlovoApprovalTx` inside `permitTx`.
  The `aar_` is still `reserved`, there is no permit row, and `effect_state` is `none`.
- [ ] T15. The schema is fail-closed: raw SQL that sets a Glovo row to `in_flight` or
  `executed`, a non-Glovo row to `reserved`, or a binding column after creation is
  rejected by the database.
- [ ] T16. Invariant table: walk every lifecycle path and assert that each
  (`aar_` state, `effect_state`) pair is in the allowed table of design §7, and that
  `consumed` holds exactly when a permit exists.
- [ ] T17. Secrecy: capture the `slog` output and audit rows across T1-T16 and assert
  that no fingerprint, basket bytes, lease token or `args_digest` of a Glovo kind
  appears. When #957's `GlovoControlInput` builder is present, assert that it carries
  only refs.
- [ ] T18. Readiness: with `glovo.Default` closed or any nil collaborator, every Glovo
  store method returns `not_ready` and `IssueWritePermit` returns
  `ErrWriteFenceUnavailable`.

## Rollback

- The feature is inert while `glovo.Default` is closed and the fence is not installed.
  To roll back behaviour, revert the PR or leave the gate closed. The bridge then keeps
  `refusingFence`.
- The schema is additive. Reverting the code leaves the widened CHECK, which admits
  more states, and an unused `glovo_approval_bindings` table. Both are harmless to the
  generic code, which never writes `reserved` or `unknown`. If needed, drop the table
  and restore the CHECK in a follow-up migration, after confirming that no
  `glovo.%` rows exist.
- The generic-path predicate (`action_kind NOT LIKE 'glovo.%'`) is a no-op for existing
  kinds, so a revert changes nothing for them.
