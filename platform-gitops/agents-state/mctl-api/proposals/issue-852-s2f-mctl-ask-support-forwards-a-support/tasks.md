# Tasks: issue-852-s2f-mctl-ask-support-forwards-a-support

- [ ] 1. Add a `jti` claim (`ID string \`json:"jti,omitempty"\``) to `jwtPayload` and factor the signing step of `issueJWTFor` into `signAccessToken(payload)` in `internal/auth/oauth_server.go`. — DoD: existing auth tests pass unchanged; a test shows that a token from `IssueJWT` has no `jti` key.
- [ ] 2. Add `internal/auth/oauth_support_token.go` with `IssueSupportToken(u *User, ttl) (SupportToken, error)`, `ErrSupportResourceDisabled`, `ErrSupportTokenRefused`, `MaxSupportTokenTTL = 15m` and the `mctl_support_token_mints_total{result}` counter (depends on 1). — DoD:
  - the claims are exactly as in design.md section 1, and the token verifies through `ValidateJWT` with `IsSupportAudience()` true;
  - every refusal case in design.md section 1 returns an error and mints nothing;
  - no refresh token or store write is made.
- [ ] 3. Add `SupportTokenMinter`, `SupportTokenAuditor`, `SupportTokenMintRecord`, `SetSupportTokenMinter` and `SetSupportTokenAuditor` to `internal/mcp/support.go`. Add `mintSupportBearer` and `supportTokenTTL` (depends on 2). — DoD: the helper returns typed tool errors `support_token_unavailable`, `support_audience_not_configured` and `support_token_refused`, and none of them contains a token.
- [ ] 4. Change `supportDo` and `supportAwait` to take an explicit `bearer`. Remove every `effectiveToken` use from support.go. Mint once per call in `toolAskSupport`, after the tenant check, and in `toolGetSupportTask`, after argument validation. Update the file-header comment and both tool descriptions (depends on 3). — DoD: `grep effectiveToken internal/mcp/support.go` is empty, and the minter check runs before any network call.
- [ ] 5. Add `audit.OperationSupportTokenMint = "support.token_mint"` and `Handlers.AuditSupportTokenMint`, then wire `opts.MCPServer.SetSupportTokenAuditor(h)` in `internal/api/router.go` next to `SetScopedCallAuditor` (depends on 3). — DoD: the entry carries `UserID`, `PrincipalID` (via `logAuditCtx`), `Tenant`, and parameters `tool`, `jti`, `aud`, `exp`, `layer=mcp`, and nothing else.
- [ ] 6. Wire `mcpSrv.SetSupportTokenMinter(oauthServer)` in `cmd/api/main.go` when `oauthServer != nil`. Leave `cmd/mcp/main.go` without a minter (depends on 3). — DoD: the in-process server mints, and stdio fails closed.
- [ ] 6a. Add `SUPPORT_TOKEN_TTL` to the support config (`SetSupportConfig` / the config parser next to `SUPPORT_ASK_WAIT`): default 11m, refused at boot outside 2m..15m, and documented in the docs/support-agent-mcp.md configuration table (depends on 3). — DoD: a config test covers the default, both bounds and an out-of-range value.
- [ ] 7. Update docs/support-agent-mcp.md ("Authority"; add a "Failure modes" note for the new errors) and docs/access-token-signing.md (internal support mint, `jti`, the effect of an empty resource, the metric) (depends on 4-6). — DoD: neither doc still says the caller's bearer is forwarded.
- [ ] 8. Update the existing tests in `internal/mcp/support_test.go` so they install a fake minter and auditor and assert the minted bearer instead of the caller token (depends on 4). — DoD: `go test ./...`, `go vet ./...` and `golangci-lint run` pass, and the MCP tool count in `server_test.go` is unchanged (no tools added).

## Tests

