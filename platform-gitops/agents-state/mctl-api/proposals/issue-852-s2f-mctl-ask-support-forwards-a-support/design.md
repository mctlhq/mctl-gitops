# Design: issue-852-s2f-mctl-ask-support-forwards-a-support

## Current state

**Forwarding (`internal/mcp/support.go`)**
- `supportDo` starts with `token := s.effectiveToken(ctx)` and sets
  `Authorization: Bearer <token>`. `effectiveToken` (`internal/mcp/server.go:2605`)
  returns `auth.TokenFromContext(ctx)`, which is the caller's raw bearer, or
  `s.apiToken` in stdio mode.
- `toolAskSupport` also checks `s.effectiveToken(ctx) == ""` before the tenant
  check (`supportTenantAllowed`).
- One budget context (`cfg.Wait`) covers the send and every poll in
  `supportAwait`.
- `toolGetSupportTask` makes one `GET /tasks/{id}` under `cfg.RequestTimeout`.
- The file header and docs/support-agent-mcp.md ("Authority") both say "the
  caller's own bearer is forwarded unchanged".

**Minting (`internal/auth/oauth_server.go`)**
- `issueJWTFor(login, principalID, groups, aud)` mints with
  `ttl = s.AccessTokenTTL` (default 1h) and calls `checkMintPrincipal(pid)`.
  It signs with `signJWTAsymmetric` (EdDSA/ES256) or `signJWT` (HS256).
- `jwtPayload` has `iss, sub, aud, pid, groups, iat, exp` and **no `jti`**.
- Refresh tokens come only from `issueRefreshToken` / `RefreshStore`. A bare
  `issueJWTFor` creates no session.
- `verifyAccessToken` sets `payload.support` when `aud` contains a non-empty
  `s.SupportResource`. It answers `aud_mismatch` when the support resource is
  empty and the token names it.

**Resource and route gating**
- `internal/auth/oauth_resource.go` has `DefaultSupportResource =
  "https://support.mctl.ai"`.
- `cmd/api/main.go:209-211` sets `oauthServer.SupportResource` from
  `OAUTH_SUPPORT_RESOURCE`. An explicitly empty value disables it.
- `internal/api/support_audience_gate.go` lets a support-audience token reach
  only `GET /api/v1/whoami`, `POST /api/v1/work-items`,
  `POST /api/v1/work-items/{id}/executions` and `POST /api/v1/agent-run-tokens`.
  `/mcp` answers 401.

**Principal and identity (`internal/auth/principal.go`, `internal/auth/oidc.go`)**
- `User.PrincipalID()`, `PrincipalUnresolved()`, `ViaPrincipalID()`,
  `GitHubLogin()`, `IsAgent()`, `IsService()`.
- `User.BoundTenant()` (`internal/auth/agent.go:141`) is non-empty only for
  agent run principals with a `BoundTenant` scope.

**Agent exclusion**
- `internal/auth/agent_scope.go:139` `supportTools` does not contain either
  tool.
- `internal/mcp/agent_receipt_gate.go:162` puts `mctl_ask_support` in
  `governedAgentTools`.
- `internal/mcp/agent_scope.go` `agentScopeMiddleware` refuses tools outside a
  scope. An *unscoped* agent token passes this middleware, and today it could
  call the read tool `mctl_get_support_task`.

**Audit**
- `internal/audit/logger.go` defines `Entry` with `UserID, PrincipalID, Tenant,
  Parameters`.
- `Handlers.logAuditCtx` (`internal/api/clientmeta.go:182`) is fire-and-forget.
- The only MCP-side audit hook is `ScopedCallAuditor`, wired in
  `internal/api/router.go:1059` with `opts.MCPServer.SetScopedCallAuditor(h)`.
  It covers audited agent scopes only. A human's tool call has no audit row
  today.

**Wiring**
- `cmd/api/main.go:956-970` builds `mcpSrv := NewInProcessServer(...)` and calls
  `SetSupportConfig`.
- `cmd/mcp/main.go:24-29` (stdio) also calls `SetSupportConfig` but has no
  `OAuthServer` and no signing key.

