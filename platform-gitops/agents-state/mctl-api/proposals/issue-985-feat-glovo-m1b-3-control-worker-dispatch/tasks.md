# Tasks: issue-985-feat-glovo-m1b-3-control-worker-dispatch

- [ ] 1. Add the control-worker principal in `internal/auth/glovo_control_worker.go`:
  `service:glovo-control-worker`, permission `glovo:control-dispatch`, config
  `MCTL_GLOVO_CONTROL_WORKER` (`issuer`, `subject`, exact audience
  `mctl-api-glovo-control`), and `User.IsGlovoControlWorker()`. A half-configured or
  reserved value disables it and logs once. DoD: unit tests show only the configured
  workload token maps to it, and facade, bridge-provider, OIDC, agent and CI
  tokens never do.
- [ ] 2. Add `ConsumeActionApprovalTx(ctx, tx, id, intentHash)` to
  `internal/workitems/action_approvals.go`, and make `ConsumeActionApproval`
  delegate to it. DoD: existing workitems tests pass unchanged, and a new test
  consumes inside a caller tx that rolls back, leaving the request `approved`.
- [ ] 3. Create the `internal/glovo/control` package (depends on 2): the
  `OrderIndex`, `Approvals`, `Connections` and `Membership` interfaces, the
  `Dispatcher`, `Ready()`, and error codes (`not_ready`, `order_not_found`,
  `order_already_dispatched`, `order_cancelled`, `order_state_conflict`,
  `approval_consumed`, `approval_expired`, `approval_binding_mismatch`,
  `connection_revoked`, `membership_revoked`, `already_completed`, `busy`). DoD: it
  compiles with nil collaborators, and `Ready()` returns `not_ready`.
- [ ] 4. Add `control.ProveColocated` (depends on 3): compare
  `pg_control_system().system_identifier` and `current_database()` across the
  bridge, work-items, order-index and connection pools, and check `to_regclass` of
  the four tables from the bridge pool. DoD: a mismatch, an error or a missing table
  makes the dispatcher `not_ready` permanently and logs no URL.
- [ ] 5. Implement `Dispatcher.Dispatch` exactly as in design section 5 (depends on
  3): order `FOR UPDATE`, replay before the `aar_` state check, `aar_` `FOR UPDATE`
  plus binding, connection `FOR SHARE`, membership, `Enqueue`
  (`place_order_fake`, `OperationKey "glovo-dispatch:"+order_ref`), order CAS,
  `ConsumeApprovalTx`, `SET LOCAL lock_timeout`. DoD: every write commits or rolls
  back together.
- [ ] 6. Add the partial unique index `bridge_commands_mutating_approval` on
  `(approval_ref) WHERE operation_kind='place_order_fake'` to `bridgeSchema` in
  `internal/bridge/store.go`. DoD: the schema test is updated, and a second
  `place_order_fake` row with the same `aar_` fails at insert.
- [ ] 7. Implement `Dispatcher.Cancel` (depends on 3): `approved -> cancelled`;
  `dispatched` calls `bridge.Store.Cancel` in the same tx and then sets
  `cancelled`; repeats are no-ops; the `aar_` is never restored. DoD: covered by
  T6-T8.
- [ ] 8. Implement `control.Fence` as a `bridge.WriteFence` that reuses the checks
  from task 5 (aar_ `consumed` and bound to the command, connection `FOR SHARE`,
  membership). DoD: unit-tested against `permitTx`, and not installed unless task 10
  gates allow it.
- [ ] 9. Add the HTTP layer in `internal/api/handlers_glovo_control.go` and
  `router.go` (depends on 1, 5, 7). It adds `glovoControlWorkerGate` (confinement)
  in the authenticated group next to `bridgeProviderGate`, and
  `requireGlovoControlWorker`. Routes are
  `POST /api/v1/internal/glovo/orders/{order_ref}/dispatch|cancel` with strict ids-only
  bodies via `readStrictJSON`, a status mapping table, a per-principal `httprate`
  bucket, and an ids-only audit. DoD: no route accepts a payload, and the OpenAPI
  doc is not updated (internal route; listed in `docs/glovo-control.md` instead).
- [ ] 10. Wire it in `cmd/api/main.go` (depends on 4, 8, 9): add the build constant
  `glovo.ControlDefault = Gate{Open: false}` and the env
  `MCTL_GLOVO_CONTROL_ENABLED`. Construct the dispatcher from the existing bridge
  and work-items stores, with M1b/1 and #959/#960 collaborators nil until they
  land. Call `SetFence(control.Fence)` only when the constant is open and
  co-location is proven. DoD: the default build mounts no route and keeps
  `refusingFence`.
