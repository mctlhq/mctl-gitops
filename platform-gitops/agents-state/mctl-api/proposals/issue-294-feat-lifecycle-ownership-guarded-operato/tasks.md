# Tasks: issue-294-feat-lifecycle-ownership-guarded-operato

- [ ] 1. Extend the lifecycle vocabulary in `internal/lifecycle/types.go` — add
      sentinels `ErrOwnerMismatch`, `ErrVersionMismatch`, `ErrOwnerNotStuck`,
      `ErrHandoffNotStalled` to the existing `var (...)` block, and event names
      `EventFenced`, `EventHandoffRequested`, `EventHandoffRetried`,
      `EventReconcileRequested` to the existing const block. — DoD: each new
      symbol carries a doc comment in the style of its neighbours saying what it
      means and what the caller should do about it; `go vet` and
      `golangci-lint` clean; no existing symbol changed.

- [ ] 2. Add `RecoveryPreconditions`, `RecoveryRequest`, `Snapshot` and
      `RecoveryResult` to a new `internal/lifecycle/recovery.go` (depends on 1)
      — DoD: `ExpectedVersion` is `*string` so absent and empty are distinct;
      a `validatePreconditions` helper rejects an empty expected owner, a
      non-positive epoch and a nil version with typed errors rather than plain
      ones (the `store.go:1252-1263` lesson — a plain error becomes a 500).

- [ ] 3. Implement `Store.FenceDeadClaim` in `recovery.go` (depends on 2) —
      DoD: runs inside `s.inTx`; re-derives `IsDead` against the database clock;
      refuses `ErrOwnerAlive` on a live owner and `ErrNotOwner` on a
      released/terminal row; executes package-level `fenceUpdateSQL` whose
      `WHERE` pins entity triple, `epoch`, `owner_type`, `owner_id`,
      `entity_version`, `last_seen_at` and `state IN ('active','handing-off')`;
      `epoch = epoch + 1` computed by the statement; sets `state='released'`,
      `released_at`, `released_reason='fenced: …'`, clears the handoff quartet,
      preserves `owner_type`/`owner_id`; appends a `fenced` event with actor
      `human-codeowner/<principal>` and a reason naming old owner, old→new
      epoch, licensing condition and the operator text; on zero rows re-reads and
      answers the sentinel that describes what actually moved.

- [ ] 4. Implement `Store.RequestHandoff` (depends on 2) — DoD: licensed by
      `IsStuck` re-derived in-tx, refusing `ErrOwnerNotStuck` on a healthy owner,
      `ErrOwnerAlive`-adjacent guidance on a dead one (point the caller at fence),
      and `ErrNoHandoff`-adjacent refusal on a row already handing off;
      `handoffRequestUpdateSQL` pins state `active`, both empty `handoff_to_*`
      columns, epoch, owner, version; sets `state='handing-off'`, the target and
      `handoff_started_at`; leaves `epoch` untouched; appends
      `handoff-requested`.

- [ ] 5. Implement `Store.RetryHandoff` (depends on 2) — DoD: licensed by
      `HandoffStalled`, refusing `ErrHandoffNotStalled` inside the bound and
      `ErrNoHandoff` on a non-handing-off row; `handoffRetryUpdateSQL` pins both
      `handoff_to_*` columns AND the observed `handoff_started_at` (the retarget
      hazard at `store.go:560-588`) plus epoch, owner and version; changes only
      `handoff_started_at` and `updated_at`; appends `handoff-retried`.

- [ ] 6. Implement `Store.RequestReconcile` and `Store.InspectConflict`
      (depends on 2) — DoD: `RequestReconcile` appends exactly one
      `reconcile-requested` event and executes no `UPDATE` against
      `lifecycle_ownership`; `InspectConflict` returns the row, `Derive`'s view,
      the most recent events and the precondition values a follow-up must send;
      both validate preconditions the same way the mutating three do, so an
      operator cannot record a reconcile request against a row they misread.

- [ ] 7. Add `internal/api/handlers_lifecycle_recovery.go` with
      `lifecycleRecoveryRequest`, `decodeLifecycleRecovery` and
      `requireLifecycleRecovery` (depends on 3-6) — DoD: decoding uses
      `http.MaxBytesReader` at `lifecycleMaxBodyBytes` and
      `Decoder.DisallowUnknownFields` so an invented `force_owner` field is a
      400; absent `expected_epoch`, `expected_owner_*`, `expected_version` or
      `reason` each produce a 400 naming the field;
      `requireLifecycleRecovery` returns the `*auth.User`, 503s on a nil store
      AND on a nil `AuditLog`, 401 unauthenticated, 403 non-admin.