**Tests**
- `internal/mcp/support_test.go` (T1-T26) injects a caller token through
  `auth.WithToken` and asserts it is what the fake server receives. Those
  assertions change with this fix.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml`:
  - `SUPPORT_A2A_URL: https://support.mctl.ai`. The comment says mctl-api
    "forwards the caller's own bearer".
  - `TENANT_AUTHZ_MODE: "principal"`.
  - `OAUTH_JWT_SIGNING_ALG: "EdDSA"`, `OAUTH_JWT_REQUIRE_AUD: "true"`,
    `OAUTH_JWT_ACCEPT_HS256: "false"`.
  - `replicaCount: 2`.
  - No `OAUTH_SUPPORT_RESOURCE` line, so the default `https://support.mctl.ai`
    applies.
  - No `SUPPORT_ASK_WAIT` or `OAUTH_TOKEN_TTL` line, so the defaults apply
    (60s and 1h).
- `$MCTL_GITOPS_ROOT/services/admins/mctl-support/values.yaml`:
  - `SUPPORT_ALLOWED_TENANTS: namax66,karabu`, `MCTL_API_URL: https://api.mctl.ai`,
    `SUPPORT_PUBLIC_URL: https://support.mctl.ai`.
  - No `SUPPORT_AUDIENCE_ENFORCEMENT` line. This is consistent with the audit
    mode the issue describes; the running pod's value was not observed.
- No mctl MCP tools were called. This run's tool policy is read-only, and the
  gitops files above answered the configuration questions. The live
  `support_audience_mismatch_total` and mctl-support behaviour were **not
  observed** (see Open questions in requirements.md).

## Proposed solution

### 1. auth: a dedicated, narrow mint (`internal/auth/oauth_support_token.go`, new)

```go
var ErrSupportResourceDisabled = errors.New("support_audience_not_configured")
var ErrSupportTokenRefused     = errors.New("support_token_refused")
const MaxSupportTokenTTL = 15 * time.Minute

type SupportToken struct { Token, JTI, Audience string; ExpiresAt time.Time }

func (s *OAuthServer) IssueSupportToken(u *User, ttl time.Duration) (SupportToken, error)
```

**Refusals.** Every refusal is an error, and nothing is minted:
- `s.SupportResource == ""` returns `ErrSupportResourceDisabled`.
- These callers get `ErrSupportTokenRefused`:
  - `u == nil`;
  - `u.IsAgent()`, which covers every run token, scoped or not, and so every
    bound-tenant caller;
  - `u.IsService()`, or a surface principal;
  - `u.IsSupportAudience()`;
  - `u.ViaPrincipalID() != ""`;
  - `u.PrincipalUnresolved()`;
  - `!ValidPrincipalID(u.PrincipalID())`.
- `ttl <= 0 || ttl > MaxSupportTokenTTL` returns an error.
- `checkMintPrincipal(pid)` runs as for every mint, so a disabled or merged
  principal is refused.

**Claims.**
- `iss` = `s.BaseURL`.
- `sub` = the GitHub login when `u.GitHubLogin()` is ok, otherwise the pid.
  Outside `PrincipalMode` a caller with no login is refused, because
  `userFromPayload` would reject a principal-only subject.
- `aud` = `{s.SupportResource}`.
- `pid` = `u.PrincipalID()`.
- `groups` = nil. In principal mode groups come from the principal. Outside it
  they are re-resolved from the login, and the claim is only a degraded
  fallback, so an empty claim can only narrow authority.
- `iat` = now, `exp` = now + ttl.
- `jti` = `uuid.NewString()`.

**Shared signing path.** `issueJWTFor` is refactored onto an internal
`signAccessToken(payload jwtPayload)`, so the alg and key choice stays in one
place. `jwtPayload` gains `ID string \`json:"jti,omitempty"\``. Only
`IssueSupportToken` sets it, so every other token stays byte-identical.

Nothing is written to `refreshTokens`, `RefreshStore` or `FlowStore`.

**Metric.** `mctl_support_token_mints_total{result="ok|disabled|refused|error"}`.

