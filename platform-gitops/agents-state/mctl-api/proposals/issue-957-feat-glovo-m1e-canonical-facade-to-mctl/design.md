# Design: issue-957-feat-glovo-m1e-canonical-facade-to-mctl

## Current state

What exists in the clone (`mctlhq/mctl-api`):

- `internal/api/router.go` `NewRouter`: public groups are the OAuth endpoints, the
  assistant catalog `/api/v1/assistant-catalog` (mctl-api#876) and webhooks. The
  authenticated group applies gates in this order: `supportAudienceGate`, surface
  aggregate limit, `requestTimeout`, `surfacePrincipalGate`, `agentScopeGate`,
  `agentPrincipalGate`, `usageWriterGate`, `evidenceWriterGate`, `securityProviderGate`,
  `registryPublisherGate`, `supportIncidentProducerGate`, `ciPrincipalGate`, the global
  300/min limiter (loopback skipped) and `tenantAuthzShadow`. The `/api/v1` routes
  follow. Nothing is Glovo-specific, and no `/assistants/` route exists.
- `internal/api/support_audience_gate.go`: an allowlist of (method, regexp). A
  support-audience token is refused with 401 `invalid_token` everywhere else, `/mcp`
  included, so routes added later are closed to it by default. This is the pattern the
  join gate follows.
- `internal/auth/oauth_support_token.go`, `internal/auth/oauth_resource.go`
  `ResolveResource`, `internal/auth/oidc.go` (`User.IsSupportAudience`, the
  `tokenAudience`/`supportAudience` flags): audience-scoped access tokens minted by
  mctl-api's own OAuth server. `cmd/api/main.go` reads `OAUTH_ACCESS_TOKEN_AUDIENCE` and
  `OAUTH_SUPPORT_RESOURCE`.
- `internal/workitems/action_approvals.go`: `ActionApprovalIDPrefix = "aar_"`,
  `CreateActionApproval`, `DecideActionApproval`, `ConsumeActionApproval`,
  `ReserveActionApproval`, `SettleActionApproval`, `IntentHash`.
  `internal/workitems/types.go`: `ExecutionIDPrefix = "we_"`. Routes
  `/action-approvals*` are at router.go lines 789-792 and 922-923.
- `internal/api/handlers_action_approvals.go:411`: the `Idempotency-Key` header must
  equal the body `idempotency_key`, otherwise 400. The join API reuses this rule.
- `internal/api/handlers_surface_identity.go` `surfaceRoutes`: the surface allowlist.
  Join routes must not be added there, because surfaces must not reach them.
- `internal/humaninput/contract.go` and `testdata/*.json`: the existing pattern for a
  cross-repo contract mirrored from another repo (`orchestrator/human_input.py`), with
  golden fixtures. `hir_` is clarification only.
- `internal/openapi/openapi.yaml` (embedded, served at `/openapi.yaml`).
- Store tests use `TEST_DATABASE_URL` (57 call sites). `e2e/e2e_test.go` exists.
  `.github/workflows/validate.yml` runs CI.
- `grep -ri glovo` over `*.go`: no matches. M1a and M1b are not implemented yet.

Sibling proposals read (mctl-gitops `agents-state`, all `status: proposed`):

- `mctl-api/proposals/issue-953-...`: Glovo audience `GLOVO_MCP_RESOURCE`,
  `User.IsGlovoAudience()`, `glovo_audience_gate.go` confining a Glovo token to
  `/api/v1/glovo/facade/*`, `internal/glovo` `Resolver.Resolve(ctx, user)`, connections
  `gcn_`, the worker token `MCTL_GLOVO_WORKER_TOKEN`. It adds no tenant selector (its own
  open question).
- `mctl-api/proposals/issue-954-...`: `provider_orders` (`pord_`), routes
  `/api/v1/provider-orders*` behind `PROVIDER_ORDERS_ENABLED`, the `aar_` created and
  consumed by the worker principal, Target
  `provider:fake/connection:<cid>/install:<iid>@<rev>/order:<pord_>`.
- `mctl-telegram/proposals/issue-1235-...`: the wire protocol `glovo-facade-mctl-api/v1alpha1`
  under `/api/v1/assistants/glovo/v1alpha1/` with headers `Authorization` (facade
  workload credential), `X-Mctl-Subject-Token`, `X-Mctl-Selected-Tenant`; routes
  `/resolve`, `/connection`, `/connections`, `/orders:list`, `/previews`, `/basket`,
  `/orders:prepare`, `/orders/{order_id}`; plus a `gsc_` scope_ref.
- `mctl-telegram/proposals/issue-1227-...`: the seven-tool table (inputs and outputs) and
  the scopes `glovo:read` and `glovo:basket:prepare`.

The mismatch: #1235 expects a facade-credential route family. #953 serves a user-token
route family at a different prefix. #954 serves owner and worker routes that the facade
must not call (confused deputy). No component owns the mapping between them.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/` (admins, karabu, labs, namax66): no `mctl-api` service
  directory and no Glovo service. mctl-api's deployed values are not in this checkout,
  so its current env (for example whether `OAUTH_SUPPORT_RESOURCE` is set) was not
  observed.
- `services/labs/mctl-telegram/values.yaml`: `PUBLIC_BASE_URL` and `OAUTH_ISSUER_URL`
  are `https://tg.mctl.ai`. The join routes therefore must not live on that host's path
  space.
- `grep -ril glovo services/ tenants/`: no matches. Nothing Glovo is deployed.
- mctl MCP tools: not called. The gitops checkout was enough for the above, and
  mctl-api's own deployed config remains unobserved (see Open questions in
  requirements.md).

