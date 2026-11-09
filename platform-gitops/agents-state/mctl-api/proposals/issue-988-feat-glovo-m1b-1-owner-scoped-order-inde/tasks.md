# Tasks: issue-988-feat-glovo-m1b-1-owner-scoped-order-inde

Blocking dependencies (amended 2026-11-09 (b); round 4: this slice provides `internal/jcs` and depends on neither #986 nor #985): mctl-agents#1059 merged with the approval
basket and fingerprint vectors (OPEN-988-1). Round 6 (G3): until #989 task 2b grants `SELECT` on `public.work_items` and `public.work_item_executions`, `Ready` is `not_ready` and the `Create` tests (T9, T13, T17) use raw-SQL `wi_`/`we_` fixtures with explicit test grants; the real-store T13 case runs in #989. #959 merged first (round 5, F1): it provides `glovo.Owner`, `glovo.Connection`,
`dbq.Querier` and the grant registry, so this slice uses no fake `Connections` and no local `Querier`.

- [ ] 1. Round 5 (F1): no new `glovo.Code` constants; #959 task 1 is the single owner of the enum. DoD: one table test pins that every code of design §7 is in that enum and its code -> HTTP status -> wire string.
- [ ] 2a. (round 4, N3) `internal/jcs`: `Canonicalize(raw []byte) ([]byte, error)` (RFC 8785)
  and `Precheck(raw []byte) error` (the #1059 token-level raw-bytes pre-check: duplicate
  keys, BOM, number forms, nesting depth, size). Round 5 (F5): this task vendors
  `vectors/jcs-digest.json` and `vectors/must-reject.json` from #1059 (merged first, at the
  commit recorded in `internal/jcs/testdata/PROVENANCE`) into `internal/jcs/testdata/`, each
  pinned by its #1059 `SHA256SUMS` sha256; there is no cycle. DoD: every #1059 `vectors/` JCS and
  digest vector reproduces byte for byte (UTF-16 key order, number forms, escapes), a
  pinned vector test names the vendored sha256, and `go vet` shows no dependency on
  `internal/bridge`. #986 imports this package.
- [ ] 2. `internal/glovo/basket` (depends on 2a): vendor the #1059 basket files
  (`approval-basket.schema.json`, `basket-fingerprint.json`, `pattern-parity.json`) by sha256
  into `internal/glovo/basket/contract/`; `must-reject.json` is the copy vendored by task 2a, read from
  `internal/jcs/testdata/`, never copied twice, and run the
  Go leg of the #1059 pattern-parity test over them; `Approval`, `Validate` (sort, uniqueness,
  arithmetic), `Parse(raw []byte) (Approval, []byte, error)` (`jcs.Precheck`, schema
  with no extra fields, `Validate`, JCS bytes) and `Fingerprint(canonical []byte)`
  (amended (c)). DoD: every vector reproduces; every `must_reject` case, an extra
  `item_name` field and `quantity: 1.0` are refused by `Parse`; no field is defined
  locally.
- [ ] 3. `internal/glovo/orders/schema.go` and `ApplySchema` (design §2, §3): schema
  `glovo`, tables, CHECKs, partial unique indexes (incl. `orders_execution`, round 4 N1), `CREATE OR REPLACE FUNCTION` for all five
  trigger functions (incl. the two insert guards), guarded trigger creation from the shared `triggerInventory` constant, ownership check, version downgrade
  refusal, column-level grants, and the `glovo.RegisterGrants` call for the #988 rows (round 5, F2). DoD: applies twice; fails on a pre-created table owned
  by another role.
- [ ] 4. `NewStore(ctx, pool, runtimeRole, migrationRole, conns, execs)` and `Ready` (round 4, N4: owners compared with exactly `migrationRole`; the `JoinKind`, `ActorKind` and `Snapshot` types of design §1; `Querier` is `dbq.Querier`): version, `to_regclass`, the exact `triggerInventory` set present (`tgenabled='O'`, expected `tgfoid`, function owner), `NOT pg_has_role(current_user, owner, 'MEMBER')` for tables, trigger
  functions and schema `glovo`, the #957 §6d.1 grants, nil collaborators ->
  `not_ready` (amended (c)).
- [ ] 5. Owner path: `NewOrderRef`, `LookupByIdempotencyKey` and `Create` with `CreateInput` incl. `OrderRef` (READ COMMITTED check, live connection,
  expected install revision, `ExecutionBindingTx` tenant+owner check and write-once
  `execution_id`, `basket.Parse` of the stored preview bytes, fingerprint check,
  idempotent insert, snapshot 1), `AppendSnapshot`, `Finalize`, `Get`, `LockOrder`,
  `Snapshot`. No owner `Cancel` (amended (c)). DoD: one statement per lookup.
- [ ] 6. `BindApproval` (amended (c): `RecordEffect` withdrawn; the effect row is written
  by `MarkDispatched`, task 7).
- [ ] 7. Control path: `PeekOrderScope`, `LockOrderForControl`, `ScopeFromRefs`,
  `MarkDispatched`, `MarkCancelled`, `MarkUnknown`, `MarkClosed` (`dispatched -> closed` only, round 6), all with `Actor`.