- [ ] 8. Implement the five handlers — `GetLifecycleConflict`,
      `RequestLifecycleReconcile`, `FenceLifecycleClaim`,
      `RequestLifecycleHandoffRecovery`, `RetryLifecycleHandoff` (depends on 7)
      — DoD: each binds the user, calls exactly one store method, and writes one
      `audit.Entry` on the success path and one on the refusal path with
      `Operation` of `lifecycle-recovery-{reconcile,fence,handoff-request,handoff-retry}`,
      `RiskLevel` high for fence and handoff-request, and `Parameters` carrying
      entity, phase, entity version, epoch before/after, owner before, state
      before/after, licensing condition, the preconditions as sent, reason and
      outcome; the file imports no client other than the lifecycle store and the
      audit log.

- [ ] 9. Extend `writeLifecycleError` in `internal/api/handlers_lifecycle.go`
      (depends on 1) — DoD: `ErrOwnerMismatch` and `ErrVersionMismatch` map to
      412 with the current record in the body; `ErrOwnerNotStuck` and
      `ErrHandoffNotStalled` map to 409 with a message naming the operation the
      caller should have used; no sentinel added in task 1 can reach the default
      500 arm.

- [ ] 10. Wire the routes in `internal/api/router.go` (depends on 8) — DoD:
      `GET /api/v1/lifecycle/ownership/conflict` sits with the reads outside any
      write group; the four `POST /api/v1/lifecycle/ownership/recovery/...`
      routes sit in a new `httprate` group at 10/min keyed
      `"lifecycle-recovery:"+user.ID`, with an inline comment justifying the
      third budget in the style of the two existing ones; a note records that
      `recovery/handoff/*` is deliberately adjacent to, and distinct from, the
      actor `handoff/start|complete` paths.

- [ ] 11. Add `internal/mcp/lifecycle_recovery.go` with the five tools
      (depends on 10) — DoD: `mctl_inspect_lifecycle_conflict` (read-only),
      `mctl_request_lifecycle_reconcile`, `mctl_fence_lifecycle_claim`,
      `mctl_request_lifecycle_handoff`, `mctl_retry_lifecycle_handoff`; every
      block declares both hints plus an idempotency hint where not read-only;
      the two destructive tools take `confirm` and call `requireConfirm`;
      mutating descriptions state the transition, the licensing condition, that
      preconditions fail closed, where to obtain them, and that the tool confers
      no GitHub merge or approval authority; posts go through `s.apiPostJSON`.

- [ ] 12. Register and record the tools (depends on 11) — DoD: five
      `srv.AddTool(...)` calls beside `s.toolGetLifecycleOwnership()` in
      `internal/mcp/server.go`; `recordedHints` in
      `internal/mcp/annotations_test.go` goes 77 → 82;
      `TestReadOnlyToolsAreTheRecordedSet`'s list gains
      `mctl_inspect_lifecycle_conflict`; `docs/portal-allowlist.json` gains five
      entries — inspect `enabled: true` with a reason, the four mutations
      `enabled: false` — so `mutatingOnPortal` needs no change;
      `go test ./internal/mcp/...` passes including the tool-count and portal
      parity tests.

- [ ] 13. Documentation (depends on 10, 12) — DoD: the five routes are added to
      `internal/openapi/openapi.yaml` (which currently documents no lifecycle
      path, so the section is new), and `LLMS.md` / `README.md` mention the
      operator recovery surface where the lifecycle read surface is already
      described. No test enforces spec parity, so this task is explicitly listed
      rather than assumed.

## Tests

Store tests follow `internal/lifecycle/store_test.go`: real Postgres via
`TEST_DATABASE_URL` (skipped on a laptop, run on every PR), prefix-scoped
cleanup. API tests follow `internal/api/handlers_lifecycle_test.go`.

- [ ] T1. Fence refuses a stale epoch — a client that read epoch 4 cannot fence a
      row at epoch 5: `ErrEpochMismatch`, row byte-for-byte unchanged. This is
      the issue's named stale-client test.
- [ ] T2. Fence refuses a moved head — owner and epoch match, `entity_version`
      moved from `sha-a` to `sha-b`: `ErrVersionMismatch`, row unchanged.
- [ ] T3. Fence refuses a mismatched expected owner even at the right epoch:
      `ErrOwnerMismatch`.
