# Tasks: issue-985-feat-glovo-m1b-3-control-worker-dispatch

Blocking dependencies (amended 2026-11-09 (b); round 4, X-3: #986 merges before this slice and
provides `bridge.ApplyReadSchemaTx`):
- #957 task A14, `glovojoin.ControlStartTx` (merge order #957 §6d.1; `control` imports `glovojoin`, never the reverse; round 6, G3);
- the amended #959 store, with tx-scoped `LockOwnerShared` and `LiveConnectionTx`,
  `Ready`, `MembershipRevocationWired`, and connection-ending paths that call the hook
  in the same tx (mctl-api#957 design §6d.4);
- the #988 order index (control-path methods);
- the amended #989 methods and `receipt.Fence`, merged first (#989 task 7 also defines
  `WriteFence.PreLock`, so there is no cycle, 2026-11-10);
- the #1059 `command-place-order-fake.schema.json` and approval basket as vendored by #986 (write schema, wire version, Claim gating) and #988 (basket) (OPEN-985-8, closed);
- #987, which drops the bridge's `AUDIT_DB_URL` fallback.

With any of them missing, the code merges with nil collaborators and answers
`not_ready`.

- [ ] 1. Add the control-worker principal in `internal/auth/glovo_control_worker.go`.
  - Principal `service:glovo-control-worker`, permission `glovo:control-dispatch`.
  - Config `MCTL_GLOVO_CONTROL_WORKER` with `issuer`, `subject`, the exact audience
    `mctl-api-glovo-control`, and a required non-empty `tenants` bound.
  - Claim pinning with the `PinClaims` pattern (`bridge_provider.go:155`).
  - `User.IsGlovoControlWorker()`.
  - The verifier is test-only until mctl-gitops#2506.

  DoD: only the configured workload token maps to the principal. A config without
  `tenants` disables it. The facade, bridge-provider, #961 Glovo-worker,
  orchestrator-DevLoop, OIDC, agent and CI tokens never map to it. The production build
  wires no verifier.