## Proposed solution

### AMEND 2026-11-08 — M0 closed refusal + DB/approval atomicity proof

`ambiguous_tenant` cannot become a public v1alpha1 refusal without deliberately changing the already-merged closed M0 contract and both source repositories. To align with the approved #953 proposal AMEND, missing or unbound selected-team OAuth grant = `ambiguous_tenant` (including one eligible team); mismatched `X-Mctl-Selected-Tenant` remains a transport refusal mapped to the supported public error. Audit the shared Go/JSON schemas, golden fixtures and facade error mapping as part of the integration contract.

The `Prepare` sequence is not atomically satisfied merely by invoking existing `workitems.CreateActionApproval` and `ExecutionByID` while holding a separate `glovojoin` transaction. Design a concrete shared DB pool and `pgx.Tx`-aware WorkItem/execution/`aar_` APIs **or** an idempotent compensating state machine with separately validated transitions; prove failure injection on each boundary, no orphan approved receipt, no duplicate pord_/we_/aar_, and zero fake-provider writes. Any fallback to partial commit must explicitly remain `not_ready`/blocked until reconciled. The legacy #954 source uses `ReserveActionApprovalTx` only for reserve, not pending creation; don't assume a `Prepare` helper exists or can span databases.



### 1. Decision: one canonical route family, owned by mctl-api

Keep the prefix #1235 froze, `/api/v1/assistants/glovo/v1alpha1/`. It is versioned, does
not collide with `/mcp`, `/api/v1/glovo/*` or `/api/v1/provider-orders/*`, and it is what
the facade already targets. Under it mctl-api serves thin join handlers that call the M1a
and M1b packages in process (`internal/glovo`, `internal/providerorders`). The facade
never calls `/api/v1/glovo/facade/*` or `/api/v1/provider-orders/*`. Those stay
human/owner and worker routes. The M1a Glovo-audience gate keeps confining a bare Glovo
token to `/api/v1/glovo/facade/*`, which this join API does not need. Whether M1a still
needs those routes for a non-facade client is M1a's call.

### 2. Identity flow (canonical, amends #1235)

```
MCP client --Glovo-aud token--> facade (verifies via JWKS, as in #1235)
facade --Authorization: Bearer <MCTL_GLOVO_FACADE_TOKEN>
       --X-Mctl-Subject-Token: <same user access token>
       --[X-Mctl-Selected-Tenant: <echo of mctl_tenant claim>]
       --traceparent, X-Request-Id
     --> mctl-api /api/v1/assistants/glovo/v1alpha1/...
         glovoJoinGate -> verify subject -> tenant claim -> M1a Resolve -> handler
```

- **Facade workload identity.** A new machine principal `NewGlovoFacadeUser()` in
  `internal/auth/oidc.go`, recognised by a constant-time compare with
  `MCTL_GLOVO_FACADE_TOKEN`. It follows the evidence-writer pattern and is refused at
  startup if the value equals any other machine token (service, evidence, usage, M1a
  worker). It carries no groups and no tenant.
- **`internal/api/glovo_join_gate.go` `glovoJoinGate`**, mounted directly after
  `supportAudienceGate`. Two rules: (a) a facade principal reaches only
  `^/api/v1/assistants/glovo/v1alpha1/` and gets 401 everywhere else, `/mcp` included;
  (b) a non-facade principal on that prefix gets 401 `not_facade_identity`. Because it
  runs before `surfacePrincipalGate` and `agentPrincipalGate`, no relay or delegation
  header can turn another principal into the facade. Join routes are not added to
  `surfaceRoutes`, `supportAudienceRoutes` or any agent scope.
