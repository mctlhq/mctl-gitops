# Design: issue-67-build-browser-based-telegram-account-onb

## Current state

### Authentication and session provisioning today

`internal/oauth/server.go` — `oauth.Server` is a full RFC 6749/8414 authorization
server. The relevant happy path:

1. An external OAuth client (Claude.ai) sends the browser to
   `GET /oauth/authorize` with `client_id`, `redirect_uri`, PKCE, and scope.
2. `handleAuthorize` stores a `pendingAuth` entry (keyed by a server-generated
   `state`) and redirects the browser to Telegram's OIDC endpoint
   (`oauth.telegram.org`).
3. Telegram redirects back to `GET /oauth/telegram/callback` with `?code=&state=`.
4. `handleTelegramCallback` exchanges the code for a JWKS-verified `id_token`,
   calls `store.EnsureUserByTelegramID`, and checks for an active MTProto
   session via `store.CheckSessionValid`.
5. If a valid session exists: `issueAuthCode` mints a one-time code and
   redirects to the client's `redirect_uri` (Claude.ai).
6. If no valid session exists (and the user is in the admin or client tier):
   the callback renders `renderEnablePhone` — the first screen of the
   `enable_access` wizard — and stores an `enableSession` keyed by an
   unguessable `es` token.
7. `POST /oauth/telegram/enable_access/start`, `.../code`, `.../password`
   (in `internal/oauth/enable_access.go`) drive a background goroutine running
   `telegram.Login` (`internal/telegram/login.go`) through channels. The
   goroutine persists the session via `internal/telegram/sessionstore.go` +
   `store.SaveSession`.
8. `finishEnable` calls `issueAuthCode`, which redirects to the Claude.ai
   `redirect_uri`.

The `LoginFunc` field (`oauth.Server.loginFn`) is set to `telegram.Login` at
construction time; tests substitute a stub.

### What is missing for standalone onboarding

There is no route that a user can hit directly to start this flow without a
pre-configured Claude.ai connector. The enable_access HTML screens exist and
work; the entry point (`/telegram/connect`) does not.

Additionally, after `finishEnable` the redirect always goes to the OAuth
client's `redirect_uri` (Claude.ai). A standalone connect flow needs the
server to act as its own OAuth client, with `redirect_uri` pointing to a
server-owned success page (`/telegram/connect/done`).

### Bridge package (not used for onboarding)

`internal/bridge/` implements the Local Bridge relay for local-mode accounts.
The `Hub` routes MCP tool-call `Envelope` frames between Claude.ai and a
local daemon over a persistent websocket. This is unrelated to MTProto
authentication and is not used by the proposed connect flow.

---

## Proposed solution

### Overview

The server acts as its own OAuth 2.1 client for the connect flow. A new
handler in `internal/web/connect.go` covers two routes:

```
GET /telegram/connect        -- landing + PKCE/state generation, redirect to /oauth/authorize
GET /telegram/connect/done   -- success page; exchanges the authorization code
```

A built-in pre-registered client (`mctl_self_connect`) is added to
`oauth.Server` during `New()`. Its single registered `redirect_uri` is
`cfg.Issuer + "/telegram/connect/done"`. Because it is a pre-registered
(not implicit) client, `validateClient` accepts it without hostname-allowlist
checks.

All existing routes and handlers (`/oauth/authorize`, `/oauth/telegram/callback`,
`/oauth/telegram/enable_access/*`) are unchanged. The connect flow reuses them
exactly as Claude.ai does.

### New components

#### `internal/web/connect.go` — `ConnectServer`

```
ConnectServer struct {
    issuer      string        // cfg.Issuer; used to build authorize URL
    clientID    string        // "mctl_self_connect"
    redirectURI string        // issuer + "/telegram/connect/done"
    oauthServer *oauth.Server // to call ExchangeConnect (see below)
    clock       func() time.Time

    mu       sync.Mutex
    sessions map[string]*connectSession // keyed by state
}

connectSession struct {
    verifier  string    // PKCE code_verifier
    createdAt time.Time
}
```

**`GET /telegram/connect`** (`handleConnect`):

1. Sweep expired sessions (those older than `CodeTTL`, default 10 min).
2. Generate `verifier` = `randomToken(32)` (same helper as `oauth.Server`).
3. Compute `challenge` = base64url(SHA256(verifier)).
4. Generate `state` = `randomToken(16)`.
5. Store `{verifier, createdAt: now}` under `state`.
6. Build authorize URL:
   ```
   /oauth/authorize
     ?client_id=mctl_self_connect
     &redirect_uri=<issuer>/telegram/connect/done
     &response_type=code
     &code_challenge=<challenge>
     &code_challenge_method=S256
     &state=<state>
   ```
