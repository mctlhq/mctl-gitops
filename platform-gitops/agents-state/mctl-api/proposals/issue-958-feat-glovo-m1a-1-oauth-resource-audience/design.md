# Design: issue-958-feat-glovo-m1a-1-oauth-resource-audience

## Current state

- **Resource indicators (RFC 8707).** `internal/auth/oauth_resource.go`:
  - `ResolveResource(values)` accepts either no value or one value naming this API (`namesThisAPI`: audience, `BaseURL`, `BaseURL/mcp`). It also accepts exactly one extra https resource, `OAuthServer.SupportResource`.
  - Anything else, including a repeated value, is `ErrInvalidTarget`.
  - `ValidateSupportResource` refuses a support resource that names this API or is not an absolute https URL without a fragment.
  - `FlowResource` stores `""` for the default API resource. `audienceForResource` maps a stored flow resource back to `aud`.
- **Wiring.** `cmd/api/main.go` calls `configureSupportResource` (`OAUTH_SUPPORT_RESOURCE`: unset uses `DefaultSupportResource = "https://support.mctl.ai"`, empty disables it) after signing is configured. An invalid value refuses boot.
- **Authorize and token endpoints.** In `internal/api/oauth_handlers.go`:
  - `handleOAuthAuthorize` calls `o.FlowResource(q["resource"])`. On error it emits `invalid_target` through the redirect and increments `oauthInvalidTarget{endpoint="authorize"}`.
  - `handleOAuthToken` maps `auth.ErrInvalidTarget` from `ExchangeCodeForResource` / `RefreshAccessTokenForResource` to `tokenError(w, "invalid_target", ...)`.
- **Verification.** `verifyAccessToken` in `internal/auth/oauth_server.go`:
  - Order: parse, pin alg, signature, `iss == BaseURL`, `exp`, `aud`.
  - The `aud` switch sets `payload.support` when `aud` contains `SupportResource` ("wins over an API entry in the same aud: fail closed"). Otherwise `aud` must contain `accessAudience()`.
  - Aud-less HS256 is allowed only during the grace period (`RequireAud`).
  - `ValidateJWT` copies `payload.support` into `User.supportAudience`. `localOAuthProvider` (`internal/auth/provider_localoauth.go:63`) carries it through `Claims.SupportAudience` (`internal/auth/federation.go:87-90`), and `internal/auth/oidc.go:1359,1366` rebuilds it on the `User`. `User.IsSupportAudience()` is at `internal/auth/oidc.go:1504`.