### 2. mcp: replace forwarding with minting (`internal/mcp/support.go`)

**New interfaces and setters.** Both are atomics, like `support` and
`scopedAuditor`.

```go
type SupportTokenMinter interface {
    IssueSupportToken(u *auth.User, ttl time.Duration) (auth.SupportToken, error)
}
type SupportTokenMintRecord struct { Tool, Tenant, JTI, Audience string; ExpiresAt time.Time }
type SupportTokenAuditor interface {
    AuditSupportTokenMint(ctx context.Context, rec SupportTokenMintRecord)
}
func (s *Server) SetSupportTokenMinter(m SupportTokenMinter)
func (s *Server) SetSupportTokenAuditor(a SupportTokenAuditor)
```

**New helper.**

```go
func (s *Server) mintSupportBearer(ctx context.Context, tool, tenant string, ttl time.Duration) (string, *mcplib.CallToolResult)
```

1. Load the minter and the auditor. If either is nil, return the tool error
   `support_token_unavailable: this server cannot mint a support-audience token`
   (stdio, or no OAuth server).
2. `u := auth.UserFromContext(ctx)`. If it is nil, return the same error.
3. Call `IssueSupportToken(u, ttl)`. Map `ErrSupportResourceDisabled` to
   `support_audience_not_configured: OAUTH_SUPPORT_RESOURCE is empty; the
   caller's token is never forwarded instead`. Map `ErrSupportTokenRefused` to
   `support_token_refused: ...`. Any other error becomes
   `support_token_unavailable: <err>`. The error text never contains a token.
4. Call `auditor.AuditSupportTokenMint(ctx, rec)` with the jti, the tenant and
   the expiry.
5. Return the token string.

**Changes to the request functions.**
- `supportDo` gains a `bearer string` parameter and stops calling
  `effectiveToken`. An empty bearer is an error. This is the structural
  guarantee: the support path has no code that reads the caller token.
- `supportAwait` gains the same `bearer` and passes it to every poll.

**Changes to the tool handlers.**
- `toolAskSupport` removes the `effectiveToken(ctx) == ""` precheck.
- After `supportTenantAllowed`, it calls `mintSupportBearer(ctx,
  "mctl_ask_support", tenant, supportTokenTTL(cfg.Wait))`. Here
  `cfg.TokenTTL`, a new support config field read from `SUPPORT_TOKEN_TTL`
  (default 11m = mctl-support's 600s task-deadline ceiling + 60s, bounded
  2m..15m, refused at boot outside that range). The token must outlive the
  whole support task, because mctl-support closes the WorkItemExecution with
  the same bearer when the task ends (`finish_task_execution`,
  `src/mctl_support/executors/lifecycle.py`), and the task keeps running after
  the tool returns non-terminal.
- The minter check is first in the handler, right after the config check. In
  stdio mode, the `apiGet("/api/v1/whoami")` fallback in `supportTenantAllowed`
  is therefore never reached with the stdio token. The function stays as-is,
  because the HTTP path always has a user in context.
- `toolGetSupportTask` mints after argument validation, with
  `ttl = min(cfg.RequestTimeout+60s, 5m)` and an empty tenant: a read keeps
  no bearer past the request.

**Unchanged.** Redirects stay unfollowed (`supportHTTPClient`). Errors from
mctl-support are reported as today. The 401 body of mctl-support never echoes
a bearer, and `shortBody` already truncates it.

**Comments and descriptions.** The file-header comment and both tool
descriptions change from "Your own token is forwarded" to "mctl-api sends the
support agent a short-lived token for your principal, valid only for the
support agent".

### 3. api: audit sink and wiring

- `internal/audit/logger.go` gets `const OperationSupportTokenMint =
  "support.token_mint"`.
- `Handlers.AuditSupportTokenMint` (in `internal/api/agent_scope_gate.go` or a
  new `support_token_audit.go`) writes this entry:

  ```
  audit.Entry{UserID: u.ID, Operation: OperationSupportTokenMint,
    RiskLevel: RiskLow, Status: "succeeded", Tenant: rec.Tenant,
    Parameters: {tool, jti, aud, exp (RFC3339), layer: "mcp"}}
  ```

  It goes through `logAuditCtx`, which fills `PrincipalID` and the client
  metadata.
