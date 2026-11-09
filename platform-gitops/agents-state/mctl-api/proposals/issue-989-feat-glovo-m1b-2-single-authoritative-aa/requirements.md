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
  exactly one `action_approval_requests` row with an action kind in
  `{glovo.place_order_fake, glovo.cancel_order_fake}`, state `pending`, and one immutable
  `glovo_approval_bindings` row in the same transaction. That row records tenant, owner
  principal id (`prn_`), `we_`, `ordr_`, `gcn_`, install id and revision, basket
  fingerprint, provider and `expires_at`.
- THE SYSTEM SHALL compute `intent_hash` with the existing `workitems.IntentHash`. Every
  binding enters the hash through the canonical Glovo `Target` string and an
  `ArgsDigest` equal to the basket fingerprint. A client-sent hash that differs is
  refused with `intent_hash_mismatch`.
- IF an order already has a non-terminal Glovo `aar_` THEN THE SYSTEM SHALL refuse a
  second one. The order row is locked and its `approval_ref` must be empty, so there is
  at most one `aar_` per order.
- WHILE a binding row exists THE SYSTEM SHALL refuse every UPDATE to it except the
  single write of `command_id` from empty to a `cmd_` value. A database trigger enforces
  this.

Decision
- WHEN a decision is posted for a Glovo-kind `aar_` THE SYSTEM SHALL accept it only from a
  direct human caller whose principal id equals the binding's owner principal id and
  who holds a live tenant role of at least `developer` on the binding's tenant. That
  caller is not a service, agent, CI, relayed or surface caller, and does not hold a
  Glovo-audience token.
- IF the caller is a platform admin but is not the owner THEN THE SYSTEM SHALL refuse a
  Glovo-kind decision with 403 `approval_decider_forbidden`.
- WHILE an `aar_` has any non-Glovo action kind THE SYSTEM SHALL keep the existing rule
  that only a human admin acting directly decides. The owner-decider rule SHALL NOT
  apply to any other kind.
- IF the caller has no role on the binding's tenant THEN THE SYSTEM SHALL answer 404
  `approval_not_found` and leak nothing.
- WHEN an approve and a refuse for the same `aar_` race THE SYSTEM SHALL let exactly one
  succeed. The other gets 409 `approval_already_decided`.
- IF the only input is a `hir_` human-input answer or a model or tool output THEN THE
  SYSTEM SHALL make no state change to any `aar_`, order or bridge command (zero effects).

Receipt lifecycle (Glovo kinds only)
- THE SYSTEM SHALL expose the receipt states
  `pending -> approved -> reserved -> consumed | unknown`, plus `refused` (stored as
  `denied`) and `expired` (derived lazily from `expires_at` while the state is
  `pending`, `approved` or `reserved`).
- WHEN #985 dispatch calls `ReserveGlovoApprovalTx(tx, id, cmd_)` THE SYSTEM SHALL move
  `approved -> reserved` with one compare-and-set. The CAS is guarded by state, intent
  hash, unexpired and fresh state, and an empty `command_id`, and it writes `command_id`
  in the same statement.
- WHEN the bridge calls `WriteFence.Check(ctx, tx, FenceBinding)` THE SYSTEM SHALL lock
  the `aar_` row `FOR UPDATE` and verify all of the following:
  - the kind is a Glovo kind and the state is `reserved`;
  - `command_id`, `we_`, work item, tenant, owner, connection, install revision and
    intent hash equal the stored command row;
  - the expiry and `fresh_until` have not passed;
  - the owner still holds a live tenant role;
  - the connection is still active at the bound install revision;
  - the order's `final_basket_fingerprint` equals the bound fingerprint.

  Only when every check passes SHALL it move `reserved -> consumed`, in the caller's
  transaction, and return an opaque fence reference.
- IF the order's fingerprint differs from the bound fingerprint at the fence THEN THE
  SYSTEM SHALL refuse with `fingerprint_changed` (wrapping `bridge.ErrWriteFenceRefused`)
  and issue no permit.
- WHILE a Glovo `aar_` is `consumed`, `unknown`, `refused` or `expired` THE SYSTEM SHALL
  never move it to any other state. No Glovo `aar_` SHALL ever reach `in_flight` or
  `executed`, or return to `approved`.
- IF a Glovo `aar_` is presented to the generic consume, reserve, settle or
  mark-executed paths (HTTP or MCP receipt gate) THEN THE SYSTEM SHALL refuse it with
  `approval_kind_not_spendable_here`.
- WHEN a connection is reconnected (a new `gcn_` or install revision) THE SYSTEM SHALL
  NOT let any `aar_` bound to the old connection or revision pass the fence. A reconnect
  never revives a receipt.
- WHEN the bridge command bound to a `reserved` `aar_` ends without a permit (expired,
  cancelled or completed with effect `none` or `not_performed`) THE SYSTEM SHALL move
  the `aar_` to `unknown` in the same transaction. It is never released back to
  `approved`.

Composition with the bridge (one source of truth)
- THE SYSTEM SHALL hold the invariant: a Glovo `aar_` is `consumed` if and only if a
  `bridge_write_permits` row exists for its `command_id`. Both are written in the one
  permit transaction.
- THE SYSTEM SHALL keep the provider outcome only in `bridge_commands.effect_state`
  (`permitted -> succeeded | failed | not_performed | unknown`). It SHALL NOT copy that
  outcome onto the `aar_`.

Secrecy
- THE SYSTEM SHALL write only ids (`aar_`, `cmd_`, `we_`, `ordr_`), state names and
  refusal codes to `slog`, audit rows and any Temporal input or signal this slice
  touches. It SHALL NOT write a basket, line items, fingerprint, lease token, permit
  token or credential to them.

Readiness
- WHILE `glovo.Default` is closed, or the co-location proof of #985 has not passed, THE
  SYSTEM SHALL leave the bridge on `refusingFence`. Every Glovo approval method SHALL
  answer `not_ready`.

## Out of scope

- The order index tables and `Transition` (#988), the prepare route and its transaction
  (#957), the dispatch and cancel routes, the control-worker principal and
  `bridge.Store.Enqueue` calls (#985), and connection, team-grant and allowlist storage
  (#959/#960). This slice only calls their interfaces.
- Any real (non-fake) Glovo provider, payments, or opening `glovo.Default`.
- Changes to the generic `aar_` behaviour of non-Glovo kinds, including the
  `in_flight -> consumed` release used by the MCP receipt gate.
- Removing the bridge's `AUDIT_DB_URL` fallback (mctl-api#987).

## Open questions

- The issue lists `unknown` as a terminal state next to `consumed`. This proposal makes
  `consumed` mean "the authorization was spent: a permit was issued". `unknown` means
  "reserved, but the command ended without a permit, or its state could not be read".
  The provider outcome stays in the bridge's `effect_state`. Under the alternative,
  `consumed` and `unknown` would mirror the provider outcome, which would duplicate the
  bridge state. The reviewer should confirm the chosen reading.
- A reserved receipt whose command expired without a permit provably caused no write.
  This proposal still moves it to `unknown`, which is fail-closed and never reusable.
  The owner prepares a new order. Should it instead read `expired`?
- Refused is stored as the existing `denied` and exposed as `refused` in the Glovo view,
  so the shared CHECK constraint does not gain a synonym. The reviewer should confirm.
- The minimum live tenant role for the owner-decider is assumed to be `developer`,
  matching WorkItem writes. The issue does not say.
- The deployed values of `COMMERCE_DB_URL` and `WORK_ITEMS_DB_URL` for mctl-api could
  not be observed (see design.md, "Deployed state checked").
