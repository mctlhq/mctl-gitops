# Tasks: issue-67-build-browser-based-telegram-account-onb

- [ ] 1. Pre-register the built-in `mctl_self_connect` OAuth client in `oauth.New`
  (`internal/oauth/server.go`) — DoD: `oauth.New` initializes `s.clients["mctl_self_connect"]`
  with `redirect_uri = cfg.Issuer + "/telegram/connect/done"` and a zero
  `CreatedAt` (never swept); the existing unit test `TestRegister` (or a new
  sibling) confirms `validateClient("mctl_self_connect", issuer+"/telegram/connect/done")`
  returns nil.

- [ ] 2. Add `ExchangeConnect` method to `oauth.Server` (depends on 1) —
  `internal/oauth/server.go` — DoD: `func (s *Server) ExchangeConnect(ctx context.Context, code, verifier, clientID, redirectURI string) (string, error)`
  redeems the one-time code using the same PKCE verification and scope
  resolution as `handleTokenAuthCode`; returns the access token string on
  success; existing token tests are not broken; a new table-driven test
  covers the valid-code, wrong-verifier, and expired-code cases.

- [ ] 3. Create `internal/web/connect.go` with `ConnectServer`, `ConnectConfig`,
  `HandleConnect`, and `HandleConnectDone` (depends on 1, 2) — DoD:
  - `HandleConnect` generates a PKCE pair + state server-side, stores the
    verifier under the state key (swept after `CodeTTL`), and renders an HTML
    page whose sole CTA is an anchor pointing to the correct `/oauth/authorize`
    URL; no JavaScript, strict CSP.
  - `HandleConnectDone` looks up the state, calls `s.oauthServer.ExchangeConnect`,
    deletes the session on success or error, and renders either a success page
    with a Claude.ai link or the error page from
    `internal/oauth/enable_access_page.go`.
  - Both handlers render into a `bytes.Buffer` before writing the response,
    matching the `renderEnable` pattern in `enable_access_page.go`.

- [ ] 4. Create HTML templates for the connect landing page and the success page
  (depends on 3) — `internal/web/connect.go` (inline templates, same approach
  as `enablePhoneTemplate` in `internal/oauth/enable_access_page.go`) — DoD:
  - Landing page: uses `enableHead`/`enableFoot` CSS palette; one card with
    title, one-paragraph explanation, and a styled anchor (the authorize URL).
  - Success page: "Your Telegram account is connected" heading; link to
    Claude.ai connector settings; brief instruction on pasting the MCP URL into
    Claude.ai; same CSS palette; no external resources.

- [ ] 5. Mount the connect routes in `cmd/server/main.go` (depends on 3) — DoD:
  `GET /telegram/connect` and `GET /telegram/connect/done` are mounted only
  when `AUTH_MODE=local-jwt`; `registerOAuth` is refactored to return
  `*oauth.Server` so `main` can pass it to `web.NewConnectServer`; `go vet`
  and `golangci-lint` pass; the server starts successfully in local-dev mode
  (routes absent) and in a local-jwt smoke test (routes respond to GET).

- [ ] 6. Integration smoke test (depends on 3, 4, 5) — DoD: a new
  `TestConnectFlow` in `internal/web/connect_test.go` (or
  `internal/oauth/server_chi_test.go`) uses `httptest.NewServer`, a stub
  `loginFn` (same seam as `server_test.go`), and a stub `telegramoidc.Authenticator`
  to exercise the full round-trip: `GET /telegram/connect` → follow authorize
  redirect → simulate Telegram callback → simulate enable_access start/code →
  `GET /telegram/connect/done` → assert 200 and "connected" text in body.

## Tests

- [ ] T1. `internal/oauth/server_test.go` — add case for `validateClient` accepting
  `mctl_self_connect` with the exact connect redirect_uri and rejecting it with
  any other redirect_uri.
- [ ] T2. `internal/oauth/server_test.go` — add table-driven tests for
  `ExchangeConnect`: valid flow succeeds; wrong `code_verifier` returns
  `invalid_grant`; expired code returns `invalid_grant`; unknown code returns
  `invalid_grant`.
- [ ] T3. `internal/web/connect_test.go` — unit tests for `ConnectServer`:
  `HandleConnect` generates distinct PKCE pairs on successive calls;
  `HandleConnectDone` with unknown state renders the error page (HTTP 400);
  expired session is swept and also renders the error page.
- [ ] T4. `internal/web/connect_test.go` — CSP header is present on both handlers'
  responses; no `script-src` without a nonce (the connect pages have no inline
  script).
- [ ] T5. `cmd/server/main.go` smoke — `GET /telegram/connect` returns 404 when
  `AUTH_MODE=local-dev` (route not mounted).

## Rollback

The connect routes are mounted conditionally behind
`if AUTH_MODE == local-jwt`. Rolling back is a two-step:

1. Remove the `mux.Get("/telegram/connect", ...)` and
   `mux.Get("/telegram/connect/done", ...)` calls from `cmd/server/main.go`
   and delete `internal/web/connect.go`. The main `oauth.Server` and all
   existing routes are unaffected.

2. Remove the `mctl_self_connect` pre-registration from `oauth.New` in
   `internal/oauth/server.go`. This has no effect on Claude.ai flows because
   Claude.ai never uses that `client_id`.

No database migration is involved so there is nothing to revert on the data
plane. The rollback is safe at any point after deployment because the connect
flow is stateless across restarts (pending sessions are in-memory) and no
external system holds a reference to `/telegram/connect/done` as an OAuth
`redirect_uri` except the built-in client, which is removed with the code.