- [ ] 2. Create the `internal/glovo/control` package. It holds the `OrderIndex`,
  `Receipts` (the #989 method set), `Connections` and `Membership` interfaces of design
  §3, the `Dispatcher`,
  `Ready()`, and the closed code table of design §2b (codes taken from the #959
  `glovo.Code` enum; no new vocabulary).

  DoD: it compiles with nil collaborators, and `Ready()` returns `not_ready`. A unit
  test enumerates the code table and fails on any code outside #1044 M10 plus the #959
  enum.
- [ ] 3. Add `control.ProveOneDatabase` (depends on 2), as in design §4:
  - the nonce through `bridge_colocation_probe`;
  - `pg_is_in_recovery`;
  - `to_regclass`;
  - `has_schema_privilege`, `has_table_privilege` and `has_column_privilege` for the
    full grant table of mctl-api#957 design §6d.1, nothing beyond it; one runtime role
    shared by the bridge and Glovo pools (`glovoStore.Pool() == bridgeStore.Pool()`),
    owning nothing, member of no owner role, with `rolsuper`, `rolcreaterole`,
    `rolcreatedb` and `rolbypassrls` all false, and every guard trigger present with
    `tgenabled = 'O'` (round 3, F1); no `glovo` access for the work-items role (amended (c));
  - explicit `GLOVO_DB_URL` and `WORK_ITEMS_DB_URL` with no fallback; the bridge store
    on the `GLOVO_DB_URL` pool (#957 §6d.1 R4).

  DoD: a missing env var, a nonce not found, a missing table or a wrong privilege makes
  the dispatcher `not_ready` permanently, and no URL is logged.
- [ ] 4. Bridge changes in `internal/bridge` (depends on 2):
  - (2026-11-10) no `WriteFence` code here: `WriteFence.PreLock(ctx, tx, c bridge.Caller,
    commandID)`, its call in `permitTx` before `lockOwned` and the no-op on
    `refusingFence` are defined by #989 task 7, which merges before this slice. This task
    only relies on the hook; T14 and T21 prove the lock order with the real fence;
  - (round 7, F2) `bridge.Store.CommandEffect(ctx, q, tenants, commandID) (status, effectState
    string, err error)`: read-only; a foreign tenant, a non-`place_order_fake` kind and an absent
    id are all `not_found`;
  - (round 7, F1) `NewRuntimeStore` calls #986 `EnableWireVersions` after `CheckReadLevel`; no
    other versioning code is written here (owner: #986 task 2);
  - (amended (c)) `bridge.ApplySchema(ctx, migrationConnStr, runtimeRole)` under the
    migration role: `bridgeSchema`, the `bridge_commands_mutating_approval` partial
    unique index, the `bridge_colocation_probe` table, `bridge_schema_version` (the mode
    selector, written last; refuses with an error naming the tables when they exist under
    another owner, OPEN-957-6), #986's read objects (one call to `bridge.ApplyReadSchemaTx(ctx, tx, runtimeRole)` inside the same transaction, round 4 X-3) and the grants
    of mctl-api#957 design §6d.1; and `bridge.NewRuntimeStore(ctx, pool)` on the shared
    `GLOVO_DB_URL` pool, which runs no DDL and only checks the schema version, #986's `bridge.CheckReadLevel` (`not_ready` below the compiled read level, round 4 R3-3) and the
    grants. `cmd/api/main.go` uses it whenever the `bridge_schema_version` row exists (whatever the Glovo flags say, round 3 F2), instead of `NewStore`
    (`internal/bridge/store.go:365-379`, which runs `bridgeSchema` at `:374` on every
    start at origin/main `ceac9ed`). This is the owner-mandated bridge startup AMEND
    (#957 §6d.1): `glovo_runtime` gets no extra right to make the old startup pass, and
    `NewStore` stays unchanged for deployments that never ran the migrator. `cmd/bridge-scrub` keeps
    `OpenExistingStore` under its own maintenance role with the grants #957 §6d.1 lists;
    No `SECURITY DEFINER` function;
  - `bridge.CancelOpenForConnections(ctx, tx, gcnIDs, actor)`, a plain Go function.

  DoD: the existing permit tests pass unchanged. `bridge.ApplySchema` applies twice in a
  row and fails under the runtime role; `NewRuntimeStore` runs no DDL (pgx tracer). A
  second `place_order_fake` row with the same `aar_` fails at insert. `CancelOpenForConnections` locks
  `ORDER BY command_id` and keeps the semantics of `Store.Cancel` (a permitted effect
  becomes `unknown`).
- [ ] 4b. (2026-11-10, review) Bound the membership call. Change `receipt.Membership` (merged
  by #989 task 7 as `IsMember(tenant, principalID string)`, `internal/glovo/receipt/fence.go:45`,
  call at `:265`) and the #985 `control.Membership` to `IsMember(ctx context.Context, tenant,
  principalID string)`; both callers wrap the call in `context.WithTimeout(ctx,
  MembershipTimeout)` (one named constant, 2 s, defined once in `receipt` and used by
  `control`), return `unavailable` on error, timeout or cancellation, and never hold L3, L4
  or L5 past the bound. Update the merged #989 tests for the new signature. DoD: T15a;
  mutation: remove the timeout wrapper and T15a fails.
- [ ] 5. Implement `Dispatcher.Dispatch` exactly as in design §5 (depends on 2, 4),
  including the explicit `Sequence` and the refusal of `created=false`. DoD: every write
  commits or rolls back together. Round 7 (F1): it passes `WireVersion: bridge.WireV1alpha2` and
  vendors nothing (#986 task 1 vendors #1059 `command-place-order-fake.schema.json`). A test
  enqueues the real approval-basket payload through the real `Store.Enqueue` and asserts that the
  stored row is wire v1alpha2 and that its claim projection validates against #986's vendored
  schema (red with `WireVersion` omitted: the v1alpha1 schema refuses the basket and dispatch is
  never green).
- [ ] 6. Implement `Dispatcher.Cancel` as in design §6 (depends on 2, 4):
  - `MarkCancelled` for an `open` order (no `Revoke`), `RevokeGlovoApprovalTx` then `MarkCancelled` for a `finalized` one;
  - for a `dispatched` order, `Store.Cancel` (nil or `ErrAlreadyCompleted`) and then `reconcileOrder` (design §2a, the one owner of every row); terminal orders write nothing;
  - no path returns the receipt to `approved`.

  DoD: covered by T6-T8.
- [ ] 7. (Moved to #989.) The fence implementation (`PreLock` body and `Check`) is #989's
  `receipt.Fence`, and since 2026-11-10 so is the `PreLock` hook definition and its call
  in `permitTx` (#989 task 7). This slice keeps only the wiring (task 9). DoD: none here.
- [ ] 8. Add the HTTP layer in `internal/api/handlers_glovo_control.go` and `router.go`
  (depends on 1, 5, 6):
  - the four routes of design §2a, including the round 7 result-to-order table (design §2a, `reconcileOrder`) and, in task 4, `bridge.Store.CommandEffect` (read-only, `(status, effectState)`, for #957 §3a);
  - `glovoControlWorkerGate` and `requireGlovoControlWorker`;
  - strict bodies;
  - `Idempotent-Replayed` on replay;
  - the §2b status table;
  - an `httprate` bucket keyed by (principal, tenant);
  - an ids-only audit;
  - round 5 (N4): `internal/glovo/control/contract/*.json` and `SHA256SUMS` (design §2a).

  DoD: no route accepts or returns a payload; a test fails when a route, a status code or a body field drifts from the contract files. The OpenAPI doc is not updated (these are
  internal routes); they are listed in `docs/glovo-control.md` instead.
- [ ] 9. Wire it in `cmd/api/main.go` (depends on 3, 8 and #989's `receipt.Fence`):
  - `const controlGateOpen = false` backing `glovo.ControlDefault`, in `internal/glovo/gate_release.go`, with the `glovojoin_fixture` twin `internal/glovo/gate_fixture.go`; `DispatchCommandTTL` in `internal/glovo/control/ttl_release.go` / `ttl_fixture.go` (design §7.4, round 8);
  - the env `MCTL_GLOVO_CONTROL_ENABLED`;
  - the dispatcher, with #959, #988 and #989 collaborators nil until they land.

  - the #959 store built with `glovo.NewStore(ctx, pool, runtimeRole, migrationRole,
    glovo.WithExplicitURL(true), glovo.WithRevocationHook(bridge.CancelOpenForConnections))` (amended (c)).
  - Amended 2026-11-10, the hook swap. Today `cmd/api/glovo_team_grant.go` builds the store with
    `glovo.WithRevocationHook(syntheticRevocationHook)` (a no-op returning nil) in
    `glovoStoreOptions()`. This task replaces it in that function (the one place the
    options are built), so no code path of a Glovo-enabled build keeps the synthetic
    hook. At startup `main.go` asserts that the installed hook IS
    `bridge.CancelOpenForConnections`; if it is not, the fence stays `refusingFence`,
    the dispatcher is `not_ready`, and one log line names the reason (no secret).
  - `MembershipRevocationWired()` is satisfied only by the positive signal of design §7.3
    item 5. Interim: false, so the fence stays `refusingFence`. OPEN-985-2 is unchanged.

  Call `SetFence(receipt.NewFence(...))` only when all six preconditions of design §7.3
  hold. DoD: the default build mounts no route and keeps `refusingFence`; a test refuses
  the fence install with the synthetic hook (T24 b), and with a hook that is not
  `bridge.CancelOpenForConnections` (T24 c); mutation: revert the swap in
  `glovoStoreOptions()`, or delete the startup assertion, and T24 b fails.
- [ ] 10. Write `docs/glovo-control.md` and reference it from the "Write fence" section
  of `docs/bridge.md`. It covers the principal, the routes, the code table, the global
  lock order (a pointer to #957 design §6b), the one-database rule and proof, the revoker contract, and the
  six fence preconditions (design §7.3). DoD: reviewed against the amended #959 and #988.
- [ ] 11. Run `go fmt`, `go vet`, `golangci-lint` and `go test ./...`. The MCP tool count
  does not change. DoD: CI is green.

## Definition of done for security tests (2026-11-10)

Every security test below, T2/T19 (exactly-one), T12-T14 and T24 (revocation races and the
end-to-end fence), T21 (deadlock freedom), T17 (missing config), T26 (role model) and T29
(fixture seam), must fail with its fix reverted, and the PR records the mutation it used. A
test that cannot be made red is not a test of the control. Each carries one `mutation:`
line, repeated in the PR description with the red output:

- T2 / T19: mutation: drop the `FOR UPDATE` on the order lock (L3) or the unique index
  `bridge_commands_mutating_approval`; the exactly-one assertion fails.
- T12: mutation: take L2 shared after L3 instead of before; the order-A interleaving
  deadlocks or dispatches over a revoked connection.
- T13 / T14: mutation: make `CancelOpenForConnections` skip `reserved` commands, or have
  `receipt.Fence.Check` ignore the connection; a permit is issued after a revoke.
- T24: mutation: see T24 (hook swap reverted).
- T21: mutation: call `lockOwned` before `PreLock`; a `40P01` appears at some paused
  interleaving.
- T17: mutation: let one precondition of §7.3 default to true; the matching case installs
  the fence.
- T26: mutation: grant `glovo_runtime` one extra right (`TRIGGER`), or skip the
  `CheckReadLevel` call; the proof or the selector case fails.
- T29: mutation: as listed in T29 (const flipped; fixture file in the release list;
  `receipt.Ready` skipped).

## Tests

All DB tests follow the Postgres harness pattern of `internal/bridge/store_pg_test.go`.
Fake order, receipt and connection tables are created in the same database, and the #959
advisory keys are used.

- [ ] T1. Repeated dispatch with the same order, `aar_` and fingerprint: the same
  `cmd_`, `Idempotent-Replayed: true` on the second call, and one `bridge_commands` row.
  Round 4 (F2): the same call after the command's result (order `closed`), after a cancel of
  the dispatched command (order `cancelled`) and after a sweeper `unknown` returns the same
  `cmd_` with the current `order_state` and `effect_state`; a different `aar_` on each of
  those orders is `approval_replayed`; an order cancelled before dispatch is
  `invalid_transition` (with the replay condition narrowed back to `dispatched` the first
  three fail).
- [ ] T2. Concurrent dispatch: N goroutines on the same order. Exactly one row exists,
  and every success returns the same `cmd_`.
- [ ] T3. A different `aar_` on a dispatched order returns `approval_replayed`, and no
  row is added.
- [ ] T4. (see also T4a) An expired `aar_` and an `aar_` past `fresh_until` both return
  `approval_expired`, and nothing is written.
- [ ] T4a. (2026-11-10) Reserve-margin boundary: with `fresh_until - now` of 119 s dispatch
  answers 409 `approval_expired`, writes nothing, and `bridge_commands` has no row; with
  121 s it enqueues, and the TTL equals the time left (capped at `fresh_until`, below
  `DispatchCommandTTL`). The check sits before `Enqueue` (a row count of zero proves it,
  not the rolled-back transaction). mutation: move the check after `Enqueue`, or compare
  with `< 0` instead of `<= ReservePermitMargin`, and the 119 s case fails.
- [ ] T5. These all return `approval_invalid`: an `aar_` in each generic work-items
  state (`consumed`, `in_flight`, `executed`), a pending, refused or `unknown` receipt, and
  a non-Glovo-kind `aar_`. A receipt reserved for another command returns
  `approval_replayed`.
- [ ] T6. Dispatch after cancel returns `invalid_transition`, and the receipt is `refused`,
  never `approved`.
- [ ] T7. Cancel after dispatch, for a command in each state:
  - `pending` gives order `cancelled` and effect `none`;
  - `leased` with a permit (effect `permitted`) gives order **`unknown`** and effect
    `unknown`, never `cancelled`;
  - `completed` gives 200 and applies the §2a row (round 7): effect `succeeded` gives order
    `closed`; effect `none` gives `closed` and the receipt `unknown`; an `expired` command with
    effect `none` gives `cancelled` and the receipt `unknown`.

  A later `IssueWritePermit` returns `command_cancelled`.
- [ ] T8. A repeated cancel is a no-op with 200. Amended (c): a cancel after #989
  already refused the `aar_` for this order, and a cancel after the #989 sweeper marked
  it `unknown` for this `cmd_`, both succeed and leave the receipt state unchanged.
- [ ] T9. A foreign tenant, a foreign owner, an order outside `tenants`, and an unknown
  order all return 404 `not_found` with an identical body.
- [ ] T10. A changed intent hash, install revision, `we_` or connection returns
  `intent_mismatch`. A changed fingerprint (body or binding) returns `basket_changed`.
- [ ] T11. Each of these, before dispatch, returns its §2b code and nothing is written:
  a revoked connection, an expired one, an absent one, and a moved install revision.
- [ ] T12. Revocation race, order A (deterministic): the revoker holds L2 exclusive
  uncommitted, dispatch blocks, the revoker commits, and dispatch then returns
  `connection_revoked`.
- [ ] T13. Revocation race, order B: the dispatch holds L2 shared uncommitted, the
  revoker blocks, the dispatch commits, and the revoker proceeds and cancels the command.
  A later permit is refused (`command_cancelled`). The same test with the permit already
  issued shows effect `unknown`.
- [ ] T14. The same two race orders against #989's `receipt.Fence` inside `IssueWritePermit`.
- [ ] T15. Membership: a fake `Membership` returning false gives `no_tenant`, and an
  error gives `unavailable`.
- [ ] T15a. (2026-11-10) Membership is bounded. A fake `Membership` that blocks until its
  `ctx` is cancelled makes dispatch answer `unavailable` within `MembershipTimeout` plus a
  small margin; a second connection that asks for the same `tenant`/`owner` L3 or L4 lock
  during the hang gets it no later than `MembershipTimeout` after the hang began (it does
  not wait for the provider). The same test in #989 `Check` with L5 held: a hung provider
  gives `unavailable` and L5 is free after `MembershipTimeout`. A provider that ignores
  `ctx` is not a case the code can fix; the wrapper must return on `ctx.Done()` and the
  test uses such a fake. mutation: remove the `context.WithTimeout` (or pass
  `context.Background()`) and this test fails by timeout.
- [ ] T16. Wrong principal: each of these is refused with 403 before any store call (a
  fake store records zero calls):
  - a human user, an admin, a Glovo-audience facade token, a bridge-provider token;
  - the #961 Glovo worker, the orchestrator-DevLoop principal, an agent token, a CI
    token, a surface principal (amended (c));
  - a control-worker token with a wrong `aud`, `iss` or `sub`, expired, or before `nbf`.

  A production build wires no control-worker verifier (build-tag test).

  A control-worker token on any other route is refused with 403 by the confining gate.
- [ ] T17. Missing config: each of these gives 503 `not_ready` with zero writes:
  - each of the three DB env vars unset;
  - the nonce not visible through one pool;
  - a missing table or privilege;
  - nil #959, #988 or #989 collaborators.

  The default build has no route (404), and the fence is `refusingFence`. Amended (c):
  one case per §7.3 precondition; with the other five true and that one false,
  `SetFence` is not called. The proof cases include each missing grant of #957 §6d.1,
  an extra grant, and a runtime role that owns a `glovo` table.
- [ ] T18. Body hygiene: unknown fields (for example `payload`, `endpoint` or
  `execution_id`) give 400 `invalid_request`. Audit entries and logs contain no payload,
  nonce, lease token or credential. Order events name the control worker as actor.
- [ ] T19. Exactly-one invariant: a property test over random interleavings of
  dispatch, cancel, revoke and permit. Each `aar_` has at most one `place_order_fake`
  row and at most one `bridge_write_permits` row, and no receipt ever returns to
  `approved`.
- [ ] T20. #957 §6b boundary: the #957 prepare writes and this dispatch run in one
  `pgx.Tx`. A failure injected after the last statement leaves no row from either side.
- [ ] T21. Deadlock freedom: deterministic interleavings of a permit (`PreLock` path)
  against `Revoke`, `RevokeInstall` and a #985 cancel, with each side paused at every
  lock level. No `40P01` occurs, and every run ends in one of the two outcomes of design
  §7.2.
- [ ] T22. A crash between commit and the HTTP response: the retry returns the same
  `cmd_` with `Idempotent-Replayed: true`, also when the command completed or was cancelled
  in between (round 4, F2). A `read_command_result` after the crash
  returns the command.
- [ ] T23. Read routes (round 5, X-4; round 8, B1: a `cancelled` and an `expired` command return the triples of design §2a over every `effect_state` value, with `none` and `not_performed` giving the `cancelled` / `failed_terminal` triple and every other value `provider_effect: unknown`): `read_command_result` and `read_approval` return only the
  fields of §2a. A sentinel placed in the stored result never appears in the response.
  A command of another tenant or a non-Glovo kind returns `not_found`.
- [ ] T24. End-to-end revocation fence (moved here from #959 T17, amended (c)): with the
  real #959 store, the real `bridge.CancelOpenForConnections` hook and #989's
  `receipt.Fence`, and a command that is reserved but not yet permitted: a `Revoke`, a
  `Reconnect` (`superseded`) and an `expires_at` that passes with no `Transition` are
  each followed by a permit attempt, and none gives a permit. A `PreLock` for a foreign
  or absent command id answers `ErrCommandNotFound` before any lock is taken.
  Amended 2026-11-10, four more cases: (b) a store built with `syntheticRevocationHook`
  never gets a fence (`SetFence` not called; refused with the reason logged); (c) a hook
  that is neither the synthetic one nor `bridge.CancelOpenForConnections` is refused the
  same way; (d) `MembershipRevocationWired()` with the label set but no detector signal,
  and with a stale signal, is false and the fence stays `refusingFence`; with a fresh
  signal it is true. mutation: swap `bridge.CancelOpenForConnections` back to the
  synthetic hook in `glovoStoreOptions()` and (b) and the main permit case fail (the permit
  is issued after a `Revoke`).
- [ ] T25. Dispatch payload and refs (round 5, N3: assert every `EnqueueInput` field, including `ProviderRef == binding.provider`, `Tenant`, `OwnerPrincipalID`, `InstallRevision` and `TTL` capped at `fresh_until`): the enqueued payload is byte-equal to the order's
  final snapshot; `workflow_id` equals `glovo.control_starts.workflow_id`; `run_id` is
  `''` before the workflow started and the started run id after.
- [ ] T26. Role model negative tests (#957 §6d.1 R5, owner decision 2026-11-09). Round 5 (#986 F3): with `bridge_read_schema_version` missing or below the compiled read level `NewRuntimeStore` gives `not_ready` (red with the `CheckReadLevel` call removed). Round 4 (F3), selector outcomes: with `bridge_schema_version` present and `GLOVO_DB_URL` unset, a probe error injected, and a version row older than the compiled level, the bridge is `not_ready` and `NewStore` is never called (a pgx tracer sees no DDL; red with the fallback restored); with the table absent `NewStore` runs unchanged; with the table present and the old `COMMERCE_DB_URL` role, the `to_regclass` probe succeeds although that role has no privilege on the table. With a
  runtime role that has `CREATEROLE`, or `CREATEDB`, or a disabled guard trigger
  (`tgenabled <> 'O'`), each giving `not_ready` with zero provider writes (round 3, F1);
  after `bridge.ApplySchema`, with every Glovo flag off, the bridge provider routes still
  work on the shared pool and no DDL is sent (round 3, F2); with a runtime role that has
  an extra `TRIGGER`, `CREATE` or ownership, or lacks one listed
  DML right, or a Glovo pool whose `current_user` is not the configured role, the proof
  fails and the dispatcher is `not_ready`; `glovo_runtime` cannot `ALTER TABLE …
  DISABLE TRIGGER`, `CREATE TABLE` or `DROP`; the work-items and commerce roles get
  `permission denied` on every `glovo.*` table; with Glovo enabled, startup sends no
  DDL (pgx tracer); the existing bridge tests (`NewStore`, Glovo disabled) and the
  bridge-scrub test pass unchanged; the fake provider sees zero writes in every case.

- [ ] T27. (Round 7, F2; round 8, B1 to B7) The result-to-order table is total. `TestReconcileOrderTable` calls `reconcileOrder` directly over every command status (`pending`, `leased`, `completed`, `cancelled`, `expired`) times every `effect_state` (`none`, `permitted`, `succeeded`, `failed`, `not_performed`, `unknown`), 30 pairs, and asserts for each the #988 call, the #989 call, the stored order state and, for every pair of the catch-all row, 503 `unavailable` with nothing written, with the order `dispatched`. One more case: a pair of the catch-all row on a `closed`, `cancelled` and on an `unknown` order gives 200, no call and no write (red if the `dispatched` guard is moved after the table lookup). It uses the same cells as T23 and #957 T6. Through the callers it drives only what each can reach: `read_command_result` every pair, `Cancel` the pairs of a `pending`, `leased`, `completed` or `expired` command (a `cancelled` one is the nil path). On the `Cancel` path the pair `reconcileOrder` sees is the pair after `Store.Cancel` (design §2a, §6): a `pending` or `leased` command with effect `none` is then `cancelled`, `none` (order `cancelled`); with `permitted` or `unknown` it is `cancelled`, `unknown` (order `unknown`); `completed` and `expired` pairs are unchanged (`ErrAlreadyCompleted`). On the `ErrAlreadyCompleted` path the test also asserts the lock set: L1 shared, L2 shared, L6 read, L3, L4, L5, in that order (round 8, S-6). Cancel on each order state: `open` gives `cancelled` with no `Revoke`; `finalized` revokes; `closed`, `cancelled` and `unknown` write nothing and answer 200. A `reconcileOrder` on an order that is not `dispatched` makes no call (a second `read_command_result` after the first is a no-op, red if the guard is removed). With the `aar_` already `unknown` or `consumed`, the `MarkGlovoApprovalUnknownTx` entry is a no-op and the order `Mark*` still commits (#989 T16a). Three end-to-end cases that left the order `dispatched` before: (a) a command that expires unclaimed, (b) a provider result `failed_terminal` / `provider_rejected` with no permit, (c) `CancelOpenForConnections` on a reserved command. Each ends with the order `cancelled` or `closed` and the receipt `unknown`, and the #957 §3a wire `state` read before the transition equals the one read after it. Proven red: delete the `none` rows (the order stays `dispatched`), revert `Cancel` to "change nothing" on `ErrAlreadyCompleted` (the `expired` case stays `dispatched`), drop the L6 read or L3 from the `Cancel` path (the lock-set assertion above fails), and make the `cancelled|expired, succeeded` row `MarkCancelled` (the pair case fails).
- [ ] T28. (Round 7, F1) Dispatch uses the #986 wire-version mechanism: the stored command is wire
  v1alpha2, a provider whose `supported_versions` lacks v1alpha2 never claims it (so it expires and
  T27 case (a) applies), and `Enqueue` while `Store.WireVersionsEnabled()` is false answers `not_ready` without a
  row. These are driven through #986's code; the mechanism's own tests are #986 T4e-T4h.

- [ ] T29. (Round 8, design §7.4) Fixture seam. (a) `TestControlGateClosedInReleaseBuild` (no tag): `glovo.ControlDefault.Open` is false and `DispatchCommandTTL == 900*time.Second`. (b) `TestFixtureFilesAreTagged`: `go list -f '{{.GoFiles}}'` for the release build lists `gate_release.go` for `./internal/glovo` and `ttl_release.go` for `./internal/glovo/control` and neither fixture file, and the repository's Dockerfile and release workflow contain no `glovojoin_fixture`. (c) With the tag, the gate is open but `main.go` still leaves the fence `refusingFence` while any of §7.3 items 2 to 6 fails (one case per item). (d) `SetFixtureDispatchCommandTTL(2*time.Second)` makes the next dispatch enqueue `ttl_seconds` 2, still capped at `fresh_until`. Proven red: with the release file's const flipped to `true`, (a) fails; with the fixture file added to the release build list, (b) fails; with `receipt.Ready` skipped under the tag, (c) fails.

## Rollback

- Everything is dark by default: the const `controlGateOpen` is false (in the release file) and
  `MCTL_GLOVO_CONTROL_ENABLED` is unset. Unsetting the env var removes the routes and
  leaves the fence `refusingFence`. It does not change the bridge's store: once
  `bridge.ApplySchema` has run, the bridge stays on `NewRuntimeStore` and the shared pool,
  so existing bridge consumers keep working; going back to `NewStore` needs an explicit
  ownership hand-back by an operator (OPEN-957-6).
- Code rollback is a revert of the PR. The schema artifacts can stay, or be removed
  with `DROP INDEX IF EXISTS bridge_commands_mutating_approval`,
  and `DROP TABLE IF EXISTS bridge_colocation_probe`. Reverting the `PreLock` hook (#989 task 7) restores the old
  permit path, which only ever ran with `refusingFence` in production.
- If commands were enqueued before the rollback, cancel the open ones with the existing
  procedure in `docs/bridge.md`. Hold mctl-gitops#2457 stays ON throughout, so no
  provider effect is possible.
