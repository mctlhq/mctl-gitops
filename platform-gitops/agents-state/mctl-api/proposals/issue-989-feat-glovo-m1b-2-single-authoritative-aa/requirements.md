# Glovo M1b/2: one authoritative `aar_` approval and a single-use receipt lifecycle

## Context

Issue mctlhq/mctl-api#989 is slice M1b/2 of the #954 decomposition (owner GO
2026-11-09). A Glovo order needs exactly one `aar_` action approval. That approval is
the only human authorization for the order's one provider write. #957 prepare creates
it `pending`, in the same transaction that writes the order (#988) and the `we_`
execution. The order's owner decides it through the existing WorkItem action-approval
decision route. #985 reserves it for exactly one bridge command. The bridge's write
fence (`bridge.WriteFence`, `internal/bridge/permit.go`) consumes it exactly once,
inside the permit transaction. Today the fence is `refusingFence`, which returns
`ErrWriteFenceUnavailable`, so no permit can be issued.

Today `aar_` (`internal/workitems/action_approvals.go`) is a generic machine with no
tenant, owner, order, connection, install-revision or basket-fingerprint binding. Only
a human admin may decide it (`isHumanAdmin`, `internal/api/handlers_action_approvals.go`).
Its MCP receipt path also lets a failed call return a receipt from `in_flight` to
`consumed`, so the receipt can be used again. A Glovo receipt must never return to a
usable state. This slice adds those bindings, an owner-only decider limited to the Glovo
action kinds, and a Glovo receipt lifecycle on the same row. It also defines how that
lifecycle composes with the bridge's `effect_state`, so that each question has exactly
one source of truth.

Amended 2026-11-09 (b); design.md has the finding -> fix table. The amendment makes the
fence recompute the fingerprint and intent hash from the written command payload,
enforces the lifecycle in the database under a migration role, follows the one lock
order of #957 §6b, drops the order `approved` state, records the decision as
`resource_owner` under a registered policy, follows owner decision A for readiness, and
provides the interfaces #985 and #1044 need.

## User stories

- AS the owner of a Glovo order I WANT to approve or refuse its one `aar_` myself SO THAT
  only I can authorize a write against my Glovo account, and no admin, model or
  clarification answer can do it for me.
- AS the #985 dispatcher I WANT a tx-scoped reserve that binds the `aar_` to exactly one
  `cmd_` SO THAT one approval can never authorize two commands.
- AS the bridge write fence I WANT a single tx-scoped check-and-consume on the `aar_` row
  SO THAT a permit is issued only for the exact tenant, owner, `we_`, order, connection,
  install revision, basket fingerprint, intent hash and provider that the human approved.
- AS a platform admin I WANT admin-only decisions for every other action kind to stay
  admin-only SO THAT the Glovo owner-decider grants no privilege outside Glovo.
- AS an auditor I WANT no approval token, credential or raw basket in Temporal history,
  signals, logs or audit rows SO THAT a leak of those stores cannot replay or reveal an
  order.

## Acceptance criteria (EARS)

Binding and creation
- WHEN #957 prepare calls `CreateGlovoApprovalTx` on its `pgx.Tx` THE SYSTEM SHALL insert
  one `action_approval_requests` row of kind `glovo.place_order_fake` or
  `glovo.cancel_order_fake`, its `glovo.approval_bindings` row, and the #988
  `BindApproval` write, all in that transaction.
- THE SYSTEM SHALL write a complete governance context at create (`intent_source =
  execution:<we_>`, registered policy rule and version, `policy_decision`,
  `policy_reasons`).
- IF a second `aar_` is created for the same `order_ref` THEN THE SYSTEM SHALL refuse it
  through `UNIQUE (order_ref)` with `approval_replayed`.
- IF the generic create route receives any `glovo.` kind THEN THE SYSTEM SHALL refuse it.
- THE SYSTEM SHALL accept only the two exact Glovo kinds for any `glovo.`-prefixed kind,
  enforced by a database CHECK.

Decision
- WHEN the bound owner, a resolved human principal with live tenant membership read
  directly (no admin pass), decides a pending Glovo `aar_` THE SYSTEM SHALL move it to
  `approved` or `denied`, writing only the `aar_` row.
- THE SYSTEM SHALL record `authority_basis = resource_owner` for a Glovo approve, and
  SHALL pass `guardDecision` in strict mode.
- IF any non-admin caller cannot decide the id (unknown, non-Glovo, someone else's, or a
  failed check) THEN THE SYSTEM SHALL answer the same 403 `approval_decider_forbidden`.
- IF an admin who is not the owner, a service, an agent, a CI caller, a relayed or
  surface caller, or a Glovo-audience token decides a Glovo `aar_` THEN THE SYSTEM SHALL
  refuse it.
- THE SYSTEM SHALL leave the decision rules of every non-Glovo kind unchanged.

Lifecycle, enforced in the database
- THE SYSTEM SHALL allow a Glovo `aar_` only the transitions `pending→approved`,
  `pending→denied`, `approved→reserved`, `approved→denied`, `reserved→consumed` and
  `reserved→unknown`, through a trigger, so raw SQL by the runtime role is refused too.
- THE SYSTEM SHALL treat `consumed`, `unknown` and `denied` as final and SHALL never
  return a Glovo `aar_` to `approved`.
- THE SYSTEM SHALL keep `action_kind`, `intent_hash`, `expires_at`, `execution_id`,
  `work_item_id`, `subject_principal_id`, `requested_by` and the policy fields of a
  Glovo row immutable, and SHALL refuse `DELETE` of a Glovo row.
- THE SYSTEM SHALL require, at commit, one binding row per Glovo `aar_`.
- WHILE a `pending`, `approved` or `reserved` row is past `expires_at` or `fresh_until`
  THE SYSTEM SHALL expose it as `expired`. A `reserved` row past expiry SHALL be able to
  move only to `unknown`.
- THE SYSTEM SHALL refuse every generic consume, reserve, settle or mark-executed path on
  a Glovo row.

Reserve, revoke, status
- WHEN #985 reserves THE SYSTEM SHALL require every command field to equal the binding,
  SHALL be idempotent for the same `cmd_`, and SHALL refuse a different `cmd_` with
  `approval_replayed`.
- WHEN #985 cancels before dispatch THE SYSTEM SHALL move a `pending` or `approved` `aar_`
  to `denied` through `RevokeGlovoApprovalTx`.
- WHEN the control worker reads an approval THE SYSTEM SHALL return ids and enums only,
  and `not_found` outside its `tenants` bound.

Fence
- WHEN `permitTx` runs for a Glovo command THE SYSTEM SHALL take L1 shared, L2 shared, L3
  and L4 in `PreLock` before the command lock, per #957 §6b.
- THE SYSTEM SHALL recompute the basket fingerprint from the stored command payload's
  approval basket, and the intent hash from the command row and that fingerprint, and
  SHALL refuse the permit unless both equal the `aar_` binding, the order's final
  fingerprint and the command's stored `intent_hash`.
- THE SYSTEM SHALL require the `aar_` to be `reserved` for this `cmd_`, unexpired, the
  owner to be a live member, the connection live at the bound install revision, and the
  order `dispatched` for this `cmd_`, and SHALL then consume the `aar_` in the same
  transaction as the `bridge_write_permits` row.
- IF any check fails THEN THE SYSTEM SHALL roll back the permit and answer with the code
  of the design §10 map.

Outcome
- WHEN a reserved command ends without a permit THE SYSTEM SHALL move the `aar_` to
  `unknown`, through #985 cancel or the sweeper, without locking L4 after L5.
- THE SYSTEM SHALL keep the provider outcome only in `bridge_commands.effect_state`.

Readiness
- WHILE `GLOVO_DB_URL`, `COMMERCE_DB_URL` or `WORK_ITEMS_DB_URL` is not set explicitly,
  #985 `ProveOneDatabase` has not passed, a trigger is missing or disabled, a table is
  owned by the runtime role, the policy is unregistered, or a collaborator is nil, THE
  SYSTEM SHALL keep `refusingFence` and answer `not_ready` from every Glovo approval
  method.
- THE SYSTEM SHALL create its schema objects only through `ApplyGlovoApprovalSchema`
  under the migration role.

Secrecy
- THE SYSTEM SHALL never write `args_digest`, a basket, a credential or a token to audit
  rows or logs for Glovo kinds.
- THE SYSTEM SHALL carry `approval_ref` and the fingerprint in `GlovoControlInput` as
  the merged #957 §6c and #1044 M10 specify, and nothing else from this slice.

## Out of scope

- The order tables (#988), the prepare route (#957), dispatch and cancel (#985), the
  connection store and revokers (#959/#960). This slice calls their interfaces.
- The approval basket schema and vectors (mctl-agents#1059).
- Any real Glovo provider, payments, or opening `glovo.Default`.
- Generic `aar_` behaviour of non-Glovo kinds.

## Open questions

Closed by the amendment: the `consumed`/`unknown` reading (kept: `consumed` = spent at a
permit; provider outcome in `effect_state`), expired versus `unknown` (`unknown` wins),
and refused stored as `denied` (kept).

- OPEN-989-1. Ownership of `action_approval_requests` moves to the migration role, and
  the generic work-items DDL moves out of `NewStore` (task 2b). This changes generic
  work-items startup, so the owner decides. Until then Glovo stays `not_ready`.
- OPEN-989-2. Role provisioning for the migration and runtime roles (shared with
  OPEN-985-6 and OPEN-988-3).
- OPEN-989-3. Minimum live tenant role for the owner-decider: `developer` is proposed.
- OPEN-989-4. mctl-telegram#1262 must write exactly the command payload's approval
  basket lines and never a re-read basket; it vendors #1059. Tracked there.
- OPEN-989-5. The fingerprint of a low-entropy fake basket travels in
  `GlovoControlInput` (Temporal history), as the merged #957/#1044 contracts say. The
  owner accepts this for fake-only M1, or asks for a keyed digest before real data.
- OPEN-989-6. The `place_order_fake` command payload must carry the approval basket
  (= OPEN-985-8 = mctl-agents OPEN-1059-1).