7. Render a minimal HTML landing page (same CSS palette as the enable_access
   pages in `internal/oauth/enable_access_page.go`) with:
   - Short explanation of what the flow does.
   - A single anchor styled as a button that links to the authorize URL.
   - No JavaScript; no external resources; strict CSP.

**`GET /telegram/connect/done`** (`handleConnectDone`):

1. Read `?code=` and `?state=` from query string.
2. If `?error=` is present: render the error page (reuse `renderEnableError`
   from `internal/oauth/enable_access_page.go`) with a back-link to
   `/telegram/connect`.
3. Look up `state` in `sessions`; if missing or expired: render error page.
4. Call `oauth.Server.ExchangeConnect` (new minimal method, see below) with
   `code`, `verifier`, `clientID`, `redirectURI` to redeem the code for an
   access token and confirm the session is live. Discard the token — it is
   not stored in the browser.
5. Delete the session from the map.
6. Render a success page with:
   - "Your Telegram account is connected."
   - A link to `https://claude.ai/settings/integrations` (configurable via
     `ConnectConfig.ClaudeAIConnectorURL`; default
     `https://claude.ai/settings/integrations`).
   - A note explaining what to paste in the Claude.ai "Add custom connector"
     dialog (the MCP URL, same as the landing page at `/`).

#### `oauth.Server.ExchangeConnect` (new exported method)

A thin wrapper around the existing `handleTokenAuthCode` logic, callable from
the connect handler without going over HTTP:

```go
func (s *Server) ExchangeConnect(ctx context.Context, code, verifier, clientID, redirectURI string) (accessToken string, err error)
```

Internally calls the same DB lookups and PKCE verification that
`handleTokenAuthCode` performs. Returns an error if the code is invalid or
expired. This avoids a self-loopback HTTP call from the connect handler to
`/oauth/token` and keeps the token exchange in-process.

Alternatively (simpler, zero new server methods): the `handleConnectDone`
handler makes a real `POST /oauth/token` HTTP call to itself (same process)
using `http.NewRequest` against the server's own listener. Both approaches are
equivalent; the in-process method is preferred to avoid a round-trip and to
keep the test surface small.

#### `oauth.New` — pre-register the built-in connect client

In `oauth.New`, after the `Server` struct is initialized, add one entry to
`s.clients`:

```go
connectClientID  := "mctl_self_connect"
connectRedirect  := cfg.Issuer + "/telegram/connect/done"
s.clients[connectClientID] = &clientReg{
    ClientID:     connectClientID,
    ClientName:   "mctl-telegram connect",
    RedirectURIs: []string{connectRedirect},
    CreatedAt:    time.Time{}, // zero — never swept
}
```

Using a zero `CreatedAt` prevents the sweeper from evicting this entry
(the sweep condition `now.Sub(c.CreatedAt) > ClientRegistrationTTL` is never
true for zero time with a positive TTL). No schema or env-var change is needed.

#### Route registration (`cmd/server/main.go`)

```go
if strings.EqualFold(cfg.AuthMode, "local-jwt") {
    connectSrv := web.NewConnectServer(web.ConnectConfig{
        Issuer:              strings.TrimRight(cfg.PublicBaseURL, "/"),
        OAuthServer:         oauthSrv, // *oauth.Server returned by registerOAuth
        CodeTTL:             cfg.OAUTHCodeTTL,
        ClaudeAIConnectorURL: "https://claude.ai/settings/integrations",
    })
    mux.Get("/telegram/connect", connectSrv.HandleConnect)
    mux.Get("/telegram/connect/done", connectSrv.HandleConnectDone)
}
```

Because both routes are `GET` and the state is passed via query string, no
CSRF token beyond the PKCE state is needed.

### Flow walkthrough

