# Design: issue-849-s2a-audience-bound-access-tokens-for-sup

## Current state

Minting (`internal/auth/oauth_server.go`)

- `OAuthServer.IssueJWT(login, principalID, groups)` builds a `jwtPayload`
  with `Audience: audience{s.accessAudience()}`.
  - `accessAudience()` returns `AccessTokenAudience` (env
    `OAUTH_ACCESS_TOKEN_AUDIENCE`, wired through `JWTSigningConfig.Audience`
    in `internal/auth/jwt_keys.go` and `cmd/api/main.go:1637`) or `BaseURL`.
  - There is no per-token audience.
- The authorization code flow carries state through several structs, none
  of which has a resource:
  - `pendingAuth` / `PendingOIDCAuth`, stored by `StorePendingAuth` /
    `StorePendingOIDCAuth`, in memory or JSON in the flow store.
  - `authzCompletion` (`internal/api/oauth_consent.go`), which is turned into
    a code by `issueGrant` -> `IssueCodeWithAuthMethod`.
  - `authCodeEntry`, consumed by `ExchangeCodeWithClientAuth`.
- `ExchangeCodeWithClientAuth` calls `IssueJWT` and `issueRefreshToken`.
- Refresh sessions are `refreshstore.Session{Login, PrincipalID, Groups,
  AuthMethod}` (`internal/auth/refreshstore/store.go`).
  - `PostgresStore` persists them in `oauth_refresh_tokens`. The
    `auth_method` column was added with
    `ALTER TABLE ... ADD COLUMN IF NOT EXISTS auth_method TEXT NOT NULL DEFAULT ''`
    (`refreshstore/postgres.go:61`). That is the precedent this design
    follows.
  - The in-memory fallback is `refreshTokenEntry`.
  - `RefreshAccessTokenWithClientAuth` rotates through
    `RefreshStore.RotateIf`, which carries the session forward, and mints
    with `IssueJWT`.

Handlers (`internal/api/oauth_handlers.go`)

- `handleOAuthAuthorize` reads `client_id`, `redirect_uri`, `response_type`,
  `state`, `code_challenge` and `code_challenge_method`.
  - It validates `client_id` and `redirect_uri` first, because of the open
    redirect concern documented in the function.
  - It reports later errors with `oauthError`.
  - It then starts GitHub (`StorePendingAuth`) or ZITADEL
    (`startZitadelAuthorize` -> `StorePendingOIDCAuth`,
    `internal/api/oauth_upstream.go:324`).
- `handleOAuthToken` reads `grant_type`, `code`, `code_verifier`,
  `redirect_uri` and `refresh_token`, and answers errors with `tokenError`.
- `resource` is read nowhere.
- `handleProtectedResourceMeta` advertises `resource = BaseURL` or
  `BaseURL + "/mcp"`. Spec-following MCP clients may therefore already send
  `resource=https://api.mctl.ai/mcp`, which today is silently ignored.

Verification

- `verifyAccessToken` checks alg, signature, `iss == BaseURL` and expiry.
  It then requires `payload.Audience.contains(s.accessAudience())`, or
  allows an aud-less HS256 token under the grace rule.
- `ValidateJWT` turns the payload into a `*User`.
- `ValidateJWT` is reached by two paths in `AuthMiddleware`
  (`internal/auth/oidc.go`):
  - the legacy chain (`oidc.go:1123`, when federation is disabled);
  - the federation registry: `localOAuthProvider.Verify`
    (`internal/auth/provider_localoauth.go`) -> `Verified{Claims}` ->
    `userFromVerified` (`oidc.go:1319`).

Routing (`internal/api/router.go`)

- One `r.Group` (lines ~487-1065) applies `opts.AuthMiddleware`, then a gate
  chain: `surfacePrincipalGate`, `agentScopeGate`, `agentPrincipalGate`,
  `usageWriterGate`, `evidenceWriterGate`, `securityProviderGate`,
  `registryPublisherGate`, `supportIncidentProducerGate`, `ciPrincipalGate`.
- That one group mounts both `/api/v1/*` and `/mcp` (POST/GET/DELETE, lines
  1062-1064). A gate placed in this group therefore covers `/mcp` too.
