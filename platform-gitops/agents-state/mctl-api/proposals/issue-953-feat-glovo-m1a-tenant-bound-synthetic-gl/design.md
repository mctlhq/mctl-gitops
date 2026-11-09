# Design: issue-953-feat-glovo-m1a-tenant-bound-synthetic-gl

## Current state

- OAuth resource indicators: `internal/auth/oauth_resource.go`
  `ResolveResource` accepts no resource or this API (audience, base URL,
  `/mcp`) and exactly one extra https resource, `SupportResource`
  (`DefaultSupportResource = "https://support.mctl.ai"`, set from
  `OAUTH_SUPPORT_RESOURCE` by `configureSupportResource` in
  `cmd/api/main.go`). `ValidateSupportResource` refuses a value that names
  this API. Anything else is `ErrInvalidTarget`.
- Token verification: `internal/auth/oauth_server.go` (around the
  `payload.Issuer != s.BaseURL` check) requires `iss == BaseURL`, then
  classifies `aud`: a support audience wins over an API entry in the same
  `aud` ("fail closed") and sets `payload.support`; otherwise the API
  audience is required. `u.supportAudience = payload.support` exposes it as
  `User.IsSupportAudience()`.
- Audience confinement: `internal/api/support_audience_gate.go`
  `supportAudienceGate` runs first in the authenticated group
  (`internal/api/router.go:534`) and returns 401 `invalid_token` for any
  route not in `supportAudienceRoutes`, so new routes are closed by default.
- Short-lived audience tokens: `internal/auth/oauth_support_token.go`
  `IssueSupportToken` mints non-renewable, unpersisted tokens bounded by
  `MaxSupportTokenTTL`.
- Machine identities: `internal/auth/oidc.go` builds narrow principals from
  dedicated env tokens (`MCTL_USAGE_WRITER_TOKEN`, `MCTL_EVIDENCE_WRITER_TOKEN`)
  with unexported flags (`usageWriter`, `evidenceWriter`) and a
  `subtle.ConstantTimeCompare` check; a token equal to another writer token is
  disabled.
- Principals: `internal/principals` (`store.go` tables `principals`,
  `external_identities`; `resolver.go` with `CacheTTL`, `ResolveTimeout`,
  and degrade-on-failure `ErrUnresolved`). `auth.PrincipalID` is "" when
  unresolved (phase 1 degrades).
- Tenancy: `User.Groups` holds tenant names; `User.HasTenantAccess`
  (`internal/auth/oidc.go:258`) admits admins and agent scopes too. Role checks
  are in `internal/api/tenant_role.go` (`checkTenantRoleByPrincipal`,
  `requireTenantRole`); `docs/tenant-roles.md` documents
  `TENANT_AUTHZ_MODE=principal`, roles viewer/developer/owner, and 503
  `tenant_role_unavailable` when the role cannot be read.
- Store pattern: `internal/commerce/store.go` keeps its schema as inline
  `CREATE TABLE IF NOT EXISTS` DDL applied by `NewStore`, uses ULIDs
  (`newULID`), `withTx` with an advisory lock key, `isUniqueViolation`, and
  tenant-scoped reads (`GetQuote(ctx, tenantID, id)`). It is wired in
  `cmd/api/main.go` with `COMMERCE_DB_URL` falling back to `AUDIT_DB_URL`,
  a `COMMERCE_DISABLED` switch, and 503 on every route when absent.
- Idempotency precedent: `commerce_invocations` `UNIQUE (tenant_id,
  principal_id, idempotency_key)`; work items return `replayed: true` and 409
  `idempotency_key_reused`.
