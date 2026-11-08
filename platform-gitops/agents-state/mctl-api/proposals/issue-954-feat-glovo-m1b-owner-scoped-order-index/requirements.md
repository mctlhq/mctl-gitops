# Glovo M1b: owner-scoped order index and single-use aar_ receipt at the fake-provider write boundary

## Context

Glovo M0 (mctl-telegram ADR 0010) requires every basket mutation to be authorized by
a canonical `aar_` ActionApprovalRequest that is bound to exactly one MCTL execution
(`we_`) and exactly one basket effect. A human-input answer (`hir_`) is clarification
and must never authorize anything. mctl-api already has the `aar_` lifecycle
(`internal/workitems/action_approvals.go`: create, decide, consume, reserve, settle)
and a pure checkpoint model for automations (`internal/automation/contract/authority.go`,
merged in mctl-api#950), but no order index, no owner scoping of provider effects, and
no write boundary that ties an `aar_` receipt to a provider I/O call.

This proposal (M1b) adds, behind a default-off switch and against a synthetic provider
only: a canonical owner-scoped order index with opaque server-assigned ids and
immutable basket snapshots; an effect ledger with one effect per `we_`; owner approval
of the existing `aar_` type with the order binding encoded in its existing intent
fields; and a reserve -> dispatch -> settle boundary that fails closed and makes zero
provider writes for any invalid, replayed, mismatched, expired, stale-revision,
revoked or wrong-owner grant. It depends on M1a (connection registry). Nothing in
this slice talks to real Glovo.

## User stories

- AS a tenant member who owns a Glovo connection I WANT to approve one specific basket
  effect for one specific execution SO THAT nothing else, and no other execution, can
  use my approval.
- AS a tenant member I WANT orders of other tenants and of other owners in my tenant to
  be invisible to me SO THAT an order id cannot be used to reach someone else's basket.
- AS the isolated provider worker I WANT a signed, single-use, short-lived effect
  authorization from mctl-api SO THAT I can refuse anything mctl-api did not authorize
  without holding user credentials in workflow history.
- AS a platform operator I WANT audit entries and metrics with redacted effect ids,
  hashed intents, receipt ids and outcomes SO THAT I can reconstruct every effect
  without seeing a raw basket, a provider secret or another tenant's order.
- AS a reviewer I WANT contract tests with a fake provider that counts writes, plus
  negative canaries SO THAT "zero writes" and "exactly one write" are proven, not
  asserted.

## Acceptance criteria (EARS)

Order index and ownership

- WHEN an order is created THE SYSTEM SHALL assign an opaque server-generated id
  (`pord_` prefix, random, never derived from provider data) and record it under the
  scope (tenant, owner principal id, connection id, install id, install revision) taken
  from authentication and the M1a connection registry, never from the request body.
- WHEN a basket snapshot is recorded THE SYSTEM SHALL store it append-only with a
  server-computed basket fingerprint (`sha256:` of a canonical encoding) and SHALL NOT
  store the raw basket in audit entries, metrics or logs.
- WHILE an order has a final basket fingerprint THE SYSTEM SHALL refuse any further
  snapshot for that order.
- IF a caller names an order that belongs to another tenant, another owner in the same
  tenant, or does not exist THEN THE SYSTEM SHALL answer the same not-found response in
  all three cases (no existence oracle).
- IF an order was created under an install revision that is no longer the connection's
  current revision, or under a connection that has been revoked or replaced by a
  reconnect, THEN THE SYSTEM SHALL refuse every effect for it with zero provider I/O.

Approval binding

- WHEN an effect approval is requested THE SYSTEM SHALL create an ordinary `aar_` via
  the existing `CreateActionApproval` whose intent fields bind execution_id (`we_`),
  action_kind, a target string encoding provider target, connection id, install id and
  revision and order id, args_digest = mutation_intent_hash, artifact_hash =
  final basket fingerprint, work_item_id, policy rule/version and expiry.
- WHEN an `aar_` of a provider-order action kind is decided THE SYSTEM SHALL accept the
  decision only from the order's owner principal acting directly as a human and a live
  member of the order's tenant; an agent, a relayed surface, the requester itself, or a
  `hir_` response SHALL NOT decide it.
- IF an `hir_` response exists for the execution but no approved `aar_` does THEN THE
  SYSTEM SHALL make zero provider I/O.
- IF the presented `aar_` is bound to a different `we_`, a different order, a different
  basket fingerprint or a different mutation intent hash THEN THE SYSTEM SHALL refuse
  with zero provider I/O, even when that `aar_` is approved.

Write boundary

- WHEN an effect is dispatched THE SYSTEM SHALL, in order: re-check live tenant
  membership, connection liveness and install revision; load the order owner-scoped;
  recompute the intent hash and compare it with the stored `aar_`; reserve the receipt
  (`ReserveActionApproval`, consumed -> in_flight); insert the effect row; and only
  then sign one effect authorization for the provider worker.
- WHILE an execution already has an effect row THE SYSTEM SHALL refuse a second effect
  for that `we_` (one execution per requested effect).
- WHEN the same effect is retried with the same idempotency key and the same intent
  THE SYSTEM SHALL return the existing effect and the identical authorization (same
  provider operation key, same deadline), never a new one.
- IF an idempotency key is reused with a different intent THEN THE SYSTEM SHALL refuse
  with `idempotency_key_reused` and zero provider I/O.
- WHEN the provider worker reports a definitive success THE SYSTEM SHALL settle the
  receipt executed and the effect succeeded exactly once; repeated callbacks SHALL be
  idempotent and SHALL NOT change the recorded outcome.
- WHEN the provider worker reports a definitive no-effect failure THE SYSTEM SHALL mark
  the effect failed and settle the receipt as spent (not returned to consumed); a new
  attempt requires a new `we_` and a new `aar_`.
- IF the outcome is ambiguous (timeout, lost response) THEN THE SYSTEM SHALL keep the
  receipt in_flight and the effect unknown, and SHALL resolve it only by provider
  read-back on the same operation key: found -> succeeded; not found after the
  authorization deadline plus clock skew -> failed (no effect); never by re-dispatch.
- IF the tenant membership, the connection or the install is revoked between approval
  and dispatch, or during an activity before dispatch, THEN THE SYSTEM SHALL refuse
  with zero provider I/O.
- IF any authority source (membership, connection registry, approval store) cannot be
  read THEN THE SYSTEM SHALL refuse with `authority_unavailable` and zero provider I/O;
  unknown is never allowed.
- WHILE the feature switch `PROVIDER_ORDERS_ENABLED` is off THE SYSTEM SHALL not
  register the routes and SHALL answer 404 for them.

Credentials, audit, metrics

- THE SYSTEM SHALL never put provider tokens, connection secrets or the effect
  authorization signature in anything it passes to Temporal; workflows carry only
  opaque ids (`pord_`, `pef_`, `aar_`, `we_`).
- THE SYSTEM SHALL authenticate the provider worker by its own scoped machine
  credential and SHALL NOT treat a Temporal task queue as an identity.
- WHEN an effect changes state THE SYSTEM SHALL write an audit entry with effect id,
  tenant, owner principal id, hashed intent, `aar_` id and outcome, and SHALL increment
  a counter labelled only by action kind and outcome (no tenant, order or principal
  labels).
- THE SYSTEM SHALL not perform any HTTP request to Glovo; only the synthetic provider
  contract exists in M1b.

## Out of scope

- Any live Glovo adapter, Glovo credentials, checkout, order placement, payment or
  user-account HTTP access (gated by a later G3 decision).
- The M1a connection registry itself (tenant/connection/install identity, reconnect);
  M1b consumes it through an interface.
- The provider worker implementation in mctl-agents / mctl-telegram; M1b ships the
  contract, a Go fake provider for tests and the verifier contract.
- New MCP tools (the MCP tool count in `internal/mcp/server_test.go` is unchanged).
- Deploying with the switch on; that needs a later release gate.
- Changing `workitems.IntentHash` or the `aar_` state machine for existing callers.

## Open questions

- Who decides a provider-order `aar_`: only the order owner (this proposal's
  assumption), or also a tenant admin, or the platform human admin who is the only
  decider today (`DecideActionApproval` requires `isHumanAdmin`)? Proceeding with
  owner-only, human, direct, live tenant member; platform admin is NOT a decider for
  this action kind.
- The M1a connection registry API (types for connection id, install id/revision,
  revocation) is not in this repo yet. M1b codes against a `ConnectionAuthority`
  interface whose default implementation answers "unavailable" (fail closed) until M1a
  lands. The exact field names need aligning with M1a.
- Whether a definitive no-effect failure should give the receipt back for a retry
  inside the same `we_` (as the MCP receipt gate does) or spend it. Proceeding with
  "spend it", because the issue demands strict single use and one effect per `we_`.
- Where the provider worker runs and which principal it uses (mctl-gitops#2456/#2457
  scope). M1b assumes a dedicated service principal with a single scope
  `provider-orders:effect`.
- The mctl-api deployed configuration could not be observed (see design.md); env var
  names for the switch and signing key are proposals, not observed values.
