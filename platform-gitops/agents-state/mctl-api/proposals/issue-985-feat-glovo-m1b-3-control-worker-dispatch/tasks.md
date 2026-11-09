# Tasks: issue-985-feat-glovo-m1b-3-control-worker-dispatch

Blocking dependencies (amended 2026-11-09 (b); round 4, X-3: #986 merges before this slice and
provides `bridge.ApplyReadSchemaTx`):
- the amended #959 store, with tx-scoped `LockOwnerShared` and `LiveConnectionTx`,
  `Ready`, `MembershipRevocationWired`, and connection-ending paths that call the hook
  in the same tx (mctl-api#957 design §6d.4);
- the #988 order index (control-path methods);
- the amended #989 methods and `receipt.Fence`;
- the #1059 approval-basket payload for Glovo `place_order_fake` (OPEN-985-8);
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
  - `WriteFence.PreLock(ctx, tx, c bridge.Caller, commandID)`, called by `permitTx`
    before `lockOwned`, with a no-op on `refusingFence`;
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
- [ ] 5. Implement `Dispatcher.Dispatch` exactly as in design §5 (depends on 2, 4),
  including the explicit `Sequence` and the refusal of `created=false`. DoD: every write
  commits or rolls back together.
- [ ] 6. Implement `Dispatcher.Cancel` as in design §6 (depends on 2, 4):
  - `RevokeGlovoApprovalTx` before dispatch;
  - after `Store.Cancel`, effect `none` gives order `cancelled` and receipt `unknown`;
    effect `unknown` gives order `unknown` and leaves the `consumed` receipt untouched;
  - completed returns 200 unchanged;
  - no path returns the receipt to `approved`.

  DoD: covered by T6-T8.
- [ ] 7. (Moved to #989.) The fence implementation (`PreLock` body and `Check`) is #989's
  `receipt.Fence`. This slice keeps the `PreLock` hook in `permitTx` (task 4) and the
  wiring (task 9). DoD: none here.
- [ ] 8. Add the HTTP layer in `internal/api/handlers_glovo_control.go` and `router.go`
  (depends on 1, 5, 6):
  - the four routes of design §2a;
  - `glovoControlWorkerGate` and `requireGlovoControlWorker`;
  - strict bodies;
  - `Idempotent-Replayed` on replay;
  - the §2b status table;
  - an `httprate` bucket keyed by (principal, tenant);
  - an ids-only audit.

  DoD: no route accepts or returns a payload. The OpenAPI doc is not updated (these are
  internal routes); they are listed in `docs/glovo-control.md` instead.
- [ ] 9. Wire it in `cmd/api/main.go` (depends on 3, 8 and #989's `receipt.Fence`):
  - `const controlGateOpen = false` backing `glovo.ControlDefault`;
  - the env `MCTL_GLOVO_CONTROL_ENABLED`;
  - the dispatcher, with #959, #988 and #989 collaborators nil until they land.

  - the #959 store built with `glovo.NewStore(ctx, pool, runtimeRole,
    glovo.WithExplicitURL(true), glovo.WithRevocationHook(bridge.CancelOpenForConnections))` (amended (c)).

  Call `SetFence(receipt.NewFence(...))` only when all six preconditions of design §7.3
  hold. DoD: the default build mounts no route and keeps `refusingFence`.
- [ ] 10. Write `docs/glovo-control.md` and reference it from the "Write fence" section
  of `docs/bridge.md`. It covers the principal, the routes, the code table, the global
  lock order (a pointer to #957 design §6b), the one-database rule and proof, the revoker contract, and the
  three fence preconditions. DoD: reviewed against the amended #959 and #988.
- [ ] 11. Run `go fmt`, `go vet`, `golangci-lint` and `go test ./...`. The MCP tool count
  does not change. DoD: CI is green.

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
- [ ] T4. An expired `aar_` and an `aar_` past `fresh_until` both return
  `approval_expired`, and nothing is written.
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
  - `completed` gives 200 and changes nothing.

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
- [ ] T23. Read routes: `read_command_result` and `read_approval` return only the
  fields of §2a. A sentinel placed in the stored result never appears in the response.
  A command of another tenant or a non-Glovo kind returns `not_found`.
- [ ] T24. End-to-end revocation fence (moved here from #959 T17, amended (c)): with the
  real #959 store, the real `bridge.CancelOpenForConnections` hook and #989's
  `receipt.Fence`, and a command that is reserved but not yet permitted: a `Revoke`, a
  `Reconnect` (`superseded`) and an `expires_at` that passes with no `Transition` are
  each followed by a permit attempt, and none gives a permit. A `PreLock` for a foreign
  or absent command id answers `ErrCommandNotFound` before any lock is taken.
- [ ] T25. Dispatch payload and refs: the enqueued payload is byte-equal to the order's
  final snapshot; `workflow_id` equals `glovo.control_starts.workflow_id`; `run_id` is
  `''` before the workflow started and the started run id after.
- [ ] T26. Role model negative tests (#957 §6d.1 R5, owner decision 2026-11-09). Round 4 (F3), selector outcomes: with `bridge_schema_version` present and `GLOVO_DB_URL` unset, a probe error injected, and a version row older than the compiled level, the bridge is `not_ready` and `NewStore` is never called (a pgx tracer sees no DDL; red with the fallback restored); with the table absent `NewStore` runs unchanged; with the table present and the old `COMMERCE_DB_URL` role, the `to_regclass` probe succeeds although that role has no privilege on the table. With a
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

## Rollback

- Everything is dark by default: the const `controlGateOpen` is false and
  `MCTL_GLOVO_CONTROL_ENABLED` is unset. Unsetting the env var removes the routes and
  leaves the fence `refusingFence`. It does not change the bridge's store: once
  `bridge.ApplySchema` has run, the bridge stays on `NewRuntimeStore` and the shared pool,
  so existing bridge consumers keep working; going back to `NewStore` needs an explicit
  ownership hand-back by an operator (OPEN-957-6).
- Code rollback is a revert of the PR. The schema artifacts can stay, or be removed
  with `DROP INDEX IF EXISTS bridge_commands_mutating_approval`,
  and `DROP TABLE IF EXISTS bridge_colocation_probe`. Reverting `PreLock` restores the old
  permit path, which only ever ran with `refusingFence` in production.
- If commands were enqueued before the rollback, cancel the open ones with the existing
  procedure in `docs/bridge.md`. Hold mctl-gitops#2457 stays ON throughout, so no
  provider effect is possible.
