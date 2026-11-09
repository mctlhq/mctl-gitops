# Tasks: issue-988-feat-glovo-m1b-1-owner-scoped-order-inde

Blocking dependencies (amended 2026-11-09 (b)): mctl-agents#1059 merged with the approval
basket and fingerprint vectors (OPEN-988-1). #959 for the real `Connections`; until then a fake
and `not_ready`.

- [ ] 1. Extend `glovo.Code` (`internal/glovo/errors.go`) with the codes of design §7
  that are missing. DoD: one table test pins code -> HTTP status -> wire string.
- [ ] 2. `internal/glovo/basket`: vendor the #1059 `approval-basket.schema.json`,
  `basket-fingerprint.json` and `must-reject.json` by sha256; `Approval`, `Validate`
  (sort, uniqueness, arithmetic), `Fingerprint` (JCS from `internal/bridge`). DoD: every
  vector reproduces; no field is defined locally.
- [ ] 3. `internal/glovo/orders/schema.go` and `ApplySchema` (design §2, §3): schema
  `glovo`, tables, CHECKs, partial unique indexes, `CREATE OR REPLACE FUNCTION` for both
  trigger functions, guarded trigger creation, ownership check, version downgrade
  refusal, column-level grants. DoD: applies twice; fails on a pre-created table owned
  by another role.
- [ ] 4. `NewStore` and `Ready`: version, `to_regclass`, triggers present with
  `tgenabled='O'`, `relowner <> current_user`, nil collaborators -> `not_ready`.
- [ ] 5. Owner path: `Create` (READ COMMITTED check, live connection, fingerprint check,
  idempotent insert, join refs, snapshot 1), `AppendSnapshot`, `Finalize`, `Get`,
  `LockOrder`, `Snapshot`, `Cancel`. DoD: one statement per lookup.
- [ ] 6. `BindApproval`, `RecordEffect` (with `ExecutionBindingTx` tenant+owner check).
- [ ] 7. Control path: `PeekOrderScope`, `LockOrderForControl`, `ScopeFromRefs`,
  `MarkDispatched`, `MarkCancelled`, `MarkUnknown`, all with `Actor`.
- [ ] 8. `MintJoinRefTx` for `tnr_`, `prr_`, `ordr_` (single owner of
  `glovo.join_refs`).
- [ ] 9. Docs in package comments: the lifecycle table, the refusal map, and a pointer to
  the canonical lock order in #957 design §6b. Run `go fmt`, `go vet`,
  `golangci-lint`, `go test ./...`; MCP tool count unchanged.

## Tests

Postgres tests use `TEST_DATABASE_URL` (skip when unset), a migration role and a
separate runtime role.

- [ ] T1. Owner isolation: another tenant and another member of the same tenant get
  `not_found` on every read and write.
- [ ] T2. Missing vs foreign vs malformed ref: same value, same query count.
- [ ] T3. Control path: `LockOrderForControl` outside `tenants` is `not_found`; inside, it
  returns the owner from the row; `ScopeFromRefs` with refs of two tenants is
  `not_found`.
- [ ] T4. Connection: absent `no_connection`, revoked `connection_revoked`, expired
  `connection_expired`, moved revision `stale_install`; reads still work after revoke.
- [ ] T5. Idempotent create: same key and request replays; same key, other basket gives
  `idempotency_key_reused`; 20 concurrent creates give one row.
- [ ] T6. Isolation: `Create` inside REPEATABLE READ is refused.
- [ ] T7. Fingerprint: the #1059 vectors reproduce byte for byte, including the
  permuted-input, price-change and fee-change vectors and every `must_reject` case; a wrong `ExpectedFingerprint` gives
  `fingerprint_changed` and writes nothing.
- [ ] T8. Snapshots are append-only; finalize freezes the fingerprint; a new basket after
  finalize needs a new order.
- [ ] T9. `RecordEffect` with a `we_` of another tenant, and of another owner in the same
  tenant, is `not_found`; a second `place_order_fake` `we_` is `invalid_transition`.
- [ ] T10. Runtime role (order tables only): no `ALTER`, `DROP`, `DELETE`, `TRUNCATE` or
  `DISABLE TRIGGER`; an `UPDATE` of an identity column is refused by grant or trigger.
- [ ] T11. Lifecycle: every allowed transition succeeds; every other pair fails through
  the Go API **and** through raw SQL under the runtime role, including
  `cancelled -> open`, `closed -> dispatched`, `unknown -> cancelled`, and
  `open -> cancelled` without a fingerprint succeeding.
- [ ] T12. Write-once: `approval_ref`, `command_id`, `execution_id` and the final
  fingerprint cannot be changed once set; a second order with the same `aar_` or `cmd_`
  is rejected; `command_id` without `approval_ref` is rejected.
- [ ] T13. Shared transaction: `Create` + `Finalize` + `BindApproval` + `RecordEffect` and
  a bridge `Enqueue` in one `pgx.Tx`; a failure after the last statement leaves nothing.
- [ ] T14. Readiness: a disabled guard trigger, a table owned by the runtime role, a
  version mismatch and a nil collaborator each give `not_ready`.
- [ ] T15. Refusal map: each design §7 row produces its code; an injected database error
  gives `dependency_unavailable`, never `not_ready`.
- [ ] T16. Audit: events carry `actor_kind`; #985 calls record `control_worker`; no
  fingerprint or basket bytes appear in events or logs.

## Rollback

- Nothing is wired, so revert is a code revert. The `glovo` schema objects can stay, or
  be dropped by the migration role after confirming no rows exist. Hold
  mctl-gitops#2457 stays ON.
