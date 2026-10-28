# Design: issue-901-qr-code-login-in-the-web-onboarding-flow

## Current state

Web connect flow (`internal/oauth/enable_access.go`, `internal/oauth/enable_access_page.go`):
- Routes are registered in `Server.Register` (`internal/oauth/server.go`):
  `POST /oauth/telegram/enable_access/{permissions,start,code,password}`. All are public; the
  unguessable `es` form field (resolved by `lookupEnable`) is the caller's identity and also the
  CSRF token. Every route is a POST; there is no GET route in the flow.
- `enableSession` holds `step` (`stepPermissions`, `stepPhone`, `stepCode`, `stepPassword`,
  `stepDone`), `flow *loginFlow`, the OIDC context `oc` (`TelegramID`, `Username`) and a
  `lock sync.Mutex`. Handlers take that lock through `acquireStepLock` and hold it across their
  MTProto wait.
- `startLoginFlow(uid, wantTgID, phone, sendOptIn, signInStartedAt)` builds a `loginFlow`
  (`codeCh`, `pwCh`, `needCode`, `needPw`, `done`, `cancel`, `step`, `superseded`), cancels the
  uid's previous flow through `s.loginFlows.Swap`, and runs a goroutine that: takes
  `uidLoginMutex(uid)`, re-checks `hasActiveLocalAccount`, calls
  `s.loginFn(bgCtx, ..., phone, askCode, askPassword, loginCfg)` with
  `loginCfg.WantTelegramID = wantTgID`, then applies the identity binding (revoke or
  `clearStraySessionIfLocal` on mismatch, with the error text "the phone number belongs to a
  different Telegram account..."), `LoadSession`, `SaveSessionForSignIn`, and `SetSendEnabled`.
  A deferred logger classifies the outcome; abandonment is WARN only when
  `lf.step` is `code_requested` or `password_requested`.
- `s.loginFn` has type `LoginFunc` (`server.go`), which matches `telegram.Login`'s phone-shaped
  signature and is set to `telegram.Login` in `New`.
- Pages are rendered by `renderEnable` with the CSP
  `default-src 'none'; style-src 'unsafe-inline'; img-src https://ui.mctl.ai; form-action 'self' https:; base-uri 'none'`
  and `Cache-Control: no-store`. Inline `<svg>` markup and `<meta http-equiv="refresh">` are not
  subresource loads, so they need no CSP change.
- Metrics: `metricsIface` exposes `ObserveLoginPhoneStep(result, seconds)`
  (`mctl_login_phone_step_total`, `mctl_login_phone_to_code_duration_seconds` in
  `internal/metrics/metrics.go`). Nothing records the login method or completed logins.
- Audit: handlers write `db.ToolCall` rows such as `connect:phone_submitted`,
  `connect:2fa_submitted`, `connect:success`, `connect:failed:<reason>`.

QR login (`internal/telegram/loginqr.go`):
- `LoginQR(ctx, apiID, apiHash, store, userID, show, password, cfgs...)` uses `qrlogin.NewQR`
  with `Migrate: client.MigrateTo`, retries `AUTH_RESTART` once (`retryAuthRestartOnce`, #900),
  calls `show(ctx, url, asciiArt)` each time a token is exported (about every 30 s), handles 2FA
  via `passwordAfterQR` -> `askPasswordChecked`, and calls `logOutIfMismatch` with
  `cfg.WantTelegramID` (#899, `internal/telegram/login_mismatch.go`).
- **Hazard found while reading:** after `client.Run`, `LoginQR` does
  `if runErr != nil && !errors.Is(runErr, context.Canceled) { return ... }` and otherwise goes on
  to `sessStore.LoadSession`. For a cancelled QR flow (the web flow supersedes by `cancel()`),
  this either returns "qr login completed but no session bytes were persisted" (logged at ERROR,
  not as an abandonment) or, if the uid already has a stored session from an earlier connect,
  returns `(0, "", "", nil)`. `startLoginFlow` would then see `tgID(0) != wantTgID` and revoke
  the user's existing valid session. This must be fixed before `LoginQR` is used from the web
  flow. The CLI (`cmd/login/main.go`, `--qr`) relies on this swallow only for Ctrl-C, where an
  error exit is also correct.
- `renderQR` uses `rsc.io/qr` (already a dependency) to produce ASCII art; `qr.Code` also
  exposes `Size` and `Black(x, y)`, which is all an SVG renderer needs.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: production, tenant `labs`, image
  tag `0.98.2`, ingress hosts `tg.mctl.ai` and `labs-mctl-telegram.mctl.ai`,
  `OAUTH_CODE_TTL: "30m"`. No QR-related env var exists.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`: preview, tenant `labs`,
  image tag `main-04a3d29` (the clone's HEAD), host `tg-preview.mctl.ai`, `OAUTH_CODE_TTL: "30m"`.
  This is where the flag is enabled first.
- mctl MCP tools were not called; the gitops files were enough for the facts above. Runtime
  behaviour (logs, replicas) was not observed and is not relied on.

## Proposed solution

### 1. Make `LoginQR` safe for cancellation (`internal/telegram/loginqr.go`)
If `ctx.Err() != nil` after `client.Run`, return `ctx.Err()` (wrapped) instead of falling
through to `LoadSession`. Also return an error if `telegramUserID == 0` at the end. With this,
`isAbandonment(lf.err)` classifies cancellation and deadline correctly, and a superseded QR flow
can never reach the identity-mismatch revoke. The CLI then exits non-zero on Ctrl-C, which is
fine.

### 2. Generalise `startLoginFlow` over the login function (`internal/oauth/enable_access.go`)
Add a method-neutral function type:

```go
type loginMethod string // "code" | "qr"

// flowLogin runs one Telegram login with the flow's callbacks.
type flowLogin func(ctx context.Context, cb flowCallbacks, cfg telegram.LoginConfig) (tgID int64, displayName, username string, err error)
```

`startLoginFlow(uid, wantTgID, method, run flowLogin, sendOptIn, signInStartedAt)` keeps
everything else (supersession, uid mutex, local re-check, identity binding, save, deferred
logger) unchanged. Two constructors:
- `s.phoneLogin(phone)` wraps `s.loginFn` (the existing `LoginFunc` seam, so current tests keep
  stubbing it).
- `s.qrLogin()` wraps a new seam `s.loginQRFn` (type `LoginQRFunc`, default `telegram.LoginQR`),
  passing `show` and `askPassword`.

`loginFlow` gains:
- `method loginMethod`;
- `qrURL atomic.Pointer[string]` written by `show`, read by the status page;
- `qrShownAt time.Time` set once on the first `show` (read only by the logger, same
  happens-before argument as `step`);
- `needQR chan struct{}` (buffered 1), signalled on the first `show`, so the start handler can
  wait for the first token like it waits for `needCode`;
- `phase atomic.Value` (string: `qr_shown`, `password_requested`, `done`), a race-free mirror of
  the stage for the lock-free status page. `step` keeps its current unsynchronised contract and
  stays logger-only.

`show` sets `lf.step = "qr_shown"`, stores the URL, and signals `needQR`. The QR context is
`context.WithTimeout(bgCtx, qrDisplayTTL)` with `qrDisplayTTL = 5 * time.Minute` (bounded by
`CodeTTL`), applied only while waiting for a scan. A `DeadlineExceeded` at `qr_shown` becomes
the "QR expired" page.

The deferred logger's WARN arm accepts `qr_shown` as well as `code_requested` and
`password_requested`, and all log lines gain `method`. The identity-mismatch error text becomes
method-neutral ("the Telegram account you logged in with is not the one you signed in with...").
The QR token URL is never logged; it is a login credential. If `qr_url`/`login_token` style
attribute names are introduced anywhere, add them to the redaction list in
`internal/audit/redact.go`.

### 3. New step and routes (`server.go`, `enable_access.go`)

Amended 2026-10-28: the first version gave the status page a `qrView` token it called
read-only, but then rendered the password and Continue forms with `es` in a hidden field, so
anyone holding the status URL could read `es` from the HTML and drive the flow. The QR pages
below never render `es`, and every QR page and action is bound to the browser that started
the flow.

**Browser binding.** `handleEnableQRStart` mints two independent 128-bit random values:
- `qrView`, carried in the status URL (`?v=`), which identifies the flow;
- `qrBind`, set as a cookie `__Host-tg_qr` (`Secure`, `HttpOnly`, `SameSite=Strict`,
  `Path=/`, no `Domain`, `Max-Age` = `qrDisplayTTL` plus the password window). Only its
  SHA-256 is kept on the enable session.

Every QR route (status GET and all QR POSTs) resolves `qrView` and then requires the cookie
to match the stored hash with a constant-time compare. On a missing or wrong cookie it renders
the same generic "this sign-in link has expired" page as for an unknown `qrView`, with no
account name, no QR and no form, and changes nothing. A stolen status URL alone therefore gives
neither the QR, nor `es`, nor any way to finish the flow. `qrView` and `qrBind` are dropped when
the flow ends, is cancelled or is superseded, and when the enable session expires. If
`SameSite=Strict` breaks the same-site meta refresh or the form POSTs in a supported browser,
`Lax` is acceptable (all actions are POSTs); the PR says which was used and why.

- `POST /oauth/telegram/enable_access/qr` (`handleEnableQRStart`): flag and `TGAPIID` checks,
  `lookupEnable` (this is the last request that carries `es`), step lock, the same duplicate
  guard and pre-flight mode gate as `handleEnableStart` (factored into a shared helper rather
  than copied), supersede `es.flow`,
  `es.flow = s.startLoginFlow(..., methodQR, s.qrLogin(), ...)`, `es.step = stepQR`, mint
  `qrView` and `qrBind`, set the cookie, then wait (up to `enableSendCodeWait`) on `needQR` /
  `done`. On `needQR`, 303-redirect to the status page; on `done`/timeout, show the phone step
  with the `friendlyErr` message, exactly as the phone path does.
- `GET /oauth/telegram/enable_access/qr/status?v=<qrView>` (`handleEnableQRStatus`): resolves
  `qrView` through a dedicated map guarded by `s.mu` (not a scan of `s.enables`), checks the
  binding cookie, takes **no** step lock and mutates nothing. It returns 204/no body for
  `isPrefetch` requests. It renders by `lf.phase`, and **no state renders `es`**:
  - `qr_shown`: the SVG of `*lf.qrURL`, the account to scan with (`es.oc.Username` /
    display name), the phishing warning (host taken from `s.cfg.Issuer`), a "Use phone number
    instead" form POSTing `v` to `/qr/cancel`, and `<meta http-equiv="refresh" content="5">`.
  - `password_requested`: no refresh; a password form (same markup and copy as the existing
    password step) POSTing `v` and the password to `/qr/password`.
  - done with `lf.err == nil`: no refresh; "Connected - Continue" form POSTing `v` to
    `/qr/finish`.
  - done with an error: no refresh; the error (`friendlyErr`, or the expired page for a
    `qr_shown` deadline) with "Try QR again" and "Use phone number" forms, both POSTing `v` to
    `/qr/cancel` with a `next=qr|phone` field.
  Headers: the `renderEnable` CSP unchanged, `Cache-Control: no-store`, plus
  `Referrer-Policy: no-referrer`.
- `POST /oauth/telegram/enable_access/qr/password` (`handleEnableQRPassword`): resolve `v`,
  check the binding cookie, take the enable session's step lock, require `es.step == stepQR` and
  `lf.phase == password_requested`, drain the one pending `needPw` signal (non-blocking; the
  lock-free status page never consumes it), then run the existing password logic, factored out of
  `handleEnablePassword` into a helper that both handlers call, so reprompts, attempt limits and
  `bad_password` stay shared with the phone path. A reprompt re-renders the QR password form
  (with `v`, never `es`). A `needCode` signal cannot occur on the QR path; if it does, treat it as
  an internal error.
- `POST /oauth/telegram/enable_access/qr/finish` (`handleEnableQRFinish`): resolve `v`, check
  the binding cookie, take the step lock, require `es.step == stepQR` and a closed `lf.done` with
  `lf.err == nil`, then `finishEnable`. Side effects stay on a POST with the step lock, never on
  the refreshing GET.
- `POST /oauth/telegram/enable_access/qr/cancel` (`handleEnableQRCancel`): resolve `v`, check
  the binding cookie, take the step lock, mark the flow cancelled and call its `cancel()`, drop
  `qrView` and `qrBind` (so the status URL immediately renders the expired page), clear the
  cookie, set `es.step = stepPhone`, then render the phone step (or start a fresh QR flow for
  `next=qr`). The phone page it renders carries `es` in its form as today; that is the same
  browser, proven by the cookie.
- **Cancel vs. a concurrent scan.** Cancelling the context is not enough: Telegram may accept
  the scan in the instant before the cancel lands, so `LoginQR` can return a fresh authorization.
  In the `startLoginFlow` goroutine, after the login function returns and **under
  `uidLoginMutex(uid)`**, check the flow's cancelled/superseded state (set by cancel and by
  supersession before they call `cancel()`) **before** `SaveSessionForSignIn` and before any
  identity-binding revoke. If the flow was cancelled or superseded, do not save, do not revoke
  the existing session, log the new authorization out (`auth.logOut` on the just-created client,
  best effort, as `logOutIfMismatch` does), and end with a context error. A cancelled flow can
  therefore never store a session or touch an existing one.
- The phone page template gets an optional "Sign in with a QR code instead" form
  (`enablePhonePage.QRAvailable bool`), set when the flag is on and the request is not mobile
  (`isMobileUA(r)`: `Sec-CH-UA-Mobile: ?1` or "Mobi" in the User-Agent).

### 4. SVG renderer (`internal/oauth/qrsvg.go`)
`renderQRSVG(url string) (template.HTML, error)` uses `rsc.io/qr` at level M, draws one `<path>`
of unit squares with a 4-module quiet zone in a `viewBox`, `shape-rendering="crispEdges"`, a
fixed CSS size of about 240 px, and `role="img"` with an `aria-label`. The output contains only
numbers built by the renderer, so returning `template.HTML` is safe. The URL itself is never
placed in the markup.

### 5. Config and metrics
- `internal/config/config.go`: `EnableAccessQREnabled bool` from
  `envBool("ENABLE_ACCESS_QR_ENABLED", false)`, wired into `oauth.Config`.
- `internal/metrics/metrics.go`: `mctl_login_completed_total{method,outcome}`
  (outcome: `ok`, `error`, `abandoned`, `superseded`, `identity_mismatch`) and
  `mctl_login_users_total{method}`, incremented on the first success of a uid for a method in this
  process (bounded `sync.Map` dedup). Extend `metricsIface` with
  `ObserveLoginCompleted(method, outcome string, firstForUser bool)`. Audit rows gain the method
  without changing the success row: both methods write the same `connect:success` row, as today,
  so every existing funnel query (the daily digest's `LastConnectStepFor`, the #902 runbook
  funnel) counts QR logins with no change. The method is recorded separately: QR flows write
  `connect:qr_started` when the QR is first shown and `connect:qr_scanned` when Telegram accepts
  the scan, and `connect:success` carries `method=qr|code` in its existing `ErrMsg`/detail field
  (whichever field `LogToolCall` already stores; no new column). Never `connect:success:qr`. The
  distinct-user truth is an `audit_logs` query; the per-process counter is a trend.
- `docs/runbook.md`: a short QR section (flag, metrics, the expected WARN line).

### 6. Rollout
Merge with the flag off (production unchanged). Set `ENABLE_ACCESS_QR_ENABLED: "true"` in
`services/labs/mctl-telegram-preview/values.yaml` (a separate gitops PR), test on
`tg-preview.mctl.ai` with a 2FA and a non-2FA test account, then a later PR for production.

## Alternatives
- **JavaScript polling or SSE for the QR page.** Smoother, but needs a nonce script, a JSON
  endpoint, and a CSP change; the issue explicitly asks for no JS and no CSP change. Dropped.
- **Status page takes the step lock and calls `finishEnable` itself on success.** Saves one click,
  but a refreshing GET would then perform the authorization-code issuance (a side effect on GET,
  exposed to prefetch), and it would contend with the start handler that holds the same lock. The
  issue requires the status page never take the step lock. Dropped in favour of the Continue POST.
- **Putting `es` in the status URL, or in hidden fields on the status page.** `es` is the full
  mutating capability and the CSRF token. A URL leaks into history and logs, and anything the
  status page renders is available to whoever can load it. Dropped: the status page never renders
  `es`, and QR actions use `qrView` plus the browser-bound `__Host-tg_qr` cookie.
- **`qrView` alone as a read-only capability.** The first version of this proposal. It is not
  read-only once the page it unlocks contains forms that can advance the flow, and a URL token is
  exactly what leaks. Dropped in favour of the cookie binding.
- **A parallel `startQRLoginFlow`.** Duplicates the uid mutex, supersession, local re-check,
  identity binding and repair defers, which carry several hard-won fixes (#821, #859, #899).
  Dropped in favour of one `startLoginFlow` with a login-function parameter, as the issue asks.

## Platform impact
- **Migrations:** none. No schema change; audit uses the existing `audit_logs` table.
- **Backward compatibility:** flag off by default; with it off the phone path is unchanged except
  for the `startLoginFlow` refactor and method-neutral mismatch wording (tests that assert the old
  string must be updated). `LoginFunc` and `s.loginFn` keep their signature, so existing stubs work.
  The CLI `--qr` now exits with an error on Ctrl-C instead of a session-load error.
- **Resources:** one extra goroutine per active QR flow (same as the phone flow); a status GET
  every 5 s per open QR page, each rendering a small SVG; bounded by `qrDisplayTTL` (5 min).
  `auth.exportLoginToken` is called about every 30 s while shown (about 10 calls per flow), through
  the existing login middleware chain (flood-wait, global limiter, per-RPC timeout).
- **Risks and mitigations:**
  - Phishing / QR relay (an attacker shows a victim our QR): the warning names the account and
    host, tells the user to check the app name in Telegram's confirmation, and the identity check
    plus `logOutIfMismatch` reject any account other than the OIDC-proven one.
  - Token leakage: the token URL is never logged or put in markup as text; pages are `no-store`
    with `no-referrer`; the status URL carries only `qrView`, which is useless without the
    browser-bound cookie, and no page in the QR flow renders `es`.
  - Superseded flow revoking a valid session: fixed by task 1, with a regression test.
  - Telegram new-device approval limits: surfaced as a normal error with the code path one click
    away.
  - Mobile misdetection: QR hidden; code path unaffected.
