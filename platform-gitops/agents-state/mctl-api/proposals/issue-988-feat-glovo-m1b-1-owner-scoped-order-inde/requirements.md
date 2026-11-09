# Glovo M1b/1: owner-scoped order index, immutable snapshots and the M1 basket fingerprint

## Context

Issue mctlhq/mctl-api#988 is slice M1b/1 of the #954 decomposition. mctl-api has no
Glovo order index. The bridge already carries an `order_ref` column
(`^ordr_[A-Za-z0-9]{16,40}$`, `internal/bridge/store.go` `refPatterns`), but nothing
mints or resolves it. The `aar_` slice (#989), dispatch/cancel (#985), the facade (#957)
and the contract tests (#990) all need one canonical, owner-scoped order record.

This slice delivers a dark Postgres store with no route, no MCP tool and no `main.go`
wiring. Amended 2026-11-09 (b); design.md has the finding -> fix table. The amendment:
- uses the **one** M1 basket fingerprint, defined over the mctl-agents#1059 **approval
  basket** projection (RFC 8785, prices included), replacing `mctl-basket/v1`;
- holds no approval authority: the order only carries a write-once reference to the
  `aar_` owned by #989;
- enforces transitions and write-once columns in the database;
- maps every refusal to #957 §4;
- serves the #985 control worker with scope derived from the order row;
- owns `glovo_join_refs`;
- lives in the one physical database of owner decision A.

Owner approval of #954 or #957 does not carry over: this slice needs its own
digest-bound approval.

## User stories

- AS a Glovo owner I WANT my orders visible and mutable only to me, within my tenant and
  my live connection SO THAT nobody else can see or change them.
- AS the #989 approval slice I WANT a final basket fingerprint that never changes and a
  write-once `approval_ref` SO THAT one approval binds exactly one basket and one order.
- AS the #985 control worker I WANT to lock and move an order on the shared transaction,
  with tenant and owner derived from the order itself, SO THAT dispatch and `Enqueue`
  commit together and are attributed to me.
- AS a platform operator I WANT the order tables owned by a migration role and guarded by
  enabled triggers SO THAT the runtime role cannot rewrite history or bypass the state
  machine.
- AS a security reviewer I WANT every miss to return one identical refusal SO THAT nothing
  leaks about other tenants' orders.

## Acceptance criteria (EARS)

Fingerprint
- THE SYSTEM SHALL compute the basket fingerprint as `"sha256:" + hex(sha256(JCS(b)))`
  over the mctl-agents#1059 approval basket, and SHALL reproduce every vendored #1059
  golden vector byte for byte.
- THE SYSTEM SHALL NOT define a basket schema or fingerprint algorithm of its own.
- WHEN `Create`, `AppendSnapshot` or `Finalize` receives an expected fingerprint that
  differs from the one it computes THE SYSTEM SHALL refuse with `fingerprint_changed`
  and write nothing.
- THE SYSTEM SHALL store the JCS bytes of every snapshot so the fingerprint can be
  re-verified.

Owner scoping
- WHEN an owner-path method is called THE SYSTEM SHALL look the order up in one statement
  on `(order_ref, tenant, owner_principal_id)`.
- IF the order is missing, foreign, malformed or outside the control worker's `tenants`
  bound THEN THE SYSTEM SHALL answer `not_found` with an identical query count and value.
- WHEN the #985 control worker calls `PeekOrderScope` or `LockOrderForControl` THE SYSTEM
  SHALL derive tenant and owner from the order row, never from the request.
- WHEN `ScopeFromRefs` is called THE SYSTEM SHALL resolve the `tnr_` and `prr_` through
  `glovo.join_refs` and require them to map to the same tenant.

Connection binding
- WHEN an order is created THE SYSTEM SHALL bind it to the owner's live connection id,
  install id and install revision read through #959 `LiveConnectionTx` on the same
  transaction.
- IF there is no connection THEN THE SYSTEM SHALL refuse with `no_connection`. IF it is
  revoked or reconnected THEN `connection_revoked`. IF it is expired THEN
  `connection_expired`. IF the install revision moved THEN `stale_install`.
- WHILE a connection is revoked THE SYSTEM SHALL still let the owner read the order and
  its snapshots, and refuse writes.

Lifecycle
- THE SYSTEM SHALL allow only the transitions of design §6 and SHALL enforce them in a
  `BEFORE UPDATE` trigger over the old and new state, so raw SQL by the runtime role is
  refused too.
- THE SYSTEM SHALL have no `approved` order state. Approval state SHALL be read only from
  the #989 `aar_` row.
- THE SYSTEM SHALL make `final_basket_fingerprint`, `final_snapshot_seq`, `approval_ref`,
  `command_id` and `execution_id` write-once, and SHALL allow at most one order per
  `approval_ref` and per `command_id`.
- WHEN an order is cancelled from `open` THE SYSTEM SHALL allow it without a fingerprint.
- WHEN #985 records that a cancelled command's effect is unknown THE SYSTEM SHALL move the
  order to `unknown`, never to `cancelled`.

Effects
- WHEN `RecordEffect` is called THE SYSTEM SHALL require the `we_`'s tenant **and** owner
  principal to equal the order's, else `not_found`.
- THE SYSTEM SHALL bind at most one `we_` per effect, and one `place_order_fake` `we_`
  per order (`Order.ExecutionID`).

Refusals
- THE SYSTEM SHALL use only `glovo.Code` values, each mapped to one #957 §4 wire row in
  design §7.
- IF a collaborator or the database fails THEN THE SYSTEM SHALL return
  `dependency_unavailable`. `not_ready` SHALL mean not configured.

Schema and roles
- THE SYSTEM SHALL create its objects only through `ApplySchema` under the migration
  role, in the Postgres schema `glovo`, with schema-qualified statements.
- IF an existing object is not owned by the migration role, or the stored schema version
  is newer than the code THEN `ApplySchema` SHALL fail.
- THE SYSTEM SHALL grant the runtime role no table-wide `UPDATE`, no `DELETE` and no
  `TRIGGER`.
- WHILE any guard trigger is missing or not enabled (`tgenabled <> 'O'`), or a table is
  owned by the runtime role THE SYSTEM SHALL report `not_ready`.
- WHEN `Create` runs in a transaction that is not READ COMMITTED THE SYSTEM SHALL refuse
  with `dependency_unavailable`.

Audit and hygiene
- THE SYSTEM SHALL append one event per write with the actor kind (`owner`,
  `control_worker`, `system`) and id, and SHALL store no fingerprint, basket or provider
  data in events or logs.

## Out of scope

- The approval basket definition and vectors (mctl-agents#1059).
- The `aar_` state machine (#989), dispatch/cancel (#985), routes and the
  Glovo join handlers (#957), the connection store (#959).
- Who moves `dispatched`/`unknown` to `closed` (OPEN-985-5).

## Open questions

- OPEN-988-1. The approval basket and its vectors are added to the mctl-agents#1059
  proposal in this same PR (`approval-basket.schema.json`, `basket-fingerprint.json`
  with permuted-input, price-change and fee-change vectors and must-reject cases). Task 2
  still waits until #1059 is approved and merged.
- OPEN-988-2. #1044 must name the same fingerprint in `GlovoControlInput` (amend in the
  same wave).
- OPEN-988-3. Role provisioning for the migration and runtime roles (shared with
  OPEN-985-6).
- OPEN-988-4. Retention of `basket_canonical` per terminal state is a precondition
  before any G3 or real-data use.