- `internal/api/router.go`, next to `SetScopedCallAuditor(h)`:
  `opts.MCPServer.SetSupportTokenAuditor(h)`.
- `cmd/api/main.go`, after building `mcpSrv`:
  `if oauthServer != nil { mcpSrv.SetSupportTokenMinter(oauthServer) }`.
  Nothing changes in `cmd/mcp/main.go`, so stdio fails closed.

### 4. Agent principals

- Scoped run tokens are refused by `agentScopeMiddleware` first, exactly as
  today (`supportTools` is unchanged).
- Unscoped run tokens, which today could reach `mctl_get_support_task`, are now
  refused at the mint.
- The receipt gate is unchanged.

### 5. Docs

- docs/support-agent-mcp.md "Authority": rewrite it to cover the mint (claims,
  TTL, no refresh, never logged or returned), the fail-closed cases (empty
  resource, stdio, agents, relayed), and the audit row.
- docs/access-token-signing.md "Resource indicators and the support audience":
  add a paragraph saying the server also mints support tokens internally for
  the MCP support tools. It also documents the optional `jti` claim and states
  that `OAUTH_SUPPORT_RESOURCE=""` disables these tools.
- `docs/` gets a short note on the
  `mctl_support_token_mints_total` metric.

## Alternatives

1. **RFC 8693 token exchange endpoint at `/oauth/token`**, with the MCP tool
   calling it over loopback. This is more standard and reusable, but it adds a
   public grant type and client-authentication questions. The tool runs
   in-process with the `OAuthServer`, so a direct method call is smaller and
   exposes nothing new. Dropped for now, but it could replace the in-process
   minter later without changing the MCP side.
2. **Keep forwarding the API token and have mctl-support accept both
   audiences.** This contradicts S2b, and it leaves a token valid for the whole
   API inside mctl-support. Dropped.
3. **A service credential from mctl-api to mctl-support, carrying the principal
   in a header.** This adds authority to mctl-api: a bearer that can speak for
   any principal. It also contradicts "no service credential" (#814). Dropped.
4. **stdio: keep forwarding with a documented limitation.** After the enforce
   flip it would fail at mctl-support anyway with a less clear error, and it
   keeps a code path that sends an API token. Dropped in favour of failing
   closed, as the issue recommends.

## Platform impact

- **Migrations:** none. No schema change, because the audit row uses the
  existing `audit` table columns.
- **Backward compatibility:**
  - Against mctl-support in audit mode, both tools keep working: the token is a
    valid support-audience token, and mctl-support's
    `GET /api/v1/whoami` call with it is allowlisted.
  - Other access tokens are unchanged, because `jti` is omitempty.
  - stdio users of the support tools lose them. The issue accepts this.
  - Unscoped agent tokens lose `mctl_get_support_task`.
- **Resource impact:** one signature per tool call (EdDSA, microseconds), one
  principal check (already cached by `principalCache`), and one audit insert.
  This is negligible.
- **Risks and mitigations:**
  - *The TTL is too short for mctl-support's downstream use of the bearer.* The
    lifetime now covers mctl-support's whole task (`SUPPORT_TOKEN_TTL`, 11m
    default), checked against mctl-support's lifecycle code. If mctl-support
    ever raises its task-deadline ceiling above 14m, raise `SUPPORT_TOKEN_TTL`
    with it.
  - *Replicas with different signing keys.* Both replicas share
    `OAUTH_JWT_SIGNING_KEYS`. mctl-support verifies by calling
    `GET /api/v1/whoami` on api.mctl.ai, and either replica verifies the token.
  - *Accidentally sending the caller token.* This is removed structurally:
    `supportDo` takes an explicit bearer, and a test asserts the caller token
    never appears in any request the fake server receives.
  - *Rollout ordering.* mctl-api must be released and verified before the
    gitops enforce flip. If the order is reversed, the tools break, which is
    the issue's starting point.
