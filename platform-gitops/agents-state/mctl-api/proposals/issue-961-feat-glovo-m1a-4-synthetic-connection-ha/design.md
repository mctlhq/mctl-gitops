# Design: issue-961-feat-glovo-m1a-4-synthetic-connection-ha

## Amendment 2026-11-09 (c), round 4 of the AMEND PR

Resolves the round-3 findings that land here (N1-N4) and the cross-slice finding X-1. Where this section and older text disagree, this section wins.

| Finding | Change here |
|---|---|
| N1 (worker routes have no owner for the #959 primitives) | Section 4: the worker routes read the connection once with #959 `GetConnectionForWorker(ctx, id)` (no owner predicate, worker-only), take the write-once Owner and `ExpectedVersion` from it, and pass them to `Transition`/`ActivateTx`, which re-check under L1/L2. No raw SQL on `glovo_connections` |
| N2 (no refusal codes for handoff and activate) | New table in section 4: every case maps to an existing #957 §4.1 code. A wrong, foreign, expired or consumed reference is one `not_found`, so it is no oracle. Tests T6 and T9 carry the rows |
| N3 (#959 purge and grant check for #961 tables) | Option (b) of #959 F2: #959 names no #961 table. This slice installs `glovo.WithEndPurger` (purge of the connection's unconsumed `glovo_handoff_refs` rows) and adds its rows to #959's `glovo.expectedGrants`; `glovoReady()` also requires `store.EndPurgerInstalled()`; the wiring passes `WithEndPurgerRequired(true)` |
| N4 (L2a row creation) | Section 5: `AfterLocks` first runs `INSERT ... ON CONFLICT DO NOTHING` of the mutex row with the fixed `window_start = 'epoch'`, then `SELECT ... FOR UPDATE`; `Sweep` never deletes `scope = 'tenant_mutex'`. T7 races from an empty table and after a `Sweep` |
| X-1 (join-API connection routes have no owner) | Section 4a (new): this slice owns `connect.Service`, the one in-process code path under both the facade connect routes and #957's `GET /connection` and `POST /connections`. The `handoff_url` source is defined there. #957 §3 and §6d.4 point at it |
| #959 F1 (`now()` is the transaction start) | `ActivateInput.ExpiresIn: 24 * time.Hour` instead of a Go `ExpiresAt`; every expiry comparison here is `clock_timestamp()` |

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
| Round 3 (F1-F6) | Activation and the limits use #959's `ActivateTx` and `ConnectInput.AfterLocks`; tables, grants and `Sweep` are specified and `glovoReady()` requires `store.Ready()`; the tenant limit uses the L2a mutex row of #957 §6b; reconnect is `TerminalOnly`; the refusal body is `glovo.WriteError`; refusal audit is `AppendRefusal` with pre-scope refusals logged only |
| P3 audit actor kind has no column in #959 | `glovo_audit_events.actor_kind` added by #959 |
| P3 no named test for the 50-per-tenant limit | T7 extended |
| Alignment with the merged #968 bridge | Worker identity is distinct from the bridge provider; mutual refusal tested (T8) |

### Joint contract frozen for #959, #960 and #961 (identical text in all three)

Verified against mctl-api main `a9ca5814` (#977 merged) and the merged #968 bridge (`docs/bridge.md`). Where an earlier section of this document disagrees, this contract wins.

| Item | Frozen value | Owner slice |
|---|---|---|
| Consent-time team selection, claims `tgr`/`stn`, `User.TeamGrant()`, `scope.Resolver` | `/oauth/consent` selection, the claims `tgr` (grant id) and `stn` (selected tenant), `User.TeamGrant() (grantID, tenant string, ok bool)` and `scope.Resolver.Resolve(ctx, *auth.User) (Scope, *glovo.Error)`. No other slice selects a team, mints a tenant claim or reads a tenant header as input; #957 consumes these (round 3: it mints no `mctl_tenant`). The `scope_ref` binding key of #957 section 2b is the grant's `refresh_family_id` (`oauth_team_grants`), read through `User.TeamGrant()` plus `teamgrant.Check`. Eligibility = membership ∩ allowlist minus `GLOVO_NON_SELECTABLE_TENANTS`; the current install is not part of it (a selected team without a current install is refused at use with `no_install` by #959) | #960 (sole owner) |
| Go package | extend the existing `internal/glovo` from #977 (`glovo.Code`, `glovo.Error`, `glovo.Gate`, `glovo.WriteError`); no parallel `RefusalCode`/`Refusal` type | #959 adds the codes |
| Tables | `glovo_installs`, `glovo_connections`, `glovo_connect_requests`, `glovo_audit_events`, `glovo_pilot_allowlist` | #959 (DDL) |
| | `glovo_handoff_refs`, `glovo_rate_counters` | #961 (DDL) |
| | `oauth_team_grants`, `oauth_refresh_tokens.team_grant_id` (refresh-store database) | #960 |
| Columns | reconnect link `supersedes_id`; `glovo_connections.expires_at TIMESTAMPTZ NULL`; `glovo_audit_events.actor_kind` (`user`, `owner`, `admin`, `worker`, `system`) | #959 |
| Store API | `Install`, `GetInstall`, `RevokeInstall`, `Reinstall`, `Connect`, `Reconnect`, `Transition`, `Revoke`, `GetConnection`, `LiveConnection`, `ListAudit`, `IsAllowlisted` | #959 |
| Store states | `pending_handoff`, `pending_provider`, `active`, `expired`, `failed`, `revoked`; wire `PublicState`: both `pending_*` -> `pending`, the rest unchanged | #959 states, #961 mapping |
| Refusal enum (closed, `glovo.Code`) | `not_ready`, `unavailable`, `not_authorized`, `invalid_request`, `not_found`, `no_install`, `ambiguous_tenant`, `no_tenant`, `scope_unsupported`, `not_in_pilot`, `stale_install`, `stale_version`, `no_connection`, `connection_exists`, `connection_revoked`, `connection_expired`, `invalid_transition`, `idempotency_key_reused`, `rate_limited`; since 2026-11-09 (c) also `fingerprint_changed`, `approval_invalid`, `approval_expired`, `approval_replayed`, `intent_mismatch`, `basket_changed`, `tenant_busy`. The one closed set, with every status and wire value, is mctl-api#957 design §4.1 | #959 adds the M1a codes; #985, #988 and #989 add theirs through #957 §4.1 |
| HTTP status | Amended 2026-11-09 (c) to equal mctl-api#957 design §4.1: 503: `not_ready`, `unavailable`; 401/403: `not_authorized` (401 only when no valid token); 400: `invalid_request`; 404: `not_found`, `no_connection`; 403: `no_install`, `ambiguous_tenant`, `no_tenant`, `scope_unsupported`, `not_in_pilot`, `stale_install`; 429: `rate_limited`; 409: every other code. One function, `glovo.Status(code)`; the #957 A6 golden test checks it against §4.1 for every code | #959 |
| Membership lost | `no_tenant` everywhere (resolver, facade, worker check); `not_authorized` only for a wrong audience or identity kind | all |
| Refusal body | #977's `glovo.WriteError` shape `{"error": <code>, "error_description": <fixed text per code>}`. No `schema`/`refusal` envelope on refusals; success bodies keep their `schema` field. This is the shape mctl-api#957 and mctl-telegram#1235 vendor | all |
| Kill switch | one name, `GLOVO_ENABLED`, default `false`, read once in `cmd/api/main.go`. Open only when `GLOVO_ENABLED=true` **and** every readiness dependency is configured and healthy. `GLOVO_MCP_RESOURCE` alone never opens anything. `GLOVO_OAUTH_ENABLED` and `GLOVO_DISABLED` are withdrawn | #960 introduces, #961 reuses |
| DDL role | DDL runs only through `glovo.ApplySchema(ctx, migrationConnStr, runtimeRole)` with a dedicated migration role that owns the objects; the one Glovo runtime role and its grants are mctl-api#957 design §6d.1 (amended (c)). `NewStore(ctx, pool *pgxpool.Pool, runtimeRole string, opts ...Option)` (round 3) takes the one shared `GLOVO_DB_URL` pool that the wiring slice opened and that the bridge store also uses (#957 §6d.1 R4), opens no pool of its own and runs no DDL: it pings and checks the recorded schema version, failing closed on a mismatch. The runtime role gets only the DML it needs (no UPDATE/DELETE on `glovo_audit_events`, no DELETE on `glovo_connections`), so it cannot `ALTER`, `DROP` or `DISABLE TRIGGER`. A test proves each of the three refusals | #959 builds it, #961 extends it |
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
  returns true only if the switch is on, the Glovo store is configured **and `store.Ready()` is
  nil** (round 3: wrong `current_user`, extra ownership, a missing trigger or a missing
  revocation hook close every route, D-A), the `GlovoResource` audience and the worker
  identity are all configured. A `glovoFeatureGate` middleware mounted on
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
| `POST /api/v1/glovo/facade/connections/{id}/handoff` | issues the synthetic handoff reference `ghr_` + 32 random bytes, stores only the SHA-256, TTL 10 min, single use. It only inserts the `glovo_handoff_refs` row; the connection stays `pending_handoff` (round 3: the state moves only in the worker `activate`, below) |
| `POST /api/v1/glovo/facade/connections/{id}/revoke` | `-> revoked`, idempotent |
| `POST /api/v1/glovo/facade/connections/{id}/reconnect` (`Idempotency-Key`) | new `gcn_` `pending`, `supersedes_id` set; this route calls #959 `Reconnect` with `ConnectInput.TerminalOnly = true` (round 3), which evaluates under L2 and takes only the terminal branch: a prior that is `expired`, `failed` or `revoked`, or `active` with `expires_at <= clock_timestamp()` (database clock), gets a new `gcn_`; a live prior is refused `connection_exists` (409), so the route never supersedes. There is no pre-check read of `GetConnection` (it does not apply the clock) |

These routes are added to #977's `glovoAudienceRoutes`, which is empty today; every other route
stays closed to a Glovo-audience token.

Every read and write uses `store.GetConnection(ctx, owner, id)`, so the
owner predicate is in the SQL and a foreign id is indistinguishable from a missing one.

### 3. Admin handlers (`internal/api/handlers_glovo_admin.go`)

- `PUT|DELETE /api/v1/glovo/tenants/{tenant}/installation` use the normal API token and
  `requireTenantRole(..., "owner")` in principal mode. Admins are not auto-admitted. These
  routes call slice 2's atomic `Reinstall` and `RevokeInstall`, which bump the revision and
  revoke live connections in one transaction under the L1 install advisory lock (#957 §6b).
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
- **How the worker routes get the owner (round 4, N1).** The worker holds only a `gcn_` id.
  Every worker handler starts with #959 `GetConnectionForWorker(ctx, id)`, the one by-id read
  without an owner predicate, which returns the connection with its write-once Owner (tenant,
  principal), state, version, install revision and `expires_at`. An absent id is `not_found`.
  That read takes no lock and is not an authority: it only supplies the Owner and the
  `ExpectedVersion` that the locked primitives then re-check. Nothing here reads
  `glovo_connections` with raw SQL, and no handler skips L1/L2.
- `POST /api/v1/glovo/worker/check` takes `{schema, connection_id, install_revision}` and
  returns `{schema, allowed, tenant, owner_principal_id, state, expires_at}`. Lost membership is
  `no_tenant`, lost pilot admission `not_in_pilot`, a `failed` connection `no_connection`. The tenant comes
  from the connection row (`GetConnectionForWorker`), never from the request. At call time the handler re-reads:
  installation state and revision, connection state and expiry, the owner's live role (through
  the same principal-mode role reader the resolver uses), and the allowlist row.
- `POST /api/v1/glovo/worker/connections/{id}/activate` takes
  `{schema, install_revision, handoff_ref}`. It makes one call, #959 `ActivateTx` (round 3)
  on a transaction it opened, with `ActivateInput{Owner, ConnectionID,
  ExpectedVersion` (the version `GetConnectionForWorker` returned, re-checked by `ActivateTx`
  under L1/L2; a change in between is `stale_version` and commits nothing)`, ExpectedInstallRevision,
  ExpiresIn: 24 * time.Hour` (computed in SQL as `clock_timestamp() + ExpiresIn`; no Go clock crosses
  the boundary)`, AfterLocks}`. `ActivateTx` takes L1 shared and L2 exclusive,
  then runs `AfterLocks`, which takes the `glovo_handoff_refs` row `FOR UPDATE` (level
  L2b of #957 §6b), verifies the reference hash, its TTL and `consumed_at IS NULL`, and
  sets `consumed_at`. `ActivateTx` then steps `pending_handoff -> pending_provider ->
  active` and sets `expires_at`, so `LiveConnectionTx` reports `connection_expired` once it
  passes. Zero or a lost row, an expired or consumed reference, or a revoked or stale
  connection commits nothing, with the codes of the table below. This slice adds no store
  primitive of its own: it uses the #959 primitives named in task 0 and writes no
  `glovo_connections` row itself.
- `POST /api/v1/glovo/worker/connections/{id}/expire` is synthetic and is used to drive the
  expiry path deterministically in tests. It reads the Owner and version with
  `GetConnectionForWorker` and calls #959 `Transition(ctx, owner, id, expired, version,
  "synthetic_expire", nil)`.

**Refusal codes of handoff and activate (round 4, N2).** Only members of the closed set of
#957 §4.1; the HTTP status is `glovo.Status(code)`. Nothing here adds a code.

| Case | `glovo.Code` | Notes |
|---|---|---|
| Handoff or activate on an unknown, foreign or never-existing connection id | `not_found` (404) | the same body as a missing id (no oracle) |
| Activate with a reference that is unknown, of another connection, of another tenant, expired or already consumed | `not_found` (404) | one code for all four, so a wrong and an expired reference are not distinguishable |
| Handoff or activate on a connection that is not `pending_handoff` (already `pending_provider` or `active`) | `invalid_transition` (409) | |
| Handoff or activate on a `revoked` connection | `connection_revoked` (409) | |
| Handoff or activate on an `expired` connection, or one whose `expires_at` has passed | `connection_expired` (409) | |
| Handoff or activate on a `failed` connection | `no_connection` (404) | as `check` |
| Install revision differs from the install's current one | `stale_install` (403) | |
| `ExpectedVersion` no longer matches under the locks | `stale_version` (409) | nothing committed |
| Store or lock failure | `unavailable` (503) | never a refusal that could read as "no" |

### 4a. Join-route connection seam (round 4, X-1; owner: this slice)

The join API of #957 serves `GET /connection` and `POST /connections`. This slice owns the
code behind them, so that the 50-per-tenant limit, the hourly limit, the L2a mutex and the
handoff are enforced on the one route that creates connections, whichever front end calls it.
`internal/glovo/connect` exports one in-process service. Both the facade handler
`POST /api/v1/glovo/facade/connections` (section 2) and #957's `glovojoin.Connections`
adapter call it; there is no second connect path and the join routes never call the
`/api/v1/glovo/facade/*` HTTP routes.

```go
// JoinScope is the verified scope: tenant, principal and install revision come from the
// #957 / #960 resolver, never from a request body.
type JoinScope struct { Tenant, PrincipalID string; InstallRevision int64 }
type ConnectOutcome struct { Connection *glovo.Connection; HandoffURL string; HandoffExpiresAt time.Time; Replayed bool }
func (s *Service) Connect(ctx context.Context, sc JoinScope, idempotencyKey string) (*ConnectOutcome, error)
func (s *Service) Current(ctx context.Context, sc JoinScope) (*glovo.Connection, error) // no_connection when none
```

- `Connect` calls #959 `Connect` with `ConnectInput.AfterLocks` (the rate limits and the L2a
  mutex of section 5), then, in a second short transaction under L1 shared and L2 shared,
  inserts the single-use `ghr_` row for the new connection and deletes the connection's
  older unconsumed rows. A replay (same key and body) returns the original connection with
  `Replayed = true` and a fresh `handoff_url`; the raw reference is never stored, so a replay
  cannot return the old one.
- **`handoff_url` source.** `GLOVO_SYNTHETIC_HANDOFF_BASE_URL` (unset: `Connect` answers
  `not_ready`, never a made-up URL) plus `/` plus the raw `ghr_` value. It is synthetic
  and test-only like the worker credential. `HandoffExpiresAt` (the 10 minute handoff TTL) is
  what #957 returns as `expires_at` of `POST /connections`.
- `Current` is #959 `LiveConnection` for the scope's Owner; none is `no_connection` (404),
  an `expires_at` that has passed is `connection_expired` (the clock rule of #959).
- Failures are the closed #957 §4.1 codes (`rate_limited`, `connection_exists`,
  `idempotency_key_reused`, `stale_install`, `no_install`, `not_ready`, `unavailable`);
  #957 maps them to the wire with its own table.
- Merge order: #959, #960, then this slice; #957's join routes (M1e) merge after it, or run
  against test doubles of `glovojoin.Connections` until then.

- The worker has no groups, no admin flag and no agent scope. Because `glovoWorkerGate` runs in
  the authenticated chain before `r.Route("/api/v1")`, the worker gets 403 on
  `/api/v1/agents/dev-loop/*` (approve, abandon, get), on Temporal-backed routes, on `/mcp` and
  on facade routes.

### 5. Limits, idempotency, audit

- Rate and count limits use #961-owned additive Postgres counters (below), checked inside
  the mutation transaction through #959's `ConnectInput.AfterLocks` (connect and reconnect):
  10 connect or reconnect requests per hour per (tenant, principal), and 50 non-terminal
  connections per tenant. The lock order is the canonical one of #957 design §6b, and this
  slice adds two levels there, both after L2 and before L3 (round 3): **L2a**, the tenant
  mutex row `glovo_rate_counters(scope='tenant_mutex', tenant_id)` taken `FOR UPDATE`
  by connect and reconnect, and **L2b**, the `glovo_handoff_refs` row taken `FOR UPDATE`
  by activate. **The mutex row is created, not assumed (round 4, N4).** `AfterLocks` first runs
  `INSERT INTO glovo.glovo_rate_counters (scope, tenant_id, principal_id, window_start,
  count, updated_at) VALUES ('tenant_mutex', $tenant, '', 'epoch', 0, clock_timestamp())
  ON CONFLICT DO NOTHING` (`window_start` is the fixed `'epoch'` timestamp, so there is
  exactly one such row per tenant) and then `SELECT ... FOR UPDATE` on it. A first connect, and
  a connect after a `Sweep`, therefore always find a row to lock. `Sweep` never deletes
  `scope = 'tenant_mutex'` rows (they are one tiny row per tenant); it deletes only stale
  `owner_hour` windows. The 50-per-tenant limit is enforced by counting non-terminal connections
  **after** L2a is held, never with `count(*)` under L1 shared and L2 alone: two replicas
  connecting for different principals of one tenant would both count 49 and insert, and
  the tenant mutex row serializes them. The hourly owner counter row is incremented
  under the owner's L2 exclusive and needs no further lock. Paths: connect and reconnect:
  L1 sh, L2 ex, L2a; activate: L1 sh, L2 ex, L2b; reinstall and revoke: unchanged
  (L1 ex, L2 ex).
- Idempotency uses slice 2's `glovo_connect_requests` table. `request_hash` is the SHA-256 of
  the canonical body plus the route.
- **Tables (round 3, D-A).** Created in schema `glovo` by `glovo.ApplySchema` under the
  migration role (this slice contributes the DDL and the grants to that one entry point; the
  R2 chain of #957 §6d.1 is unchanged), never by the runtime role:
  `glovo.glovo_handoff_refs(ref_hash BYTEA PRIMARY KEY, connection_id TEXT NOT NULL
  REFERENCES glovo.glovo_connections, tenant_id TEXT NOT NULL, principal_id TEXT NOT
  NULL, created_at TIMESTAMPTZ NOT NULL, expires_at TIMESTAMPTZ NOT NULL, consumed_at
  TIMESTAMPTZ NULL)` and `glovo.glovo_rate_counters(scope TEXT NOT NULL CHECK (scope IN
  ('owner_hour','tenant_mutex')), tenant_id TEXT NOT NULL, principal_id TEXT NOT NULL
  DEFAULT '', window_start TIMESTAMPTZ NOT NULL, count INTEGER NOT NULL, updated_at
  TIMESTAMPTZ NOT NULL, PRIMARY KEY (scope, tenant_id, principal_id, window_start))`.
  **Ownership of the purge and of the grant check (round 4, N3).** #959 names no table of this
  slice. This slice installs `glovo.WithEndPurger` with a function that deletes the ended
  connections' unconsumed `glovo_handoff_refs` rows on the revoker's own transaction, adds
  its `glovo_handoff_refs`, `glovo_rate_counters` rows (and the extra `DELETE` right on
  `glovo_connect_requests` is already a #959 row) to #959's `glovo.expectedGrants`, and
  `glovoReady()` requires `store.EndPurgerInstalled()`. The wiring passes
  `WithEndPurgerRequired(true)` once these routes are mounted, so a deployment that forgot
  the purger is `end_purger_missing`, never silently purge-less. The exact `glovo_runtime` rights are rows of #957 §6d.1: `glovo_handoff_refs`
  `SELECT, INSERT, UPDATE (consumed_at), DELETE` (the TTL purge and #959's `endConnection`
  purge of unconsumed rows); `glovo_rate_counters` `SELECT, INSERT, UPDATE (count,
  updated_at), DELETE` (stale `owner_hour` windows, never `tenant_mutex`); and `DELETE` on `glovo.glovo_connect_requests`
  for the 24 h cleanup. That cleanup is this slice's `Sweep(ctx, limit)`, a bounded
  `DELETE` batch of the three tables (excluding `tenant_mutex` rows), run by a ticker that exists only while
  `GLOVO_ENABLED=true`; it is the cleanup #959 refers to.
- Every mutation, and every refusal on a mutating route that names an existing install or
  connection, appends to `glovo_audit_events` with `actor_kind` (`user|owner|admin|worker`,
  column added by #959): mutations through #959's own transactions, refusals through
  #959 `AppendRefusal` (round 3). Refusals that arrive before any entity exists
  (`ambiguous_tenant`, `scope_unsupported`, `no_tenant`, `not_in_pilot`, `no_install`,
  and `rate_limited` on a connect) cannot fill the audit row's required tenant, entity and
  revision, so they are logged with `slog` and counted in metrics only, never written
  with fabricated values. Logs (`slog`) carry only ids, states and codes.

### 6. End-to-end contract tests (`internal/api/glovo_e2e_test.go`)

- The tests build the actual `NewRouter(...)` with a real `glovo.Store` on `TEST_DATABASE_URL`.
  The schema is applied by the production `glovo.ApplySchema` under a migration role, and the
  store is opened with `NewStore` (no DDL) under the runtime role of mctl-api#957 design §6d.1,
  in a per-test schema or with cleanup (amended 2026-11-09 (c)).
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

- Migrations: #961 adds versioned, additive and idempotent handoff-reference and quota-counter tables to the #959 data model, in schema `glovo`, through `glovo.ApplySchema` under the migration role. Existing tables remain unchanged. Missing #958/#959/#960 primitives are hard dependency blockers, not an excuse to add duplicate migrations.
- Backward compatibility: with `GLOVO_ENABLED` unset (the deployed state), every Glovo route
  answers 503 `not_ready`, and token issuance and verification are unchanged. Regression tests
  cover support, DevLoop, MCP and Telegram routes.
- Resources: a few indexed queries per call. Two replicas are safe because limits, idempotency
  and handoff consumption are in Postgres under the canonical lock order of #957 design §6b (L1, L2, then L2a/L2b), with the tenant limit serialized by the L2a mutex row.
- Risks and mitigations:
  - Drift from the slice 1-3 contracts: task 0 reconciles first, and no primitive is duplicated.
  - An existence oracle: one 404 path and body for foreign and missing ids, tested.
  - Worker overreach: gate plus handler check, and a negative route matrix including dev-loop.
  - Leaks: secretscan over logs, audit rows and responses, and handoff references stored hashed.
  - Accidental enablement: a separate gitops change is required, which is out of scope.
  - Incompatibility with #957 and #1235: shared JSON Schemas and the same refusal enum. The
    readiness document says NOT READY.