- [ ] T1. `internal/auth`: `IssueSupportToken` for a principal-mode GitHub user gives `aud` == `SupportResource` (single string), `pid` == the caller's pid, `exp - iat` <= the requested ttl, a non-empty `jti` that differs on every call, and no groups. `ValidateJWT` returns `IsSupportAudience()` true. Run it under both HS256 and EdDSA.
- [ ] T2. `internal/auth`: `SupportResource=""` gives `ErrSupportResourceDisabled`. Each of the following gives `ErrSupportTokenRefused`: an agent user (scoped, unscoped, and a `BoundTenant` scope with a tenant), a service user, a surface user, a relayed user, an unresolved principal, and an empty pid. A ttl of 0 or above 15m is refused. A disabled principal (fake `TokenPrincipalChecker`) is refused. No refresh session exists after any call.
- [ ] T3. `internal/auth`: a token from `IssueJWT` has no `jti` key (byte-compatibility guard).
- [ ] T4. `internal/mcp` (handler, fake support server built from the existing fixtures, real `OAuthServer` as the minter): for `mctl_ask_support` with polling, every request's bearer verifies with `aud` == the support resource, `pid` == the caller, and `exp` == mint time + `SUPPORT_TOKEN_TTL` (default 11m), so it is still valid when mctl-support finishes the execution after the tool has returned. It is the same token across the send and the polls. The caller's token string (from `auth.WithToken`) never appears in any header or body received. This fails when task 4 is reverted.
- [ ] T5. `internal/mcp`: `mctl_get_support_task` sends a minted bearer with `exp` <= now + RequestTimeout+60s and never the caller token. Error paths (a 401 from the fake server, a 5xx, a timeout) also never send or echo the caller token or the minted token in the tool result.
- [ ] T6. `internal/mcp`: with `SupportResource=""`, both tools return `support_audience_not_configured`, and the fake server records zero requests. This fails if a fallback to forwarding is added back.
- [ ] T7. `internal/mcp`: with no minter wired (the stdio-shaped `NewServer(url, token)`), both tools return `support_token_unavailable`, and the fake server records zero requests. The same holds with a minter but no auditor.
- [ ] T8. `internal/mcp`: a bound-tenant support-scope run user is refused by `agentScopeMiddleware` (the existing T12 stays green). An unscoped agent user calling `mctl_get_support_task` gets `support_token_refused` and zero requests.
- [ ] T9. `internal/api`: `AuditSupportTokenMint` writes one entry with operation `support.token_mint`, the caller's `PrincipalID`, `Tenant`, and parameters `jti`, `tool`, `aud`, `exp`. A recursive scan of the stored entry finds no substring of the minted token's signature or payload segments.
- [ ] T10. `internal/mcp`: a log-capture test (slog handler into a buffer) over T4 and T5 finds neither token in any log line.
- [ ] T12. `internal/api` (handler, real `OAuthServer`, principal mode): `GET /api/v1/whoami` with a minted support token returns `audience` == [support resource] and the same `id`, `isAdmin`, `namespaces` and `groups` as the same caller's API token. This holds although the minted token has no `groups` claim. The test fails if group resolution falls back to the token claim.
- [ ] T13. `internal/mcp`: with `SUPPORT_TOKEN_TTL` = 11m, a fake support server that answers the send and then, after the tool returned non-terminal, replays the bearer it received against a verifier at now + 10m accepts it, and rejects it at now + 12m.
- [ ] T11. Regression proof: with task 4 temporarily reverted, T4, T5 and T6 fail locally. Note this in the PR description.

## Rollback

- **Before the mctl-support enforce flip:** revert the mctl-api release with the
  usual image-tag rollback in mctl-gitops. In audit mode, mctl-support accepts
  the forwarded API token again, so the tools keep working.
- **After the enforce flip:** first revert the gitops change that set
  `SUPPORT_AUDIENCE_ENFORCEMENT=enforce`, back to audit. Then roll back
  mctl-api. Doing it in the other order breaks both tools until the flip is
  reverted.
- **Emergency disable without a rollback:** remove `SUPPORT_A2A_URL` from
  `bootstrap/templates/mctl-platform/mctl-api.yaml`. Both tools then answer "not
  configured". Do not set `OAUTH_SUPPORT_RESOURCE=""` for this purpose: it also
  disables support-audience sign-in for mctl-support's own callers.
- **After a rollback:** minted tokens expire within 15 minutes and no sessions
  exist, so nothing needs revoking.
