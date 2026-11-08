# Tasks: issue-954-feat-glovo-m1b-owner-scoped-order-index

Precondition: the proposal is approved by a human (separate GO), and the M1a connection
registry interface shape is agreed. Until M1a merges, tasks use the fail-closed default
`ConnectionAuthority` and a test fake.

- [ ] 1. Create `internal/providerorders` with id generators (`pord_`, `pef_`), the
  versioned `BasketFingerprint` and `MutationIntentHash` encoders, the `ActionKind`
  constant `provider.fake.basket.mutate`, `OwnerDecidedKinds`, and the `Target`
  builder/parser — DoD: pure functions with unit tests (golden vectors, length-prefix
  collision cases, parse(build(x)) == x); `go vet` and `golangci-lint` clean.
- [ ] 2. Postgres store: `provider_orders`, `provider_order_snapshots`,
  `provider_effects` created idempotently at init; `CreateOrder`, `AppendSnapshot`,
  `Finalize` (CAS), `Order(id, tenant, owner)`, `OrderForTarget`, `CreateEffect`
  (idempotent per (requested_by, idempotency_key), UNIQUE execution_id and approval_id),
  effect state CAS transitions, `SetDispatchDeadline` (write-once) (depends on 1) — DoD:
  store tests against Postgres; uniform `ErrOrderNotFound`; no UPDATE/DELETE on
  snapshots in package SQL.
- [ ] 3. `ConnectionAuthority` interface, `unavailableAuthority` default, test fake, and
  `checkpoint()` adapter that builds `contract.Inputs` and calls
  `internal/automation/contract.Decide` (depends on 1) — DoD: table tests mapping
  revoked/expired/stale-revision/non-member/unavailable to the contract codes.
- [ ] 4. Additive `workitems.Store.ReserveActionApprovalTx(ctx, tx, ...)` sharing the SQL
  of `ReserveActionApproval` — DoD: existing action approval tests unchanged and green;
  new test proves identical refusals inside a transaction.
- [ ] 5. `EffectSigner` (Ed25519, version tag `mctl-provider-effect/v1`), modelled on
  `commerce.DispatchSigner`, plus a `VerifyEffectAuthorization` for the worker contract
  (depends on 1) — DoD: deterministic signature tests, tamper tests for every field,
  no-key -> `dispatch_unavailable`.
- [ ] 6. `Boundary.Dispatch`, `Boundary.Report`, `Boundary.ReadBack` per design
  section 5; definitive outcomes spend the receipt (`SettleActionApproval(..., true)`),
  unknown keeps it in_flight, read-back uses deadline + `commerce.MaxClockSkew`
  (depends on 2, 3, 4, 5) — DoD: unit tests with the fake provider for every branch.
- [ ] 7. Owner-decider branch in `DecideActionApproval`
  (`internal/api/handlers_action_approvals.go`) for `OwnerDecidedKinds` only: human,
  direct, owner principal, live tenant member, live connection (depends on 2, 3) — DoD:
  handler tests; all existing decision tests unchanged and green.
- [ ] 8. HTTP handlers and routes under `PROVIDER_ORDERS_ENABLED` in
  `internal/api/router.go`; worker routes require scope `provider-orders:effect`;
  config read in `cmd/api/main.go` with fail-closed defaults (depends on 6, 7) — DoD:
  routes 404 with the switch off; handlers use `writeError`/`writeJSON`.
- [ ] 9. Audit entries and `mctl_provider_effects_total{action_kind,outcome}` metric
  (depends on 6) — DoD: test asserts audit fields present and that no basket content,
  raw provider ref, signature or other tenant's order id appears.
- [ ] 10. `internal/providerorders/fakeprovider` test-support package and the contract
  test suite in Tests below (depends on 6, 8) — DoD: all T-tests green in CI.
- [ ] 11. Contract doc `docs/provider-effect-contract.md` describing the worker
  ingress verification, operation-key dedupe, read-back endpoint, scoped credential,
  and "no task-queue identity" rule (depends on 5, 6) — DoD: reviewed alongside the PR.
- [ ] 12. Independent review and green CI; do not enable the switch in any environment
  (release gate is a later decision) — DoD: PR approved; deploy unchanged.

## Tests

All provider-side assertions use the fake provider's write counter.

- [ ] T1. Two tenants: tenant B's owner cannot read, finalize, approve or dispatch
  tenant A's order; response identical to a nonexistent id; writes == 0.
- [ ] T2. Same tenant, different owner: same as T1 inside one tenant.
- [ ] T3. Foreign order id in the `aar_` target (approved for order X, presented for
  order Y): reserve refused; writes == 0.
- [ ] T4. Stale install revision: order created at rev 1, connection now rev 2;
  dispatch refused; writes == 0. Reconnect (new connection id) cannot revive an old
  receipt.
- [ ] T5. Revocation during activity: membership or connection revoked after approval,
  before dispatch -> refused, writes == 0; revoked between dispatch and callback ->
  callback recorded, status read refused for the revoked owner.
- [ ] T6. `hir_` answer present, no approved `aar_` -> writes == 0.
- [ ] T7. Approved `aar_` from a different `we_`, or with a different mutation intent
  hash or basket fingerprint -> writes == 0.
- [ ] T8. Expired, denied, already executed, and in_flight receipts -> refused;
  writes == 0.
- [ ] T9. Wrong deciders: platform human admin, agent token, relayed surface and the
  requester itself are refused for the provider-order kind; owner succeeds.
- [ ] T10. Duplicate dispatch signals (N concurrent calls, same effect): exactly one
  authorization fence, identical bytes returned, writes == 1.
- [ ] T11. Repeated callbacks: same terminal outcome twice is idempotent; conflicting
  outcome refused and audited.
- [ ] T12. Timeout after apply: outcome unknown, receipt stays in_flight; read-back
  finds the operation -> succeeded; writes == 1 overall.
- [ ] T13. Timeout before apply: read-back not found before deadline+skew -> unknown;
  after -> failed; no re-dispatch; writes == 0.
- [ ] T14. Idempotency key reuse: same key + same intent -> same effect; same key +
  different intent -> `idempotency_key_reused`, writes == 0.
- [ ] T15. Definitive no-effect failure spends the receipt; a second dispatch with the
  same `aar_` is refused.
- [ ] T16. Negative canary: a valid grant moves the counter to exactly 1 (proves the
  counter works), and a deliberately mismatched grant in the same suite leaves it at 0.
- [ ] T17. No secrets in workflow payloads: the worker contract fixtures contain only
  opaque ids; a `secretscan` pass over audit output and fixtures finds nothing.
- [ ] T18. Switch off: every new route 404; `DecideActionApproval` behaviour for
  existing kinds unchanged (existing suite).
- [ ] T19. Unavailable authority (default `ConnectionAuthority`): every checkpoint
  denies with `authority_unavailable`; writes == 0.

## Rollback

The feature is additive and default off. To roll back: set
`PROVIDER_ORDERS_ENABLED=false` (routes disappear, and the owner-decider branch in
`DecideActionApproval` is also gated on the switch, so a provider-order `aar_` falls
back to today's human-admin-only rule and can never be dispatched) or revert the PR. The
three new tables can be left in place (unused) or dropped manually; no existing table
or `aar_` row is modified, so no data migration is needed. Any effect left `unknown`
at rollback time keeps its receipt in_flight (fail closed) and is resolved by the
fake provider read-back before re-enabling.