- The routes mctl-support relays are all in this group:
  - `GET /api/v1/whoami` (line 564);
  - `POST /work-items` (719);
  - `POST /work-items/{id}/executions` (731);
  - `POST /agent-run-tokens` (839, `MintAgentRunToken`, which allows a
    tenant-member mint for scopes with `MintByTenantMember`, the support
    scope in `internal/auth/agent_scope.go:226`).
- Existing gates such as `supportIncidentProducerGate`
  (`internal/api/handlers_support_incidents.go:29`) show the "this
  principal may reach only these routes" pattern. `agent_scope.go` uses
  anchored regexes (`getRoute`, `tenantRoute`) to match paths before chi
  resolves the route.

whoami

- `Handlers.Whoami` (`internal/api/handlers_read.go:40`) returns `id`,
  `groups`, `isAdmin`, `namespaces` and optionally `boundTenant`. It does not
  return an audience.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/mctl-support/values.yaml`:
  - mctl-support is deployed in tenant `admins`;
  - public hosts `support.mctl.ai` and `admins-mctl-support.mctl.ai`;
  - env `SUPPORT_PUBLIC_URL=https://support.mctl.ai`,
    `MCTL_API_URL=https://api.mctl.ai`,
    `MCTL_AUTH_ISSUER=https://api.mctl.ai`,
    `SUPPORT_ALLOWED_TENANTS=namax66,karabu`.
  - This confirms the support resource value `https://support.mctl.ai` and
    that mctl-support trusts api.mctl.ai as its issuer.
- `$MCTL_GITOPS_ROOT/services/admins/`: no `mctl-api` directory.
- `mctl_get_service_config(team=admins, service=mctl-api)`: error
  "service not found". mctl-api is not a catalogue service.
- Taken together: mctl-api's own deployed env (`OAUTH_ACCESS_TOKEN_AUDIENCE`,
  `OAUTH_BASE_URL`) could not be observed in this run. It is recorded under
  Open questions in requirements.md and is not assumed.

## Proposed solution

### 1. Resource allowlist (`internal/auth/oauth_resource.go`, new)

- Add a field `SupportResource string` to `OAuthServer`. It is set from the
  new env `OAUTH_SUPPORT_RESOURCE` in `cmd/api/main.go`, default
  `https://support.mctl.ai`. An empty value disables it.
- Add an exported constant-style helper:

  ```go
  // ResourceKind classifies a token's resource.
  const (
      ResourceAPI     = "api"
      ResourceSupport = "support"
  )
  // ResolveResource maps an RFC 8707 resource value to the audience to
  // mint. "" -> accessAudience(). Errors with ErrInvalidTarget.
  func (s *OAuthServer) ResolveResource(values []string) (string, error)
  ```

- Rules:
  - zero values return `accessAudience()`;
  - more than one value is `ErrInvalidTarget`;
  - a value that is not an absolute `https` URI, or that has a fragment, is
    `ErrInvalidTarget`;
  - a value matching `accessAudience()`, `BaseURL` or `BaseURL+"/mcp"`
    under `normalizeIssuer` returns `accessAudience()`, so every existing
    and spec-following MCP client keeps today's `aud`;
  - a value matching `SupportResource` returns `SupportResource`;
  - anything else is `ErrInvalidTarget`.
- `var ErrInvalidTarget = errors.New("invalid_target")` is mapped by the
  handlers.

### 2. Carry the resource through the flow

- Add `Resource string` (JSON `omitempty`) to `pendingAuth`,
  `PendingOIDCAuth`, `authCodeEntry`, `refreshTokenEntry` and
  `refreshstore.Session`.
- Add a `resource` parameter to `StorePendingAuth`.
- Add the same field to `authzCompletion` in `oauth_consent.go`. Both
  callbacks (`oauth_handlers.go:340`, `oauth_upstream.go:433`) copy
  `pending.Resource` into it.
- `IssueCodeWithAuthMethod` gains a `resource` argument. `IssueCode` keeps
  its signature and passes `""`. Internal callers are updated.
- Entries already in the flow store decode with `Resource == ""`, which
  means the default. This is safe during a rolling deploy.

### 3. Mint per resource

- `IssueJWT` keeps its signature for its many callers and delegates to a new
  `issueJWTFor(login, pid, groups, aud string)`. An empty `aud` means
  `accessAudience()`.
