# QR code login in the web onboarding flow (slice 1: desktop MVP behind a flag)

## Context
Today the in-browser connect flow (`/telegram/connect` -> `/oauth/telegram/enable_access/*`)
supports only phone -> login code -> optional 2FA password, driven by `startLoginFlow` in
`internal/oauth/enable_access.go`. The CLI already supports QR login
(`mctl-telegram-login --qr`, `telegram.LoginQR` in `internal/telegram/loginqr.go`, with 2FA via
`passwordAfterQR` since #895 and a logout of a mismatched account since #899). Issue #901 asks
for QR login (`auth.exportLoginToken` / `auth.importLoginToken`) as an equal alternative to
phone + code in the web flow. It is not the default, and the code path stays available as the
fallback everywhere.

This proposal covers **slice 1** of the issue: a desktop MVP behind a feature flag, enabled on
the preview deployment first. QR login avoids login-code delivery problems (codes that never
arrive, phone-number entry), but it grants full account access to whoever completes the scan,
so the page has to state clearly which account to scan with and carry a phishing warning.

## User stories
- AS a desktop user connecting my Telegram account I WANT to scan a QR code with the Telegram
  app on my phone SO THAT I do not have to type my phone number or wait for a login code.
- AS a user whose account has a 2FA cloud password I WANT the QR path to ask for my password
  on the existing password screen SO THAT 2FA works the same way on both paths.
- AS a user I WANT the QR page to tell me which account to scan with and warn me about
  phishing SO THAT I do not grant full access to the wrong account or the wrong site.
- AS the operator I WANT the QR option behind a flag, with per-method metrics, SO THAT I can
  try it on preview first and choose the default from data later (slice 2).

## Acceptance criteria (EARS)
- WHILE `ENABLE_ACCESS_QR_ENABLED` is false (the default) THE SYSTEM SHALL render the phone
  step and every enable_access route exactly as today, and the QR routes SHALL answer as an
  expired/unknown session without starting any Telegram login.
- WHEN the flag is true AND the request comes from a desktop browser (no mobile User-Agent
  hint) THE SYSTEM SHALL offer "Sign in with a QR code instead" on the phone step, next to
  the unchanged phone form, which stays the primary option.
- WHEN the flag is true AND the request comes from a mobile User-Agent THE SYSTEM SHALL NOT
  offer the QR option (same-phone `tg://login` behaviour is unverified).
- WHEN the user chooses QR THE SYSTEM SHALL start a login flow through the same
  `startLoginFlow` machinery as the phone path (uid mutex, supersession of the previous flow,
  local-account re-check, identity binding, SaveSessionForSignIn, send opt-in), with the
  login function set to `telegram.LoginQR` instead of `telegram.Login`.
- WHEN `LoginQR` exports a login token THE SYSTEM SHALL record the flow stage `qr_shown` and
  make the latest token URL available to the status page.
- WHILE the flow is at `qr_shown` THE SYSTEM SHALL serve a server-rendered status page with an
  inline SVG QR code of the current `tg://login?token=` URL and
  `<meta http-equiv="refresh">` (every 5 seconds), using no JavaScript and the unchanged
  `renderEnable` CSP.
- THE status page SHALL NOT take the enable session step lock and SHALL NOT mutate the enable
  session; it only reads flow state.
- THE status page SHALL name the account to scan with (the OIDC-proven Telegram display
  name/@username from the enable session) and SHALL show a phishing warning that: the scan
  gives full access to the account; scan only on the issuer host (tg.mctl.ai in production);
  check the app name in Telegram's confirmation prompt; and the session can be revoked in
  Telegram Settings -> Devices.
- WHEN the QR has been displayed for 5 minutes without a scan THE SYSTEM SHALL end the flow
  and show an "expired" page offering to start again with a QR code or with the phone number.
- WHEN Telegram accepts the scan but answers `SESSION_PASSWORD_NEEDED` THE SYSTEM SHALL show
  the existing password step, and the submitted password SHALL reach `passwordAfterQR` through
  the flow's `pwCh`, with the same reprompt and attempt limits as the phone path.
- WHEN the QR login completes for a Telegram account other than the OIDC-proven one THE SYSTEM
  SHALL log that authorization out (`logOutIfMismatch`), revoke/clear the stored session exactly
  as the phone path does, and show a method-neutral identity-mismatch error.
- WHEN the QR login completes for the right account THE SYSTEM SHALL show a "Continue" button
  whose POST (under the step lock) runs the existing `finishEnable`.
- WHEN a QR flow starts THE SYSTEM SHALL bind it to the starting browser with a `__Host-`
  prefixed `Secure`, `HttpOnly`, `SameSite` cookie holding a random value, kept server-side only
  as a hash. THE status page and every QR action SHALL require both the `qrView` URL token and a
  matching cookie; without the cookie they SHALL render a generic expired page and change nothing.
- THE QR status page and QR forms SHALL NEVER render the enable-session token `es`; QR actions
  (password, continue, cancel) SHALL be addressed by `qrView` plus the binding cookie.
- WHEN the user chooses "Use phone number instead" (or "Try QR again") THE SYSTEM SHALL, in a POST
  under the step lock, cancel the QR flow and invalidate its `qrView` and binding before rendering
  the next step.
- IF Telegram accepts a scan for a flow that has already been cancelled or superseded THEN THE
  SYSTEM SHALL NOT save the session, SHALL NOT revoke or modify an existing session, and SHALL log
  the new authorization out (best effort).
- IF the QR flow is superseded or cancelled THEN THE SYSTEM SHALL report a context error, never
  a successful login with an empty Telegram id, and SHALL NOT revoke an existing valid session.
- IF a QR flow is abandoned at `qr_shown` (deadline or cancellation with no supersession) THEN
  THE SYSTEM SHALL log "enable: onboarding abandoned" at WARN with `step=qr_shown`, not ERROR.
- WHEN any enable_access login completes THE SYSTEM SHALL record the method (`code` or `qr`) in
  metrics, counting a success once per distinct user per method, and SHALL write the same
  `connect:success` audit row for both methods, with the method recorded separately (a detail
  field on that row and the `connect:qr_started` / `connect:qr_scanned` rows), so that existing
  funnel queries count QR logins unchanged.
- THE QR token URL SHALL never be logged, and the status page SHALL be served with
  `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.

## Out of scope
- Slice 2: offering "Didn't get it? Use a QR code instead" after about 3 minutes at
  `code_requested`, and choosing the default method from data.
- Offering QR on mobile browsers, or a tappable `tg://login?token=` link.
- Enabling the flag in production (a follow-up gitops change after preview validation).
- Any JavaScript polling, Server-Sent Events, or CSP change.
- Changes to the CLI `--qr` flow beyond the shared `LoginQR` cancellation fix.

## Open questions
- The issue says the work "depends on the code-path and logOut issues". Both have shipped: the
  code-path issue is #900 (forgiving code and 2FA entry, `retryAuthRestartOnce`), released in
  0.98.1 via #908, and the logOut issue is #899 (`logOutIfMismatch` in
  `internal/telegram/login_mismatch.go`, called from `LoginQR`), released in 0.97.1. The
  implementer works from current main. #902's implementation also edits `enablePhoneTemplate`;
  this work starts after that PR merges and rebases onto it.
- Same-phone `tg://login?token=` behaviour on iOS/Android is undocumented (from the issue); it
  needs a manual test before mobile gets the option. Slice 1 hides QR on mobile.
- Telegram's new-device approval limits on accounts with only one recent device may block the
  scan; slice 1 surfaces Telegram's error through `friendlyErr` and leaves the code path one click
  away.
- "Success counted per distinct user": this proposal dedups per process in memory (resets on
  restart, per pod) and treats the audit table (`audit_logs`, `connect:success` with the method detail) as
  the source of truth for distinct-user analysis. If an exact global distinct count is needed in
  Prometheus, that needs a DB-backed counter.
- Mobile detection is a heuristic (`Sec-CH-UA-Mobile: ?1` or "Mobi" in the User-Agent); a
  misdetected tablet just falls back to the code path.
