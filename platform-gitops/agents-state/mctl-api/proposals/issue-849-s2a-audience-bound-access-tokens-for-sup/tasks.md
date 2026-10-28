# Tasks: issue-849-s2a-audience-bound-access-tokens-for-sup

- [ ] 1. Add the resource allowlist in `internal/auth/oauth_resource.go`:
  `OAuthServer.SupportResource`, `ResolveResource(values []string)` and
  `ErrInvalidTarget`. Wire `OAUTH_SUPPORT_RESOURCE` (default
  `https://support.mctl.ai`, empty disables it) in `cmd/api/main.go` and the
  helm values/env docs.
  - DoD: unit tests cover the cases below; `go vet` and `golangci-lint` are
    clean.
    - empty input returns `accessAudience()`;
    - `BaseURL`, `BaseURL/` and `BaseURL/mcp` return `accessAudience()`;
    - the support resource returns itself;
    - an unknown resource, two values, a fragment and a non-https value each
      return `ErrInvalidTarget`.
- [ ] 2. Carry the resource through the flow (depends on 1).
  - Add `Resource` to `pendingAuth`, `PendingOIDCAuth`, `authCodeEntry`,
    `refreshTokenEntry` and `api.authzCompletion`.
  - Thread it through `StorePendingAuth`, `startZitadelAuthorize`, both
    callbacks (`oauth_handlers.go`, `oauth_upstream.go`), `issueGrant` and
    `IssueCodeWithAuthMethod`. `IssueCode` keeps its signature.
  - Add `resource` to the `oauth.grant_issued` audit parameters.
  - DoD: a code issued after a support-resource `/authorize` carries
    `Resource` through both the in-memory and the flow-store paths.
- [ ] 3. Mint per resource (depends on 2).
  - Add `issueJWTFor(..., aud)`; `IssueJWT` delegates with `""`.
  - Add the `requested []string` parameter to `ExchangeCodeWithClientAuth`
    and `RefreshAccessTokenWithClientAuth`, keeping the existing exported
    wrappers.
  - Resolve before `takeCode`, so a bad resource does not burn the code.
    Compare against `entry.Resource` after it.
  - On refresh, refuse inside the `RotateIf` accept callback, and in the
    in-memory path before deleting the token.
  - DoD: a support code yields `aud="https://support.mctl.ai"`, and its
    refresh yields the same `aud`.
- [ ] 4. Persist the session resource in `refreshstore` (depends on 3).
  - Add `Session.Resource`.
  - Add the migration
    `ALTER TABLE oauth_refresh_tokens ADD COLUMN IF NOT EXISTS resource TEXT NOT NULL DEFAULT ''`.
  - Add the column to both INSERTs and to the parent/child SELECTs in
    `RotateIf`. Rotation carries it forward.
  - DoD: `refreshstore/postgres_test.go` round-trips `Resource` through
    Insert, RotateIf and the in-flight-rotation grace child. Existing rows
    read `""`.
- [ ] 5. Verify and classify (depends on 1).
  - In `verifyAccessToken`, accept `aud` containing `SupportResource` and
    record the classification. A support entry wins over an API entry in the
    same `aud`.
  - `ValidateJWT` sets `User.tokenAudience`. Add `User.TokenAudience()` and
    `User.IsSupportAudience()`.
  - Add `Claims.TokenAudience`, set in `localOAuthProvider.Verify` and copied
    in both branches of `userFromVerified`.
  - DoD: both the legacy chain (`MCTL_FEDERATION_DISABLED`) and the registry
    path yield a `User` whose `IsSupportAudience()` is true for a support
    token. An unknown `aud` is still refused.
- [ ] 6. Handlers (depends on 3).
  - In `handleOAuthAuthorize`, read `resource` after the `redirect_uri`
    check and answer `invalid_target` through `oauthError`.
  - In `handleOAuthToken`, read `r.Form["resource"]` and map
    `ErrInvalidTarget` to 400 `invalid_target`.
  - Add the `oauth_invalid_target_total{endpoint}` counter and an Info log
    with `client_id`.
  - DoD: handler tests pass. The existing OAuth handler tests pass
    unchanged.
