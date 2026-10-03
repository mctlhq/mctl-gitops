# Design: issue-695-connect-oauth-reused-single-use-links-sh

## Current state

### The two single-use routes

`/telegram/connect/done` is served by `ConnectServer.HandleConnectDone`
(`internal/web/connect.go:160`). It is mounted only in `local-jwt` mode at
`cmd/server/main.go:447`, next to `GET /telegram/connect`
(`main.go:446`). The pending state lives in an in-process map:

```go
mu       sync.Mutex
sessions map[string]*connectSession // keyed by state token
```

`HandleConnect` (`connect.go:118`) mints a PKCE verifier plus a 16-byte
state, stores `connectSession{verifier, createdAt}`, and embeds the state in
the `/oauth/authorize` URL. `HandleConnectDone` then does, at
`connect.go:176-186`:

```go
s.mu.Lock()
sess, ok := s.sessions[state]
if ok { delete(s.sessions, state) }
s.mu.Unlock()
if !ok || s.clock().Sub(sess.createdAt) > s.codeTTL {
    renderConnectError(w, "This connect session has expired or is unknown. Please start again.", ...)
    return
}
```

Three facts follow directly from this code and together explain the
incident:

1. The `delete` happens before any validation, so the first request wins and
   every later request with the same URL falls into the `!ok` branch. A
   refresh, the back button, a reopened tab, or a prefetch GET all land
   there.
2. `renderConnectError` (`connect.go:339`) always writes
   `http.StatusBadRequest` via `renderConnect` (`connect.go:350`). That is
   the bare 400 Cloudflare recorded.
3. There is no `slog` call on any of those branches. The only logging in the
   handler is `slog.Error("connect: ExchangeConnect failed", ...)` at
   `connect.go:190`. So `missing_state`, `unknown_state` and `expired_state`
   produce literally nothing in the pod logs — matching the issue's
   "Nothing in the pod logs."

The `?error=` branch at `connect.go:164` and the `code == "" || state == ""`
branch at `connect.go:171` are equally silent.

`/oauth/telegram/callback` is `Server.handleTelegramCallback`
(`internal/oauth/server.go:1516`), registered at `server.go:1234`. It has
the same shape, with two storage backends:

- `server.go:1519-1522`: `missing state` -> `http.Error(w, "missing state",
  400)`, no log.
- `server.go:1567-1571` (DB backend): `store.ConsumeOAuthPending` returns
  `db.ErrOAuthNotFound` -> `http.Error(w, "unknown or expired state", 400)`,
  no log.
- `server.go:1589-1605` (in-memory backend): map miss -> same 400, no log;
  and a defensive `CodeTTL` check -> `http.Error(w, "state expired", 400)`,
  no log.

Every other failure in this handler *does* log (`slog.Error` at
`server.go:1573`, `1629`, `1659`, `1742`). The 4xx state branches are the
only silent ones, which is exactly the asymmetry the issue reports.

### The cookie, and why recovery differs per route

`HandleConnectDone` sets the session cookie at `connect.go:200-207`:

```go
http.SetCookie(w, &http.Cookie{
    Name: "mctl_connect_token", Value: tok,
    Path: "/telegram/connect", HttpOnly: true,
    SameSite: http.SameSiteLaxMode,
    Secure: strings.HasPrefix(s.issuer, "https://"),
})
```

`localjwt.Provider.Authenticate` (`internal/auth/localjwt/issuer.go:274-286`)
accepts that cookie as an alternative to a `Bearer` header, which is how the
browser reaches `/telegram/connect/manage`.

The `Path=/telegram/connect` scope is the decisive constraint for this
design. `/telegram/connect/done` is inside that subtree, so the cookie *is*
delivered there and a cookie-based recovery is possible. `/oauth/telegram/callback`
is *not* inside that subtree, so the cookie is never sent to it. The issue's
proposed "redirect to manage if the browser has a valid `mctl_connect_token`
cookie" is therefore implementable only on the `web` route. The oauth
callback gets the friendly-page half of the same bullet. Widening the cookie
path to `/` to make the oauth route symmetric is rejected below.

### Login failure classification