- Automation contract `internal/automation/contract` (#948/#950) is schema
  only; it grants no Glovo authority and is not touched here.
- No Glovo code exists in the repo (`grep -ri glovo` over `*.go`: no hits).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml`:
  `replicaCount: 2`, host `api.mctl.ai`, `TENANT_AUTHZ_MODE: "principal"`,
  `AUDIT_DB_URL` on `shared-pg-rw.platform-db.svc:5432/mctl-api`. No
  `OAUTH_SUPPORT_RESOURCE` override (default applies) and no Glovo env var.
- `grep -ri glovo` over `$MCTL_GITOPS_ROOT`: only proposal text
  (mctl-gitops#2456 Temporal trust-domain design naming a future
  `temporal-provider-<name>` namespace; mctl-telegram#1184 spike). No Glovo
  service, tenant, hostname or Ingress is deployed.
- `$MCTL_GITOPS_ROOT/tenants/`: admins, commerce-proof, erpact, karabu, labs,
  mctl, namax66. `services/labs/` lists many services, none Glovo.
- mctl MCP read tools were not called; the gitops checkout was sufficient.

## Proposed solution

### AMEND 2026-11-08 — selected-team OAuth grant, no ambient tenant inference

This proposal MUST implement the owner-confirmed team choice at the protected-resource **OAuth authorization-code consent step** (a human, first-party MCTL screen), persist `selected_team_tenant` in the *server-owned authorization grant*, and bind that selected team to the Glovo `aud` in a tamper-evident access token/verified server-side token record. The service must validate live role membership **and** per-principal pilot allowlist on each Glovo call; a single eligible tenant after filtering still does **not** constitute explicit selection. Missing selection = existing `ambiguous_tenant` refusal (no new public enum required), and a team switch requires new user consent/new OAuth grant. Any tool-provided `tenant` or fake installation hint is ignored/rejected. Issuer and exact audience remain mandatory.

The previous resolver sketch below that automatically maps exactly one membership∩allowlist tenant to a `Scope` is **superseded**. Resolver must read `SelectedTeamTenant` from the authenticated grant, ensure selection integrity and expiry/revocation, then test membership+principal-specific allowlist and emit a `Scope` for that team; never select a team itself. Adapt OAuth authorize/consent and refresh tests, not just token-verifier tests.

M1 pilot allowlist schema must be `(tenant_id, principal_id NOT NULL)` with a unique key, **no tenant wildcard row**; team membership alone cannot authorize entry. The deployment tenant `labs` cannot become the caller tenant. Preserve a negative test where the principal is allowlisted in exactly one team **but has not explicitly selected it**; route must refuse before any store or provider effect.



### 1. Glovo resource audience (`internal/auth`)

- Add `OAuthServer.GlovoResource string` (env `GLOVO_MCP_RESOURCE`, default
  empty = disabled; intended `https://glovo.mctl.ai/mcp`), validated like
  `ValidateSupportResource` and additionally refused if equal to
  `SupportResource`.
- `ResolveResource`: when it matches, mint `aud = GlovoResource` (normal
  authorization-code flow, so the facade's OAuth client obtains it).
- Verification: in the `aud` switch, a Glovo entry wins over support and API
  entries (fail closed) and sets `payload.glovo`; issuer is still the existing
  `iss == BaseURL` check. New `User.IsGlovoAudience()` with unexported
  `glovoAudience` flag. Refresh tokens keep the flow resource via
  `FlowResource` unchanged.
- New `internal/api/glovo_audience_gate.go`, mounted beside
  `supportAudienceGate`: a Glovo-audience token reaches only
  `/api/v1/glovo/facade/*`; everything else (including `/mcp`) is 401. The
  existing support gate is unchanged; support tokens never reach Glovo routes.

### 2. Worker machine identity (`internal/auth/oidc.go`)

- `MCTL_GLOVO_WORKER_TOKEN`, same pattern as the evidence writer:
  `NewGlovoWorkerUser()`, unexported `glovoWorker` flag, constant-time
  compare, disabled if it equals any other configured machine token. A
  `glovoWorkerGate` confines it to `/api/v1/glovo/worker/*` and refuses those
  routes to every other identity (service token, mctl-telegram tokens, admins
  included). It carries no tenant groups.

### 3. Package `internal/glovo`

- `scope.go` — `Resolver.Resolve(ctx, user) (Scope, *Refusal)`:
  1. not Glovo-audience or `PrincipalID == ""` -> `not_authorized`;
  2. memberships = tenants where the principal has a principal-mode role
     (reusing the tenant role reader behind `checkTenantRoleByPrincipal`;
     admin status and agent scopes are NOT honoured, `HasTenantAccess` is not
     used); role read failure -> 503, never an answer;
  3. none -> `no_tenant` (or `scope_unsupported` when a personal scope marker
     is the only candidate);
  4. Require `SelectedTeamTenant` on the authenticated OAuth grant (selected directly by human at authorization), reject absence as `ambiguous_tenant` even if exactly one eligible team, then intersect live role membership AND per-principal allowlist for **this** selected team. Only then return `Scope{PrincipalID, Tenant, Role}`.
  The resolver takes no tenant selection from MCP arguments, request headers or body.
- `types.go` — refusal codes (closed enum), connection states and the
  transition table `allowed[from][to]`.
- `store.go` — inline DDL (commerce pattern):
  - `glovo_installations(id gin_ PK, tenant_id UNIQUE, revision BIGINT,
    state active|removed, created_by, created_at, updated_at)`;
  - `glovo_connections(id gcn_ PK, tenant_id, owner_principal_id,
    installation_id, install_revision, provider CHECK = 'synthetic', state
    CHECK in (pending_handoff, pending_provider, active, expired, failed,
    revoked), secret_ref TEXT NULL CHECK (secret_ref IS NULL), replaces_id,
    expires_at, revoked_reason, created_at, updated_at)` with
    `UNIQUE (tenant_id, owner_principal_id, id, install_revision)` and a
    partial unique index on `(tenant_id, owner_principal_id,
    installation_id) WHERE state IN (pending_handoff, pending_provider,
    active)`;
  - `glovo_connection_requests(tenant_id, principal_id, idempotency_key,
    request_hash, connection_id, created_at, UNIQUE(tenant_id, principal_id,
    idempotency_key))`;
  - `glovo_pilot_allowlist(tenant_id, principal_id NOT NULL, added_by,
    added_at, UNIQUE(tenant_id, principal_id))` — **per-principal and per-team only**, no wildcard/tenant-wide entries in M1;
  - `glovo_audit_events(id gae_ PK, tenant_id, principal_id, actor_kind,
    connection_id NULL, installation_id NULL, install_revision, event,
    from_state, to_state, refusal_code, created_at)` with a trigger that
    rejects UPDATE and rejects DELETE of rows younger than the retention
    window; a retention sweep deletes older rows.
  - All reads take `(tenant_id, owner_principal_id, id)`; a miss on any
    component returns `ErrNotFound`, so a foreign id and a missing id are
    indistinguishable.
  - Mutations run in `withTx` under an advisory lock on
    `glovo:<tenant>` so revocation, reinstall and connect serialise per tenant.
- `secrets.go` — `SecretRefStore` interface (`Put(ctx, connID, sealed
  Envelope) (SecretRef, error)`, `Open`, `Destroy`) with `SecretRef` opaque
  `gsr_` id and `Envelope{KEKID, WrappedDEK, Nonce, Ciphertext}`; the design
  (random 256-bit DEK per connection, AES-GCM, DEK wrapped by an independent
  KEK held outside Postgres, AAD = tenant|owner|connection|revision) is
  documented. M1 ships only `refusingSecretStore` returning
  `ErrSecretsUnsupported`; nothing calls it on the synthetic path.
- `synthetic.go` — fake provider: `pending_provider -> active` with a fixed
  expiry, no network, no bytes stored.
- `ratelimit.go` — DB-backed counts (connect requests in last hour per
  principal, live connections per tenant), so limits hold across the two
  replicas.

### 4. HTTP API (`internal/api/handlers_glovo.go`, routes in `router.go`)

Facade (Glovo-audience token; tenant/owner always from `Resolve`):
- `GET  /api/v1/glovo/facade/context` -> `{principal_id, tenant,
  installation_id, install_revision, connection?}` or refusal.
- `POST /api/v1/glovo/facade/connections` (header `Idempotency-Key`) ->
  201 `pending_handoff` connection, or replay.
- `POST /api/v1/glovo/facade/connections/{id}/reconnect` (Idempotency-Key).
- `POST /api/v1/glovo/facade/connections/{id}/handoff` -> `pending_provider`
  (synthetic stand-in for the user handoff).
- `POST /api/v1/glovo/facade/connections/{id}/revoke`.
- `GET  /api/v1/glovo/facade/connections/{id}`.
Body fields such as `tenant`, `owner`, `namespace`, `task_queue` are rejected
by strict decoding (`DisallowUnknownFields`) with 400, not silently used.

Worker (`MCTL_GLOVO_WORKER_TOKEN`):
- `POST /api/v1/glovo/worker/check` `{connection_id, install_revision}` ->
  `{allowed: true, tenant, owner_principal_id, state}` or refusal. Re-derives
  membership and pilot status for the owner at call time.
- `POST /api/v1/glovo/worker/connections/{id}/activate|fail` (synthetic only;
  requires a passing check in the same transaction).

Tenant administration (normal API token, `requireTenantRole` owner):
- `PUT /api/v1/glovo/tenants/{tenant}/installation` (create or reinstall:
  revision++ and revoke all live connections atomically).
- `DELETE` same path (remove installation, revoke all).
Admin only: `PUT|DELETE /api/v1/glovo/pilot/{tenant}[/principals/{prn}]`.

Refusal HTTP mapping: `not_authorized` 401/403, `not_found` 404, the
`no_*`/`ambiguous_tenant`/`scope_unsupported`/`not_in_pilot` 403,
`stale_install`/`connection_revoked`/`connection_expired` 409. Store
unavailable is 503, never a refusal code.

### 5. Wiring and docs

- `cmd/api/main.go`: `GLOVO_DB_URL` falling back to `AUDIT_DB_URL`, switch
  `GLOVO_DISABLED`; routes 503 when the store or `GLOVO_MCP_RESOURCE` is
  absent. Defaults leave the feature off.
- `internal/glovo/schema/*.json` JSON Schemas for each request/response and
  the refusal envelope; `docs/glovo-connections.md` with state diagram,
  schema, refusal table, secret envelope design and the test matrix; OpenAPI
  entries in `internal/openapi`.
- No MCP tool is added (`internal/mcp/server.go` and the
  `TestNewMCPServer_ToolCount` expectation are unchanged).
- Logging via `slog` carries only ids, states and refusal codes.

## Alternatives

- Registry in mctl-telegram: rejected by the issue as authority duplication;
  mctl-api already owns principals, tenant roles and OAuth audiences.
- Reuse the API audience and add a `tenant` argument: puts tenant selection in
  caller hands and lets any mctl-api token act on Glovo; rejected.
- Reuse `HasTenantAccess`: it admits admins and agent scopes as members of
  every tenant, which would let a platform admin or agent token impersonate a
  tenant owner of a connection; rejected in favour of principal-mode role rows
  only.
- Store in the commerce package: different lifecycle and retention; a
  separate package keeps blast radius and review scope small.

## Platform impact

- Migrations: additive `glovo_*` tables in the existing mctl-api database,
  applied idempotently on start like commerce. No change to existing tables.
  Rollback leaves unused tables.
- Backward compatibility: with `GLOVO_MCP_RESOURCE` unset (the default and the
  current deployed state) token minting and verification are byte-identical;
  new routes answer 503. Existing support/API audiences, `tg.mctl.ai` auth,
  automation and DevLoop routes are covered by regression tests.
- Resources: negligible; a few indexed queries per facade call. Two replicas
  are safe because limits and idempotency are in Postgres and mutations take a
  per-tenant advisory lock.
- Risks and mitigations:
  - Audience confusion between support, Glovo and API tokens -> precedence
    Glovo > support > API with fail-closed gates and tests for mixed `aud`.
  - Existence oracle on ids -> single `not_found` path and body; timing kept
    to one indexed lookup.
  - Membership revoked mid-flow -> worker check re-derives membership each
    call; facade calls do too (no cache longer than the role reader's).
  - Secrets leakage -> `secret_ref IS NULL` CHECK, refusing secret store,
    tests scanning logs, audit rows and fixtures with `internal/secretscan`.
  - Accidental production enablement -> off by default; enabling needs a
    separate gitops change and is out of scope.
