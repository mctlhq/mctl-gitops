# Glovo M1b/3: control-worker dispatch/cancel with aar_ re-check and atomic bridge enqueue

## Context

Glovo M1 splits the fake-order write path into slices. #957 owns the client side
(`/resolve`, preview, prepare, creating the pending `aar_`, the workflow-start
outbox). Nothing owns the route the trusted control worker (mctlhq/mctl-agents#1044)
uses to ask mctl-api to dispatch or cancel one approved fake order. This slice
(M1b/3 of #954, extended by the owner decision of 2026-11-09, OPEN-3 of the #957
amendment) adds two internal routes for that worker. Each call re-checks, inside one
`pgx.Tx`, the `aar_` binding, live connection revocation, tenant membership and the
order state (CAS), and then calls the in-process `bridge.Store.Enqueue(ctx, tx, ...)`
in the same transaction (owner decision M7 = (b)). The server issues the `cmd_`.

It matters because this is the only point at which an approved human intent becomes
a provider command. Each valid intent must produce exactly one bridge command, the
revocation race must be fenced at the actual write, and nothing may become a generic
or public enqueue path. Fake provider only. The write fence stays blocked while
hold mctlhq/mctl-gitops#2457 is ON.

## User stories

- AS the Glovo control worker (mctl-agents#1044) I WANT to dispatch one approved
  fake order by naming its `order_ref` and `aar_` SO THAT the provider receives
  exactly one bridge command for that approved intent.
- AS the Glovo control worker I WANT to cancel one order SO THAT a command that has
  not been carried out is stopped, and a possibly-performed one is recorded as
  `unknown` and never re-armed.
- AS a tenant owner I WANT my revocation of a connection or of a membership to win
  against any write that has not been physically permitted yet SO THAT a revoked
  grant can never place an order.
- AS a platform operator I WANT the route to answer `not_ready` whenever its stores,
  database co-location proof or feature gate are missing SO THAT a
  misconfiguration fails closed instead of writing.

## Acceptance criteria (EARS)

Identity and exposure
- WHEN a request reaches `POST /api/v1/internal/glovo/orders/{order_ref}/dispatch`
  or `.../cancel` THE SYSTEM SHALL admit it only if the authenticated user is the
  dedicated control-worker principal (`service:glovo-control-worker`).
- IF the caller is a human user, an admin, a Glovo-audience (facade) token, a
  bridge-provider token, an agent, a surface, a CI principal or any other service
  principal THEN THE SYSTEM SHALL refuse with 403 `not_authorized` before any
  database read.
- WHILE a request is authenticated as the control-worker principal THE SYSTEM SHALL
  refuse every route other than the two above with 403, before any handler runs.
- THE SYSTEM SHALL expose no HTTP route that enqueues a generic bridge command; the
  only callers of `bridge.Store.Enqueue` for `place_order_fake` remain in-process.

Readiness
- IF the Glovo control gate is closed, the bridge store, work-items store, order
  index or connection store is not configured, or the startup co-location proof
  failed THEN THE SYSTEM SHALL answer 503 `not_ready` and write nothing.

Dispatch
- WHEN a valid dispatch arrives THE SYSTEM SHALL, in one `pgx.Tx`: lock the order
  row, lock the `aar_` row, lock the connection row (shared), check membership,
  check every binding, consume the `aar_`, CAS the order to `dispatched`, and call
  `bridge.Store.Enqueue` with `Kind=place_order_fake`, then commit; all of it or
  none of it is persisted.
- THE SYSTEM SHALL bind the `aar_` to tenant, owner principal, execution `we_`,
  `order_ref`, `connection_ref`, install revision, basket fingerprint and intent
  hash, and SHALL refuse with 409 `approval_binding_mismatch` if any differs from
  the locked order row.
- IF the `aar_` is expired or past its freshness bound THEN THE SYSTEM SHALL refuse
  with 409 `approval_expired`.
- IF the `aar_` is consumed (or in flight or executed) and the order is not already
  dispatched under that same `aar_` THEN THE SYSTEM SHALL refuse with 409
  `approval_consumed`.
- IF the `aar_` or order belongs to another tenant or owner, or does not exist, THEN
  THE SYSTEM SHALL answer 404 `order_not_found` (no existence oracle).
- IF the order's basket fingerprint differs from the one bound in the `aar_` THEN
  THE SYSTEM SHALL refuse with 409 `approval_binding_mismatch`.
- IF the connection is revoked, or its current install revision differs from the
  bound one, THEN THE SYSTEM SHALL refuse with 409 `connection_revoked`.
- IF the owner principal is no longer a member of the tenant THEN THE SYSTEM SHALL
  refuse with 403 `membership_revoked`.
- WHEN a dispatch repeats for an order already dispatched under the same `aar_`
  THE SYSTEM SHALL return 200 with the same `cmd_` and `replayed: true` and SHALL
  create no second command.
- WHEN two dispatches for the same order race THE SYSTEM SHALL serialize them on the
  order row lock so that exactly one command exists afterwards and both callers
  receive the same `cmd_`, or the loser receives a 409.
- IF a dispatch arrives for an order that is `cancelled` THEN THE SYSTEM SHALL
  refuse with 409 `order_cancelled`.
- IF a dispatch names a different `aar_` for an order already dispatched THEN THE
  SYSTEM SHALL refuse with 409 `order_already_dispatched`.

Cancel
- WHEN a cancel arrives for an order that is not yet dispatched THE SYSTEM SHALL CAS
  the order to `cancelled` in one transaction and SHALL leave the `aar_` unconsumed
  but unusable for this order.
- WHEN a cancel arrives for a dispatched order THE SYSTEM SHALL call
  `bridge.Store.Cancel(ctx, tx, cmd, actor)` in the same transaction as the order
  CAS, so a `permitted` effect becomes `unknown`, and SHALL never return the `aar_`
  to `approved`.
- WHEN a cancel repeats THE SYSTEM SHALL return 200 with the current state and
  change nothing.
- IF the dispatched command is already `completed` or `expired` THEN THE SYSTEM
  SHALL answer 409 `already_completed` and change nothing.

Revocation race
- WHILE the write fence is installed THE SYSTEM SHALL re-check connection
  revocation, install revision, membership and `aar_` binding inside the
  `IssueWritePermit` transaction (`bridge.WriteFence.Check`), which is the actual
  write.
- WHEN a revocation commits before a dispatch or permit transaction takes its
  connection lock THE SYSTEM SHALL refuse that dispatch or permit.
- WHEN a dispatch or permit commits before a revocation THE SYSTEM SHALL make the
  revocation wait for the row lock and then cancel every open command of that
  connection through `bridge.Store.Cancel` (so a permitted effect becomes
  `unknown`).
- IF the order index, connection store, `action_approval_requests` and
  `bridge_commands` are not proven at startup to be in one database THEN THE
  SYSTEM SHALL keep the routes `not_ready` and the fence refusing.

Data hygiene
- THE SYSTEM SHALL accept no provider payload, credential, endpoint or token in the
  request body; the body names only ids (`approval_ref`, `execution_id`).
- THE SYSTEM SHALL return and audit only ids, codes and digests: never a payload,
  nonce, lease token or credential.

## Out of scope

- The order index itself (M1b/1) and the `aar_` receipt binding columns (M1b/2);
  this slice consumes their interfaces and fails closed without them.
- The connection store and its revocation write path (#959/#960), except the
  requirement that revocation takes the connection row lock and cancels open
  commands.
- Client-side `/resolve`, preview, prepare and `aar_` creation (#957).
- The control worker (mctl-agents#1044) and the provider (mctl-telegram#1262).
- Enqueuing a compensating `cancel_order_fake` command for an order the provider
  may already have placed.
- Lifting hold mctlhq/mctl-gitops#2457 or opening `glovo.Default`. Real Glovo access.

## Open questions

- Tenant membership is read from GitOps (`gitops.PrincipalMembership`,
  `internal/api/tenant_role.go` `checkTenantRoleByPrincipal`), not from Postgres, so
  it cannot be locked inside the transaction. This proposal assumes membership
  removal also writes a revocation to the connection row (#959/#960); until that
  hook exists, membership is checked before and inside the transaction
  best-effort, and the write fence stays refusing. Confirm the owner accepts that.
- Does M1b/1 or this slice install the concrete `bridge.WriteFence` via
  `Store.SetFence`? This proposal implements one shared check function used by both
  dispatch and the fence. It still installs the fence only behind the closed build
  gate.
- How does the control worker authenticate: a workload token with
  issuer/subject/audience, as bridge providers do, or a federated OIDC machine user,
  as the orchestrator DevLoop principal does? This proposal mirrors the bridge
  provider (workload token, audience `mctl-api-glovo-control`).
- Should cancel of a `permitted`/`unknown` dispatch also enqueue a
  `cancel_order_fake` command, which needs its own `aar_`? Deferred here.
- The exact order-state vocabulary and the `aar_` binding column names depend on
  M1b/1 and M1b/2, which are not in the clone yet.