- `ExchangeCodeWithClientAuth` gains a `requested []string` resource
  argument. The current exported names keep working through wrappers that
  pass `nil`.
- After client authentication and before `takeCode`, it calls
  `ResolveResource(requested)` when values are present. An unknown resource
  must not burn the code.
- After `takeCode` it compares the result with `entry.Resource`, normalized
  so that `""` means the default. A mismatch is `ErrInvalidTarget`.
- It mints with `entry.Resource` and stores `Resource` on the refresh
  session.
- The rule is "the token resource must equal the authorized resource". RFC
  8707 allows a subset; with a single resource per flow, a subset is the
  same thing as equality.
- `RefreshAccessTokenWithClientAuth` gains `requested []string`. Inside the
  `RotateIf` `accept` callback it refuses with `ErrInvalidTarget` when a
  requested resource resolves to anything other than `sess.Resource`.
  Because the check runs inside the callback, the refusal happens before the
  rotation writes, the same reasoning as the 2026-10-17 comment there.
- It then mints with `sess.Resource`. The in-memory path checks the
  resource before `loadAndDelete`, using a peek, so a refusal does not
  delete the token. It carries `entry.Resource` into the successor.
- `refreshstore.PostgresStore`:
  - migration statement
    `ALTER TABLE oauth_refresh_tokens ADD COLUMN IF NOT EXISTS resource TEXT NOT NULL DEFAULT '';`;
  - add `resource` to both `INSERT`s and to the `SELECT`s at lines ~206 and
    ~266;
  - carry it in `childSess` / `sess`.

### 4. Verify and classify

- In `verifyAccessToken`, change the audience branch:
  - if `aud` contains `accessAudience()`, the token is an API token
    (unchanged);
  - otherwise, if `SupportResource != ""` and `aud` contains it, accept the
    token and record `payload.resource = SupportResource`;
  - otherwise `aud_mismatch` as today.
- Add an unexported, non-JSON field on `jwtPayload` (`resource string`) to
  hold the result.
- A token whose `aud` names both the API and the support resource is never
  minted. If one appears, the support check wins: the token is restricted.
  That is the fail-closed reading.
- `ValidateJWT` copies the classified audience onto the `User` as a new
  unexported `tokenAudience string`, exposed as `User.TokenAudience()
  (string, bool)` and `User.IsSupportAudience() bool`.
- For the registry path, add `TokenAudience string` to `auth.Claims`
  (`federation.go`). `localOAuthProvider.Verify` sets it, and
  `userFromVerified` copies it in both its `ProviderGitHub` and
  `ProviderPrincipal` branches.
- The legacy chain gets it for free from `ValidateJWT`.
- The aud-less HS256 grace token stays an API token with audience
  `accessAudience()`.

### 5. Route confinement gate (`internal/api/support_audience_gate.go`, new)

```go
var supportAudienceRoutes = []struct{ method string; path *regexp.Regexp }{
    {GET,   ^/api/v1/whoami$},
    {POST,  ^/api/v1/work-items$},
    {POST,  ^/api/v1/work-items/[^/]+/executions$},
    {POST,  ^/api/v1/agent-run-tokens$},
}
func (h *Handlers) supportAudienceGate(next http.Handler) http.Handler
```

- If `auth.UserFromContext(r).IsSupportAudience()` and no entry matches
  `(r.Method, r.URL.Path)`, the gate answers 401.
  - The body is `{"error":"invalid_token","error_description":"this token's
    audience is https://support.mctl.ai; it is not valid for this route"}`.
  - The header is `WWW-Authenticate: Bearer error="invalid_token",
    error_description="..."`.
  - It increments `mctl_support_audience_refusals_total{route_class}`.
- It is registered in `router.go` as the first `r.Use` after
  `opts.AuthMiddleware` in the authenticated group, ahead of
  `surfacePrincipalGate`. No later gate then sees a support token on a
  route it may not reach, and `/mcp`, mounted in the same group, is
  covered.
- 401 rather than 403, as the issue requires. To this route the token is
  not a credential at all.
- The exported list is mirrored in a test that walks chi's route tree. If a
  route on the list disappears or is renamed, the test fails.

### 6. Handlers