- **Audience confinement.** `internal/api/support_audience_gate.go` `supportAudienceGate` runs first in the authenticated group (`internal/api/router.go:534`, the group that also mounts `/mcp`). It answers 401 `invalid_token` to a support-audience token on any route not in `supportAudienceRoutes`, so routes added later are closed to it by default.
- **Support mint.** `internal/auth/oauth_support_token.go` `issueSupportToken` refuses agent, surface, service, relayed, unresolved and support-audience callers.
- **Machine identities.** `internal/auth/oidc.go` follows a fixed pattern for each service identity: a constant ID (for example `SupportIncidentProducerUserID = "service:mctl-support-incidents"`), a constructor, an unexported flag and an `IsX()` accessor. The token is read from an env var (for example `MCTL_EVIDENCE_WRITER_TOKEN`) and mapped in `provider_static.go` and `principal.go`.
- **Discovery.** `handleProtectedResourceMeta` (`internal/api/oauth_handlers.go:133`) serves `BaseURL` or `BaseURL/mcp` only. It is routed at `/.well-known/oauth-protected-resource[/mcp]` (`internal/api/router.go:467-468`).
- **Docs.** `docs/access-token-signing.md` documents `OAUTH_SUPPORT_RESOURCE` (env table, line 18, and a section around line 110). `docs/support-agent-mcp.md` describes the support token.
- No Glovo code exists in the repository (`grep -ri glovo` finds nothing outside the MCP server's domain text).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/*/`: listed. It has no `mctl-api` service directory. mctl-api is deployed as platform infrastructure, not as a tenant service, so its live values were **not observed** here.
- `grep -rl "GLOVO_MCP_RESOURCE|OAUTH_SUPPORT_RESOURCE"` over `services/` and `tenants/`: no match. Because the mctl-api values are not in this checkout, this does not show that the variables are absent in production.
- `services/labs/mctl-telegram/values.yaml`: `PUBLIC_BASE_URL` and `OAUTH_ISSUER_URL` are `https://tg.mctl.ai`. `tg.mctl.ai` is mctl-telegram's own issuer and host, not a route served by mctl-api. "Preserve `tg.mctl.ai` routes" therefore means: mctl-telegram's calls into mctl-api (surface principal, relay) keep working unchanged.
- Parent proposal `agents-state/mctl-api/proposals/issue-953-.../design.md` records (second-hand) that production has no `OAUTH_SUPPORT_RESOURCE` override and no Glovo env var. Not re-verified in this run.
- mctl MCP tools were not called. This run only needed code-level facts, and the deployed mctl-api config is not exposed as a tenant service.

## Proposed solution

All changes ship feature-off. With `GLOVO_MCP_RESOURCE` unset, every code path matches today's except for one added `if` per function, each guarded by `GlovoResource != ""`.

### 1. Glovo resource configuration (`internal/auth/oauth_resource.go`, `oauth_server.go`)
- Add `OAuthServer.GlovoResource string` (doc comment: RFC 8707 resource of the Glovo MCP facade; empty disables it).
- Add the constant `GlovoResourceIntended = "https://glovo.mctl.ai/mcp"`. It is documentation and test data only, never used as a default.
- Add `ValidateGlovoResource() error`. Empty is valid. A non-empty value must:
  - be an absolute https URL without a fragment;
  - not satisfy `namesThisAPI`;
  - not normalize-equal `SupportResource`.
  
  `ValidateSupportResource` also gains the symmetric check, so neither value can shadow the other in whichever order they are set.
- `cmd/api/main.go`: add `configureGlovoResource(o, lookup)`. It reads `GLOVO_MCP_RESOURCE`, trims it, sets the field and validates it, and is called right after `configureSupportResource`. Boot is refused on error, with the same `slog.Error` and `os.Exit(1)` pattern.

### 2. Never mint while gated (`ResolveResource`)
- Add a sentinel `ErrGlovoNotReady = fmt.Errorf("%w: glovo resource not ready", ErrInvalidTarget)`. It wraps `ErrInvalidTarget`, so the existing handler mapping (`errors.Is(err, auth.ErrInvalidTarget)`) and its metrics apply with no handler change.
- In `ResolveResource`, after the support match: if `GlovoResource != ""` and `n == normalizeIssuer(GlovoResource)`, return `ErrGlovoNotReady`.
- Consequences:
  - `/oauth/authorize` answers `invalid_target` before any upstream redirect, and no pending entry is stored.
  - `/oauth/token` (code exchange or refresh with `resource=`) answers `invalid_target`, and nothing is signed.
  - With the variable unset, the URL falls through to the existing final `ErrInvalidTarget`, so the observable answer is identical either way.
- No other mint path accepts an arbitrary audience: `issueSupportToken` hard-codes `SupportResource`, and the default mint uses `audienceForResource`.

### 3. Exact-audience verification (`verifyAccessToken`)
- Add an unexported `glovo bool` to `jwtPayload`, next to `support`. Verification sets it; the token never does.
- Insert a new first case in the `aud` switch:
  ```go
  case s.GlovoResource != "" && payload.Audience.contains(s.GlovoResource):
      if len(payload.Audience) != 1 {
          return fail("aud_mismatch", errors.New("JWT audience for the glovo resource must be exact"))
      }
      payload.glovo = true
  ```
  It comes first so that a mixed `[glovo, api]` or `[glovo, support]` token is refused outright instead of being treated as an API or support token. The issuer is still the existing `iss == BaseURL` check; there is no second trusted issuer.
- No new metric label: `aud_mismatch` already exists. This keeps the label cardinality unchanged.
- Propagation follows `supportAudience` field for field:
  - `User.glovoAudience` and `User.IsGlovoAudience()` in `oidc.go`;
  - `Claims.GlovoAudience` in `federation.go`;
  - set in `ValidateJWT` and `provider_localoauth.go`;
  - restored in both `oidc.go` user-construction branches (GitHub and principal).

  Only `localOAuthProvider` sets it. Federated (ZITADEL), GitHub, CI, static and agent-run credentials can never carry it.
- Because §2 means no Glovo token can be minted, this verification path is reachable only from test-signed tokens. It exists so that slice 2 has nothing auth-sensitive left to add.

### 4. Confinement gate (`internal/api/glovo_audience_gate.go`)
- Add `glovoAudienceGate`, mounted in `router.go` immediately before `supportAudienceGate` as the first middleware after `AuthMiddleware`.
- `glovoAudienceRoutes` is empty in this slice. A Glovo-audience token therefore gets 401 `invalid_token` ("this token's audience is the glovo resource; it is not valid for this route") on every authenticated route, `/mcp` included.
- Add the metric `mctl_glovo_audience_refusals_total{route_class="mcp"|"api"}`, in the same style as the support gate.
- `issueSupportToken` also refuses `u.IsGlovoAudience()`.

### 5. Typed errors and the closed feature gate (`internal/glovo`)
- New package `internal/glovo`:
  - `errors.go`: `type Code string`, `CodeNotReady = "not_ready"`, `CodeNotAuthorized = "not_authorized"`, and `type Error struct{ Code; Description string }` implementing `error`, with `errors.Is` support on the code.
  - `gate.go`:
    ```go
    type Gate struct{ Open bool }
    func (g Gate) Authorize(u *auth.User) *Error
    ```
    - If `!g.Open`, return `not_ready`.
    - Otherwise return `not_authorized` unless `u.IsGlovoAudience()` and `u.PrincipalID() != ""` and `!u.PrincipalUnresolved()`, and the caller is none of: agent, surface, service, `ViaPrincipalID() != ""`, support-audience, or CI. Admin status grants nothing.
    - `Authorize` never returns a tenant; there is no tenant inference.
    - The package-level `var Default = Gate{Open: false}`.
  - `http.go`: `WriteError(w, *Error)` maps `not_ready` to 503 (with `Retry-After` omitted) and `not_authorized` to 403, writing the JSON envelope `{"error","error_description"}`. It is the same shape as `writeJSON` but kept local, so `internal/glovo` does not import `internal/api`.
- The package is not referenced from `router.go` in this slice. It has unit tests only.

### 6. Reserved worker identity (`internal/auth/oidc.go`)
- Add `GlovoWorkerUserID = "service:mctl-glovo-worker"`, an unexported `glovoWorker bool` and `IsGlovoWorker()`.
- There is no constructor and no env var read. `MCTL_GLOVO_WORKER_TOKEN` is deliberately not read, and a test pins that setting it changes nothing.
- `provider_static.go` and `principal.go` gain no mapping. A token subject, `X-Mctl-*` header or relay link equal to `GlovoWorkerUserID` yields an ordinary user or a refusal, never `IsGlovoWorker()`.
- Audience separation for the future worker is documented: the worker will use a machine token, never an OAuth access token of any audience. It is not modelled further here.

### 7. Docs
- `docs/access-token-signing.md`: add a `GLOVO_MCP_RESOURCE` row to the env table and a short section on exact `aud`, the gate and "never minted in this slice".
- New `docs/glovo-auth.md`. It covers:
  - the resource identity and the precedence order (Glovo exact, then support, then API);
  - the error codes and their HTTP mapping;
  - the reserved worker id;
  - the test matrix;
  - the slice plan (slice 2: connection domain/store).
- No OpenAPI change: no route is added.

## Alternatives

1. **Precedence switch like support (#953 design) instead of exact `aud`.** Rejected for this slice. The issue explicitly asks for exact `aud` and multi-aud negative tests. Refusing a mixed token removes any question of which gate a `[glovo, api]` token should face.
2. **Register `/api/v1/glovo/*` routes that always return 503 `not_ready`.** Rejected. The issue requires "no new endpoint reachability by default", and a placeholder route would make OpenAPI, the portal allowlist and surface allowlists change in a slice that has no behaviour. The typed 503 mapping is still delivered and tested in `internal/glovo`.
3. **Env-switchable gate (`GLOVO_ENABLED`) now.** Rejected. An operator could flip it before tenant resolution exists, which would make Glovo-audience tokens mintable with no tenant binding. A closed constant cannot be opened by configuration. Slice 2 replaces it on purpose.
4. **Serve protected-resource metadata for the Glovo resource now.** Rejected. Discovery must stay inert, and advertising a resource that answers `invalid_target` would mislead clients.

## Platform impact

- **Migrations:** none.
- **Backward compatibility:** with `GLOVO_MCP_RESOURCE` unset (the expected deployed state), every existing request and response is unchanged. The only new boot-time refusal needs a non-empty, invalid `GLOVO_MCP_RESOURCE`, or one equal to the support resource. The symmetric support check refuses boot only if the two collide, and that cannot happen while the Glovo variable is unset.
- **DevLoop / agent-run, Support, Telegram (surface/relay):** their tokens never carry the Glovo `aud`, so the new switch case is skipped. Regression tests pin each of them.
- **Resources:** one string compare per verification and one middleware check per request. Negligible.
- **Risks and mitigations:**
  - *A Glovo token reaching existing routes.* The gate is mounted first, its allowlist is empty, and a test covers `/mcp`, `/api/v1/whoami` and every `supportAudienceRoutes` entry.
  - *Accidental minting.* `ErrGlovoNotReady` sits in the only resource resolver. Tests cover authorize, code exchange and refresh.
  - *Shadowing between resources.* Symmetric boot validation, plus tests.
  - *Metric cardinality.* No new label values on existing metrics. One new counter with 2 labels.
  - *Scope creep.* The changed file list is fixed in tasks.md. CI and a security review are required before merge.