- [ ] 8. `MintJoinRefTx` and `LookupJoinRefTx` for `tnr_`, `prr_` and `irv_` (no `ordr_` kind: the ref is the order's own column)
  (single owner of `glovo.join_refs`; amended (c)).
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
  `connection_expired`, moved revision `stale_install`; reads still work after revoke. Round 4 (N2): after a revoke `AppendSnapshot`, `Finalize` and `BindApproval` give `connection_revoked`, while `MarkCancelled` and `MarkUnknown` still succeed and `MarkDispatched` does not re-read the connection (a #959 store double counts `LiveConnectionTx` calls per method and asserts the table of design §6).
- [ ] T5. Idempotent create: same key and request replays; same key, other basket gives
  `idempotency_key_reused`; 20 concurrent creates give one row, one `ordr_` and (with #957 T5) zero extra `work_items`/`work_item_executions` rows; `LookupByIdempotencyKey` writes nothing; `Create` with a malformed `OrderRef` is `invalid_request`.
- [ ] T6. Isolation: `Create` inside REPEATABLE READ is refused.
- [ ] T7. Fingerprint: the #1059 vectors reproduce byte for byte, including the
  permuted-input, price-change and fee-change vectors and every `must_reject` case; a wrong `ExpectedFingerprint` gives
  `fingerprint_changed` and writes nothing.
- [ ] T8. Snapshots are append-only; finalize freezes the fingerprint; a new basket after
  finalize needs a new order; a raw-SQL snapshot insert for a finalized order and a
  snapshot whose fingerprint does not hash its bytes are refused (amended (c)).
- [ ] T9. `Create` with a `we_` of another tenant, and of another owner in the same
  tenant, is `not_found`; a `we_`+UUID id from the real generic work-items store is
  refused by the CHECK; changing `execution_id` after insert is refused; `MarkDispatched`
  writes exactly one effect row (amended (c)).
- [ ] T10. Runtime role (order tables only): no `ALTER`, `DROP`, `DELETE`, `TRUNCATE` or
  `DISABLE TRIGGER`; an `UPDATE` of an identity column is refused by grant or trigger.
- [ ] T11. Lifecycle: every allowed transition succeeds; every other pair fails through
  the Go API **and** through raw SQL under the runtime role, including
  `cancelled -> open`, `closed -> dispatched`, `unknown -> cancelled`, and
  `open -> cancelled` without a fingerprint succeeding.
- [ ] T12. Write-once: `approval_ref`, `command_id`, `execution_id` and the final
  fingerprint cannot be changed once set; a second order with the same `aar_`, `cmd_` or `we_` (`orders_execution`, round 4 N1; with the index dropped the test fails)
  is rejected; `command_id` without `approval_ref` is rejected.
- [ ] T13. Shared transaction: #989 `CreateGlovoExecutionTx` + `Create` + `Finalize` +
  `BindApproval`, and `MarkDispatched` + a bridge `Enqueue` in one `pgx.Tx`; a failure
  after the last statement leaves nothing. `order_ref` equals the `ordr_` in the workflow id, `engine_ref` and the `aar_` key.
- [ ] T14. Readiness (round 5, F2: the grant check reads the registry; with the #988 rows removed from it `Ready` is red, and a registered row of another slice for an existing table leaves it green): for each of the eight triggers of `triggerInventory` in turn, disable it, drop it, and re-point it at another function (each gives `not_ready`, and is wrongly ready with the matching check removed), plus: an unlisted extra trigger, a trigger function not owned by the migration role, a table owned by the runtime role, a
  table owned by a role the runtime role inherits, schema `glovo` owned by the runtime
  role, an extra grant, a version mismatch and a nil collaborator each give `not_ready`;
  with the matching check removed, each case is wrongly reported ready (mutation
  check). `ApplySchema` refuses a downgrade (amended (c)).
- [ ] T15. Refusal map: each design §7 row produces its code; an injected database error
  gives `unavailable`, never `not_ready`; a held `FOR UPDATE` on the order row plus `SET LOCAL lock_timeout` gives `tenant_busy` (fails with the mapping reverted, mutation check).
- [ ] T17. Raw-SQL inserts under the runtime role (round 3): an `orders` insert as `dispatched`, with a fingerprint matching no snapshot, with an `aar_`/`cmd_`, or with a `we_` of another owner or tenant, or a second order for a `we_` that already has one, is refused; an `order_effects` insert for an order that is not `finalized`, or with another execution, tenant, owner or fingerprint, is refused; the legitimate `Create` and `MarkDispatched` paths still pass.
- [ ] T18. (round 4, N3) JCS owner: `internal/jcs` reproduces every #1059 vector, and the same bytes go through `basket.Parse` and `basket.Fingerprint`; a grep test asserts that no other package in `internal/glovo` or `internal/bridge` implements its own canonicalizer (they import `internal/jcs`).
- [ ] T19. (round 4, N4) `NewStore` with a wrong `migrationRole` gives `not_ready` even though the schema is owned by a non-superuser role and the runtime role is not its member (fails with the owner comparison reduced to `NOT pg_has_role`).
- [ ] T16. Audit: events carry `actor_kind`; #985 calls record `control_worker`; no
  fingerprint or basket bytes appear in events or logs.

## Rollback

- Nothing is wired, so revert is a code revert. The `glovo` schema objects can stay, or
  be dropped by the migration role after confirming no rows exist. Hold
  mctl-gitops#2457 stays ON.
