# Audience-bound access tokens for support.mctl.ai (RFC 8707 resource)

## Context

The OAuth authorization server in mctl-api mints every access token with a
single audience: `OAuthServer.accessAudience()` in
`internal/auth/oauth_server.go` returns `AccessTokenAudience`, or `BaseURL`
when that is unset. `/authorize` and `/token` (`internal/api/oauth_handlers.go`)
never read the RFC 8707 `resource` parameter. mctl-support admits a caller by
forwarding the presented bearer to `GET /api/v1/whoami`. So any token minted
for api.mctl.ai, such as the one an MCP client holds, is accepted by
support.mctl.ai and then relayed by it to mctl-api with full API reach.

This proposal is S2a of the tenant support agent pilot (mctlhq/.github#243),
the "hard audience check" that must exist before external tenant agents call
support.mctl.ai. A client must be able to obtain a token minted for
`https://support.mctl.ai`. That token must be usable on mctl-api only on the
few routes mctl-support calls with the caller's bearer. `whoami` must report
the token's audience, so mctl-support can refuse an api.mctl.ai token without
parsing JWTs.

## User stories

- AS an external tenant agent I WANT to request an access token for
  `https://support.mctl.ai` SO THAT I can call the support agent with a
  credential that cannot drive the rest of the platform.
- AS mctl-support I WANT `GET /api/v1/whoami` to tell me the audience of the
  bearer I was given SO THAT I can refuse tokens minted for api.mctl.ai
  without verifying JWTs myself.
- AS a platform operator I WANT a support-audience token to be refused on
  every mctl-api route except the ones mctl-support relays, `/mcp` included,
  SO THAT a leaked support token cannot be used as a general API token.
- AS an existing MCP or portal client I WANT my sign-in and refresh to
  behave exactly as today SO THAT this change breaks nothing I rely on.

## Acceptance criteria (EARS)

Resource selection

- WHEN `/authorize` is called without a `resource` parameter THE SYSTEM
  SHALL record the default API resource for the flow. The tokens it later
  mints SHALL carry the same `aud` as today (`accessAudience()`).
- WHEN `/authorize` or `/token` is called with a `resource` equal (after
  trailing-slash normalization) to `accessAudience()`, `BaseURL` or
  `BaseURL + "/mcp"` THE SYSTEM SHALL treat it as the default API resource
  and mint `aud = accessAudience()`.
- WHEN `/authorize` is called with `resource` equal to the configured
  support resource (default `https://support.mctl.ai`) THE SYSTEM SHALL
  carry that resource through the pending authorization, the upstream
  sign-in, consent and the authorization code.
- IF `/authorize` is called with a `resource` that is not on the allowlist,
  is not an absolute URI, contains a fragment, or appears more than once,
  THEN THE SYSTEM SHALL answer `invalid_target`. This happens only after
  `client_id` and `redirect_uri` are validated, and it uses the existing
  `oauthError` redirect.
- IF `/token` is called with a `resource` that is not on the allowlist or
  appears more than once THEN THE SYSTEM SHALL answer HTTP 400
  `{"error":"invalid_target"}`. It SHALL NOT consume the authorization code
  or rotate the refresh token.
- IF the `/token` authorization_code grant carries a `resource` that differs
  from the resource the code was issued for THEN THE SYSTEM SHALL answer
  `invalid_target` and SHALL NOT mint tokens.
- WHEN the `/token` authorization_code grant carries no `resource` THE
  SYSTEM SHALL mint for the resource the code was issued for.
- WHEN an access token is minted for the support resource THE SYSTEM SHALL
  set its `aud` to exactly that single resource string, never an array that
  also names the API.

Refresh

- WHEN a refresh token is issued THE SYSTEM SHALL store the resource of its
  session (`refreshstore.Session.Resource`, persisted in Postgres and in the
  in-memory store).
- WHEN a refresh token is rotated THE SYSTEM SHALL carry the resource to the
  successor and mint the new access token for that same resource.
- IF a refresh grant carries a `resource` that differs from the session's
  resource THEN THE SYSTEM SHALL answer `invalid_target` and SHALL NOT
  rotate the token.
- WHILE a refresh session predates this change (empty stored resource) THE
  SYSTEM SHALL treat it as the default API resource.

Verification and route confinement

- WHEN an access token whose `aud` contains the support resource is
  verified THE SYSTEM SHALL accept the signature, issuer and expiry exactly
  as for an API token. It SHALL mark the resulting `User` with the support
  audience.
- IF an access token's `aud` contains neither the API audience nor the
  support resource THEN THE SYSTEM SHALL refuse it as today
  (`aud_mismatch`).
- WHILE the authenticated caller holds a support-audience token THE SYSTEM
  SHALL allow only these requests:
  - `GET /api/v1/whoami`
  - `POST /api/v1/work-items`
  - `PATCH /api/v1/work-items/{id}`
  - `POST /api/v1/work-items/{id}/executions`
  - `POST /api/v1/agent-run-tokens`
- IF a support-audience token is presented on any other route, `POST`,
  `GET` and `DELETE /mcp` included, THEN THE SYSTEM SHALL answer HTTP 401
  with an `invalid_token` error. This happens before any surface, agent or
  delegation gate runs.
- WHILE a token has the API audience THE SYSTEM SHALL route it exactly as
  today.

whoami

- WHEN `GET /api/v1/whoami` is called with an access token minted by this
  server THE SYSTEM SHALL include `"audience": "<resource>"`. For a
  default-audience token that value is `accessAudience()`. For a support
  token it is the support resource.
- WHEN `GET /api/v1/whoami` is called with any other credential (GitHub PAT,
  Dex/OIDC token, static service token, agent run token) THE SYSTEM SHALL
  omit `audience`. Absent means "not a support-audience token".

Tests

- WHEN the test suite runs THE SYSTEM SHALL have tests that cover both
  directions:
  - a support token passes every allowlisted route;
  - a support token gets 401 on another route and on `/mcp`;
  - an API token reports its audience on whoami;
  - unknown resources are `invalid_target`;
  - a refresh keeps the resource.
- Each of these tests SHALL fail when the check it covers is removed.

## Out of scope

- Enforcement inside mctl-support, meaning refusing a whoami answer whose
  `audience` is not the support resource (a separate S2 issue).
- The HS256 drain (G0a D) and any change to `RejectHS256` / `RequireAud`
  behaviour.
- Advertising support.mctl.ai's own RFC 9728 protected resource metadata.
  That document is served by mctl-support, not by mctl-api.
- Downscoping by `scope`. `mctl` stays the only scope.
- Token exchange (RFC 8693) from an API token to a support token.

## Open questions

- Which exact routes mctl-support calls with the caller's bearer. The issue
  names "whoami, the support work-item execution create/update, the support
  run-token mint". `internal/api/router.go` has no route literally named
  "execution update". This proposal allowlists `POST /work-items`,
  `PATCH /work-items/{id}` and `POST /work-items/{id}/executions` plus the
  mint `POST /agent-run-tokens`. A reviewer who knows mctl-support's client
  should trim this list, for example if it uses
  `POST /work-items/{id}/execution-requests` instead or never calls
  `PATCH /work-items/{id}`. The list is one table in one file, so changing it
  is cheap.
- Whether a support token should also be allowed on
  `POST /api/v1/agent-run-tokens/self/revoke`. Today that route is called
  with a run token, not the caller's bearer, so it is left out.
- Whether the support resource should be fixed in code or configurable. This
  proposal adds `OAUTH_SUPPORT_RESOURCE`, defaulting to
  `https://support.mctl.ai`. An empty value disables the support resource,
  which then answers `invalid_target`. That gives tests and staging their
  own value, while production keeps a fixed allowlist.
- mctl-api's own deployed env (for example whether
  `OAUTH_ACCESS_TOKEN_AUDIENCE` is set in production) could not be observed
  from this run (see design.md "Deployed state checked"). The design does
  not depend on its value. Whatever `accessAudience()` returns stays the
  default.