`internal/oauth/enable_access.go` already has the machinery the issue asks
for. `shortReason(err)` (`enable_access.go:1151`) maps an error to the audit
suffix and `friendlyErr(err)` (`enable_access.go:1115`) maps it to page
copy. Call sites are `enable_access.go:808`, `830`, `931` and `1018`:

```go
s.store.LogToolCall(r.Context(), es.uid, "connect:failed:"+shortReason(lf.err), "", "error", lf.err.Error(), "")
```

`shortReason` handles `PHONE_NUMBER_INVALID`, `PHONE_CODE_INVALID`,
`PHONE_CODE_EXPIRED`, `FLOOD_WAIT_*`, the context errors, the mode conflict
and the identity mismatch. It has no arm for a rejected 2FA password and no
arm for `AUTH_RESTART`, so both fall through to `return "unknown"` at
`enable_access.go:1180` — which is precisely the `connect:failed:unknown`
the incident table shows for both 14:14:52 and 14:14:59.

The incident's `AUTH_RESTART` arrived as `send code: rpc error code 500:
AUTH_RESTART`, i.e. a `*tgerr.Error` with `Message == "AUTH_RESTART"`, which
`errors.As(err, &rpcErr)` in `shortReason` already reaches; only the `switch`
arm is missing. The rejected password arrived as `sign in with password:
invalid password` (a `gotd/td` wrapping); see the Open question in
requirements.md about its exact inner type.

On the page side, `handleEnablePassword` (`enable_access.go:958`) currently
sends a rejected password back to the *phone* step at
`enable_access.go:1025-1028` with `"The password was not accepted: " +
friendlyErr(...) + " Start again."`. Since `friendlyErr` has no password arm
either, `friendlyErr` falls through to `enable_access.go:1139-1146` and
echoes the raw truncated error string. `renderEnablePassword` already
accepts an `Error` field (`enable_access_page.go:38-48`) and is already used
that way at `enable_access.go:992-999`, so keeping the user on the password
step needs no new renderer.

### The root path

`cmd/server/main.go:409` registers only `mux.Get("/", web.Landing(...))` on
the chi router built at `main.go:377`. chi answers a `POST /` with its
default `405 Method Not Allowed` and an empty body — the bare 405 the issue
reports at 18:06 and 16:09. The MCP handler itself is mounted separately at
`main.go:627`:

```go
mux.Mount(cfg.MCPPath, web.BrowserRedirect(guarded, "/"))
```

There is already a precedent for a method/Accept-aware hint on the MCP
boundary: `web.BrowserRedirect` (`internal/web/landing.go:113`) redirects a
browser `GET /mcp` to `/`, with `isBrowserGet` (`landing.go:123`) explicitly
excluding clients that announce `application/json` or `text/event-stream`.
This proposal adds the mirror-image handler for `POST /`.

### Prefetch

`grep -rn "Sec-Purpose"` over `internal/` returns nothing: no route inspects
prefetch headers today. The Google-owned re-fetches in the incident
(66.249.x.x / 66.102.x.x) therefore hit the consuming path like any other
request.

## Proposed solution

Five narrowly-scoped changes. Nothing about state minting, PKCE, the
Telegram OIDC exchange, token issuance or scope resolution moves.

### 1. A shared reason vocabulary and one logging helper per package

Introduce a small closed set of reason constants, duplicated per package
rather than shared through a new import, because `internal/web` deliberately
avoids importing `internal/oauth` (see the comment at `connect.go:31-35`
explaining `OAuthExchanger` exists to break that cycle). The set:
`missing_state`, `unknown_state`, `expired_state`, `exchange_failed`,
`oidc_error`, `prefetch_refused`.

In `internal/web/connect.go` add:

```go
func logConnectReject(r *http.Request, reason string) {
    slog.Warn("connect: request rejected",
        "route", "/telegram/connect/done",
        "reason", reason,
        "prefetch", isPrefetch(r))
}
```

and call it on each early-return branch in `HandleConnectDone`. In
`internal/oauth/server.go` add the equivalent `logCallbackReject` for
`/oauth/telegram/callback` and call it at `server.go:1519`, `1567`, `1594`
and `1602`. The attributes are deliberately limited to route, reason and the
prefetch boolean: no `code`, no `state`, no cookie value. `internal/audit/redact.go`
is the slog handler that enforces redaction by field name; because no new
sensitive field name is introduced, that file needs no change — but the
implementer must confirm this rather than assume it, and add any new name
there if the final attribute set grows.

`exchange_failed` replaces the ad-hoc message at `connect.go:190` so the
reason vocabulary is complete; it stays at `slog.Error` (a server-side
failure), while the state branches are `slog.Warn` (client-side).

### 2. Cookie-aware recovery on `/telegram/connect/done`

`ConnectServer` gains one optional collaborator, following the existing
`OAuthExchanger` pattern of a locally-declared minimal interface:

```go
// ConnectIdentifier reports whether the request carries a credential this
// server should treat as an already-connected browser session.
type ConnectIdentifier interface {
    Authenticate(r *http.Request) (*auth.Identity, error)
}
```

`auth.Provider` as implemented by `localjwt.Provider` already satisfies this
shape (`internal/auth/localjwt/issuer.go:274`), so `ConnectConfig` gains an
`Identifier ConnectIdentifier` field and `main.go` passes the provider it
already builds. This requires hoisting the
`workerTokenRevocationCache` / `selectProvider` block (`main.go:~455-465`)
above the `local-jwt` block at `main.go:425`; `selectProvider` depends only
on `cfg`, `store` and that cache, so the move is mechanical and introduces
no new ordering hazard.

`HandleConnectDone`'s unknown/expired branch becomes:

```go
if !ok || s.clock().Sub(sess.createdAt) > s.codeTTL {
    reason := reasonUnknownState
    if ok { reason = reasonExpiredState }
    logConnectReject(r, reason)
    if s.alreadyConnected(r) {
        http.Redirect(w, r, "/telegram/connect/manage", http.StatusSeeOther)
        return
    }
    renderConnectReused(w, s.issuer+"/telegram/connect")
    return
}
```

`alreadyConnected` returns true only when `Identifier != nil` and
`Authenticate` returns a non-nil identity with a nil error. A nil
`Identifier` (any test that does not wire one, and the shared-hmac mode
where these routes are unmounted anyway) degrades to the friendly page, not
to a panic and not to a redirect.

`renderConnectReused` is a new template beside `connectErrorTemplate`
(`connect.go:326`), rendered through the existing `renderConnect` helper at
status `200`. It reuses the same `connectHead`/`connectFoot` chrome and the
same CSP string, so no CSP change is needed and
`TestHandleConnectDone_CSPPresent` (`connect_test.go:130`) keeps passing for
it. Copy: "This link was already used. Connect links work once. Start again
if you still need to connect." plus a `.btn` to `/telegram/connect`.

The `missing_state` branch (`connect.go:171`) keeps `400` and the existing
error page — a request without a `state` is malformed, not a reused link.

### 3. Friendly page on the oauth callback's reused state

`handleTelegramCallback` cannot read the connect cookie (Path scope, above),
so its three plain-text `http.Error` 4xx bodies are replaced with
`renderEnableError(w, ...)` — the renderer this same handler already uses
for the OIDC-error and missing-code branches at `server.go:1612` and
`server.go:1617`. Copy for the unknown/expired case: "That sign-in link was
already used or has expired. Close this page and start connecting again from
your MCP client." The `missing state` branch keeps `400` plus a short
message; the unknown/expired branch moves to `200` with the friendly page,
matching the decision recorded in requirements.md.

This is presentation only. The `delete` / `ConsumeOAuthPending` ordering at
`server.go:1563-1606` is untouched, and the comment there — "state is
single-use whatever the outcome, so an error redirect cannot be replayed
against a fresh code" — remains true.

### 4. Two new classification arms plus a password-step retry

In `shortReason` (`enable_access.go:1151`), inside the existing
`errors.As(err, &rpcErr)` switch, add:

```go
case rpcErr.Message == "AUTH_RESTART":
    return "auth_restart"
