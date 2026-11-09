# Glovo M1b/3: control-worker dispatch/cancel with aar_ re-check and atomic bridge enqueue

## Context

Glovo M1 splits the fake-order write path into slices. #957 owns the client side:
`/resolve`, preview, prepare, creating the pending `aar_`, and the workflow-start outbox.
Nothing yet owns the routes that the trusted control worker (mctlhq/mctl-agents#1044)
uses to ask mctl-api to dispatch or cancel one approved fake order, and to read back a
command result or an approval state.

This slice is M1b/3 of #954. It was extended by the owner decision of 2026-11-09 (OPEN-3
of the #957 amendment) and amended on 2026-11-09 (b); design.md has the finding -> fix
table.

Each dispatch or cancel re-checks the following inside one `pgx.Tx`: the `aar_` receipt
(through the #989 interface), the order (#988), live connection revocation (#959) and
tenant membership. It then calls the in-process `bridge.Store.Enqueue(ctx, tx, ...)` in
the same transaction (owner decision M7 = (b)). The server issues the `cmd_`.

This is the only point at which an approved human intent becomes a provider command, so
three things must hold:
- each valid intent produces exactly one bridge command;
- the revocation race is fenced at the actual write;
- nothing becomes a generic or public enqueue path.

Owner decision A (2026-11-09) puts every participating store in **one physical
database**, used through one shared `pgx.Tx`. It also requires one documented lock
order. Fake provider only. The write fence stays blocked while hold
mctlhq/mctl-gitops#2457 is ON.

## User stories

- AS the Glovo control worker (mctl-agents#1044) I WANT to dispatch one approved fake
  order by naming its `order_ref`, `aar_` and basket fingerprint SO THAT the provider
  receives exactly one bridge command for that approved intent.
- AS the Glovo control worker I WANT to cancel one order SO THAT a command that has not
  been carried out is stopped, and a command that may have been performed is recorded as
  `unknown` and never re-armed.
- AS the Glovo control worker I WANT to read a command's result and an approval's state
  as ids and enums SO THAT I never need a payload to make a decision.
- AS a tenant owner I WANT my revocation of a connection, an install or a membership to
  win against any write that has not been physically permitted yet SO THAT a revoked
  grant can never place an order.
- AS a platform operator I WANT the routes to answer `not_ready` whenever a store, the
  one-database proof or the feature gate is missing SO THAT a misconfiguration fails
  closed instead of writing.

## Acceptance criteria (EARS)

Identity and exposure
- WHEN a request reaches any route in design §2a THE SYSTEM SHALL admit it only if the
  authenticated user is the dedicated control-worker principal
  (`service:glovo-control-worker`).
- IF the caller is any other principal THEN THE SYSTEM SHALL refuse with 403
  `not_authorized` before any database read. This covers a human user, an admin, a
  Glovo-audience (facade) token, a bridge-provider token, the #961 Glovo worker, the
  orchestrator-DevLoop principal, an agent, a surface and a CI principal.
- WHILE a request is authenticated as the control-worker principal THE SYSTEM SHALL
  refuse every route outside design §2a with 403, before any handler runs.
- IF an order or command belongs to a tenant outside the worker's configured `tenants`
  bound THEN THE SYSTEM SHALL answer 404 `not_found`.
- WHILE the issuer decision mctl-gitops#2506 is open THE SYSTEM SHALL wire no
  production verifier for the control-worker credential. The credential is test-only.
- THE SYSTEM SHALL expose no HTTP route that enqueues a generic bridge command. The only
  callers of `bridge.Store.Enqueue` for `place_order_fake` SHALL remain in-process.

Readiness and one database (owner decision A)
- IF any of the following holds THEN THE SYSTEM SHALL answer 503 `not_ready` and write
  nothing:
  - the Glovo control gate is closed;
  - `GLOVO_DB_URL` or `WORK_ITEMS_DB_URL` is unset, or `current_user` of the Glovo pool is not the configured `glovo_runtime` role, or its grants differ from #957 §6d.1;
  - the #959, #988 or #989 collaborator is missing;
  - the startup one-database proof failed.
- THE SYSTEM SHALL NOT fall back to `AUDIT_DB_URL`, and SHALL NOT accept equal URL
  strings as proof of one database.
- WHEN the process starts THE SYSTEM SHALL prove one database by writing a nonce through
  the bridge pool and reading it back through the work-items and Glovo pools. It SHALL
  also check `to_regclass` and the expected table privileges from the bridge pool.

Dispatch
- WHEN a valid dispatch arrives THE SYSTEM SHALL do the following in one `pgx.Tx`, in
  the order of design §5, and then commit. Either all of it is persisted or none of it.
  - take the advisory keys (L1, L2 shared), then lock the order (L3) and the receipt
    (L4);
  - check every binding, the live connection and membership;
  - call `bridge.Store.Enqueue` with `Kind=place_order_fake` and an explicit sequence;
  - reserve the receipt through #989 (`ReserveGlovoApprovalTx`, idempotent for the same
    `cmd_`), with the command payload being the order's final approval basket;
  - move the order to `dispatched`.
- IF `fingerprint` in the body differs from the order's final basket fingerprint or the
  `aar_` binding THEN THE SYSTEM SHALL refuse with 409 `basket_changed`.
- IF tenant, owner, `we_`, order, connection, install revision or intent hash differ
  between the receipt binding and the locked order THEN THE SYSTEM SHALL refuse with 409
  `intent_mismatch`.
- IF the `aar_` is not `approved`, or is not a receipt managed by #989, THEN THE SYSTEM
  SHALL refuse with 409 `approval_invalid`. IF it is expired or past its freshness bound
  THEN 409 `approval_expired`. IF it is reserved or consumed for another command THEN
  409 `approval_replayed`.
- IF the order does not exist, belongs to another tenant or owner, or lies outside the
  `tenants` bound THEN THE SYSTEM SHALL answer 404 `not_found`, with no existence
  oracle.
- IF there is no live connection THEN THE SYSTEM SHALL answer 404 `no_connection`. IF
  the connection is revoked or expired THEN 409 `connection_revoked` or
  `connection_expired`. IF the install revision moved THEN 403 `stale_install` (amended (c), mctl-api#957 design §4.1).
- IF the owner principal is no longer a member of the tenant THEN THE SYSTEM SHALL
  refuse with 403 `no_tenant`.
- WHEN a dispatch repeats for an order already dispatched under the same `aar_` and
  fingerprint, or for an order that later became `cancelled`, `unknown` or `closed` and
  still has its `command_id`, THE SYSTEM SHALL return 200 with the same `cmd_`, the
  current `order_state` and `effect_state`, and the header `Idempotent-Replayed: true`. It
  SHALL create no second command. The same SHALL hold after a crash between commit and
  response. (round 4, F2)
- WHEN the bridge starts and `bridge_schema_version` exists but `GLOVO_DB_URL` is unset, or the
  selector probe or version read fails THE SYSTEM SHALL leave the bridge `not_ready` and
  SHALL NOT fall back to `NewStore`. (round 4, F3)
- WHEN two dispatches for the same order race THE SYSTEM SHALL serialize them on the
  order row lock. Exactly one command SHALL exist afterwards, and every success SHALL
  return the same `cmd_`.
- IF a dispatch arrives for an order that is `cancelled`, `unknown` or `closed` THEN THE
  SYSTEM SHALL refuse with 409 `invalid_transition`. IF a dispatch names a different
  `aar_` for an order that is already dispatched THEN THE SYSTEM SHALL refuse with 409
  `approval_replayed`.
- THE SYSTEM SHALL send only the codes of design §2b, each with the #959
  `{"error","error_description"}` body.

Cancel
- WHEN a cancel arrives for an order that is not yet dispatched THE SYSTEM SHALL revoke
  the receipt through #989 (`pending|approved -> refused`) and move the order to
  `cancelled`, in one transaction.
- WHEN a cancel arrives for a dispatched order THE SYSTEM SHALL call
  `bridge.Store.Cancel(ctx, tx, cmd, actor)` in the same transaction. Then:
  - IF the resulting effect is `none` THEN it SHALL mark the reserved receipt `unknown`
    through #989 (never spendable again) and move the order to `cancelled`;
  - IF the effect is `unknown` THEN it SHALL move the order to `unknown`, SHALL NOT set
    `cancelled`, and SHALL leave the already `consumed` receipt untouched.

  The response SHALL carry `effect_state`.
- THE SYSTEM SHALL never return an `aar_` to `approved`.
- WHEN a cancel repeats, or the command is already `completed` or `expired`, THE SYSTEM
  SHALL return 200 with the current state and change nothing.

Read routes
- WHEN the control worker calls `read_command_result` or `read_approval` THE SYSTEM
  SHALL return only ids, enums, timestamps and digests. It SHALL never return a payload
  or a stored result body.

Revocation race and the write fence
- THE SYSTEM SHALL take locks only in the canonical order L1..L6 of #957 design §6b on every
  Glovo write path, including `IssueWritePermit` (through `WriteFence.PreLock`) and the
  #959 revokers.
- WHILE the write fence is installed THE SYSTEM SHALL re-check the following inside the
  `IssueWritePermit` transaction, which is the actual write, through #989's fence:
  connection revocation, install revision, membership, the receipt state `reserved`
  bound to the command, and the fingerprint recomputed from the stored command payload.
  #989 SHALL consume the receipt there.
- WHEN a revocation commits before a dispatch or permit takes its locks THE SYSTEM SHALL
  refuse that dispatch or permit.
- WHEN a dispatch or permit commits before a revocation THE SYSTEM SHALL make the
  revocation wait on the advisory key. The revocation SHALL then cancel every open
  command of the ended connections in its own transaction, so a permitted effect
  becomes `unknown`.
- THE SYSTEM SHALL install the write fence only when all six hold (design §7.3, the
  only list; amended (c)): `glovo.ControlDefault.Open` is true; the owner has lifted hold
  mctl-gitops#2457; the one-database proof passed; #959 `Ready()` returns nil (a
  `RevocationHook` is installed); #959 `MembershipRevocationWired()` is true; #989
  `receipt.Ready(ctx)` returns nil.
- WHEN a `lock_timeout` (SQLSTATE `55P03`) occurs on any lock of the #957 §6b order THE
  SYSTEM SHALL answer 409 `tenant_busy`; any other store I/O error SHALL be 503
  `unavailable`. (amended (c))

Data hygiene
- THE SYSTEM SHALL accept no provider payload, credential, endpoint or token in a
  request body. Bodies name only `approval_ref` and `fingerprint`.
- THE SYSTEM SHALL return and audit only ids, codes and digests: never a payload, nonce,
  lease token or credential. Order events SHALL attribute the control worker as the
  actor.

## Out of scope

- The order index (#988) and the `aar_` receipt machine (#989). This slice consumes
  their interfaces and fails closed without them.
- The connection store and its revocation write path (#959/#960). The exception is the
  contract in design §7.2, which #959 is amended to provide.
- Client-side `/resolve`, preview, prepare and `aar_` creation (#957).
- The control worker (mctl-agents#1044) and the provider (mctl-telegram#1262).
- Enqueuing a compensating `cancel_order_fake` for an order whose effect is `unknown`.
- A production verifier for the worker credential (after mctl-gitops#2506).
- Lifting hold mctlhq/mctl-gitops#2457, opening `glovo.Default`, and real Glovo
  access.

## Open questions

- OPEN-985-1. Resolved in this PR: #989 is amended to provide the methods of design §3
  (`LockGlovoApprovalTx`, idempotent `ReserveGlovoApprovalTx`, `RevokeGlovoApprovalTx`,
  `MarkGlovoApprovalUnknownTx`, `GlovoApprovalStatus`) and the fence. It stays open only
  until #989 is approved at its amended digest.
- OPEN-985-2. Who builds the detector that turns a GitOps membership removal into a #959
  `Revoke` with reason `membership_removed` (likely #960)? The owner must also accept
  the residual window explicitly. The fence stays refusing until both are done.
- OPEN-985-3. Does #1044 already map the #959 codes of design §2b (`no_tenant`,
  `no_connection`, `connection_revoked`, `connection_expired`, `stale_install`,
  `invalid_transition`, `not_found`, `unavailable`)? Does it read replay from
  `Idempotent-Replayed`? If not, #1044 is amended in the same wave.
- OPEN-985-10 (new, round 4; recommendation: probe by `to_regclass`). The startup mode probe
  reads table existence, not the row, through the legacy bridge DSN when `GLOVO_DB_URL` is
  unset, because that role has no `SELECT` on `bridge_schema_version` after the ownership
  move. The owner confirms that this one read-only use of `COMMERCE_DB_URL` by the bridge is
  acceptable (it is also the answer to what an operator sees after unsetting `GLOVO_DB_URL`).
- OPEN-985-4. Who owns `revalidate_scope` and `resolve_connection` from #1044's
  `ControlApiPort`?
- OPEN-985-9 (new, round 3; X-7; recommendation: remove from #1044). mctl-agents#1044
  calls an activity `release_reservation` (design 236-238, tasks 7 and T12, requirement
  109) that no port route provides and that contradicts the receipt machine (`reserved`
  goes only to `consumed` or `unknown`, and no path returns an `aar_` to `approved`). This
  slice adds no route for it and no mctl-api slice depends on it: #985 `cancel` already
  revokes a pending or approved `aar_` and marks a reserved one `unknown`. Recommendation:
  amend #1044 to drop `release_reservation` (activity, T12 and the requirement line) in
  the same wave as OPEN-985-3. If the owner prefers to keep it, its semantics must equal
  `cancel` and it is added to the §2a route table. #1044 is not edited here.
- OPEN-985-5. Who owns the transition from a completed command result to order `closed`
  (or `unknown` after a timeout)?
- OPEN-985-6. How the migration role and the one Glovo runtime role of mctl-api#957
  design §6d.1 are provisioned (CNPG managed roles in mctl-gitops). Until they exist
  with exactly those grants, the §4 proof fails (it checks every grant) and the routes
  stay `not_ready`. (amended (c): no `SECURITY DEFINER` grantee any more)
- OPEN-985-7. The live pod env of mctl-api was not observed. The startup proof covers it
  either way.
- OPEN-985-8. The command payload of a Glovo `place_order_fake` is exactly the order's
  final approval-basket bytes, with no wrapper (fixed by mctl-api#957 design §6d.3,
  amended (c)), so #989's fence recomputes the fingerprint from what is written.
  v1alpha1 fixes the payload to `{item_codes, quantity_total, note}` without prices, and
  #1059 covers reads only. Still open: whether #1059 or a separate contract issue adds
  this write schema and version (= mctl-agents OPEN-1059-1). Until then dispatch is
  `not_ready`.
