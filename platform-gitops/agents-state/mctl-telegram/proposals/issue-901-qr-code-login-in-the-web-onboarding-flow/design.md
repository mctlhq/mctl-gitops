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
Add `stepQR` to `enableStep`, and a per-session `qrView string` token.
- `POST /oauth/telegram/enable_access/qr` (`handleEnableQRStart`): flag and `TGAPIID` checks,
  `lookupEnable`, step lock, same duplicate guard and pre-flight mode gate as
  `handleEnableStart` (factored into a shared helper rather than copied), supersede `es.flow`,
  `es.flow = s.startLoginFlow(..., methodQR, s.qrLogin(), ...)`, `es.step = stepQR`, mint a fresh
  128-bit `qrView` token, then wait (up to `enableSendCodeWait`) on `needQR` / `done`. On
  `needQR`, 303-redirect to the status page; on `done`/timeout, show the phone step with the
  `friendlyErr` message, exactly as the phone path does.
- `GET /oauth/telegram/enable_access/qr/status?v=<qrView>` (`handleEnableQRStatus`): resolves
  `qrView` to an enable session through a separate map (or scan of `s.enables` under `s.mu`). It
  takes **no** step lock and mutates nothing. `qrView` is a read-only capability distinct from
  `es`, so the token in the URL (history, proxy logs) cannot advance or finish the flow. It
  returns 204/no body for `isPrefetch` requests. It renders by `lf.phase`:
  - `qr_shown`: the SVG of `*lf.qrURL`, the account to scan with (`es.oc.Username` /
    display name), the phishing warning (host taken from `s.cfg.Issuer`), a "Use phone number
    instead" POST form (to the existing permissions/phone screen), and
    `<meta http-equiv="refresh" content="5">`.
  - `password_requested`: no refresh; the existing password form (`renderEnablePassword` with
    the `es` hidden field, posting to `/password`). `es` is rendered into the form body, never
    into a URL.
  - done with `lf.err == nil`: no refresh; "Connected - Continue" form POSTing `es` to
    `/oauth/telegram/enable_access/qr/finish`.
  - done with an error: no refresh; the error (`friendlyErr`, or the expired page for a
    `qr_shown` deadline) with "Try QR again" and "Use phone number" buttons.
  Headers: the `renderEnable` CSP unchanged, `Cache-Control: no-store`, plus
  `Referrer-Policy: no-referrer`.
- `POST /oauth/telegram/enable_access/qr/finish` (`handleEnableQRFinish`): `lookupEnable`, step
  lock, requires `es.step == stepQR` and a closed `lf.done` with `lf.err == nil`, then
  `finishEnable`. Side effects stay on a POST with the step lock, never on the refreshing GET.
- `handleEnablePassword` accepts `es.step == stepQR` when `lf.phase == password_requested`: under
  its step lock it drains the one pending `needPw` signal (non-blocking; it was not consumed by the
  lock-free status page), sets `es.step = stepPassword`, and continues with the existing code.
  Every later reprompt, `bad_password` and done branch is shared with the phone path. A
  `needCode` signal cannot occur on the QR path; if it does, treat it as an internal error.
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
  `ObserveLoginCompleted(method, outcome string, firstForUser bool)`. Audit rows gain the method:
  `connect:qr_started`, `connect:qr_scanned`, and `connect:success` with method in `ErrMsg`/a
  method suffix (`connect:success:qr`, keep `connect:success` for code, so existing queries do not
  change). The distinct-user truth is a `tool_calls` query; the per-process counter is a trend.
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
- **Putting `es` in the status URL.** Simplest, but `es` is the full mutating capability and the
  CSRF token; a URL leaks into history and logs. A separate read-only `qrView` token costs little.
  Dropped.
- **A parallel `startQRLoginFlow`.** Duplicates the uid mutex, supersession, local re-check,
  identity binding and repair defers, which carry several hard-won fixes (#821, #859, #899).
  Dropped in favour of one `startLoginFlow` with a login-function parameter, as the issue asks.

## Platform impact
- **Migrations:** none. No schema change; audit uses existing `tool_calls`.
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
    with `no-referrer`; the status URL carries only the read-only `qrView` token.
  - Superseded flow revoking a valid session: fixed by task 1, with a regression test.
  - Telegram new-device approval limits: surfaced as a normal error with the code path one click
    away.
  - Mobile misdetection: QR hidden; code path unaffected.
