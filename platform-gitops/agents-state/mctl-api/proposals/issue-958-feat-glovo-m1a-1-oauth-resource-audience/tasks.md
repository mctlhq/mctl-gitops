# Tasks: issue-958-feat-glovo-m1a-1-oauth-resource-audience

The changed files are limited to:
- `internal/auth/oauth_resource.go`, `oauth_server.go`, `oidc.go`, `federation.go`, `provider_localoauth.go`, `oauth_support_token.go`;
- `internal/api/glovo_audience_gate.go`, `router.go`;
- the new `internal/glovo/*`;
- `cmd/api/main.go`;
- `docs/access-token-signing.md` and the new `docs/glovo-auth.md`;
- tests next to each.

No migrations, no MCP tools (the `server_test.go` count is unchanged), no helm or gitops changes.

- [ ] 1. Add `OAuthServer.GlovoResource`, `GlovoResourceIntended`, `ValidateGlovoResource`, and a symmetric collision check in `ValidateSupportResource` (`internal/auth/oauth_resource.go`, `oauth_server.go`). DoD: empty is valid; non-https, fragment, API-naming or support-equal values are refused.
- [ ] 2. Add `configureGlovoResource` in `cmd/api/main.go`, called after `configureSupportResource`, with boot refused on error (depends on 1). DoD: unset or empty leaves the field `""`; an invalid value exits at boot; there is a unit test with a fake `lookup`.
- [ ] 3. Add `ErrGlovoNotReady` (wrapping `ErrInvalidTarget`) and the Glovo branch in `ResolveResource` (depends on 1). DoD: the configured Glovo resource is never resolved to an audience; `FlowResource` propagates the error; no handler change.
- [ ] 4. Add exact-audience classification in `verifyAccessToken`, the `jwtPayload.glovo` field, and propagation through `ValidateJWT`, `Claims.GlovoAudience`, `provider_localoauth.go` and both `oidc.go` user branches. Add `User.IsGlovoAudience()` (depends on 1). DoD: a single-valued Glovo `aud` sets the flag; any multi-valued `aud` containing Glovo fails `aud_mismatch`; behaviour with `GlovoResource == ""` is unchanged.
- [ ] 5. Add `internal/api/glovo_audience_gate.go` with an empty allowlist and the `mctl_glovo_audience_refusals_total` counter, mounted before `supportAudienceGate` in `router.go`. Make `issueSupportToken` refuse Glovo-audience callers (depends on 4). DoD: a Glovo-audience user gets 401 `invalid_token` on every authenticated route.
- [ ] 6. Add package `internal/glovo`: `Code`, `Error`, `Gate{Open}`, `Default` (closed), `Authorize`, `WriteError` (depends on 4). DoD: closed returns `not_ready` for everyone; open returns `not_authorized` for every non-Glovo or unresolved, relayed, surface, agent, service, CI or support caller; there is no tenant output; there are no router references.
- [ ] 7. Reserve `GlovoWorkerUserID`, the `glovoWorker` flag and `IsGlovoWorker()` in `oidc.go`, with no constructor and no env read. DoD: grep shows no reader of `MCTL_GLOVO_WORKER_TOKEN`; no provider maps to the id.
- [ ] 8. Docs: add the `GLOVO_MCP_RESOURCE` row and section to `docs/access-token-signing.md`; create `docs/glovo-auth.md` covering the resource, exact `aud`, gate codes, the reserved worker id, the test matrix and the next slice (depends on 1-7). DoD: the docs match the code and state that this slice mints no Glovo token.
- [ ] 9. Run `go fmt`, `go vet`, `golangci-lint`, `go test ./...` (depends on 1-8). DoD: all green, existing tests unmodified.

## Tests
- [ ] T1. `ValidateGlovoResource` table: empty, `https://glovo.mctl.ai/mcp`, http, relative, fragment, equal to `BaseURL`, `BaseURL/mcp` or the audience, equal to the support resource in either configuration order.
- [ ] T2. `ResolveResource` / `FlowResource`: the Glovo URL is `ErrInvalidTarget` when unset and `ErrGlovoNotReady` (also `errors.Is(ErrInvalidTarget)`) when set; repeated `resource` values including Glovo give `ErrInvalidTarget`; API and support resolution are unchanged.
- [ ] T3. Handlers: `/oauth/authorize?resource=https://glovo.mctl.ai/mcp` redirects with `invalid_target` and stores no pending entry; `/oauth/token` code exchange and refresh with that resource give `invalid_target` and no token. Both are checked with the variable set and unset.
- [ ] T4. `verifyAccessToken` negative matrix, with Glovo configured and unconfigured: malformed (2 parts, bad base64, bad JSON), bad signature, `alg=none`, expired, wrong issuer (including `iss=https://glovo.mctl.ai`), `aud=[other]`, `aud=[glovo, api]`, `aud=[glovo, support]`, `aud=[glovo, glovo]`, and aud-less. Each is refused with the expected metric result.
- [ ] T5. `verifyAccessToken` positive: `aud=[glovo]` with `iss=BaseURL` sets `glovo` only; `IsGlovoAudience()` is true and `IsSupportAudience()` is false; the same token is refused when `GlovoResource == ""`.
- [ ] T6. Router: a test-signed Glovo-audience token gets 401 `invalid_token` on `/mcp`, `/api/v1/whoami`, every `supportAudienceRoutes` entry and a sample admin route; the refusal counter increments.
- [ ] T7. No-regression: API-audience, support-audience (support routes allowed, others 401), agent-run token (DevLoop), and Telegram surface/relay callers get the same status codes as before with `GLOVO_MCP_RESOURCE` both unset and set.
- [ ] T8. No new reachability: compare chi route walk output before and after with Glovo unset and set (no `/glovo` paths, identical set); the protected-resource metadata bodies are byte-identical; the MCP tool count is unchanged.
- [ ] T9. `glovo.Gate`: closed returns `not_ready` for every user kind including admin; open returns `not_authorized` for nil, API, support, agent, surface, relayed, service, CI, unresolved principal and admin users, and `nil` only for a Glovo-audience user with a resolved principal. `WriteError` returns 503 or 403 with the exact JSON envelope.
- [ ] T10. Worker reservation: with `MCTL_GLOVO_WORKER_TOKEN` set, presenting its value as a bearer is not a Glovo worker (refused or ordinary); a JWT with `sub=service:mctl-glovo-worker` and `X-Mctl-*` headers naming it never produce `IsGlovoWorker()`.
- [ ] T11. `issueSupportToken` refuses a Glovo-audience caller with `ErrSupportTokenRefused`.

## Rollback
The change is additive and inert while `GLOVO_MCP_RESOURCE` is unset. Rollback is a plain revert of the PR and a redeploy of the previous image, with no data or config to clean up. If a boot refusal appears because someone set an invalid `GLOVO_MCP_RESOURCE`, unset the variable and the pods start with today's behaviour.