- [ ] 7. Route confinement gate (depends on 5). Add
  `internal/api/support_audience_gate.go`.
  - It holds the `supportAudienceRoutes` table and `supportAudienceGate`.
  - The gate answers 401 `invalid_token` with `WWW-Authenticate` and
    increments `mctl_support_audience_refusals_total`.
  - Register it in `internal/api/router.go` as the first `r.Use` after
    `opts.AuthMiddleware` in the authenticated group, which also mounts
    `/mcp`.
  - DoD: a support token is refused on every route except the four on the
    allowlist; `PATCH /api/v1/work-items/{id}` is refused.
- [ ] 8. whoami reports the audience (depends on 5). In `Handlers.Whoami`
  (`handlers_read.go`), add `"audience"` (a JSON array of strings) when `user.TokenAudience()` is
  ok.
  - DoD: an API token reports `[accessAudience()]`, a support token reports
    `["https://support.mctl.ai"]`, and a GitHub PAT or run token omits the field.
- [ ] 9. Docs. Describe the `resource` parameter, `invalid_target`, the
  support allowlist and the whoami `audience` field in the repo's OAuth/auth
  docs, and note `OAUTH_SUPPORT_RESOURCE` in the env reference.
  - DoD: docs merged in the same PR.

## Tests

Each test must go red when the check it covers is removed. The PR
description lists, for each test, the line whose deletion turns it red.

- [ ] T1. `/authorize` with `resource=https://evil.example` redirects with
  `error=invalid_target`. With no `resource`, and with
  `resource=<BaseURL>/mcp`, it proceeds as today.
- [ ] T2. `/token` (authorization_code) with an unknown `resource` gives 400
  `invalid_target`, and the same code still redeems afterwards, which shows
  it was not consumed. A `resource` that differs from the authorized one
  gives `invalid_target`.
- [ ] T3. A full flow with `resource=https://support.mctl.ai` mints a token
  whose decoded `aud` is exactly `"https://support.mctl.ai"`. With no
  resource, `aud` equals `accessAudience()`, byte for byte as before.
- [ ] T4. Refresh keeps the resource. A support session's refresh mints
  support `aud`, and so does the successor's refresh. A refresh with a
  mismatching `resource` gives `invalid_target` and the token still works.
  Run against both the in-memory store and `PostgresStore`.
- [ ] T5. The gate, positive direction. Through the real router
  (`NewRouter` with stub handlers or the e2e harness), a support token gets
  past auth on each of the four allowlisted method+path pairs: the response
  is not 401.
- [ ] T6. The gate, negative direction. A support token gets 401
  `invalid_token` on `GET /api/v1/services`,
  `POST /api/v1/operations/{name}/execute`, `PATCH /api/v1/work-items/{id}`,
  `POST /mcp` and `GET /mcp`. An
  API token on the same routes is not refused by the gate.
- [ ] T7. whoami: an API-audience token reports
  `audience == [accessAudience()]` (a JSON array), a support token reports
  `["https://support.mctl.ai"]`, the field never decodes as a bare string, and a GitHub PAT or static service user has no
  `audience` key.
- [ ] T8. Verification: a token with `aud=["https://other.example"]` is still
  refused (`aud_mismatch`). With `SupportResource=""`, a support-`aud` token
  is refused.
- [ ] T9. Route-table drift: every entry of `supportAudienceRoutes` matches a
  route registered in the chi tree, so a rename fails the test.
- [ ] T10. Both auth paths: the legacy chain (`MCTL_FEDERATION_DISABLED=true`)
  and the federation registry both mark the user `IsSupportAudience()` for a
  support token.

## Rollback

- No `resource` is sent by any current client, so reverting the PR restores
  today's behaviour.
  - Support-audience tokens already minted are then refused by the reverted
    `verifyAccessToken` (`aud_mismatch`), which is fail-closed.
  - Their refresh sessions mint API tokens again. That is acceptable because
    nothing in production uses them before mctl-support enforcement ships.
  - If that is not acceptable, revoke them by client before reverting.
- The `resource` column is additive with a default. Leave it in place on
  rollback; older code ignores it.
- Quicker partial rollback without a redeploy of code: set
  `OAUTH_SUPPORT_RESOURCE=""`. The support resource then answers
  `invalid_target` at `/authorize` and `/token`, and support-`aud` tokens are
  refused at verification.
