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

## Out of scope
- Real Glovo login, provider basket or order mutation, provider secrets.
- Deploying the public MCP facade, or the facade routes themselves (slice 4). Defining the Glovo audience and its route gate (slice 1). Connection and installation domain tables (slice 2).
- New Temporal auth, and any system-wide OAuth default change (the default API and support audiences are untouched).
- Personal-scope Glovo access (#309).
- Approval: this proposal does not inherit the #953 grant. It needs its own reviewed digest and human implementation approval.

## Open questions
- Ownership of the `glovo_pilot_allowlist` table between slice 2 and slice 3. Assumption: slice 3 ships the DDL with `CREATE TABLE IF NOT EXISTS` and the identical schema from the #953 design, so either merge order converges. If slice 2 has already merged it, slice 3 reuses slice 2's reader.
- Exact identifiers from slices 1 and 2 (`OAuthServer.GlovoResource`, `User.IsGlovoAudience()`, the `internal/glovo` refusal enum) are taken from the #953 design and are not yet in the clone. The implementer codes against the closed interfaces described in design.md until they land.
- Which tenants are excluded from selection besides `admins`. Assumption: `labs` (the Glovo service's deployment tenant, per the #953 amendment), configurable through `GLOVO_NON_SELECTABLE_TENANTS` (default `admins,labs`). There is no personal-tenant marker in the code today, so personal scope is refused by rule rather than detected (see design).
- Team grant lifetime. Assumption: equal to the refresh token TTL (`RefreshTokenTTL`, default 30 days), with no sliding extension. Re-consent is needed after expiry.
- The refusal code for membership removed mid-session. `no_tenant` is chosen as the existing typed refusal. The reviewer should confirm it is in the closed M0 contract.