- `handleOAuthAuthorize`: after the `redirect_uri` check, read
  `q["resource"]` and call `o.ResolveResource`. On `ErrInvalidTarget` it
  answers `oauthError(w, redirectURI, state, "invalid_target", ...)`.
  Otherwise it passes the resolved value to `StorePendingAuth` /
  `startZitadelAuthorize`, which forwards it into `PendingOIDCAuth`.
- `handleOAuthToken`: read `r.Form["resource"]` and pass it to the exchange
  and refresh functions. Map `ErrInvalidTarget` to
  `tokenError(w, "invalid_target", ...)` with HTTP 400, ahead of the
  existing `invalid_grant` mapping.
- `handleOAuthMeta`: no change to the shape. Optionally list the support
  resource in a comment, but do not invent a non-standard field.
- `Whoami`: when `user.TokenAudience()` is ok, add `"audience"` to the
  response map as a JSON array of strings (`[]string`), the token's verified
  `aud` values; never a bare string. Keep the verified `aud` list on the
  `User` next to the classification so whoami reports what was verified.

### 7. Audit

- `issueGrant`'s `oauth.grant_issued` audit entry gains a `resource`
  parameter. That way an operator can see which sign-ins produced support
  tokens.

## Alternatives

1. **Separate issuer or signing key for support tokens.** The support
   tokens would be verified by a distinct provider. This was dropped
   because:
   - mctl-support already trusts `MCTL_AUTH_ISSUER=https://api.mctl.ai`;
   - a second issuer means new JWKS and new discovery documents;
   - it would still need a route gate in mctl-api, because mctl-support
     forwards the bearer to it.
   The `aud` claim is the standard place for this binding (RFC 8707 / RFC
   9068).
2. **Have mctl-support exchange the caller's API token for a support
   token (RFC 8693).** This was dropped because it does not stop an API
   token being accepted at support.mctl.ai, which is the actual problem. It
   also adds a grant type, and the issue scopes the work to the `resource`
   parameter.
3. **Enforce the route allowlist per handler**, with each handler checking
   `IsSupportAudience`. This was dropped because a new route would be open
   by default. A single gate ahead of every other gate is fail-closed for
   routes added later, which matches the existing `supportIncidentProducerGate`
   and `usageWriterGate` pattern.
4. **Reject any unknown `resource` silently by falling back to the default
   audience.** This was dropped because the issue requires `invalid_target`.
   A silent fallback would also hand a client that asked for a narrow token
   a broad one.

## Platform impact

- Migration:
  - one additive, idempotent column on `oauth_refresh_tokens`
    (`resource TEXT NOT NULL DEFAULT ''`), run by the existing schema
    bootstrap in `refreshstore/postgres.go`;
  - existing rows read as the default API resource;
  - no backfill.
- Backward compatibility:
  - a client that sends no `resource` gets byte-identical tokens;
  - a client that sends `resource=https://api.mctl.ai` or `.../mcp` (as
    advertised by `/.well-known/oauth-protected-resource/mcp`) also gets
    today's `aud`.
  - Risk: a client sending some other, today-ignored `resource` value
    starts getting `invalid_target`.
  - Mitigation: log the refused value with `client_id` at Info and count it
    in `oauth_invalid_target_total{endpoint}`, so the rollout can be
    watched. Because the code path only reads, a client that breaks can be
    unblocked by adding its value to the API alias list.
- Rolling deploy:
  - old pods ignore the new `Resource` JSON field in flow-store entries, so
    a flow started on a new pod with a support resource and finished on an
    old pod would mint an API token;
  - mitigation: do not use the support resource until the rollout
    completes. Nothing calls it yet, because mctl-support enforcement is a
    separate issue.
  - An old pod verifying a support token refuses it (`aud_mismatch`), which
    is fail-closed.
- Security:
  - the gate runs before every other gate and covers `/mcp`;
  - the allowlist is the smallest set the issue names.
  - `POST /agent-run-tokens` stays governed by `MintAgentRunToken`'s own
    checks (member mint only for `MintByTenantMember` scopes). The gate only
    removes reach; it never adds any.
- Resource impact: negligible. There is one string comparison per request
  and one extra column.
- Out of scope: mctl-support must still start refusing whoami answers whose
  `audience` is not `https://support.mctl.ai`. Until it does, this change
  makes the hard check possible but does not enforce it at support.mctl.ai.