- **Subject re-verification.** `glovojoin.SubjectVerifier` calls the same local-OAuth
  verification path as `AuthMiddleware` (`internal/auth/provider_localoauth.go`) on
  `X-Mctl-Subject-Token`. It checks: signature, `iss == BaseURL`, `aud` containing
  `GLOVO_MCP_RESOURCE` and no API or support audience (precedence as M1a defines it,
  fail closed), `exp`, revocation by `jti` or token family, and a principal-backed
  `sub`. The raw header is deleted from the request after verification. Only
  `sha256(token)` reaches the audit record and the span. The subject token is never
  accepted in a query string or body.
- **Server-bound selected tenant.** M1e extends `/oauth/consent`: when the resource is
  `GLOVO_MCP_RESOURCE`, the consent page lists the M1a-eligible tenants (membership ∩
  pilot allowlist ∩ current install), with nothing preselected. The human must pick one.
  The choice is stored on the authorization code and the refresh-token family and minted
  as the claim `mctl_tenant`. On every join call the tenant is that verified claim. The
  `X-Mctl-Selected-Tenant` header is optional, compared and never read as input. Then
  `glovo.Resolver.Resolve(ctx, subject)` runs and the claim tenant must be among its
  eligible set, otherwise the M1a refusal code is returned. There is no default tenant,
  no sole-membership fallback and no `labs`.
- **No `scope_ref`.** Every call re-verifies, so a `gsc_` bearer handle would add state
  without adding any guarantee. v1alpha1 drops it and #1235 must remove
  `X-Mctl-Scope-Ref`.

