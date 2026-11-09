# Design: issue-961-feat-glovo-m1a-4-synthetic-connection-ha

## Amendment 2026-11-09 — joint 959/960/961 AMEND

Independent review of digest `sha256:75e615f99f39894730fcd530251fa05a6e423fed77a2ad723dfa50d068bfa4e0` (mctl-api#961, comment of 2026-11-09) required one joint amendment across #959, #960 and #961. Finding -> change in this slice:

| Finding | Change |
|---|---|
| P2 worker gate assumed from #977, which has only the reserved `IsGlovoWorker()` stub; task 0 always STOPs | Building the worker identity and `glovoWorkerGate` is task 5a of this slice; task 0 no longer requires them; design section 4 rewritten |
| P2 names diverge from #959 | All names follow the joint contract (`glovo_installs`, `glovo_connect_requests`, `no_install`, `supersedes_id`, `GetConnection`, `RevokeInstall`, store states with `PublicState`) |
| P2 "fixed synthetic expiry" has no column | `glovo_connections.expires_at` is added by #959 (joint contract) |
| P2 membership loss `not_authorized` here, `no_tenant` in #960 | `no_tenant` everywhere |
| P2 error body `{schema, refusal:{code,message}}` conflicts with #977's `WriteError` | Refusals use `glovo.WriteError`; the `Refusal` wire struct is removed |
| P3 allowlist PUT/DELETE defined in both #960 and here | Removed here; #960 owns them |
| P3 Rollback says "no new tables" | Rollback lists `glovo_handoff_refs` and `glovo_rate_counters` |
| P3 `glovoAudienceRoutes` is empty and no task adds the facade routes | Task 3 adds `/api/v1/glovo/facade/*` to `glovoAudienceRoutes` |
| P3 audit actor kind has no column in #959 | `glovo_audit_events.actor_kind` added by #959 |
| P3 no named test for the 50-per-tenant limit | T7 extended |
| Alignment with the merged #968 bridge | Worker identity is distinct from the bridge provider; mutual refusal tested (T8) |

### Joint contract frozen for #959, #960 and #961 (identical text in all three)

Verified against mctl-api main `a9ca5814` (#977 merged) and the merged #968 bridge (`docs/bridge.md`). Where an earlier section of this document disagrees, this contract wins.

| Item | Frozen value | Owner slice |
|---|---|---|
| Go package | extend the existing `internal/glovo` from #977 (`glovo.Code`, `glovo.Error`, `glovo.Gate`, `glovo.WriteError`); no parallel `RefusalCode`/`Refusal` type | #959 adds the codes |
| Tables | `glovo_installs`, `glovo_connections`, `glovo_connect_requests`, `glovo_audit_events`, `glovo_pilot_allowlist` | #959 (DDL) |
| | `glovo_handoff_refs`, `glovo_rate_counters` | #961 (DDL) |
| | `oauth_team_grants`, `oauth_refresh_tokens.team_grant_id` (refresh-store database) | #960 |
| Columns | reconnect link `supersedes_id`; `glovo_connections.expires_at TIMESTAMPTZ NULL`; `glovo_audit_events.actor_kind` (`user`, `owner`, `admin`, `worker`, `system`) | #959 |
| Store API | `Install`, `GetInstall`, `RevokeInstall`, `Reinstall`, `Connect`, `Reconnect`, `Transition`, `Revoke`, `GetConnection`, `LiveConnection`, `ListAudit`, `IsAllowlisted` | #959 |
| Store states | `pending_handoff`, `pending_provider`, `active`, `expired`, `failed`, `revoked`; wire `PublicState`: both `pending_*` -> `pending`, the rest unchanged | #959 states, #961 mapping |
| Refusal enum (closed, `glovo.Code`) | `not_ready`, `unavailable`, `not_authorized`, `invalid_request`, `not_found`, `no_install`, `ambiguous_tenant`, `no_tenant`, `scope_unsupported`, `not_in_pilot`, `stale_install`, `stale_version`, `no_connection`, `connection_exists`, `connection_revoked`, `connection_expired`, `invalid_transition`, `idempotency_key_reused`, `rate_limited` | #959 |
| HTTP status | 503: `not_ready`, `unavailable`; 401/403: `not_authorized` (401 only when no valid token); 400: `invalid_request`; 404: `not_found`; 403: `no_install`, `ambiguous_tenant`, `no_tenant`, `scope_unsupported`, `not_in_pilot`; 429: `rate_limited`; 409: every other code. One function, `glovo.Status(code)` | #959 |
| Membership lost | `no_tenant` everywhere (resolver, facade, worker check); `not_authorized` only for a wrong audience or identity kind | all |
| Refusal body | #977's `glovo.WriteError` shape `{"error": <code>, "error_description": <fixed text per code>}`. No `schema`/`refusal` envelope on refusals; success bodies keep their `schema` field. This is the shape mctl-api#957 and mctl-telegram#1235 vendor | all |
| Kill switch | one name, `GLOVO_ENABLED`, default `false`, read once in `cmd/api/main.go`. Open only when `GLOVO_ENABLED=true` **and** every readiness dependency is configured and healthy. `GLOVO_MCP_RESOURCE` alone never opens anything. `GLOVO_OAUTH_ENABLED` and `GLOVO_DISABLED` are withdrawn | #960 introduces, #961 reuses |
| DDL role | DDL runs only through `glovo.ApplySchema(ctx, migrationConnStr)` with a dedicated migration role that owns the objects. `NewStore(ctx, runtimeConnStr)` runs no DDL: it pings and checks the recorded schema version, failing closed on a mismatch. The runtime role gets only the DML it needs (no UPDATE/DELETE on `glovo_audit_events`, no DELETE on `glovo_connections`), so it cannot `ALTER`, `DROP` or `DISABLE TRIGGER`. A test proves each of the three refusals | #959 builds it, #961 extends it |
| Worker identity | none exists today: `auth.IsGlovoWorker()` is the reserved stub (`internal/auth/oidc.go`, always false). #961 builds it, default OFF. It is distinct from the #968 bridge provider (`service:bridge-provider:<ref>`, `bridge:provide`): the Glovo worker is refused on `/api/v1/bridge/*` and the bridge provider on `/api/v1/glovo/*`, tested both ways. Its credential is test-only until the issuer decision (mctl-gitops#2506 / #2540) | #961 |
| Facade routes | `/api/v1/glovo/facade/*` is added to #977's empty `glovoAudienceRoutes` by #961 (the only slice that adds those routes) | #961 |
| Allowlist routes | `PUT\|DELETE /api/v1/glovo/pilot/{tenant}/principals/{principal_id}` are defined only in #960 | #960 |

## Current state

- (Amended 2026-11-09) Slice 1 is merged as mctl-api#977 (`a9ca5814`): `internal/glovo`
  (`glovo.Code`, `glovo.Error`, `glovo.WriteError`, closed `glovo.Default`),
  `GlovoResource`, `User.IsGlovoAudience()`, `glovoAudienceGate` with an empty
  `glovoAudienceRoutes`, and the reserved `IsGlovoWorker()` that is always false. There is no
  `glovoWorkerGate` and no worker token. Slices 2-3 (#959 store, #960 selected-team grant and
  resolver) are not merged. The names below were the pre-amendment assumptions; the joint
  contract above replaces them. Their intended shapes come from the reviewed
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

## AMEND 2026-11-08 — worker auth and DB effect contracts

#958 only reserves the Glovo worker ID, not a live token or `glovoWorkerGate`. #961 must add a genuine fail-closed workload identity gate behind an explicit **default-OFF** configuration, narrowly confined to versioned worker routes and never granting access to MCP, DevLoop or admin APIs. Local integration tests may use synthetic credentials; production issuance is subject to separately approved P1 GitOps secrets. If a compatible credential cannot be built safely in-scope, mark worker routes `not_ready` rather than interpreting generic service/admin token as worker.

The #959 schema provides **neither** `glovo_handoff_refs` nor `glovo_rate_counters`. #961 owns their additive, tested schema: hash-only single-use reference and expiry, connection/install revision; row-locked or CAS-fenced atomic consume and revoke; a row-locked per-hour owner counter and transactionally enforced tenant active limit across both API replicas. Include indexes, TTL cleanup restricted to these synthetic-only tables and a migration rollback. Tests race two workers consuming one handoff, token expiry, revoked revision and two replicas at the limit: at most one successful activation, no quota overrun.

Old statements that the slice has *no new migration*, that *#959 supplies counters* or that *#958 issues the worker token* are superseded. #958/#959/#960 are hard **merged prerequisites**. The user may explicitly select the `labs` team when individually allowlisted, but no implicit `labs` default.

## Proposed solution

This slice is integration only. It adds handlers, gates wiring, schemas and tests, and it
consumes the slice 1-3 primitives without redefining them.

### 0. Precondition

Implementation starts only after #958, #959 and #960 have merged. The first task reconciles
the names assumed here (`glovo.Resolver`, `glovo.Store`, refusal enum, gates) with the merged
code. If a primitive is missing, the implementer stops and reports it. It does not add the
primitive inside this slice.

### 1. Feature gate and versioned wire types (`internal/glovo/wire`)

- `GLOVO_ENABLED` (default `false`) is introduced by #960 and reused here. `Handlers.glovoReady()`
  returns true only if the switch is on and the Glovo store, the `GlovoResource` audience and
  the worker identity are all configured. A `glovoFeatureGate` middleware mounted on
  `r.Route("/glovo", ...)` answers 503 `not_ready` otherwise, before decoding.
- Wire structs carry a mandatory `schema` constant, for example
  `glovo-connection/v1alpha1.Connection`, `...ConnectRequest`, `...WorkerCheckRequest`,
  `...WorkerCheckResponse`, `...Installation`. Refusals are not a wire struct: they are written
  by `glovo.WriteError` as `{"error","error_description"}`.
- Decoding uses `http.MaxBytesReader(16 KiB)` and `json.Decoder.DisallowUnknownFields`, then
  checks for an exact `schema` match. Any failure is 400 `invalid_request`.
- JSON Schemas are committed in `internal/glovo/wire/schema/*.json`, and a golden test checks
  that the Go marshal output validates against them. #957 and mctl-telegram#1235 can vendor the
  same files.
- Public connection states are `pending | active | expired | failed | revoked`.
  `wire.PublicState(store.State)` maps `pending_handoff` and `pending_provider` to `pending`. The table test covers
  every store state.
- Refusal to HTTP status mapping is #959's single `glovo.Status(code)` (joint contract table);
  this slice adds no second mapping.

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
| `POST /api/v1/glovo/facade/connections/{id}/reconnect` (`Idempotency-Key`) | new `gcn_` `pending`, `supersedes_id` set; only from `expired`, `failed` or `revoked` |

These routes are added to #977's `glovoAudienceRoutes`, which is empty today; every other route
stays closed to a Glovo-audience token.

Every read and write uses `store.GetConnection(ctx, owner, id)`, so the
owner predicate is in the SQL and a foreign id is indistinguishable from a missing one.

### 3. Admin handlers (`internal/api/handlers_glovo_admin.go`)

- `PUT|DELETE /api/v1/glovo/tenants/{tenant}/installation` use the normal API token and
  `requireTenantRole(..., "owner")` in principal mode. Admins are not auto-admitted. These
  routes call slice 2's atomic `Reinstall` and `RevokeInstall`, which bump the revision and
  revoke live connections in one transaction under the per-tenant advisory lock.
- The pilot allowlist routes are #960's; this slice does not define them.
- `glovoAudienceGate` already refuses Glovo-audience tokens on these routes.

### 4. Worker handlers and scope gate (`internal/api/handlers_glovo_worker.go`)

- This slice builds the worker identity, default OFF: `auth.NewGlovoWorkerUser` sets the
  reserved `glovoWorker` flag for `GlovoWorkerUserID` only when a worker credential is configured
  (`MCTL_GLOVO_WORKER_TOKEN_FILE`, a mounted file, test-only until the issuer decision in
  mctl-gitops#2506/#2540; no production credential is issued under this proposal). It adds
  `glovoWorkerGate`, which confines the worker to `^/api/v1/glovo/worker/`, and the inverse
  check in each worker handler: `user.IsGlovoWorker()` or 403. Admins, service tokens and the
  #968 bridge provider (`bridge:provide`) are refused on worker routes; the Glovo worker is
  refused on `/api/v1/bridge/*` by `bridgeProviderGate`'s counterpart. If the credential is
  absent, worker routes answer 503 `not_ready`.
- `POST /api/v1/glovo/worker/check` takes `{schema, connection_id, install_revision}` and
  returns `{schema, allowed, tenant, owner_principal_id, state, expires_at}`. Lost membership is
  `no_tenant`, lost pilot admission `not_in_pilot`, a `failed` connection `no_connection`. The tenant comes
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

- Rate and count limits use #961-owned additive Postgres counters, checked inside the mutation transaction:
  10 connect or reconnect requests per hour per (tenant, principal), and 50 non-terminal
  connections per tenant.
- Idempotency uses slice 2's `glovo_connect_requests` table. `request_hash` is the SHA-256 of
  the canonical body plus the route.
- Every mutation and every refusal on a mutating route appends to `glovo_audit_events` with
  `actor_kind` (`user|owner|admin|worker`, column added by #959). Logs (`slog`) carry only ids, states and codes.

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
  - happy path: connect, handoff, activate, check, revoke (the pilot allowlist row is created
    through #960's admin route);
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

- Migrations: #961 adds versioned, additive and idempotent handoff-reference and quota-counter tables to the #959 data model. Existing tables remain unchanged. Missing #958/#959/#960 primitives are hard dependency blockers, not an excuse to add duplicate migrations.
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
