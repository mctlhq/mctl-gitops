# Glovo M1b/1: owner-scoped order index, immutable snapshots and basket fingerprint

## Context

Issue mctlhq/mctl-api#988 is slice M1b/1 of the #954 decomposition. mctl-api has no
Glovo order index. The bridge already carries an `order_ref` column matching
`^ordr_[A-Za-z0-9]{16,40}$` (`internal/bridge/store.go`, `refPatterns`), but nothing
mints or resolves that ref. Every later slice needs a canonical, owner-scoped order
record: the `aar_` receipt binding (M1b/2), dispatch/cancel (#985, M1b/3) and the
contract tests (M1b/4). The #957 amendment (§2a, mctlhq/mctl-gitops#2547) defines the
external `ordr_` ref and requires raw ids (`pord_`, `prn_`, tenant names) to stay
inside mctl-api. Its §6b (owner decision D2) requires every Glovo write to run on one
`pgx.Tx` opened from `bridge.Store.Pool()`, with no `AUDIT_DB_URL` fallback.

This slice delivers a dark Postgres-backed store with no route, no MCP tool and no
`cmd/api/main.go` wiring. It covers orders keyed by (tenant, principal, connection,
install revision), append-only immutable basket snapshots, a versioned canonical basket
fingerprint, a one-`we_`-per-effect binding and an audit trail that holds no basket or
provider data. Tables are created only by `ApplySchema` under a migration role, and the
runtime role gets minimum DML grants. Owner approval of #954 or #957 does not carry over:
this slice needs its own review and its own digest-bound approval.

## User stories

- AS a Glovo owner principal I WANT my orders visible and mutable only to me, within my
  tenant and my live connection SO THAT another tenant or another member of my tenant
  cannot see or change them.
- AS the M1b/2 `aar_` receipt slice I WANT a final basket fingerprint that never changes
  once set SO THAT an approval binds to exactly one basket.
- AS the #985 dispatch slice I WANT to lock and transition an order on the bridge's
  transaction SO THAT the order change and `bridge.Store.Enqueue` commit or roll back
  together.
- AS a platform operator I WANT the order tables owned by a migration role, with no DDL
  at startup SO THAT the runtime role cannot alter, drop or disable the immutability
  triggers.
- AS a security reviewer I WANT every miss to return one identical refusal SO THAT ids,
  errors and query shape reveal nothing about other tenants' orders.

## Acceptance criteria (EARS)

Schema and roles

- WHEN `orders.ApplySchema(ctx, migrationConnStr, runtimeRole)` runs THE SYSTEM SHALL
  create `glovo_join_refs`, `glovo_orders`, `glovo_order_snapshots`,
  `glovo_order_effects`, `glovo_order_events` and `glovo_orders_schema_version` in one
  transaction under `pg_advisory_xact_lock(hashtext('glovo-orders-schema'))`, install
  the immutability triggers and grant the runtime role only the DML listed in design.md.
- WHEN `orders.NewStore(ctx, pool)` is called THE SYSTEM SHALL run no DDL. It SHALL check
  that every order table exists and that `glovo_orders_schema_version` equals the
  compiled version, and SHALL fail closed with `not_ready` otherwise.
- THE SYSTEM SHALL accept only a `*pgxpool.Pool` (the bridge pool) in `NewStore` and no
  connection string, so the store cannot resolve its own database or fall back to
  `AUDIT_DB_URL`.
- IF the runtime role issues `UPDATE` or `DELETE` on `glovo_order_snapshots`,
  `glovo_order_effects`, `glovo_order_events` or `glovo_join_refs`, or `DELETE` on
  `glovo_orders`, or `ALTER TABLE`, `DROP TABLE` or `ALTER TABLE ... DISABLE TRIGGER` on
  any order table, THEN THE SYSTEM SHALL refuse it.

Ownership and identifiers

- WHEN an order is created THE SYSTEM SHALL assign a random internal `pord_` id and a
  random external `ordr_` ref (prefix plus 26 base62 characters from `crypto/rand`). It
  SHALL record the `ordr_` to `pord_` mapping in `glovo_join_refs` and SHALL bind the
  order to the caller's tenant, `prn_` principal, `gcn_` connection, `gin_` install and
  install revision.
- THE SYSTEM SHALL accept only `ordr_` refs at the store API and SHALL never return a
  `pord_`, a raw principal id of another caller or another tenant's name in any result
  or refusal.
- WHEN any order is read or mutated THE SYSTEM SHALL resolve it with one statement whose
  predicate includes the ref, tenant and owner principal. A miss SHALL return
  `order_not_found` with no second probe, whether the order is absent, foreign to the
  tenant, foreign to the owner or the ref is malformed.
- IF the caller's live connection is revoked or absent when an order is created or
  mutated THEN THE SYSTEM SHALL refuse with `connection_revoked` and write nothing.
- IF the caller's live connection or install revision differs from the order's bound
  `connection_id` or `install_revision` THEN THE SYSTEM SHALL refuse with
  `install_revision_stale` and write nothing.

Snapshots and fingerprint

- WHEN a basket snapshot is appended to an `open` order THE SYSTEM SHALL validate the
  synthetic basket, compute its `mctl-basket/v1` fingerprint over the canonical encoding
  and insert an immutable row `(order_id, seq)` with the next sequence number.
- THE SYSTEM SHALL produce the same fingerprint for the same basket regardless of item
  order or JSON key order. It SHALL produce a different fingerprint for any change to the
  store ref, currency, any SKU, any quantity, the item set or the encoding version.
- WHEN an order is finalized THE SYSTEM SHALL set `final_basket_fingerprint` and
  `final_snapshot_seq` once, by compare-and-set from `open`, to the latest snapshot.
- WHILE an order is not `open` THE SYSTEM SHALL refuse every snapshot append with
  `order_finalized`. A changed basket SHALL require a new order with a new `ordr_`.
- IF any statement tries to update or delete a snapshot row, or to change
  `final_basket_fingerprint`, `final_snapshot_seq` or an identity column of
  `glovo_orders` once it is set, THEN THE SYSTEM SHALL raise an exception in the
  database trigger, whatever the calling code.

Effects and executions

- WHEN an effect is recorded for an order THE SYSTEM SHALL bind exactly one `we_`
  execution to it (`UNIQUE (execution_id)`). It SHALL require that the execution's work
  item tenant equals the order's tenant, and SHALL refuse a `we_` already bound to any
  effect with `execution_already_bound`.

Idempotency and concurrency

- WHEN two creates with the same (tenant, principal, idempotency key) and the same
  request hash run concurrently THE SYSTEM SHALL create exactly one order, and both
  calls SHALL return the same `ordr_` (one with `Replayed=true`).
- IF a create reuses an idempotency key with a different request hash THEN THE SYSTEM
  SHALL refuse with `idempotency_key_reused`.
- THE SYSTEM SHALL perform every write on the caller-supplied `pgx.Tx`. It SHALL never
  open, commit or roll back its own transaction inside a write method.

Audit and data

- WHEN an order is created, snapshotted, finalized, transitioned or bound to an effect
  THE SYSTEM SHALL append a `glovo_order_events` row with the `ordr_`, actor `prn_`,
  event, from/to state and snapshot sequence. The row SHALL hold no basket content, no
  fingerprint and no provider data.
- THE SYSTEM SHALL accept only `provider = 'fake'` (database CHECK), and every fixture
  SHALL be synthetic.
- THE SYSTEM SHALL use only this closed set of domain refusal codes: `order_not_found`,
  `connection_revoked`, `install_revision_stale`, `order_finalized`,
  `order_state_conflict`, `idempotency_key_reused`, `execution_already_bound`,
  `invalid_basket`, `not_ready`.

## Out of scope

- HTTP routes, MCP tools, the `cmd/api/main.go` wiring and the readiness signal that
  opens `glovo.Default` (#957 and #985 wire the store).
- `aar_` creation or binding (M1b/2), dispatch/cancel and `bridge.Store.Enqueue` calls
  (#985, M1b/3) and contract tests across the facade (M1b/4).
- The `tnr_` and `prr_` kinds of `glovo_join_refs`. The table is created here, but only
  the `order` kind is minted in this slice. #957 mints the other kinds.
- Minting `we_` executions. Tx-aware execution creation in `internal/workitems` belongs
  to #957 §6b. This slice binds a caller-supplied `we_`.
- Removing the bridge's `AUDIT_DB_URL` fallback in `cmd/api/main.go` (mctl-api#987).
- The #959 connection store itself. This slice consumes it through an interface.
- Retention or purge of order rows and events. That needs a later, separately approved
  maintenance design, the same as #959's audit retention.
- Real Glovo access, real baskets or payments.

## Open questions

- Ownership of `glovo_join_refs` DDL: #957 §2a defines the table, but M1b/1 is the first
  slice to need `ordr_`. This proposal creates it here, with all three kinds allowed by
  CHECK and only `order` minted. If #957 must own it, move the DDL there and make this
  slice require the table.
- Whether mctl-api stores the canonical synthetic basket. #985's design says the dispatch
  payload "comes from the order index row". #954's earlier design kept only the
  fingerprint and left the raw basket with the worker. This proposal stores the canonical
  bytes in the snapshot row (`basket_canonical BYTEA`, synthetic only, never in events or
  logs) so #985 can build the payload and the fingerprint can be re-verified.
- Basket schema. The issue does not define the synthetic basket fields. This proposal
  uses `{store_ref, currency, items: [{sku, quantity}]}`, rejects duplicate SKUs, and puts
  the fields behind the `mctl-basket/v1` version tag so later fields need a new tag.
- #985's `OrderIndex.LockOrder(ctx, tx, orderRef)` has no owner argument. This store
  takes a `Scope{Tenant, PrincipalID}` on every call, so #985 must pass the owner it
  takes from the `aar_` binding. Its interface needs that one-argument change.
- Which migration entrypoint runs `ApplySchema`, and the runtime role name. #959
  introduces `glovo.ApplySchema` but names no job or command. This slice exposes
  `orders.ApplySchema` for that same entrypoint and takes the runtime role name as a
  parameter.
- The #959 connection store may live on `GLOVO_DB_URL`, a different database. Liveness
  is then a read outside the shared transaction, and #957 §6b's revoke-after-approval
  TOCTOU test applies. This slice re-checks liveness on every mutation but cannot close
  that window by itself.
- The deployed configuration of mctl-api (which `*_DB_URL` values are set) was not
  observed. See design.md "Deployed state checked".
