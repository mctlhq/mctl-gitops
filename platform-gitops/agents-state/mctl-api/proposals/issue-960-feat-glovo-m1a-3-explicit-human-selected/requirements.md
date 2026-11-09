# Glovo M1a slice 3: explicit human-selected team OAuth grant and per-principal pilot allowlist

## Context
Issue mctlhq/mctl-api#960 is slice 3 of 4 split out of the failed #953 ("Glovo
M1a tenant-bound synthetic connections"). The owner's final decision
(mctlhq/.github#324) is that the first pilot supports **only an explicitly
selected team tenant**. Personal scope is unsupported until #309, and there is
no `labs` fallback. Today mctl-api's OAuth authorization server
(`internal/auth/oauth_server.go`, `internal/api/oauth_consent.go`) binds a
code and a refresh session to a principal, a client and an RFC 8707 resource.
It binds them to no tenant. Tenant authority is derived from group
membership at each request, and nothing records which team a human chose to
act as.

This slice adds that missing binding. For flows targeting the Glovo resource
audience (introduced by slice 1), the first-party consent step makes the
human pick one team. The server records the choice as a server-owned team
grant tied to the principal, the client, the Glovo audience and the refresh
chain. The grant is carried as signed claims in the access token. On every
Glovo resource request, a pure scope resolver re-checks the grant, live
principal-mode membership and a per-(tenant, principal) pilot allowlist.
Membership alone never admits a principal to the pilot. A single eligible
team is never chosen on the human's behalf.

## AMEND 2026-11-08 — explicit team ≠ banning `labs`; cross-slice and token-commit gates

**Independent review P1:** the user's architecture decision [.github#324](https://github.com/mctlhq/.github/issues/324) forbids **automatically assigning `labs`** as a caller tenant, but does **not** forbid a human who is a current member of the `labs` team, individually allowlisted, from selecting `labs` explicitly. The previous default `GLOVO_NON_SELECTABLE_TENANTS=admins,labs` would make the owner's own allowlisted pilot unable to select that team. Default exclusion may cover non-customer/system tenants such as `admins`, **not `labs` merely because it hosts the service**. Explicit authenticated selection + live role + per-principal allowlist remain mandatory; no fallback ever.

**Cross-slice blocker:** #958 defines `ResolveResource` returning `ErrGlovoNotReady` for every Glovo resource even when `GLOVO_MCP_RESOURCE` is configured. This slice MUST explicitly replace that unconditional denial with a **separately disabled-by-default Glovo OAuth admission switch**, enabled only when grant store, allowlist, live membership, consent binding and token minting are ready. Presence of `GLOVO_MCP_RESOURCE` by itself never issues Glovo tokens. All tests must verify disabled-by-default and normal OAuth unchanged. The feature cannot open public routes or publish DNS before separate P2 activation.

**Transactional integrity:** the proposed team-grant, auth-code and refresh-family stores may use different transactions. Before minting any selected-team token, prove one shared atomic transaction or durable, idempotent, fail-closed commit/compensation protocol. Crash or DB outage after grant creation, code issuance, refresh rotation, grant activation or family revoke must never leave a usable token tied to an uncommitted/revoked grant, duplicate active grants or a refresh session with an invalid team. The design must cite concrete shared pool/transaction APIs or mark integration NOT READY. Do not silently assume atomicity.

**Dependency ordering:** #960 implementer MUST stop if #958 and #959 are unmerged or interfaces absent. Do not add temporary duplicate auth/store implementations to make it compile alone; separately approved slices are authority boundaries.

## User stories
- AS a pilot user in one or more teams I WANT to choose the team I am acting for when I connect an assistant to Glovo SO THAT my orders and connections are never placed in a team I did not choose.
- AS a team owner I WANT pilot access to be granted per principal, not per team SO THAT joining my team does not by itself admit someone to the pilot.
- AS a platform admin I WANT a revoked, expired or forged team selection to fail closed with the existing typed refusal SO THAT no Glovo state is touched without a valid, human-made grant.
- AS a later slice (facade/store) implementer I WANT a pure `Resolve(ctx, user)` that takes no caller-supplied tenant, owner, namespace or task queue SO THAT tenant scope cannot be injected through tool arguments or headers.

## Acceptance criteria (EARS)
- WHEN an authorization request's resource resolves to the Glovo resource audience THE SYSTEM SHALL show the first-party consent page for every client kind (CIMD, pre-registered, dynamic) and SHALL NOT issue a code without a team selection.
- WHEN the consent page is rendered for a Glovo flow THE SYSTEM SHALL list only teams where the principal holds a live principal-mode tenant role AND has a pilot allowlist row. No option is pre-selected, even when exactly one team is eligible.
- WHEN the consent decision is posted THE SYSTEM SHALL recompute eligibility server-side and accept the posted `tenant` only if it is in the recomputed eligible set. Any other value, an empty value or a repeated field SHALL be refused with no code issued.
- IF no team is eligible THEN THE SYSTEM SHALL answer the client with `access_denied` and SHALL create no grant.
- WHEN a team is selected and approved THE SYSTEM SHALL persist a team grant `(grant_id, principal_id, tenant, resource, client_id, refresh family, state, expires_at)`, bind the authorization code to it, and revoke any earlier active grant for the same (principal, client, resource).
- WHEN a Glovo-audience access token is minted (code exchange or refresh) THE SYSTEM SHALL include the signed claims `tgr` (grant id) and `stn` (selected tenant), and SHALL NOT include them in any other audience's token.
- WHEN a refresh token bound to a team grant is rotated THE SYSTEM SHALL require that grant to be active, unexpired and matching the session principal, client and resource, and SHALL carry the same grant id forward. A refresh SHALL NOT change the selected tenant.
- IF a token endpoint request for a Glovo session carries a `tenant`, `selected_tenant` or similar team parameter THEN THE SYSTEM SHALL refuse it with `invalid_request`. Switching team requires a new authorization and consent.
- WHEN a team-grant-bound refresh family is revoked (RFC 7009 revoke, reuse detection, auth-method downgrade, or `RevokePrincipalSessions`) THE SYSTEM SHALL revoke the team grant in the same operation, or fail the operation.
- WHEN the scope resolver handles a Glovo resource request THE SYSTEM SHALL, in order, require a human principal with a Glovo-only audience (exactly one `aud` entry), require `tgr` and `stn`, load the grant and match it to the token, re-read live membership of `stn`, and re-read the allowlist row `(stn, principal_id)`. Only then SHALL it return `Scope{PrincipalID, Tenant, Role, GrantID}`.
- IF the token carries no grant claims, or the grant is unknown, expired, revoked or mismatched THEN THE SYSTEM SHALL refuse with the closed M0 code `ambiguous_tenant`, before any store or provider effect.
- IF the principal no longer holds a role on the selected tenant THEN THE SYSTEM SHALL refuse with `no_tenant`. IF the allowlist row is absent THEN THE SYSTEM SHALL refuse with `not_in_pilot`. IF the selected scope is a personal scope THEN THE SYSTEM SHALL refuse with `scope_unsupported`.
- IF the grant store, membership reader or allowlist cannot be read THEN THE SYSTEM SHALL answer 503 (unknown) and SHALL NEVER treat the failure as absence or as an answer.
- WHILE resolving scope THE SYSTEM SHALL ignore every header (including `X-Mctl-Selected-Tenant`), query parameter, body field and MCP tool argument as a source of tenant, owner, namespace or task queue. It SHALL use neither admin status nor agent-run scopes nor Telegram/surface principals, and it SHALL NOT default to `labs`.
- WHILE the Glovo resource is not configured THE SYSTEM SHALL behave exactly as today for every OAuth flow, and SHALL NOT create team grants.
- WHEN an admin adds a pilot allowlist entry THE SYSTEM SHALL require both a tenant and a non-empty principal id. A tenant-wide or wildcard entry SHALL NOT be possible.

## Acceptance criteria added by the 2026-11-09 joint AMEND

- WHILE `GLOVO_ENABLED` is not `true`, or any readiness dependency (Postgres refresh store, team grant store, principal-mode role reader, allowlist reader, valid `GLOVO_MCP_RESOURCE`) is missing or unhealthy, THE SYSTEM SHALL keep refusing the Glovo resource as not ready and SHALL keep `glovo.Gate` closed.
- WHEN a Glovo authorization code is exchanged THE SYSTEM SHALL insert the refresh token and activate the team grant in one database transaction, and SHALL sign the access token only after that transaction commits.
- WHEN a refresh family or a principal's sessions are revoked THE SYSTEM SHALL revoke the bound team grants in the same transaction.
- THE SYSTEM SHALL use the joint contract's names, refusal enum, status mapping and `{"error","error_description"}` refusal body (design.md).

## Out of scope
- Real Glovo login, provider basket or order mutation, provider secrets.
- Deploying the public MCP facade, or the facade routes themselves (slice 4). Defining the Glovo audience and its route gate (slice 1). Connection and installation domain tables (slice 2).
- New Temporal auth, and any system-wide OAuth default change (the default API and support audiences are untouched).
- Personal-scope Glovo access (#309).
- Approval: this proposal does not inherit the #953 grant. It needs its own reviewed digest and human implementation approval.

## Open questions
- Resolved by the 2026-11-09 amendment: #959 owns the `glovo_pilot_allowlist` DDL and grants the runtime role `SELECT, INSERT, DELETE` on it; this slice ships no DDL and no grant, only `Add`/`Remove` and the admin routes.
- Exact identifiers from slices 1 and 2 (`OAuthServer.GlovoResource`, `User.IsGlovoAudience()`, the `internal/glovo` refusal enum) are taken from the #953 design and are not yet in the clone. The implementer codes against the closed interfaces described in design.md until they land.
- Which tenants are excluded from selection besides `admins`. Corrected: `labs` is **not** implicitly selected, but an explicitly consenting allowlisted team member may select it. `GLOVO_NON_SELECTABLE_TENANTS` defaults to `admins` only; personal/system-only scopes remain unsupported. There is no personal-tenant marker in the code today, so personal scope is refused by rule rather than detected (see design).
- Team grant lifetime. Assumption: equal to the refresh token TTL (`RefreshTokenTTL`, default 30 days), with no sliding extension. Re-consent is needed after expiry.
- The refusal code for membership removed mid-session. `no_tenant` is chosen as the existing typed refusal. The reviewer should confirm it is in the closed M0 contract.