- [ ] 11. Write `docs/glovo-control.md`, and reference it from `docs/bridge.md`
  "Write fence". It covers the principal, routes, codes, the transaction order, the
  co-location rule, and the revocation-writer contract (exclusive row lock plus
  `bridge.Store.Cancel` of open commands in the same tx). DoD: reviewed with the
  #959/#960 owners.
- [ ] 12. Run `go fmt`, `go vet`, `golangci-lint`, `go test ./...`. The MCP tool
  count does not change (no MCP tool added). DoD: CI green.

## Tests

All DB tests use the existing Postgres test harness pattern of
`internal/bridge/store_pg_test.go`, with fake `OrderIndex` and `Connections` tables
created in the same database.

- [ ] T1. Repeated dispatch: same order and `aar_` twice. Both calls return the same
  `cmd_`, the second has `replayed=true`, and there is one `bridge_commands` row.
- [ ] T2. Concurrent dispatch: N goroutines on the same order and `aar_`. Exactly one
  row exists, and every success returns the same `cmd_`.
- [ ] T3. Dispatch with a different `aar_` on a dispatched order returns
  `order_already_dispatched` and no new row.
- [ ] T4. Expired `aar_` and past-`fresh_until` `aar_` return `approval_expired`,
  with nothing written (order still `approved`, no command).
- [ ] T5. A consumed `aar_` (consumed for another order or by another path) returns
  `approval_consumed`.
- [ ] T6. Dispatch after cancel returns `order_cancelled`, and the `aar_` stays
  unconsumed.
- [ ] T7. Cancel after dispatch, for a command in each state: `pending` becomes
  `cancelled` with effect `none`; `leased` with a permit (effect `permitted`)
  becomes `cancelled` with effect `unknown`; `completed` returns
  `already_completed`. The `aar_` is never `approved` again, and a later
  `IssueWritePermit` returns `command_cancelled`.
- [ ] T8. Repeated cancel is a no-op with 200.
- [ ] T9. A foreign tenant, foreign owner or unknown order returns 404
  `order_not_found`, with an identical body for each.
- [ ] T10. A change to the basket fingerprint, intent hash, install revision or
  `execution_id` returns `approval_binding_mismatch`.
- [ ] T11. Revoke before dispatch returns `connection_revoked`, and nothing is
  written.
- [ ] T12. Revocation race, order A (deterministic): the revoker tx holds the
  `UPDATE` lock uncommitted, dispatch blocks on `FOR SHARE`, the revoker commits,
  and dispatch then returns `connection_revoked`.
- [ ] T13. Revocation race, order B: the dispatch tx holds `FOR SHARE` uncommitted,
  the revoker blocks, dispatch commits, the revoker proceeds and cancels the
  command, and the permit is then refused (`command_cancelled`). The same test with
  the permit already issued shows effect `unknown`.
- [ ] T14. The same two race orders against `control.Fence` inside `IssueWritePermit`.
- [ ] T15. Membership revoked (fake `Membership` returns false) gives
  `membership_revoked`, and a membership error gives `not_ready`.
- [ ] T16. Wrong principal: a human user, an admin, a Glovo-audience facade token,
  a bridge-provider token, an agent token and a CI token are each refused with 403
  before any store call (a fake store records zero calls). A control-worker token
  on any other route is refused with 403 by the confining gate.
- [ ] T17. Missing or unknown DB config: nil stores, the co-location proof failing
  (different `current_database`), and a missing table all give 503 `not_ready`
  with zero writes. The default build has no route (404) and the fence is
  `refusingFence`.
- [ ] T18. Body hygiene: unknown fields (for example `payload` or `endpoint`) give
  400. Audit entries and logs contain no payload, nonce, lease token or credential
  (assert on captured `slog` output and the audit entry).
- [ ] T19. Exactly-one invariant: property test over random interleavings of
  dispatch, cancel, revoke and permit. Each `aar_` has at most one
  `place_order_fake` row and at most one `bridge_write_permits` row.

## Rollback

- Everything is dark by default (build constant `glovo.ControlDefault` closed, and
  `MCTL_GLOVO_CONTROL_ENABLED` unset). Disabling is unsetting the env var or
  reverting the constant. The routes then disappear and the fence reverts to
  `refusingFence`.
- Code rollback is a revert of the PR. The only schema artifact is the additive
  partial index `bridge_commands_mutating_approval`, which can stay, or be removed
  with `DROP INDEX IF EXISTS`. `ConsumeActionApprovalTx` is a pure refactor.
- If commands were enqueued before rollback, cancel open ones with the existing
  bridge procedure in `docs/bridge.md` (mark open commands `cancelled`). Hold
  mctl-gitops#2457 stays ON throughout, so no provider effect is possible.