```
User browser                  mctl-telegram server             Telegram OIDC
     |                               |                               |
     | GET /telegram/connect         |                               |
     |------------------------------>|                               |
     |   302 → /oauth/authorize?...  |                               |
     |<------------------------------|                               |
     | GET /oauth/authorize          |                               |
     |------------------------------>|                               |
     |   302 → oauth.telegram.org    |                               |
     |<------------------------------|                               |
     | [Telegram login]              |                               |
     |--------------------------------------------------------->|  |
     |                               |<--------------------------|  |
     |                 GET /oauth/telegram/callback?code=&state= |  |
     |                               |                               |
     |                (if no session)|                               |
     |  [enable_access phone screen] |                               |
     |<------------------------------|                               |
     | POST /oauth/telegram/enable_access/start (phone)             |
     |------------------------------>|                               |
     |  [code screen]                |                               |
     |<------------------------------|                               |
     | POST .../code                 |                               |
     |------------------------------>|                               |
     |  [optional: password screen]  |                               |
     | POST .../password             |                               |
     |------------------------------>|                               |
     |                               |  (finishEnable)               |
     |   302 → /telegram/connect/done?code=&state=                  |
     |<------------------------------|                               |
     | GET /telegram/connect/done    |                               |
     |------------------------------>|                               |
     |  (ExchangeConnect verifies)   |                               |
     |  [success page + Claude.ai link]                             |
     |<------------------------------|                               |
```

### HTML pages

Both new pages (`/telegram/connect` and `/telegram/connect/done`) use the same
inline CSS palette already defined in `enableHead` / `enableFoot` in
`internal/oauth/enable_access_page.go`. They are rendered via
`html/template` into a pre-allocated `bytes.Buffer` before writing the
response, matching the existing `renderEnable` pattern. CSP is
`default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'`.

---

## Alternatives

### A: Bypass the OAuth layer — connect page talks directly to Telegram OIDC

The `/telegram/connect` handler performs the OIDC exchange itself (duplicating
the logic in `telegramoidc.Authenticator` and `handleTelegramCallback`).

Dropped because: this duplicates roughly 150 lines of validated OIDC exchange
and PKCE code; it bypasses the existing session-check and enable_access logic;
and it creates a second authentication path that must be kept in sync with the
main one. The added risk is not justified when the main flow can be reused
unchanged.

### B: Implicit-client allowlist expansion

Add the server's own hostname to `AllowedImplicitHosts` at construction time
so the connect flow can use any client_id with `redirect_uri=/telegram/connect/done`
without pre-registration.

Dropped because: it permanently expands the implicit-client host set to include
the server itself, which means any client — including an external attacker who
crafts an `/oauth/authorize` request with `redirect_uri=<server>/some-path` —
would pass `validateClient`. Pre-registering a named client is stricter: only
`mctl_self_connect` with exactly `{issuer}/telegram/connect/done` is accepted.

### C: Server makes a loopback HTTP call to `/oauth/token` in `handleConnectDone`

Rather than exposing `ExchangeConnect` on `oauth.Server`, `handleConnectDone`
posts a form to `http://localhost:{port}/oauth/token`.

Dropped because: it requires the handler to know the listening port (which is
not part of `ConnectServer`'s config), introduces a dependency on the HTTP
listener being available when the handler runs, and adds a round-trip for no
benefit. An in-process call is equivalent and simpler. If simplicity is valued
over API surface, using the loopback approach is acceptable — both are correct.

---

## Platform impact

### Migrations
None. The connect flow is entirely in-memory; it uses existing DB rows
(`users`, `telegram_accounts`). No schema changes.

### Backward compatibility
All existing routes (`/oauth/authorize`, `/oauth/telegram/callback`,
`/oauth/telegram/enable_access/*`) are unchanged. The built-in
`mctl_self_connect` client is added to the in-memory `clients` map only; it
does not affect dynamic registration or Claude.ai flows. The new routes are
mounted only when `AUTH_MODE=local-jwt`.

### Resource impact
Each pending connect session holds two short strings (state + verifier, ~80
bytes each) plus a timestamp. A sweep runs at the end of every
`GET /telegram/connect` call (O(n) over the session map) and discards entries
older than `CodeTTL` (default 10 min). At 100 concurrent onboarding users,
the map holds ~16 KB; this is negligible.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| State/PKCE replay: attacker captures the `?code=&state=` in the done URL | `handleConnectDone` consumes and deletes the session on first use; the code is single-use per `handleToken` logic |
| Memory growth from abandoned sessions | Sweep on every `GET /telegram/connect`; sessions expire after `CodeTTL` |
| The built-in connect client being swept | Zero `CreatedAt` is never past `ClientRegistrationTTL`; it is never swept |
| Users reaching `/telegram/connect` in shared-hmac or local-dev mode (no OAuth) | Route is mounted only under `if AUTH_MODE == local-jwt` in `cmd/server/main.go` |
| `ExchangeConnect` exposing token internals | The method mirrors existing `handleTokenAuthCode` logic; the returned token is discarded by the caller and never written to the browser |
