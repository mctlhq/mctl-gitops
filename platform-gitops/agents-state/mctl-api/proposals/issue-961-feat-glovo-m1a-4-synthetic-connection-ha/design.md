# Design: issue-961-feat-glovo-m1a-4-synthetic-connection-ha

## Current state

- No Glovo code exists in this clone: `grep -ril glovo --include=*.go .` returns no hits at
  HEAD `5f60792`. Slices 1-3 (#958 audience and gates, #959 store, #960 selected-team grant and
  resolver) are open issues and are not merged. Their intended shapes come from the reviewed
  #953 design (`agents-state/mctl-api/proposals/issue-953-.../design.md`):
  - `OAuthServer.GlovoResource` (`GLOVO_MCP_RESOURCE`) and `User.IsGlovoAudience()`;
  - `glovoAudienceGate`, which confines a Glovo token to `/api/v1/glovo/facade/*`;
  - `MCTL_GLOVO_WORKER_TOKEN` and `glovoWorkerGate`;
  - `internal/glovo` with `Resolver.Resolve(ctx, user) (Scope, *Refusal)`, the
    `glovo_installations`, `glovo_connections`, `glovo_connection_requests`,
    `glovo_pilot_allowlist` and `glovo_audit_events` tables, and the `gcn_`/`gin_` ids;
  - a `synthetic` provider, refusing secret store, and DB-backed rate limit counters.
- Router: `internal/api/router.go` `NewRouter`. The authenticated group (around line 527) chains
  `supportAudienceGate`, the surface and agent gates, then one confinement gate per machine
  principal: `usageWriterGate`, `evidenceWriterGate`, `securityProviderGate`,
  `registryPublisherGate`, `supportIncidentProducerGate` and `ciPrincipalGate`. After that come
  the 300/min limiter, `tenantAuthzShadow`, and `r.Route("/api/v1", ...)` at about line 606.
- Machine-principal confinement pattern: `internal/api/handlers_evidence.go` `evidenceWriterGate`
  answers 403 for every route except its allowlist, keyed on `user.IsEvidenceWriter()`. The
  identity comes from `internal/auth/oidc.go` (`evidenceWriter` unexported flag,
  `NewEvidenceWriterUser`, `evidenceWriterToken()`).
- Tenancy: `User.HasTenantAccess` (`internal/auth/oidc.go:258`) admits admins and agent scopes,
  so it must not be used for Glovo ownership. `internal/api/tenant_role.go`
  `requireTenantRole` and `checkTenantRoleByPrincipal` give principal-mode roles. Deployed mode
  is `principal`.
- Real-DB handler tests: `internal/api/handlers_commerce_test.go` builds a fixture on
  `TEST_DATABASE_URL` (it skips when that is unset, line 80) and calls handlers with
  `httptest`. The tests compare foreign, cross-tenant and missing ids for an identical 404 (about
  lines 444-483). CI `.github/workflows/validate.yml:54-55` provides a Postgres service and sets
  `TEST_DB_URL`/`TEST_DATABASE_URL`, so DB tests do run in CI.