```

and, ahead of the final `return "unknown"`, a password arm keyed on whatever
`gotd/td v0.161.0` actually exports (see the Open question), falling back to
a case-insensitive substring check on `invalid password` /
`PASSWORD_HASH_INVALID`. Mirror both in `friendlyErr`
(`enable_access.go:1115`): "That two-step verification password was not
accepted. Check it and try again." and "Telegram ended the sign-in session.
Submit your phone number again to get a fresh code."

The routing change in `handleEnablePassword` (`enable_access.go:1015-1029`):
when `shortReason(lf.err) == "bad_password"`, re-render
`renderEnablePassword` with `Error: friendlyErr(lf.err)` (keeping
`WizardMode`/`WizardStep: 3` as the existing call at
`enable_access.go:992-999` does) instead of bouncing to
`renderEnablePhoneStep`. Every other error keeps the current phone-step
behaviour, including the `db.ErrAccountModeConflict` terminal arm at
`enable_access.go:1021`.

One caveat the implementer must respect: keeping the user on the password
step is only safe if the login goroutine can still accept another password.
`enable_access.go:184-235` shows the goroutine exits (closing `lf.done`) once
`s.loginFn` returns, and `es.flow` is then spent — so a second submit will
hit the `es.step != stepPassword || es.flow == nil` guard at
`enable_access.go:970`. The retry screen must therefore be rendered with the
step reset so the user's next submit restarts the login flow rather than
dead-ending; if that cannot be done without a new flow state, fall back to
the phone step with the *correct* `bad_password` copy and audit label, which
still satisfies every acceptance criterion except the "stay on the password
step" nicety. The audit label and the wording are the contract; the step is
the affordance.

### 5. `POST /` hint and prefetch refusal

Add beside `main.go:409`:

```go
mux.Post("/", web.RootPostHint(cfg.MCPPath))
```

`web.RootPostHint` returns `405` with `Content-Type: application/json`,
`Cache-Control: no-store`, and a JSON-RPC 2.0 error object whose message
names the correct URL, e.g. `{"jsonrpc":"2.0","id":null,"error":{"code":
-32600,"message":"This is not the MCP endpoint. Use https://<host>/mcp."}}`.
The path comes from `cfg.MCPPath` so the hint cannot drift from the mount at
`main.go:627`. `GET /` is untouched.

Prefetch refusal is a tiny shared predicate, duplicated in both packages for
the same import-cycle reason as the reason constants:

```go
func isPrefetch(r *http.Request) bool {
    if strings.Contains(strings.ToLower(r.Header.Get("Sec-Purpose")), "prefetch") { return true }
    return strings.EqualFold(strings.TrimSpace(r.Header.Get("Purpose")), "prefetch")
}
```

It is checked at the very top of `HandleConnectDone` and of
`handleTelegramCallback` — before the `s.sessions` lookup and before the
activation dispatch at `server.go:1529` — returning `204` with
`Cache-Control: no-store` and one INFO line with `reason=prefetch_refused`.
`Sec-Purpose` uses substring matching because the header is a structured
list; `Purpose` uses exact matching because the legacy Chrome header is the
bare token `prefetch`.

This is a refusal, never a fallback: a prefetch gets no page and consumes
nothing, so it cannot burn the user's state and cannot be cached in place of
the real response.

## Alternatives

**Make connect state multi-use (reference-counted or N-use).** Would fix the
user-visible symptom most directly: a refresh would just work. Dropped
because `server.go:1563-1564` documents single-use as a deliberate security
property ("state is single-use whatever the outcome, so an error redirect
cannot be replayed against a fresh code"), and because an authorization code
from Telegram is itself single-use at Telegram's end — a second exchange
would fail anyway, turning a clean "already used" page into an opaque
`exchange_failed`. Presentation is the bug; single-use is not.

**Widen the `mctl_connect_token` cookie to `Path=/` so
`/oauth/telegram/callback` can also recover to `/telegram/connect/manage`.**
Would make the two routes symmetric. Dropped because the narrow path is
load-bearing: the comment at `connect.go:197-199` and at
`issuer.go:271-273` both record that the cookie is deliberately not
delivered to `/mcp`, and `internal/auth/middleware.go:230` notes a
`Vary: Cookie` cache-fragmentation concern tied to it. Sending a bearer
credential to every route to improve one error page is the wrong trade.
The callback gets the friendly page instead.

**Middleware that logs all 4xx responses globally.** A single
`chi` middleware wrapping the `ResponseWriter` would cover every route at
once and could not be forgotten on a future branch. Dropped for this issue
because the acceptance criteria demand a *stable per-branch reason*
(`unknown_state` vs `expired_state`), which a status-code observer cannot
infer, and because a blanket 4xx logger over `/mcp` and `/api/*` would be a
much larger observability change than the incident justifies. Worth
revisiting separately.

**Require a POST (user gesture) before state is consumed on both routes.**
The issue floats this. Dropped for `/oauth/telegram/callback`: Telegram's
OIDC provider performs a GET redirect there (documented at
`server.go:1229-1234`), so the route cannot become POST-only without
renegotiating the registered redirect contract. Dropped for
`/telegram/connect/done` too, because it is the `redirect_uri` handed to
`/oauth/authorize` at `connect.go:143-150` and the same GET constraint
applies transitively. The prefetch-header refusal delivers most of the
benefit at a fraction of the risk.

## Platform impact

**Migrations.** None. No schema change, no new table, no new column. The two
new audit `tool_name` values (`connect:failed:bad_password`,
`connect:failed:auth_restart`) are free-text in the existing `tool_calls`
column, exactly like the values already written at `enable_access.go:755`
and the `connect:failed:flood_wait` / `connect:failed:code_invalid` values
asserted in `internal/db/connect_step_test.go:53,128`.

**Backward compatibility.**

- `ConnectConfig.Identifier` is an added optional field; existing
  constructions (including `newTestConnectServer` at `connect_test.go:27`)
  compile and behave as before, degrading to the friendly page.
- Three existing tests assert the current 400 on reused/expired state:
  `TestHandleConnectDone_UnknownState` (`connect_test.go:152`),
  `TestHandleConnectDone_ExpiredSession` (`connect_test.go:169`, whose
  comment at line 209 spells out "should return 400") and
  `TestHandleConnectDone_OIDCError` (`connect_test.go:220`). The first two
  must be updated to the new contract (`200` + reused page when no
  identity; `303` to manage when an identity is present). The OIDC-error
  test keeps its `400`. Callers who script against a `400` here are not a
  supported contract — these are browser-facing HTML pages.
- `POST /` moves from an empty `405` to a `405` with a JSON body. Status
  unchanged, so any client keying on the status is unaffected.
- Audit consumers that match the literal string `connect:failed:unknown`
  will see fewer hits. That is the point of the change, but any dashboard or
  alert keyed on that exact value should be reviewed before rollout.

**Resource impact.** Negligible. Two extra header reads per request on two
low-traffic routes, one extra JWT verification (`localjwt.VerifyWithClaims`,
HMAC only, no DB round trip for an interactive token per
`issuer.go:303-314`) on the reused-link path only, and a handful of new WARN
lines on paths that currently log nothing. No new goroutines, no new
timers, no new DB queries on the happy path.

**Risks and mitigations.**

- *Prefetch refusal breaks a legitimate client.* A client that sets
  `Purpose: prefetch` on the real navigation would get a `204` and appear
  stuck. Mitigated by matching only the two documented prefetch headers, by
  the INFO log line making such a case immediately visible, and by the fact
  that no MCP client sends these headers (only browsers and crawlers do).
- *The 2FA-password classification misses.* If the `gotd` error shape
  differs from the assumption, the new arm silently never fires and the
  behaviour reverts to today's `unknown`. Mitigated by the substring
  fallback, by a unit test built from the literal observed string, and by
  the fact that a miss is a no-op rather than a regression.
- *Redirecting to `/telegram/connect/manage` on a stale-but-verifying
  cookie.* If the JWT verifies but the underlying session was revoked, the
  user lands on manage's own unauthorized page
  (`ManageServer.WriteUnauthorized`, `manage.go:40`), which already links
  back to `/telegram/connect`. Degraded, not broken, and no worse than the
  bare 400 it replaces.
- *Hoisting `selectProvider` in `main.go` changes boot order.* Mitigated by
  the dependency check above (`cfg`, `store`, the revocation cache only) and
  by `internal/web/deploy_smoke_test.go`, which exercises the assembled
  route table.
- *Reason vocabulary duplicated across two packages drifts.* Mitigated by
  keeping the set to six constants and asserting the exact strings in the
  per-branch regression tests, so a rename in one package fails the other's
  test.
