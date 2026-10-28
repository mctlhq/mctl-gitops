# Tasks: issue-901-qr-code-login-in-the-web-onboarding-flow

- [ ] 1. Fix cancellation handling in `telegram.LoginQR` (`internal/telegram/loginqr.go`): return the wrapped `ctx.Err()` when the context ended, and an error when `telegramUserID == 0` — DoD: a cancelled or expired `LoginQR` returns an error satisfying `errors.Is(err, context.Canceled|DeadlineExceeded)` and never `(0, "", "", nil)`; `cmd/login --qr` still builds and works.
- [ ] 2. Add `ENABLE_ACCESS_QR_ENABLED` (`envBool`, default false) to `internal/config/config.go` and wire it into `oauth.Config` — DoD: config test covers default false and true.
- [ ] 3. Refactor `startLoginFlow` to take a `loginMethod` and a `flowLogin` function; add the `phoneLogin(phone)` adapter over `s.loginFn`; switch `handleEnableStart` to it; make the identity-mismatch message method-neutral; add `method` to the deferred logger lines (depends on 1) — DoD: all existing `internal/oauth` enable_access tests pass (with the updated mismatch string); no behaviour change on the phone path.
- [ ] 4. Add the QR seam and flow state: `LoginQRFunc` type and `s.loginQRFn` (default `telegram.LoginQR`), `qrLogin()` adapter, `loginFlow.qrURL`/`phase`/`needQR`, the `show` callback setting `step = "qr_shown"`, `qrDisplayTTL = 5*time.Minute`, and the WARN abandonment arm for `qr_shown` (depends on 3) — DoD: unit tests drive a stub `LoginQRFunc` through shown -> success, shown -> password, shown -> expired.
- [ ] 5. Add `renderQRSVG` in `internal/oauth/qrsvg.go` using `rsc.io/qr` — DoD: output is a well-formed `<svg>` with a quiet zone, contains no URL text, and its module grid matches `qr.Encode` for a fixed input.
- [ ] 6. Add `stepQR`, the `qrView` token, and the routes `POST /oauth/telegram/enable_access/qr`, `GET /oauth/telegram/enable_access/qr/status`, `POST /oauth/telegram/enable_access/qr/finish` in `Server.Register`; factor the duplicate guard and pre-flight mode gate shared with `handleEnableStart` (depends on 2, 4, 5) — DoD: with the flag off the QR routes start nothing and render the expired-session error; the status GET takes no step lock, mutates no session state, returns nothing useful for prefetch, and sets `Referrer-Policy: no-referrer` and the unchanged CSP.
- [ ] 7. Status page and templates in `internal/oauth/enable_access_page.go`: `qr_shown` (SVG, meta refresh 5 s, account name, phishing warning with the issuer host, "Use phone number instead"), password form, Continue form, error/expired page; `enablePhonePage.QRAvailable` plus the "Sign in with a QR code instead" form shown only when the flag is on and `isMobileUA(r)` is false (depends on 6) — DoD: page tests assert each state's markup and that no `<script>` appears.
- [ ] 8. Let `handleEnablePassword` accept `stepQR` at `phase == password_requested`: drain the pending `needPw`, set `stepPassword`, reuse the existing branches (depends on 6) — DoD: QR + 2FA test passes, including a wrong-password reprompt and the final `bad_password`.
- [ ] 9. Metrics and audit: `mctl_login_completed_total{method,outcome}`, `mctl_login_users_total{method}` with per-process uid dedup, `ObserveLoginCompleted` on `metricsIface`, `connect:qr_started` / `connect:qr_scanned` / `connect:success:qr` audit rows (depends on 4) — DoD: metrics tests assert labels and the dedup; the phone path records `method="code"`.
- [ ] 10. Docs: a QR section in `docs/runbook.md` (flag, metrics, WARN `step=qr_shown`, rollout order) and a CHANGELOG-ready conventional commit message — DoD: runbook doc tests (`internal/oauth/runbook_doc_test.go`, `docs/runbook_test.go`) pass.
- [ ] 11. Follow-up gitops PR (not in this repo): set `ENABLE_ACCESS_QR_ENABLED: "true"` in `platform-gitops/services/labs/mctl-telegram-preview/values.yaml` after release, validate manually on `tg-preview.mctl.ai`; production stays off until a separate decision (depends on 1-10) — DoD: preview checklist done with a 2FA and a non-2FA synthetic test account.

## Tests
- [ ] T1. `LoginQR` cancellation: a stubbed client run returning `context.Canceled` with a pre-existing stored session yields an error, not `(0, nil)`; `startLoginFlow` with a superseded QR flow does not call `RevokeActiveSession`.
- [ ] T2. QR happy path with a stub `LoginQRFunc`: start -> 303 to status -> status shows SVG and meta refresh -> stub completes -> status shows Continue -> finish POST issues the auth code via `finishEnable`.
- [ ] T3. QR + 2FA: stub returns via the password callback; status renders the password form; `/password` delivers to `pwCh`; reprompt and attempt limits match the phone path.
- [ ] T4. Identity mismatch on QR: the stub returns a different tg id; the session is revoked (or cleared if local) and the method-neutral error is shown. Use only the existing synthetic personas and ids (check with `git grep <id>`).
- [ ] T5. Expiry: with `qrDisplayTTL` shortened, the flow ends at `qr_shown`; the logger emits WARN "enable: onboarding abandoned" with `step=qr_shown`; the status page shows the expired page.
- [ ] T6. Supersession: starting phone after QR (and QR after phone) cancels the predecessor, which logs the INFO supersession line.
- [ ] T7. Flag off: no QR option on the phone page; the QR routes do not call `loginQRFn`.
- [ ] T8. Mobile UA (`Sec-CH-UA-Mobile: ?1`, an iPhone UA): no QR option.
- [ ] T9. Status GET concurrency: run under `-race` while the start handler holds the step lock; the status page still answers and never blocks on the lock.
- [ ] T10. Headers and CSP: status page CSP equals the `renderEnable` CSP, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`; an unknown or `es`-valued `v` parameter does not resolve.
- [ ] T11. No token in logs: capture slog output during T2 and assert the `tg://login?token=` URL never appears.
- [ ] T12. Metrics: `method` label for code and QR, the distinct-user dedup, and the existing `mctl_login_phone_step_total` unchanged.

## Rollback
The feature is off by default. To stop QR on an environment, remove `ENABLE_ACCESS_QR_ENABLED`
(or set it to `"false"`) in that environment's `values.yaml`; the QR option and routes go inert
on the next rollout, with in-flight QR flows ending at their deadline. If the `startLoginFlow`
refactor itself regresses the phone path, roll the image back with the usual release flow
(`mctl_rollback_service` to the previous tag, for example `0.98.2` in production) or revert the
merge commit. No data migration needs to be undone.