Why forward the user token instead of having the facade assert the subject: a stolen
facade credential alone cannot act for any user, and a stolen user token cannot reach the
join routes without the facade credential (TM3 in #1235).

### 3. Route matrix (frozen, v1alpha1)

All paths are relative to `/api/v1/assistants/glovo/v1alpha1`. No query strings are used.
Scopes are checked against the subject token.

| MCP tool | Verb + path | Request body | 200 body (= tool output) | Scope | Backing call | Source owner |
|---|---|---|---|---|---|---|
| (preflight) | `POST /resolve` | `{}` | `{tenant, principal_ref, contract_version}` | any Glovo scope | `glovo.Resolver.Resolve` | M1a #953 |
| `glovo_auth_status` | `GET /connection` | none | `{connection_state, connection_id?, provider_account_label?, expires_at?}` | `glovo:read` | `glovo.Connections.Current(tenant, principal)` | M1a #953 |
| `glovo_connect_account` | `POST /connections` | `{idempotency_key}` | `{connection_id, state:"pending_handoff", handoff_url, expires_at}` | `glovo:basket:prepare` | `glovo.Connections.Create` (synthetic handoff URL) | M1a #953 |
| `glovo_get_order_history` | `POST /orders:list` | `{limit<=20, cursor?}` | `{orders:[...], next_cursor?}` | `glovo:read` | `ReadBridge.History` | M1e (protocol), #1043 (transport), #1236 (fake data) |
| `glovo_preview_reorder` | `POST /previews` | `{order_ref}` | `{preview_id, items, unavailable_items, fingerprint, expires_at}` | `glovo:read` | `ReadBridge.Preview` plus a `glovo_join_previews` row | M1e |
| `glovo_get_basket` | `GET /basket` | none | `{store_name?, items, totals_label, fingerprint}` | `glovo:read` | `ReadBridge.Basket` | M1e / #1043 / #1236 |
| `glovo_prepare_order` | `POST /orders:prepare` | `{preview_id, idempotency_key}` | `{order_id, fingerprint, consent_request_id, expires_at}` | `glovo:basket:prepare` | `providerorders.Service.Prepare` -> `pord_` + `we_` + pending `aar_`, zero provider writes | M1b #954 |
| `glovo_order_status` | `GET /orders/{order_id}` | none | `{state, outcome, handoff_url?}` | `glovo:read` | `providerorders.Service.OwnerStatus` | M1b #954 |
| (launch) | `GET /compatibility` | none | `{contract_version, contract_digest, api_version, dependencies:{connection_registry, provider_orders, read_bridge, control_worker, provider_worker}, deploy_ready}` | facade identity, no subject needed | `glovojoin.Readiness` | M1e |

`consent_request_id` is the `aar_` id. The human decides it only through the existing
owner decision route (`POST /api/v1/action-approvals/{id}/decision`), which the facade
cannot reach. No join route decides, consumes, reserves or settles an `aar_`, and none
accepts an `hir_`.

### 4. Refusal and status mapping (closed enum, in the contract)

| HTTP | `error` codes |
|---|---|
| 400 | `invalid_request` (schema, unknown field, duplicate key, header/body key mismatch) |
| 401 | `not_facade_identity`, `subject_token_invalid` (+ `WWW-Authenticate`) |
| 403 | `insufficient_scope`, `ambiguous_tenant`, `tenant_mismatch`, and the M1a codes passed through unchanged: `no_tenant`, `ambiguous_tenant`, `not_in_pilot`, `scope_unsupported`, `not_authorized`, `no_install`, `stale_install`, `connection_revoked` |
| 404 | `connection_not_found`, `preview_not_found`, `order_not_found` (owner and tenant mismatch included) |
| 409 | `idempotency_key_reused`, `preview_expired`, `fingerprint_changed`, `connection_not_active` |
| 429 | `rate_limited` |
| 503 | `not_ready` (+ `dependency`), `dependency_unavailable` (a store or bridge read failed; never mapped to empty) |

The error body is `{"error": code, "dependency"?: name, "request_id": id}`, with no
free-text detail that could echo input.

### 5. Read bridge protocol

`internal/glovojoin/bridge.go`:

```go
type ReadBridge interface {
    Read(ctx context.Context, req GlovoReadRequest) (GlovoReadResult, error)
}
// GlovoReadRequest{APIVersion "glovo-read/v1alpha1", RequestID "grr_...", Kind history|preview|basket,
//   Tenant, PrincipalRef (opaque hash, not principal id), ConnectionID, InstallID, InstallRevision,
//   Args (bounded), Deadline, TraceParent}
// GlovoReadResult{RequestID, Kind, ConnectionID, InstallRevision, Payload (schema per kind), Synthetic: true}
```

- The join handler validates that the result echoes `RequestID`, `ConnectionID` and
  `InstallRevision`, that `Synthetic` is `true`, and that `Payload` matches the kind's
  schema. Anything else becomes `dependency_unavailable`.
- Implementations: `NotReadyBridge` (the default: every call gets `not_ready`,
  `dependency: read_bridge`); `FixtureBridge` (tests and harness only, built under the
  `glovojoin_fixture` tag so it cannot ship in the release image); and later
  `TransportBridge` once mctl-agents#1043 picks the transport. That transport carries
  messages to the control workflow (#1044), which talks to the fake provider worker
  (#1236). mctl-api assumes no cross-namespace Temporal Activity.
- Previews are persisted in mctl-api so that prepare binds to what the user saw. The
  table is `glovo_join_previews(id 'gpv_'+128-bit, tenant, principal_id, connection_id,
  install_id, install_revision, fingerprint, payload_hash, created_at, expires_at <=
  15m)`, with inline DDL in the commerce-store pattern.

### 6. Prepare path (zero writes)

`POST /orders:prepare` runs as follows. Load the `gpv_` row by (id, tenant, principal),
otherwise 404. Check it is unexpired, otherwise 409. Re-check that the connection is
active and the install revision is current through M1a. Then call
`providerorders.Service.Prepare(ctx, PrepareInput{Tenant, Owner, ConnectionID, Install,
Fingerprint, Items, IdempotencyKey})`. In one transaction that call must create the
`pord_`, a `we_` owned by the principal, and a pending `aar_` (`CreateActionApproval`,
whose `IntentHash` covers the full Target string from #954 plus the fingerprint). No
provider effect row and no dispatch is created. Idempotency is
`UNIQUE(requested_by, idempotency_key)` in M1b, and a replay with a different
fingerprint gets 409 `idempotency_key_reused`. If M1b does not expose a verified transactional or compensating `Prepare`, `Readiness` reports `provider_orders: not_ready` and the route returns 503. A nominal `Prepare` method without tested cross-store atomicity and crash recovery does not satisfy readiness.

### 7. Contract package (shared with mctl-telegram)

- `internal/glovojoin/contract/glovo-facade-mctl-api.v1alpha1.json`: the version, the
  route matrix, the request and response JSON Schemas (draft 2020-12,
  `additionalProperties: false`), the refusal table, the idempotency rules, the rate
  limits, the timeouts (5 s), the OAuth resource metadata expectations (`resource`,
  `scopes_supported`, `bearer_methods_supported: ["header"]`) and `dependencies` version
  gates (minimum M1a and M1b schema versions, bridge `glovo-read/v1alpha1`).
- `contract.go` (`//go:embed`) and `contract_test.go`, which pins `Digest` (sha256 of
  the file). Changing the file without bumping the digest fails the test, and so does
  bumping the digest without bumping the version.
- `testdata/v1alpha1/<route>/<case>.json`: golden {request headers (token placeholders),
  body, expected status, expected body} cases. `testdata/glovo-mcp-tools.json` is a
  pinned copy of the M0 tool schema with its digest. A test asserts that every 200
  response schema equals the matching tool `output_schema`.
- Cross-repo: mctl-telegram vendors the same contract file and fixtures and asserts the
  same digest in `internal/glovo/mctlapi/wire_test.go`. Each repo's CI fails on a digest
  mismatch with the other side's pinned value. The pin is updated by PR in both repos;
  a drift in either fails.

### 8. Harness against real handlers

`internal/glovojoin/harness_test.go` (requires `TEST_DATABASE_URL`, build tag
`glovojoin_fixture`) builds the real `api.NewRouter` with the real `workitems.Store`, the
M1a `glovo` store, the M1b `providerorders` store, a test OAuth server that mints real
local-OAuth Glovo tokens, and `FixtureBridge`. It then replays every golden fixture and
the negative matrix (tasks.md T6). An exported `cmd/glovo-join-harness` (fixture tag)
serves the same stack on a local port so the mctl-telegram facade's integration test can
target real mctl-api handlers instead of `fakeapi`.

### 9. Readiness and launch matrix

`glovojoin.Readiness` probes each dependency: the M1a store is configured and has its
schema version, the M1b store and `Prepare` are present, the bridge is not
`NotReadyBridge`, and the control and provider worker heartbeats are seen through the
bridge. `docs/glovo-join.md` holds the launch compatibility matrix (facade image ×
mctl-api release × control worker × provider worker × gitops revision × contract
digest). `deploy_ready` stays false in this proposal's scope.

### 10. Rate limits and tracing

Join routes get their own `httprate` group: per subject principal 60/min, writes
10/min, and a facade aggregate of 600/min (keyed `glovo-facade-total`). The global
300/min limiter keys on the facade identity, so it is skipped for this prefix in favour
of the per-subject limiter, the same reasoning `agentAggregateLimit` uses. `traceparent`
is honoured by the existing telemetry middleware. Span attributes are route, refusal
code, tenant and request_id.

## Alternatives

1. **Facade calls the M1a `/api/v1/glovo/facade/*` and M1b `/api/v1/provider-orders/*`
   routes directly.** Rejected. M1b's routes are owner and worker routes, so letting the
   facade hold that privilege is a confused deputy, and history/basket have no owner
   there at all.
2. **Overload M1a's connection registry with history, preview and order adapters.**
   Rejected by the issue as unapproved scope expansion of #953. It would also tie M1a's
   review to M1b.
3. **Trust `X-Mctl-Selected-Tenant` (or have the facade assert the subject) with only the
   workload credential.** Rejected. It makes the tenant caller-controlled and makes a
   facade compromise a full user compromise. The issue forbids a raw JWT or header
   becoming a trusted tenant string.
4. **RFC 8693 token exchange (facade swaps the user token for a mctl-api join token).**
   Deferred, not rejected. It is cleaner but needs a token-exchange grant mctl-api does
   not have yet. The `SubjectVerifier` interface leaves room for it in v1alpha2.

## Platform impact

- **Migrations:** one inline-DDL table `glovo_join_previews` (created only when
  `GLOVO_JOIN_ENABLED=true`) and one column on the OAuth authorization-code and
  refresh-family store for the selected tenant (nullable, ignored for non-Glovo
  resources). Both are additive.
- **Backward compatibility:** everything is behind `GLOVO_JOIN_ENABLED` (default off), so
  the routes are 404 when off. Consent for non-Glovo resources is unchanged. No existing
  gate's behaviour changes for existing principals. `glovoJoinGate` only refuses on the
  new prefix or for the new principal.
- **MCP tool count:** unchanged. No tool is added to `internal/mcp/server.go`, so the
  `server_test.go` expectation stays the same.
- **Resources:** negligible. One extra JWT verification per join call and one Postgres
  table.
- **Risks and mitigations:**
  - Gate ordering bug lets another principal reach join routes. Mitigation: router test
    over every principal kind × every join route, plus a facade × non-join routes test.
  - Token leak through logs. Mitigation: the header is stripped after verification, only
    the hash is recorded, and a log-capture test greps for the token.
  - Cross-repo drift. Mitigation: a digest pinned on both sides plus golden fixtures.
  - Premature launch claim. Mitigation: `deploy_ready` is false until all dependencies
    are ready, and the docs require M1a and M1b to be merged first.
  - M1b API shape differs from the assumed `Prepare` and `OwnerStatus`. Mitigation: the
    join layer depends on a narrow interface `glovojoin.Orders`, and a mismatch shows up
    as `not_ready` rather than a broken route.
