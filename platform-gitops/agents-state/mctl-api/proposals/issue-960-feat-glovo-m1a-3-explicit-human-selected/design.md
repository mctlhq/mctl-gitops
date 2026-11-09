# Design: issue-960-feat-glovo-m1a-3-explicit-human-selected

## Amendment 2026-11-09 — joint 959/960/961 AMEND

Independent review of digest `sha256:9be361b79d65b262733aa87e077b4b66e0247ac630bda5379d7f1b26751693a6` (mctl-api#960, comment of 2026-11-09) required one joint amendment across #959, #960 and #961. Finding -> change in this slice:

| Finding | Change |
|---|---|
| P2 atomic grant/code/refresh write required but not designed; grants on `OAUTH_DB_URL`, allowlist on `GLOVO_DB_URL` | Section "Atomic grant binding" below: `oauth_team_grants` lives in the refresh-store database and pool; grant activation and the refresh-token insert commit in one transaction; revocation updates grant and family in one transaction; the allowlist is a live read, never part of the write. Without a Postgres refresh store the Glovo resource stays `not_ready` |
| P2 task 0 cannot pass (allowlist DDL and refusal enum absent from #959) | #959 now owns the `glovo_pilot_allowlist` DDL, `IsAllowlisted` and the full closed enum (joint contract); task 0 checks those exact names |
| P2 kill switch only in AMEND text; name differs from #961 | One switch `GLOVO_ENABLED` (joint contract). New task 10 changes `ResolveResource` and replaces the #977 build-constant `glovo.Default` with a config gate; body, Rollback and tasks updated; `GLOVO_OAUTH_ENABLED`/`GLOVO_DISABLED` withdrawn |
| P3 "merge is mechanical" contradicts the task 0 STOP | Risk text corrected |
| P3 no named test for consent-token replay or auth-code reuse | T13 and T14 added |

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

Authorization flow (all read in the clone at `5f60792`):
- `internal/api/oauth_handlers.go` `handleOAuthAuthorize` stores a
  `pendingAuth` (`internal/auth/oauth_server.go`: Upstream, ClientID,
  RedirectURI, CodeChallenge, Resource). The upstream callback then calls
  `finishAuthorization` (`internal/api/oauth_consent.go`).
- `finishAuthorization` shows the consent page only for CIMD clients
  (`o.IsCIMDClient`). Every other client gets a code at once through
  `issueGrant` -> `OAuthServer.IssueCodeWithAuthMethod`. The consent page
  (`requestConsent`) stores an `auth.ConsentEntry` (`internal/auth/oauth_cimd.go`)
  under a single-use token plus a `__Host-mctl_consent_<hash>` cookie.
  `takeConsentDecision` accepts only `token` and `decision=approve|deny`.
  Nothing on that page selects a tenant, and the page text says the
  application "does not choose this account".
- `authCodeEntry`, `pendingAuth` and `refreshTokenEntry` (oauth_server.go
  ~2258-2300) and `refreshstore.Session` (`internal/auth/refreshstore/store.go`)
  carry Login, PrincipalID, Groups, ClientID, AuthMethod and Resource. They
  carry no tenant. The Postgres table `oauth_refresh_tokens`
  (`refreshstore/postgres.go`) has `family_id`, `principal_id`,
  `auth_method` and `resource` columns, added through inline
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
- `RefreshAccessTokenForResource` decides every refusal inside
  `RefreshStore.RotateIf`'s `accept` callback, before the successor is
  written. The comment there records the 2026-10-17 incident in which a
  post-rotation refusal revoked a family. A downgrade revokes the family
  (`RevokeFamily`). `RevokePrincipalSessions` -> `RevokePrincipal`.
- Tokens: `jwtPayload` (oauth_server.go ~2071) has iss, sub, aud (an
  `audience` list), pid, client_id, groups, iat, exp and jti. It has no tenant
  claim. `verifyAccessToken` classifies `aud`: a support audience wins over
  an API entry in the same `aud` (fail closed). `User.IsSupportAudience()`
  is confined by `internal/api/support_audience_gate.go`.
- Resources: `internal/auth/oauth_resource.go` `ResolveResource` /
  `FlowResource` / `audienceForResource`. Today only the API and
  `SupportResource` exist. The Glovo audience comes from slice 1 (#953
  design section 1: `OAuthServer.GlovoResource`, `GLOVO_MCP_RESOURCE`,
  `User.IsGlovoAudience()`, a Glovo audience gate).
- Membership: principal mode (`TENANT_AUTHZ_MODE=principal`,
  `OAuthServer.PrincipalMode`). `api.PrincipalMembershipReader`
  (`internal/api/tenant_authz_shadow.go`) is implemented by
  `gitops.Reader.TryNamespacesForPrincipal` / `MemberRolesForPrincipal`
  (`internal/gitops/principal_membership.go`) and used by
  `checkTenantRoleByPrincipal` (`internal/api/tenant_role.go`). A read
  failure is 503 there, never an answer.
- Since mctl-api#977 (merged `a9ca5814`): `internal/glovo` (`glovo.Code`,
  `glovo.Error`, `glovo.WriteError`, closed `glovo.Default` gate),
  `OAuthServer.GlovoResource` (`GLOVO_MCP_RESOURCE`), `User.IsGlovoAudience()`,
  `glovoAudienceGate` with an empty route list, and `ResolveResource`
  returning `ErrGlovoNotReady` for the Glovo resource unconditionally. There
  is still no `X-Mctl-Selected-Tenant` header, no `ambiguous_tenant` code and
  no personal-tenant marker. Authorization codes are held in memory
  (`OAuthServer.codes`, a `sync.Map`), not in Postgres. The only `X-Mctl-*` headers are `X-Mctl-Surface`,
  `X-Mctl-Agent-Scope-Shadow` and `X-Mctl-Audit-Parent`.
- The closest precedent for a tenant-bound credential is the `support` agent
  scope (`docs/support-agent-scope.md`, `internal/auth/agent_scope.go`). The
  tenant is stored server-side on the token row, and every check compares
  against it rather than against caller input.

Deployed state checked:
- `mcp__mctl__mctl_get_service_config(team=admins, service=mctl-api)`
  returned "service not found". mctl-api is not a catalogue service in this
  view, so its deployed env (whether `GLOVO_MCP_RESOURCE` or
  `TENANT_AUTHZ_MODE` is set) could **not be observed**.
- `$MCTL_GITOPS_ROOT/services/` holds admins, karabu, labs and namax66. No
  mctl-api values file is present and no Glovo service exists (grep
  `glovo` found only agents-state proposals).
- `$MCTL_GITOPS_ROOT/tenants/` holds admins, commerce-proof, erpact, karabu,
  labs, mctl and namax66. `tenants/labs/values.yaml` uses
  `members[].principalId` + `role`, which confirms principal-keyed
  membership data exists.
- `helm/values.yaml` in the clone: `TENANT_AUTHZ_MODE: ""` (chart default).
  `docs/tenant-roles.md` states principal mode is the current mode in
  production. This is not verified against the deployed env (see gap above).
- `agents-state/mctl-api/proposals/issue-953-.../design.md` (status
  needs-triage) is the parent design. Its "AMEND 2026-11-08" is the contract
  this slice implements.

## AMEND 2026-11-08 — final Glovo OAuth opening and tenant selection contract

The default `GLOVO_NON_SELECTABLE_TENANTS=admins,labs` below is superseded by **`admins` only** (or other explicitly reviewed system-only tenants): `labs` as a team can be chosen by an authorized, allowlisted principal after the human consent step; simply hosting the Glovo workload in `labs` never grants membership or silently selects it.

The #958 proposal deliberately installs an **unconditionally closed** Glovo resource gate (`ErrGlovoNotReady`). #960 must add a separate default-FALSE authorization-code admission guard, (amended 2026-11-09: the single name is `GLOVO_ENABLED`, see the joint contract), with a single documented check: only if the operator explicitly enables it **and** grant store, selected-team consent, principal-mode role reader and per-principal pilot allowlist are healthy can `ResolveResource` admit this resource. Configuring `GLOVO_MCP_RESOURCE` alone still refuses `invalid_target`. Any public-facing enablement is a distinct P2 release approval; the code change and isolated tests do not enable pilot by themselves.

All teamgrant/authorization-code/refresh stores must use a demonstrably atomic Postgres transaction covering issue-code, family activation/rotation/revocation and grant records **or** a versioned recoverable saga whose intermediate states are always denied for access-token minting and scope resolution. The project MUST identify the real `refreshstore` transaction hooks/pool topology and test interleavings including crash/restart. Do not emit signed access tokens before durable grant and refresh binding commits; revoked families cannot leave an active authorization grant. If no atomic/saga implementation is proven, expose `not_ready` for Glovo scope and report a separate integration blocker.

Slice #958 and #959 must already be merged and reviewed before this implementation starts. No temporary stubs/shims duplicating their responsibilities; align to their **actual** exported APIs after merge, otherwise stop at BLOCKED_DEPENDENCY.

## Proposed solution

Everything below is inert unless `GLOVO_ENABLED=true` **and** the readiness
checks pass (Postgres refresh store, team grant store, principal-mode role
reader, allowlist reader, `GLOVO_MCP_RESOURCE` valid). Otherwise
`ResolveResource` keeps answering `ErrGlovoNotReady`, no code path creates a
grant or emits the new claims, and `glovo.Gate` stays closed.

### 0. Atomic grant binding (amended 2026-11-09)

- `oauth_team_grants` is created by the teamgrant package **in the
  refresh-store database** and used through the same `pgxpool` as
  `refreshstore.PostgresStore` (`OAUTH_DB_URL`, falling back as today). The
  allowlist stays on the Glovo database and is only ever *read* live; it is
  not part of any write below.
- Consent writes a `pending` grant only. A `pending` grant never passes
  `Check`. The authorization code is in memory (`OAuthServer.codes`); a crash
  after code issue loses the code and leaves only a pending grant that
  expires, which grants nothing.
- Code exchange: new `refreshstore.PostgresStore.InsertBound(ctx, rawToken,
  clientID, sess, expiresAt, bind func(pgx.Tx) error)` begins one
  transaction, inserts the refresh token, and calls `bind`, which runs
  `teamgrant.ActivateTx(tx, grantID, familyID)` (`pending -> active`, CAS on
  state, principal, client and resource). Either both commit or neither does.
  The access token is signed only after the commit returns.
- Rotation: `RotateIf`'s `accept` runs inside the existing `rotateTx`
  transaction; grant checks there use the same `tx` (`teamgrant.CheckTx`).
- Revocation: `RevokeFamily` and `revokePrincipalTx` gain the grant update
  (`active|pending -> revoked`) in their existing transaction, so no
  committed state has a revoked family with a live grant or the reverse.
- With the in-memory refresh store (`OAUTH_DB_URL` unset) the Glovo resource
  is `not_ready`: there is no transaction to bind to.

### 1. Team grant store (`internal/auth/teamgrant`)

A new package following the `refreshstore` pattern: a `Store` interface,
`PostgresStore` with inline DDL, and a `MemoryStore` for tests and
DB-less runs.

```
CREATE TABLE IF NOT EXISTS oauth_team_grants (
  grant_id          TEXT PRIMARY KEY,          -- "tgr_" + ULID
  principal_id      TEXT NOT NULL CHECK (principal_id <> ''),
  tenant            TEXT NOT NULL CHECK (tenant <> ''),
  resource          TEXT NOT NULL CHECK (resource <> ''),
  client_id         TEXT NOT NULL,
  refresh_family_id UUID NULL,
  state             TEXT NOT NULL CHECK (state IN ('pending','active','revoked')),
  created_at        TIMESTAMPTZ NOT NULL,
  expires_at        TIMESTAMPTZ NOT NULL,
  revoked_at        TIMESTAMPTZ NULL,
  revoked_reason    TEXT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS oauth_team_grants_one_active
  ON oauth_team_grants (principal_id, client_id, resource) WHERE state IN ('pending','active');
CREATE INDEX IF NOT EXISTS oauth_team_grants_family ON oauth_team_grants (refresh_family_id);
ALTER TABLE oauth_refresh_tokens ADD COLUMN IF NOT EXISTS team_grant_id TEXT NOT NULL DEFAULT '';
```

Operations:
- `Create(ctx, Grant) (Grant, error)` inserts `pending` and revokes any
  earlier pending or active grant for the same (principal, client, resource)
  with reason `superseded`, in one transaction. This is how switching teams
  replaces the old team's session.
- `Activate(ctx, grantID, familyID)` runs on code exchange.
- `Check(ctx, grantID, principalID, clientID, resource) (Grant, error)`
  returns `ErrGrantInvalid` for unknown, revoked, expired or mismatched
  grants, and a wrapped error for a store failure. The two are never conflated.
- `RevokeByFamily`, `RevokeByPrincipal` and `Revoke(grantID, reason)`.

The grant is server-owned. The client never sees anything but the opaque
`tgr_` id inside a signed JWT.

### 2. Consent step with mandatory team selection (`internal/api/oauth_consent.go`)

- `finishAuthorization`: when `c.Resource` is the Glovo flow resource, it
  always calls `requestTeamConsent`, for every client kind, not only CIMD.
- Eligible set = `TeamEligibility.Eligible(ctx, principalID)` (new small
  interface in `internal/glovo/scope`):
  `TryNamespacesForPrincipal(prn)` -> drop the non-customer/system tenants (default `admins`) and every name in
  `GLOVO_NON_SELECTABLE_TENANTS` (default `admins`) -> keep only tenants
  where `MemberRolesForPrincipal` yields a tenant role -> keep only tenants
  with an allowlist row `(tenant, prn)`. The principal must be a human
  (`KindHuman`) with a non-empty `prn_` id. Login-only and non-principal-mode
  sessions are refused with `access_denied` ("Glovo pilot requires principal
  sign-in"). If any read fails or the reader is busy, the human sees a retry
  page (503) and no grant is created. A failure never shrinks the list.
- Zero eligible -> `oauthError(..., "access_denied", ...)`, no consent entry,
  no grant.
- One or more eligible -> render the consent page. It reuses
  `renderShellPage`/`consentPage` and adds a radio group named `tenant`.
  No radio is `checked`, the submit button is disabled until a choice is
  made, and the server never relies on that client-side state. The text
  names the team being granted. `ConsentEntry` gains `TeamSelection bool`;
  `EligibleTenants` is stored for display auditing only.
- `takeConsentDecision`: for a `TeamSelection` entry, `approve` requires
  exactly one non-empty `tenant` form value (`len(r.PostForm["tenant"]) == 1`).
  It recomputes eligibility now and requires the value to be a member.
  Otherwise it returns `access_denied` (the token is already spent, so no
  retry). Then: `teamgrant.Create` (a `pending` row, inert until activated
  in the exchange transaction of section 0), followed by `issueGrant` with
  the new `authzCompletion.TeamGrantID`/`SelectedTenant`. The audit
  `oauth.grant_issued` gains `tenant` and `team_grant_id`.
- No header (`X-Mctl-Selected-Tenant` included), query parameter or
  `/oauth/authorize` parameter can pre-fill or set the choice.
  `handleOAuthAuthorize` refuses a `tenant`/`selected_tenant` parameter on a
  Glovo flow with `invalid_request`.

### 3. Code, token and refresh binding (`internal/auth/oauth_server.go`, `refreshstore`)

- `authCodeEntry`, `refreshTokenEntry` and `refreshstore.Session` gain
  `TeamGrantID string` (and `SelectedTenant` on the code entry). `IssueCode*`
  gets a variant that takes them. Existing signatures stay and pass "".
- `ExchangeCodeForResource`: if the code has a `TeamGrantID`, it calls
  `teamgrant.Check` (principal, client, resource must match) inside the
  exchange, and fails with `invalid_grant` before minting. It then calls
  `InsertBound` (section 0), which inserts the refresh token and activates
  the grant in one transaction, and mints the access token with the claims
  only after that commit. A code for the Glovo resource **without** a
  grant id is refused, so a non-consent code path can never yield a Glovo
  token.
- `jwtPayload` gains `TeamGrant string json:"tgr,omitempty"` and
  `SelectedTenant string json:"stn,omitempty"`. `issueJWTFor` sets them
  only when `aud == GlovoResource`. The `aud` of a Glovo token is that
  single value, with no API entry.
- `verifyAccessToken` / `userFromPayload`: a Glovo-audience token must have
  `len(aud) == 1`; otherwise it fails as `aud_mismatch` (multi-aud closed).
  Claims are copied into unexported `User` fields exposed as
  `User.TeamGrant() (grantID, tenant string, ok bool)`. `tgr`/`stn` on a
  non-Glovo token are ignored and never surfaced. This mirrors how
  `supportAudience` is never honoured outside its audience.
- `RefreshAccessTokenForResource`: the `accept` callback (inside `RotateIf`,
  per the 2026-10-17 lesson) adds the step: if `sess.TeamGrantID != ""`, run
  `teamgrant.Check` plus a live `TeamEligibility.Has(prn, tenant)`. If the
  grant is invalid, refuse `invalid_grant` and revoke the family. If
  eligibility is lost, refuse `invalid_grant` and revoke the grant and the
  family. On a store failure, refuse with `server_error` and spend nothing.
  `RotateIf` carries `team_grant_id` forward like `resource`. The in-memory
  path does the same before `loadAndDelete`.
- `handleOAuthToken`: on a Glovo session, a `tenant`/`selected_tenant` form
  field returns `invalid_request`. The resource mismatch refusal that exists
  today already blocks retargeting to another audience.
- Revocation coupling: `RevokeRefreshToken`, the `RevokeFamily` calls (reuse
  and downgrade) and `RevokePrincipalSessions` each call the matching
  `teamgrant.Revoke*` **before** revoking the refresh family. The grant is
  what the per-request `Check` reads, so revoking it first makes access
  tokens fail immediately. If the grant revoke fails, the operation returns
  an error: 503 `temporarily_unavailable` on `/oauth/revoke` (permitted by
  RFC 7009 section 2.2.1) and 503 on the admin path. It is never reported as
  revoked. A test pins the order.

### 4. Pure scope resolver (`internal/glovo/scope`)

```go
type GrantChecker interface{ Check(ctx context.Context, grantID, principalID, clientID, resource string) (teamgrant.Grant, error) }
type MembershipReader interface{ MemberRolesForPrincipal(tenant, principalID string) ([][]string, error) }
type AllowlistReader interface{ IsAllowlisted(ctx context.Context, tenant, principalID string) (bool, error) }

func (r *Resolver) Resolve(ctx context.Context, u *auth.User) (Scope, *Refusal)
```

The resolver takes no other input, so there is nothing a caller can forge.
Steps:
1. `u.IsGlovoAudience()`, a `KindHuman` identity, `PrincipalID() != ""`, no
   agent-run scope, no surface/relay (Telegram) identity. Otherwise `not_authorized`.
2. `u.TeamGrant()` absent -> `ambiguous_tenant`.
3. `GrantChecker.Check`: `ErrGrantInvalid` -> `ambiguous_tenant`. The grant
   tenant must equal the `stn` claim, else `ambiguous_tenant`. A store error
   -> 503 `unavailable`.
4. Tenant in the non-selectable set (`admins`, or separately reviewed system-only tenants, ...) or a personal
   scope -> `scope_unsupported`. Since there is no personal tenant in M1,
   any tenant not present as a gitops team tenant counts here.
5. `MembershipReader.MemberRolesForPrincipal(tenant, prn)` -> no tenant role
   -> `no_tenant`. Read error -> 503. Admin status is **not** consulted.
6. `AllowlistReader.IsAllowlisted(tenant, prn)` false -> `not_in_pilot`.
   Error -> 503.
7. `Scope{PrincipalID, Tenant, Role, GrantID}`.

The refusal codes are the closed M0 enum from the #953 design. No
`tenant_selection_required` is added. Slice 4's facade calls `Resolve` first
on every request, before any store or provider call. This slice adds a
middleware helper `glovo.RequireScope(resolver)` that puts the `Scope` in the
context, plus a test-only route so the behaviour is testable without slice 4.

### 5. Pilot allowlist (`internal/glovo/allowlist.go`)

The DDL and `IsAllowlisted` belong to #959 (joint contract). This slice adds
only `Add`/`Remove` and the admin routes, with an INSERT/DELETE grant for the
admin path issued by `ApplySchema`. Table shape, for reference:
`glovo_pilot_allowlist(tenant_id TEXT NOT NULL, principal_id TEXT NOT NULL
CHECK (principal_id LIKE 'prn\_%'), added_by TEXT NOT NULL, added_at
TIMESTAMPTZ NOT NULL, UNIQUE (tenant_id, principal_id))`. There is no
wildcard and no tenant-only row. Admin-only routes (`requireAdmin`):
`PUT|DELETE /api/v1/glovo/pilot/{tenant}/principals/{prn}`. No route
operates on a tenant without a principal. The tenant must exist (404 on a
definite miss, 503 on a gitops read failure). Removing a row takes effect on
the next resource request (step 6) and on the next refresh.

### 6. Wiring

`cmd/api/main.go`: read `GLOVO_ENABLED` (default `false`); build
`teamgrant.PostgresStore` on the refresh-store pool (`OAUTH_DB_URL` as
today), the #959 store on `GLOVO_DB_URL` (no `AUDIT_DB_URL` fallback for
writes), and `GLOVO_NON_SELECTABLE_TENANTS`. Construct `glovo.Gate{Open:
enabled && ready}` instead of using the build constant `glovo.Default`, and
pass the same readiness to `ResolveResource`. Startup refuses
`GLOVO_ENABLED=true` together with `TENANT_AUTHZ_MODE != principal`, an
in-memory refresh store, or a missing grant store. Docs: `docs/glovo-team-grant.md`
(flow, claims, refusal table, test matrix).

## Alternatives

1. **Infer the tenant when exactly one team is eligible** (the superseded
   #953 resolver sketch). Rejected by the owner's decision (.github#324) and the
   #953 amendment: one eligible team is not consent, and the inferred team
   changes silently when memberships change.
2. **Forward the selection as a header or tool argument**
   (`X-Mctl-Selected-Tenant`, `tenant` in MCP args) and validate it against
   membership. Rejected: the selection would be caller authority, not a
   server-owned grant. Any client could switch teams per request without
   consent, and the acceptance criteria forbid it explicitly.
3. **Tenant claim in the JWT only, with no server-side grant row.**
   Rejected: a self-contained claim cannot be revoked before the access
   token expires, cannot be tied to the refresh family, and cannot be
   superseded on a team switch. The row plus a per-request `Check` gives
   immediate revocation at the cost of one indexed lookup.

## Platform impact

- Migrations: one new table (`oauth_team_grants`) and one additive column
  (`oauth_refresh_tokens.team_grant_id DEFAULT ''`), both idempotent inline
  DDL. Existing rows mean "no team grant". The allowlist table is shared with
  slice 2 under `IF NOT EXISTS`.
- Backward compatibility: with `GLOVO_ENABLED` unset (or `GLOVO_MCP_RESOURCE` unset), nothing changes.
  The API and support audiences, non-CIMD clients and existing refresh
  sessions follow identical paths. New claim fields use `omitempty`.
  `refreshstore.Store` grows a session field, not a method. `RotateIf` must
  copy it (two replicas: an old replica during rollout would drop
  `team_grant_id` on rotate, so the new code also treats an empty grant id on
  a Glovo-resource session as `invalid_grant`, and the session must
  re-consent).
- Resources: one indexed grant lookup, one cached gitops membership read and
  one indexed allowlist lookup per Glovo request. Negligible.
- Risks and mitigations:
  - Store outage read as "no grant": typed errors, 503, and tests that
    simulate store failure at each step.
  - Grant and refresh family desync on partial failure: activation happens
    inside the exchange, and an unactivated `pending` grant never passes
    `Check`.
  - Refresh refusal spending the token (2026-10-17 class): all grant
    decisions run inside the `RotateIf` `accept` callback.
  - Audience confusion: a Glovo token must carry a single `aud`, and claims
    are honoured only on the Glovo audience.
  - Dependency on slices 1 and 2: slice 1 (#977) is merged; slice 2 (#959)
    must be merged first and task 0 stops otherwise. Nothing here is a
    mechanical merge.