- Route compatibility: the #957 proposal freezes the facade join prefix
  `/api/v1/assistants/glovo/v1alpha1/` with a separate `MCTL_GLOVO_FACADE_TOKEN` workload
  identity. It states that `/api/v1/glovo/facade/*` stays a human route family and that the
  facade never calls it. Missing selection maps to `ambiguous_tenant`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml`: `replicaCount: 2`,
  `TENANT_AUTHZ_MODE: "principal"`. No `glovo` string in it.
- `grep -rli glovo $MCTL_GITOPS_ROOT/services $MCTL_GITOPS_ROOT/tenants`: no hits. No Glovo
  service or tenant is deployed. Tenants: admins, commerce-proof, erpact, karabu, labs, mctl,
  namax66.
- `gh issue view 958/959/960 -R mctlhq/mctl-api`: all OPEN. Their scopes are summarised above.
- mctl MCP read tools were not called. The gitops checkout and the issues were enough for this
  code-only, default-off change.

## Proposed solution

This slice is integration only. It adds handlers, gates wiring, schemas and tests, and it
consumes the slice 1-3 primitives without redefining them.

### 0. Precondition

Implementation starts only after #958, #959 and #960 have merged. The first task reconciles
the names assumed here (`glovo.Resolver`, `glovo.Store`, refusal enum, gates) with the merged
code. If a primitive is missing, the implementer stops and reports it. It does not add the
primitive inside this slice.

### 1. Feature gate and versioned wire types (`internal/glovo/wire`)

- `GLOVO_ENABLED` (default `false`) is read in `cmd/api/main.go`. `Handlers.glovoReady()`
  returns true only if the switch is on and the Glovo store, the `GlovoResource` audience and
  the worker token are all configured. A `glovoFeatureGate` middleware mounted on
  `r.Route("/glovo", ...)` answers 503 `not_ready` otherwise, before decoding.
- Wire structs carry a mandatory `schema` constant, for example
  `glovo-connection/v1alpha1.Connection`, `...ConnectRequest`, `...WorkerCheckRequest`,
  `...WorkerCheckResponse`, `...Installation`, `...Refusal`.
- Decoding uses `http.MaxBytesReader(16 KiB)` and `json.Decoder.DisallowUnknownFields`, then
  checks for an exact `schema` match. Any failure is 400 `invalid_request`.
- JSON Schemas are committed in `internal/glovo/wire/schema/*.json`, and a golden test checks
  that the Go marshal output validates against them. #957 and mctl-telegram#1235 can vendor the
  same files.
- Public connection states are `pending | active | expired | revoked`. If the slice 2 store has
  internal sub-states, a single `wire.PublicState(store.State)` maps them. The table test covers
  every store state.
- Refusal to HTTP status mapping is one function `refusalStatus(code)`:
  - `not_authorized` 403, or 401 when no token;
  - `not_found` 404;
  - `ambiguous_tenant`, `scope_unsupported`, `not_in_pilot`, `no_installation` 403;
  - `stale_install`, `connection_revoked`, `connection_expired`, `invalid_transition`,
    `idempotency_key_reused` 409;
  - `rate_limited` 429;
  - `invalid_request` 400;
  - `not_ready` 503.

  Store or role-read failure is 503 `unavailable`, and never a refusal that could read as "no".

### 2. Facade handlers (`internal/api/handlers_glovo_facade.go`)

These are reachable only with a Glovo-audience token, through slice 1's `glovoAudienceGate`.
Every handler first calls `glovo.Resolver.Resolve(ctx, user)`, which is slice 3's grant-bound
resolver. Tenant, principal and install revision come only from the returned `Scope` and the
store.

| Route | Effect |
|---|---|
| `GET /api/v1/glovo/facade/context` | `{schema, tenant, principal_id, installation_id, install_revision, connections:[...]}` for the caller only |
| `POST /api/v1/glovo/facade/connections` (`Idempotency-Key`) | 201 `pending`, or 200 replay with `replayed:true` |
| `GET /api/v1/glovo/facade/connections/{id}` | owner-scoped read; foreign or missing ids get the same 404 |
| `POST /api/v1/glovo/facade/connections/{id}/handoff` | issues the synthetic handoff reference `ghr_` + 32 random bytes, stores only the SHA-256, TTL 10 min, single use |
| `POST /api/v1/glovo/facade/connections/{id}/revoke` | `-> revoked`, idempotent |
| `POST /api/v1/glovo/facade/connections/{id}/reconnect` (`Idempotency-Key`) | new `gcn_` `pending`, `replaces_id` set; only from `expired` or `revoked` |

Every read and write uses `store.Get(ctx, scope.Tenant, scope.PrincipalID, id)`, so the
owner predicate is in the SQL and a foreign id is indistinguishable from a missing one.

### 3. Admin handlers (`internal/api/handlers_glovo_admin.go`)

- `PUT|DELETE /api/v1/glovo/tenants/{tenant}/installation` use the normal API token and
  `requireTenantRole(..., "owner")` in principal mode. Admins are not auto-admitted. These
  routes call slice 2's atomic `Reinstall` and `Remove`, which bump the revision and revoke
  live connections in one transaction under the per-tenant advisory lock.
- `PUT|DELETE /api/v1/glovo/pilot/{tenant}/principals/{principal_id}`: platform admin only,
  using slice 3's allowlist store. The principal must resolve in `internal/principals`.
- `glovoAudienceGate` already refuses Glovo-audience tokens on these routes.

### 4. Worker handlers and scope gate (`internal/api/handlers_glovo_worker.go`)

- `glovoWorkerGate` (slice 1) confines the worker to `^/api/v1/glovo/worker/`. This slice adds
  the inverse check in each worker handler: `user.IsGlovoWorker()` or 403. Admins and service
  tokens are refused, so no other identity can reach worker routes.
- `POST /api/v1/glovo/worker/check` takes `{schema, connection_id, install_revision}` and
  returns `{schema, allowed, tenant, owner_principal_id, state, expires_at}`. The tenant comes
  from the connection row, never from the request. At call time the handler re-reads:
  installation state and revision, connection state and expiry, the owner's live role (through
  the same principal-mode role reader the resolver uses), and the allowlist row.
- `POST /api/v1/glovo/worker/connections/{id}/activate` takes
  `{schema, install_revision, handoff_ref}`. It verifies the reference hash and its TTL and
  repeats the check in the same transaction, then moves to `active` with
  `expires_at = now + 24h` (synthetic).
- `POST /api/v1/glovo/worker/connections/{id}/expire` is synthetic and is used to drive the
  expiry path deterministically in tests.
- The worker has no groups, no admin flag and no agent scope. Because `glovoWorkerGate` runs in
  the authenticated chain before `r.Route("/api/v1")`, the worker gets 403 on
  `/api/v1/agents/dev-loop/*` (approve, abandon, get), on Temporal-backed routes, on `/mcp` and
  on facade routes.

### 5. Limits, idempotency, audit

- Rate and count limits use slice 2's DB counters, checked inside the mutation transaction:
  10 connect or reconnect requests per hour per (tenant, principal), and 50 non-terminal
  connections per tenant.
- Idempotency uses slice 2's `glovo_connection_requests` table. `request_hash` is the SHA-256 of
  the canonical body plus the route.
- Every mutation and every refusal on a mutating route appends to `glovo_audit_events` with
  actor kind (`user|owner|admin|worker`). Logs (`slog`) carry only ids, states and codes.

### 6. End-to-end contract tests (`internal/api/glovo_e2e_test.go`)

- The tests build the actual `NewRouter(...)` with a real `glovo.Store` on `TEST_DATABASE_URL`.
  The schema is applied by the production `NewStore` migration code, in a per-test schema or
  with cleanup, following the commerce fixture.
- Auth uses the real middleware. Glovo-audience access tokens are minted through the real
  `OAuthServer` authorization-code and consent flow with a selected team (slice 3). The worker
  uses its real token through the real token provider. Users are not injected via context.
- Fixtures: tenants `alpha` and `beta`. Users `a1` and `a2` are in `alpha`, both allowlisted;
  `b1` is in `beta`. There is also `u3`, eligible in `alpha` but with no selection. All are
  principal-mode role rows in the real tenant-role reader backend.
- The matrix covers:
  - happy path: connect, handoff, activate, check, revoke;
  - reconnect issues a new id;
  - `a2` gets 404 on `a1`'s connection;
  - `b1` gets 404 on `alpha` ids;
  - stale install after reinstall;
  - revoked and expired connections;
  - role removed mid-session;
  - allowlist removed;
  - no grant, unselected single eligible team, personal scope, forged `tenant` body field;
  - forged `X-Mctl-Selected-Tenant` header;
  - worker on facade, MCP and dev-loop routes;
  - admin on worker routes;
  - idempotent replay and key reuse;
  - rate limit;
  - feature-off 503 on every route.
- Audit and no-leak assertions: each mutation produces the expected audit rows. A captured
  `slog` buffer, all audit rows and all responses (except the one handoff response) are scanned
  with `internal/secretscan` and for the raw token, handoff and `Idempotency-Key` strings.
- A route inventory test walks `chi.Walk` and asserts that every `/api/v1/glovo/` route is
  covered by the feature-off test and by the worker or Glovo gate matrix, so a newly added route
  cannot be left untested.

### 7. Docs

- `docs/glovo-connections.md`: state diagram, route table, schemas, refusal table, the test
  matrix, an anti-regression list, and an explicit "default OFF, integration NOT READY until
  #957 and mctl-telegram#1235" section.
- OpenAPI entries in `internal/openapi`.
- No MCP tools are added.

## Alternatives

- Serve only the #957 join prefix and drop `/api/v1/glovo/facade/*`. This removes one route
  family, but #957 is not approved or merged, and the facade join needs a facade workload
  identity that does not exist yet. Testing the user lifecycle would then depend on #957.
  Rejected for now; listed under Open questions.
- Test with handler-level `httptest` calls and context-injected users, as most of
  `handlers_*_test.go` does. That is cheaper, but it skips the gates and the token verification
  the issue requires ("actual mctl-api handlers, not self-made mocks"). Rejected.
- Let the worker read through a generic admin-like scope. That is simpler, but it would expose
  the facade and the DevLoop routes. Rejected in favour of the dedicated gate and the per-call
  scope re-derivation.

## Platform impact

- Migrations: none new. The tables come from slice 2, and this slice adds at most an index if
  the reconcile in task 0 finds one missing. Any such change must be additive and idempotent.
- Backward compatibility: with `GLOVO_ENABLED` unset (the deployed state), every Glovo route
  answers 503 `not_ready`, and token issuance and verification are unchanged. Regression tests
  cover support, DevLoop, MCP and Telegram routes.
- Resources: a few indexed queries per call. Two replicas are safe because limits, idempotency
  and handoff consumption are in Postgres under the per-tenant advisory lock.
- Risks and mitigations:
  - Drift from the slice 1-3 contracts: task 0 reconciles first, and no primitive is duplicated.
  - An existence oracle: one 404 path and body for foreign and missing ids, tested.
  - Worker overreach: gate plus handler check, and a negative route matrix including dev-loop.
  - Leaks: secretscan over logs, audit rows and responses, and handoff references stored hashed.
  - Accidental enablement: a separate gitops change is required, which is out of scope.
  - Incompatibility with #957 and #1235: shared JSON Schemas and the same refusal enum. The
    readiness document says NOT READY.
