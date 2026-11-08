# Design: issue-954-feat-glovo-m1b-owner-scoped-order-index

## Current state

What exists in the clone (HEAD 722d839):

- `internal/workitems/action_approvals.go` — the `aar_` ActionApprovalRequest.
  - `ActionIntent` + `IntentHash` (lines ~313-357): a versioned, length-prefixed
    SHA-256 over execution_id, action_kind, target, args_digest, policy_rule_id,
    policy_version, artifact_hash, work_item_id. Tenant and principal are not part of
    the hash; the table `action_approval_requests` has no tenant column (the tenant is
    reached through the execution's work item).
  - State machine pending -> approved|denied, approved -> consumed (`ConsumeActionApproval`,
    CAS on state + intent hash + expiry), consumed -> in_flight
    (`ReserveActionApproval`, CAS on requester, target, non-empty artifact_hash,
    consumed_at age bound and fresh_until), in_flight -> executed|consumed
    (`SettleActionApproval(succeeded)`). Lazy expiry; idempotent per
    (requested_by, idempotency_key).
  - `SettleActionApproval(..., false)` puts the receipt back to `consumed` so it can be
    retried. That is right for the MCP gate, but wrong for a provider write whose
    outcome is ambiguous: it would allow a second dispatch.
- `internal/api/handlers_action_approvals.go` — HTTP layer. `DecideActionApproval`
  (line 652) admits only `isHumanAdmin(user)`; there is no notion of an owner decider.
  Create admits agents bound to an open execution (`admitAgentApprovalCreate`,
  `requireOpenExecution`). Routes in `internal/api/router.go` lines 789-792 and 922-923.
  Audit via `auditActionApproval` / `auditActionApprovalRefusal`.
- `internal/mcp/agent_receipt_gate.go` — reserve-before-call / settle-after-call for
  governed MCP tools (mctl-api#772/#773). It documents that a cancelled/timed-out call
  "spends" the receipt and an unsettleable reservation stays in_flight (fail closed).
  The same discipline is reused here, with a stricter failure rule.
- `internal/commerce/dispatch.go` — ADR 020 dispatch: a once-written
  `dispatch_deadline` fence, deterministic Ed25519 authorization (`DispatchSigner`),
  provider-side dedupe on the operation key, `MaxClockSkew` before a provider
  `not_found` is definitive. This is the template for the effect authorization and the
  timeout read-back.
- `internal/automation/contract/authority.go` — `Decide(Checkpoint, Inputs)` pure
  function (from mctl-api#950): denies on any unavailable source, non-live link,
  unknown/revoked/expired install, non-member, owner mismatch (as not-found), policy
  drift, approval bound to another execution (`CodeApprovalNotReusable`), and missing
  approval at `CheckpointSideEffect`. Its comment says it has no production caller yet.
- `internal/workitems/types.go` — `ExecutionIDPrefix = "we_"`; `Store.ExecutionByID`
  (`store.go:780`) resolves an execution with its tenant.
- `internal/humaninput/` — `hir_` request/response contract and ledger. It has no path
  into approvals and this design adds none.
- No Glovo, connection-registry, `connection_id` or `install_id` code exists in the repo
  (grep over `*.go`). M1a is not merged.
- `CLAUDE.md`: interface-based design, `fmt.Errorf("...: %w")`, `writeError`/`writeJSON`,
  MCP tool count asserted in `internal/mcp/server_test.go`.

Deployed state checked:

- `mctl_get_service_config(team=admins, service=mctl-api)` -> error "service not found:
  admins/mctl-api". mctl-api is not a catalogue tenant service under that name.
- `$MCTL_GITOPS_ROOT/services/*/` listing: tenants admins, karabu, labs, namax66; no
  `mctl-api` directory. `grep -l mctl-api services/*/*/values.yaml` only hits clients
  (mctl-agents-worker*, mctl-support, labs/mctl-telegram*, etc.).
- Result: mctl-api's own deployed env vars, replicas and secrets could NOT be observed
  in this run (it is likely deployed from a platform path outside the mounted
  directories). Nothing below claims a deployed value; env var names are proposals.

## Proposed solution

### 1. New package `internal/providerorders`

Postgres store following the `workitems` pattern (`CREATE TABLE IF NOT EXISTS` at store
init, pgx, injectable clock). Three tables:

- `provider_orders` — `id TEXT PK` (`pord_` + random 128-bit, opaque),
  `tenant`, `owner_principal_id`, `connection_id`, `install_id`, `install_revision`,
  `provider` (only `fake` accepted in M1b), `state` (`open`, `finalized`, `closed`),
  `final_basket_fingerprint` (empty until finalized), `created_at`.
  Every read is `WHERE id=$1 AND tenant=$2 AND owner_principal_id=$3`; a miss is
  `ErrOrderNotFound` regardless of cause.
- `provider_order_snapshots` — `(order_id, seq)` PK, `basket_fingerprint`,
  `line_count`, `created_at`. The raw basket is not stored in mctl-api in M1b; only its
  fingerprint is, and the raw basket stays with the provider worker. Append-only: no
  UPDATE/DELETE statement exists in the package (asserted by a test that greps the
  package SQL). Finalizing sets `final_basket_fingerprint` once via CAS
  (`WHERE final_basket_fingerprint=''`).
- `provider_effects` — `id TEXT PK` (`pef_` + random), `order_id`, `execution_id`
  `UNIQUE`, `approval_id` `UNIQUE`, `mutation_intent_hash`, `basket_fingerprint`,
  `idempotency_key`, `requested_by`, `operation_key` (= effect id, sent to the provider),
  `dispatch_deadline` (written once), `state` (`reserved`, `dispatched`, `succeeded`,
  `failed`, `unknown`), `outcome_ref` (provider's opaque confirmation, hashed),
  timestamps. `UNIQUE (requested_by, idempotency_key)`.

Basket fingerprint and mutation intent hash use the same length-prefixed SHA-256 style
as `workitems.IntentHash`, with their own version tags (`mctl-basket/v1`,
`mctl-basket-mutation/v1`), so they can never collide with an action intent.

### 2. Binding to the existing `aar_` without forking it

No change to `IntentHash`, the table or the state machine. A provider effect's approval
is an ordinary `aar_` whose `ActionIntent` is:

- `ExecutionID` = the effect's `we_`
- `ActionKind` = `provider.fake.basket.mutate` (constant; the only kind in M1b)
- `Target` = `provider:fake/connection:<cid>/install:<iid>@<rev>/order:<pord_>`
- `ArgsDigest` = mutation_intent_hash; `ArtifactHash` = final basket fingerprint
- `WorkItemID`, `PolicyRuleID`, `PolicyVersion` as today; `expires_at` as today.

Tenant and principal are enforced by the order row (owner-scoped read) and by the
execution's work item tenant (`ExecutionByID`), checked to be equal to the order's
tenant. Because the target and artifact hash are in the hash and in the
`ReserveActionApproval` CAS, an `aar_` approved for another order, basket, revision or
`we_` cannot be reserved for this effect.

### 3. Owner decider for provider-order kinds

In `DecideActionApproval`, before the `isHumanAdmin` check, branch on
`cur.ActionKind` in a closed set `providerorders.OwnerDecidedKinds`:

- the caller must be a human acting directly (not `isDirectService`, not an agent run
  token, not relayed — reuse the existing predicates in the same file);
- `providerorders.Store.OrderForTarget(target)` must resolve, and
  `caller principal id == order.owner_principal_id`;
- live tenant membership of the caller in `order.tenant` (existing tenant membership
  check used by work items), and live connection/install via `ConnectionAuthority`;
- the existing self-decision guard still applies (requester is the worker principal).

The branch is active only when `PROVIDER_ORDERS_ENABLED` is on; with the switch off a
provider-order `aar_` falls back to today's rule and has no dispatch route.
For these kinds the platform human admin is not a decider (owner-only). All other kinds
keep today's `isHumanAdmin` rule unchanged. `hir_` has no route into this handler.

### 4. Live authority: `ConnectionAuthority` + `contract.Decide`

```go
type ConnectionAuthority interface {
    // Resolve returns the live state of a connection/install for a principal.
    Resolve(ctx context.Context, tenant, principalID, connectionID, installID string) (ConnectionState, error)
}
```

`ConnectionState` maps to `contract.LinkState` / `contract.InstallState` plus the current
install revision. The default implementation `unavailableAuthority` returns an error,
so with M1a absent every checkpoint yields `CodeAuthorityUnavailable`. A boundary
helper `checkpoint(ctx, cp, order, executionID, approval)` builds `contract.Inputs` and
calls `contract.Decide` — giving that function its first production caller. Revision
mismatch (order revision != current) is mapped to `InstallExpired`. Reconnect in M1a
yields a new `connection_id`, so old orders and their `aar_` targets can never match.

Checkpoints run at: order creation (`CheckpointCreateUpdate`), effect request
(`CheckpointFire`), immediately before signing the authorization
(`CheckpointSideEffect`), on every worker callback, and on order status reads.

### 5. Write boundary (`internal/providerorders/boundary.go`)

`Boundary.Dispatch(ctx, caller, req)`:

1. `CheckpointSideEffect` (membership, connection, install revision). Fail -> zero I/O.
2. Load order owner-scoped; require `finalized` and fingerprint == req fingerprint.
3. Recompute the `ActionIntent` from the order + req and compare `IntentHash` with the
   `aar_`'s stored `intent_hash`; require `aar_.ExecutionID == req.ExecutionID` and the
   execution open and in the order's tenant.
4. In one transaction: insert `provider_effects` (UNIQUE execution_id / approval_id /
   idempotency key; a replay with the same key and same intent returns the stored row)
   and `ReserveActionApproval(id, target, fingerprint, caller, maxAge)`. The reservation
   is the single-use fence; a second dispatcher gets `ErrApprovalInFlight` /
   `ErrApprovalExecuted`. (Reserve uses `s.pool`; add a `ReserveActionApprovalTx`
   variant taking a `pgx.Tx` — additive, same SQL.)
5. Write `dispatch_deadline` once (CAS on NULL) and sign an `EffectAuthorization`
   with an Ed25519 signer modelled on `commerce.DispatchSigner` (own key id, own
   version tag `mctl-provider-effect/v1`) over: effect id, operation key, order id,
   connection/install/revision, fingerprint, mutation intent hash, `aar_` id, `we_`,
   deadline. Deterministic: a retry gets the identical bytes.
6. Return the authorization to the worker. The worker verifies it at its ingress with
   the public key and dedupes on the operation key; it never receives user tokens from
   mctl-api and never writes them into Temporal history: workflows pass ids only, and
   the activity fetches the authorization and uses it in-process, never returning it
   as an activity result or passing it as an input.

`Boundary.Report(ctx, caller, effectID, outcome)` (worker callback):

- `succeeded` -> effect `succeeded` (CAS from `dispatched|unknown`), then
  `SettleActionApproval(id, caller, true)`.
- `failed_no_effect` -> effect `failed`, then `SettleActionApproval(id, caller, true)`
  as well: in this action kind the receipt is spent by any definitive outcome
  (aar_ `executed` here means "spent"; the outcome lives on the effect row). This is
  deliberately stricter than the MCP gate. A retry needs a new `we_` and new `aar_`.
- `unknown` (timeout) -> effect `unknown`, receipt stays `in_flight`.
- Repeated callbacks with the same terminal outcome return the stored row; a
  conflicting terminal outcome is refused and audited.

`Boundary.ReadBack(ctx, effectID)` (reconciler and on-demand): asks the worker's
read-back endpoint for the operation key. Found -> succeeded; not found and
`now > dispatch_deadline + commerce.MaxClockSkew` -> failed (no effect); otherwise
remains unknown. Never re-dispatches.

### 6. HTTP routes (behind `PROVIDER_ORDERS_ENABLED`, default off)

Registered in `internal/api/router.go` only when the switch is on:

- `POST /api/v1/provider-orders` (owner, human or owner-delegated surface) — create.
- `POST /api/v1/provider-orders/{id}/snapshots`, `POST .../{id}/finalize`.
- `GET /api/v1/provider-orders/{id}` — owner-scoped status (runs the checkpoint).
- `POST /api/v1/provider-orders/{id}/effects` — worker principal with scope
  `provider-orders:effect` only; returns effect + authorization.
- `POST /api/v1/provider-effects/{id}/outcome`, `POST .../{id}/read-back` — worker only.

The `aar_` itself is created and consumed through the existing
`/action-approvals` routes by the worker principal (bound to the `we_`), and decided by
the owner through the existing decision route (section 3).

### 7. Fake provider and contract tests

`internal/providerorders/fakeprovider` (test-support package, not linked into
`cmd/api`): an in-memory provider that verifies `EffectAuthorization`, dedupes on the
operation key, counts writes, and can be told to time out after applying, time out
before applying, or reject. Contract tests drive the real HTTP handlers against
Postgres (same harness as existing workitems store tests) and assert write counts.
Negative canaries: a test that deliberately sends a mismatched grant must observe
`writes == 0`, and a sentinel test proving the counter does move for a valid grant (so
"0" is not a broken counter).

### 8. Audit and metrics

Audit entries via the existing audit logger, ops `provider_order.created`,
`provider_effect.dispatched|succeeded|failed|unknown|refused`, fields: effect id,
tenant, owner principal id, mutation intent hash, `aar_` id, outcome, refusal code.
Never: basket contents, provider refs in clear (hashed), authorization signature.
Metric `mctl_provider_effects_total{action_kind,outcome}` — no tenant/order labels.

## Alternatives

1. Extend `IntentHash` with tenant, principal, connection and order fields. Dropped: it
   changes the hash of every existing `aar_` (breaking mctl-agents and the MCP gate)
   and forks the encoding the issue says to reuse. The target string and artifact hash
   already carry the binding, and tenant/owner are enforced by the owner-scoped order.
2. Reuse the MCP receipt gate (`agent_receipt_gate.go`) and expose the fake provider as
   a governed MCP tool. Dropped: the gate does not bind arguments (documented in its
   header), returns a receipt on handler failure, and puts provider mutation behind the
   public MCP gateway, which the issue explicitly rejects.
3. Authorize via `hir_` answer or a signed "confirm" flag on a tool call. Dropped by the
   issue and ADR 0010: `hir_` is clarification only, and an unsigned flag is not an
   action receipt.
4. Put the order index in the commerce ledger (`internal/commerce`). Dropped: commerce
   models paid capability invocations with budgets and pricing; an order index with
   owner scoping and basket snapshots is a different aggregate, and coupling them would
   make M1b depend on commerce funds modes.

## Platform impact

- Migrations: three new tables created idempotently at store init; no change to
  existing tables. One additive store method (`ReserveActionApprovalTx`) in
  `workitems`. Existing `aar_` behaviour for all other action kinds is unchanged.
- Backward compatibility: routes are not registered unless `PROVIDER_ORDERS_ENABLED=true`;
  the owner-decider branch only triggers for the new action kind, which no existing
  client creates. MCP tool count unchanged.
- Resources: negligible (small tables, no background job except an optional read-back
  reconciler that is off with the switch).
- New config (proposed names, not observed): `PROVIDER_ORDERS_ENABLED`,
  `PROVIDER_EFFECT_SIGNING_KEY_ID`, `PROVIDER_EFFECT_SIGNING_SEED` (Vault-sourced),
  `PROVIDER_EFFECT_DISPATCH_WINDOW` (default 60s), `PROVIDER_EFFECT_RECEIPT_MAX_AGE`.
  With no key configured, dispatch fails closed (`dispatch_unavailable`), like commerce.
- Risks and mitigations:
  - Double write on timeout -> receipt never returns to consumed for this kind;
    read-back only, operation-key dedupe at the provider, once-written deadline.
  - Cross-tenant/owner leakage -> every query keyed by (id, tenant, owner); uniform
    not-found; metrics without tenant labels; tests for two tenants and same-tenant
    different owner.
  - M1a not ready -> default `ConnectionAuthority` is unavailable, so the feature is
    inert (every checkpoint denies) even if switched on.
  - Owner-decider widening the decider set -> closed kind set, human-direct-only,
    live membership re-check; dedicated tests that admin, agent and requester are refused.
  - Credentials in Temporal history -> mctl-api never returns provider tokens; the
    authorization is fetched inside the activity; a test asserts the worker contract
    payloads contain only ids and the signed authorization.