- [ ] T4. Fence refuses a live owner (`ErrOwnerAlive`) and a released/terminal row
      (`ErrNotOwner`); succeeds on a dead one, leaving `state=released`,
      `epoch+1`, the fenced owner still named on the row, and one `fenced` event
      whose actor is `human-codeowner/<principal>`.
- [ ] T5. Fence loses the CAS when the owner revives between read and write —
      drive `reacquireRefreshSQL` (or a raw `UPDATE` of `last_seen_at`) inside the
      test, then fence, and assert the refusal. Proves the pinned `last_seen_at`
      is load-bearing, the technique `store_test.go` already uses for the other
      statements.
- [ ] T6. `fenceUpdateSQL`, `handoffRequestUpdateSQL` and `handoffRetryUpdateSQL`
      are executed directly with a weakened `WHERE` to show each pinned column
      changes the outcome — the reason `store.go:107-113` gives for making them
      package constants.
- [ ] T7. `RequestHandoff` succeeds only on a stuck owner: refused on healthy
      (`ErrOwnerNotStuck`), refused on dead, refused on a row already handing
      off; on success the epoch is unchanged, the state is `handing-off`, and the
      named target's ordinary `HandoffComplete` still works and bumps the epoch.
- [ ] T8. `RetryHandoff` succeeds only on a stalled handoff: refused inside the
      bound (`ErrHandoffNotStalled`), refused when the target was retargeted
      between read and write (pinned `handoff_started_at` + `handoff_to_*`);
      on success only `handoff_started_at` and `updated_at` move.
- [ ] T9. `RequestReconcile` leaves every ownership column identical (compare a
      full row snapshot before and after) and appends exactly one
      `reconcile-requested` event.
- [ ] T10. `InspectConflict` returns preconditions that a subsequent fence
      accepts verbatim — the round trip an operator actually performs.
- [ ] T11. API auth boundary: each of the five endpoints answers 401
      unauthenticated, 403 for a non-admin, 503 with a nil store, and 503 with a
      nil `AuditLog`.
- [ ] T12. API validation: absent `expected_version`, `expected_epoch`,
      `expected_owner_id` or `reason` each give 400 naming the field (not 412);
      a body containing `force_owner` gives 400; a body over
      `lifecycleMaxBodyBytes` is rejected.
- [ ] T13. API audit: a successful fence and a 412-refused fence each produce
      exactly one entry in a fake `audit.Log`, with the expected `UserID`,
      `Operation`, `RiskLevel`, `Status`, and the enumerated `Parameters` keys
      present and non-empty.
- [ ] T14. API status mapping: epoch, owner and version mismatches are three
      distinguishable 412 bodies, each carrying the current record; not-stuck and
      not-stalled are 409; nothing reaches 500.
- [ ] T15. No merge authority: the recovery handlers are exercised against a
      `Handlers` built with `Options{Lifecycle: store, AuditLog: fake}` and
      nothing else — no GitHub, Temporal, Argo or gitops client — and all five
      succeed. A nil-pointer panic here would mean a path to something that can
      merge.
- [ ] T16. MCP: tool count and `recordedHints` agree; the read tool stays in the
      read-only set and the four mutations are absent from it; each destructive
      tool refuses without `confirm=yes`; each tool POSTs the preconditions
      verbatim to the expected path, asserted against an `httptest` API.
- [ ] T17. Portal allowlist parity passes with the five new entries and
      `mutatingOnPortal` unchanged.

## Rollback

Revert the commit. Everything added is additive: five routes, five MCP tools,
one new store file, four sentinels and four event names. No schema migration
exists to undo, and no existing endpoint, request shape or tool is modified
except `writeLifecycleError` (new arms only) and the `recordedHints` table.

State written before a revert stays valid without the new code: a fenced row is
an ordinary `released` row that any actor may `Acquire`, and the four new event
names sit inertly in `lifecycle_events`, which every reader returns as raw JSON
rather than switching on. Audit rows in `audit_events` are likewise inert.

If only the MCP surface is at fault, removing the five `AddTool` calls plus their
`recordedHints` and allowlist entries is a self-contained revert that leaves the
HTTP endpoints in place. If a single operation misbehaves, deleting its route is
enough — the store methods are independent of one another and share no state
beyond the precondition helper.

There is no configuration kill switch: setting `Options.Lifecycle` to nil would
503 the actor surface too, which is a worse outage than the problem it would be
reverting.
