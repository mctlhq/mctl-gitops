# Tasks: issue-988-feat-glovo-m1b-1-owner-scoped-order-inde

- [ ] 1. Create `internal/glovo/orders/refusal.go` with `Code` and `Refusal` for the
  closed set (`order_not_found`, `connection_revoked`, `install_revision_stale`,
  `order_finalized`, `order_state_conflict`, `idempotency_key_reused`,
  `execution_already_bound`, `invalid_basket`, `not_ready`) and `errors.Is` support.
  DoD: no refusal carries free text or an id, and a unit test enumerates the set.
- [ ] 2. Add `basket.go` with `Basket`, validation, the canonical `mctl-basket/v1`
  encoding and `Fingerprint` (depends on 1). DoD: the function is pure and table-tested
  for ordering independence and per-field sensitivity.
- [ ] 3. Add `schema.go` with the DDL, named CHECKs, the `glovo_orders_immutable_rows()`
  and `glovo_orders_guard()` triggers, the version table and
  `ApplySchema(ctx, migrationConnStr, runtimeRole)`. It runs under
  `pg_advisory_xact_lock(hashtext('glovo-orders-schema'))` and issues the runtime grants
  (depends on 1). DoD: running it twice is a no-op, the role name is validated and quoted
  with `pgx.Identifier`, and no other file contains DDL.
- [ ] 4. Add `store.go` with `NewStore(ctx, pool, conns, execs, opts...)` (no DDL; checks
  the version and `to_regclass` of every table), `Ready`, `WithClock`, and the
  `Connections`/`Executions` interfaces (depends on 3). DoD: a missing table, a wrong
  version or a nil collaborator gives `not_ready`, and `NewStore` takes no connection
  string.
- [ ] 5. Implement `Create`, mint the `pord_`/`ordr_` refs and the `glovo_join_refs` row,
  write the first snapshot and the event, and make the insert idempotent with
  `ON CONFLICT DO NOTHING` plus a request-hash compare (depends on 2, 4). DoD: all writes
  run on the caller's `pgx.Tx`, and no `Begin`/`Commit`/`Rollback` exists in write
  methods (a test greps the package for them).
- [ ] 6. Implement `Get`, `LockOrder`, `Snapshot`, `AppendSnapshot` and `Finalize` with
  single-statement owner-scoped lookups and the connection/revision re-check (depends on
  5). DoD: each lookup is one query whatever the cause of a miss.
- [ ] 7. Implement `Transition` with the state table and `RecordEffect` with the
  one-`we_`-per-effect binding through `Executions.ExecutionTenantTx` (depends on 6).
  DoD: CHECKs and Go agree, and a conflict on `execution_id` maps to
  `execution_already_bound`.
- [ ] 8. Add synthetic fixtures (`testdata/` or test helpers): 2 tenants, with 2
  principals in tenant A. Use synthetic `gcn_`/`gin_` ids, `provider=fake` and
  `store_ref=synthetic-store-1` (depends on 5). DoD: no real names, addresses, SKUs or
  credentials.
- [ ] 9. Add a package doc in `orders/doc.go` stating the store is dark, no DDL runs at
  runtime, and how #957/#985 wire it from `bridge.Store.Pool()` (depends on 4). DoD: the
  doc states the `Scope` requirement for #985's `LockOrder`.
- [ ] 10. Run `go fmt`, `go vet`, `golangci-lint` and `go test ./internal/glovo/...`
  with `TEST_DATABASE_URL` (depends on 1-9). DoD: CI is green, the diff does not touch
  `cmd/api/main.go`, `internal/api/router.go` or `internal/mcp/server.go`, and the MCP
  tool count is unchanged.

## Tests

Postgres tests use `TEST_DATABASE_URL` and skip when it is unset, like
`internal/bridge/outbox_pg_test.go`. Each test applies the schema with a migration role
and runs the store with a separate, non-owner runtime role.

- [ ] T1. Two tenants: an order created by tenant A/principal P1 is `order_not_found` for
  tenant B/any principal on `Get`, `LockOrder`, `AppendSnapshot`, `Finalize`,
  `Transition` and `RecordEffect`. The refusal is byte-identical to a never-existing
  `ordr_`.
- [ ] T2. Same tenant, different owner: tenant A/principal P2 gets `order_not_found` for
  P1's order on every method.
- [ ] T3. Foreign or unknown ids: a random well-formed `ordr_`, a malformed ref, a `pord_`
  passed as a ref, and another tenant's `ordr_` all give the same refusal. A query-count
  hook shows the same number of statements for each.
- [ ] T4. Stale install revision: the fake `Connections` bumps the revision. Every
  mutation refuses with `install_revision_stale` and writes no row or event.
- [ ] T5. Revoked connection: `Create` and every mutation refuse with
  `connection_revoked` when there is no live connection or the live `gcn_` differs. `Get`
  still returns the order.
- [ ] T6. Snapshot mutation after finalize or approve: `AppendSnapshot` gives
  `order_finalized`. Under the runtime role, raw `UPDATE`/`DELETE` on
  `glovo_order_snapshots` raises, and a raw `UPDATE` of `final_basket_fingerprint`,
  `tenant`, `owner_principal_id` or `install_revision` on `glovo_orders` raises.
- [ ] T7. Fingerprint stability: the same basket in permuted item order gives the same
  hash. Changing the store ref, currency, any SKU or any quantity, or adding or removing
  an item, gives a different hash. A golden vector pins `mctl-basket/v1`. Duplicate SKUs
  and out-of-range quantities give `invalid_basket`.
- [ ] T8. Concurrent creates with one idempotency key: N goroutines, each in its own
  transaction on one pool, create with the same key and basket. Exactly one order row,
  one join-ref and one seq-1 snapshot exist, and all calls return the same `ordr_`. The
  same key with a different basket gives `idempotency_key_reused`. If the first
  transaction rolls back, the second inserts.
- [ ] T9. One `we_` per effect: binding the same `we_` to a second effect, on the same or
  another order, gives `execution_already_bound`. A `we_` from another tenant gives
  `order_not_found`. A same-key replay returns the stored effect.
- [ ] T10. Role boundaries: the runtime role cannot run `CREATE TABLE`, `ALTER TABLE`,
  `DROP TABLE` or `ALTER TABLE ... DISABLE TRIGGER` on any order table, and cannot
  `DELETE` from any of them.
- [ ] T11. No DDL at runtime: `NewStore` against an empty database gives `not_ready`
  and creates nothing. A version mismatch gives `not_ready`.
- [ ] T12. Shared transaction: `Create` plus a `bridge.Store.Enqueue` on the same
  `pgx.Tx`, with an injected error before commit, leave no order, snapshot, event or
  bridge row.
- [ ] T13. Audit content: after a full lifecycle, `glovo_order_events` rows contain no
  fingerprint, SKU, store ref, currency or `pord_`. A captured `slog` buffer contains none
  either.
- [ ] T14. State machine: every disallowed transition gives `order_state_conflict`, and
  the database CHECKs reject the same rows when written raw.

## Rollback

The slice is additive and dark: nothing constructs the store, and no route or MCP tool
exists. To roll back, revert the PR. That removes the package with no behaviour change.

If `ApplySchema` was already run in an environment, the tables are unused and harmless
and can stay. To remove them, the migration role runs
`DROP TABLE glovo_order_events, glovo_order_effects, glovo_order_snapshots, glovo_orders, glovo_join_refs, glovo_orders_schema_version`
and drops the two trigger functions. Hold that step if #957 has started minting
`tnr_`/`prr_` rows into `glovo_join_refs`.
