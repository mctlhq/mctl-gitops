# Tasks: issue-695-connect-oauth-reused-single-use-links-sh

- [ ] 1. Add the reason vocabulary and the prefetch predicate to
  `internal/web/connect.go`: unexported constants `reasonMissingState`,
  `reasonUnknownState`, `reasonExpiredState`, `reasonExchangeFailed`,
  `reasonOIDCError`, `reasonPrefetchRefused`; `isPrefetch(*http.Request) bool`
  matching `Sec-Purpose` by substring and `Purpose` by exact token; and
  `logConnectReject(r, reason)` emitting one `slog.Warn` with `route`,
  `reason`, `prefetch`. — DoD: package builds, `go vet` clean, no attribute
  carries `code`, `state` or a cookie value.

- [ ] 2. Wire logging into every early return of `HandleConnectDone`
  (`internal/web/connect.go:160`) — the `?error=` branch, the
  `code == "" || state == ""` branch, the unknown/expired branch, and the
  `ExchangeConnect` failure (replacing the ad-hoc message at line 190 with
  `reasonExchangeFailed`, kept at `slog.Error`). (depends on 1) — DoD: each
  branch emits exactly one line; the happy path emits none.

- [ ] 3. Add `ConnectIdentifier` (a locally-declared minimal interface with
  `Authenticate(*http.Request) (*auth.Identity, error)`, mirroring the
  `OAuthExchanger` pattern at `connect.go:31`), an `Identifier` field on
  `ConnectConfig`, and `(*ConnectServer).alreadyConnected(r)` returning true
  only for a non-nil identifier yielding a non-nil identity and nil error.
  (depends on 1) — DoD: a nil `Identifier` never panics and never redirects.

- [ ] 4. Add `renderConnectReused` plus its template beside
  `connectErrorTemplate` (`connect.go:326`), rendered through the existing
  `renderConnect` helper at `http.StatusOK` with the unchanged CSP string and
  a `.btn` to `/telegram/connect`. (depends on 1) — DoD: response carries
  `Content-Security-Policy`, `Cache-Control: no-store`, status 200, and names
  no state or code value in the body.

- [ ] 5. Rewrite `HandleConnectDone`'s unknown/expired branch: distinguish
  `reasonUnknownState` from `reasonExpiredState`, log, then `303 See Other`
  to `/telegram/connect/manage` when `alreadyConnected(r)`, else
  `renderConnectReused`. Leave the `missing_state` branch at `400` with the
  existing error page. (depends on 2, 3, 4) — DoD: all four outcomes
  reachable and covered by T1/T2/T3.

- [ ] 6. Refuse prefetch at the top of `HandleConnectDone`, before the
  `s.sessions` lookup: `204 No Content`, `Cache-Control: no-store`, one
  `slog.Info` with `reason=prefetch_refused`. (depends on 1) — DoD: the
  pending entry for that state is still present in `s.sessions` after the
  prefetch request returns.

- [ ] 7. Mirror tasks 1, 2 and 6 in `internal/oauth/server.go` for
  `handleTelegramCallback` (`server.go:1516`): the same reason constants and
  `isPrefetch`/`logCallbackReject` helpers (duplicated, not shared — the
  `web` package must not import `oauth`), logging at `server.go:1519`
  (`missing_state`), `1567` (`unknown_state`, DB backend), `1594`
  (`unknown_state`, in-memory backend) and `1602` (`expired_state`), and the
  prefetch check placed ahead of the activation dispatch at `server.go:1529`.
  — DoD: all four 4xx state branches log exactly once; the existing
  `slog.Error` calls at `server.go:1573`, `1629`, `1659` and `1742` are
  unchanged.

- [ ] 8. Replace the plain-text bodies on the callback's unknown/expired
  branches with `renderEnableError` (the renderer this handler already uses at
  `server.go:1612`/`1617`), status 200, copy: "That sign-in link was already
  used or has expired. Close this page and start connecting again from your
  MCP client." Keep `missing state` at `400`. (depends on 7) — DoD: no
  remaining `http.Error(w, "unknown or expired state", ...)` or
  `http.Error(w, "state expired", ...)` in the file.

- [ ] 9. Confirm the `gotd/td v0.161.0` error shape for a rejected two-step
  verification password (the observed string is `sign in with password:
  invalid password`) and add the classification: an `AUTH_RESTART` arm inside
  the existing `errors.As(err, &rpcErr)` switch in `shortReason`
  (`internal/oauth/enable_access.go:1151`) returning `auth_restart`, and a
  `bad_password` arm keyed on the exported sentinel if one exists, falling
  back to a case-insensitive substring check on `invalid password` /
  `PASSWORD_HASH_INVALID`. Keep every existing mapping and the final
  `return "unknown"`. — DoD: `shortReason` returns `bad_password` for the
  observed error and `auth_restart` for `tgerr.New(500, "AUTH_RESTART")`;
  every pre-existing mapping still returns its old value.

- [ ] 10. Add the matching `friendlyErr` arms (`enable_access.go:1115`):
  "That two-step verification password was not accepted. Check it and try
  again." and "Telegram ended the sign-in session. Submit your phone number
  again to get a fresh code." (depends on 9) — DoD: neither message echoes
  the raw error string, and no other arm changes.

- [ ] 11. Route a `bad_password` failure in `handleEnablePassword`
  (`enable_access.go:1015-1029`) back to `renderEnablePassword` with
  `Error: friendlyErr(lf.err)`, `WizardMode: es.isWizardMode()`,
  `WizardStep: 3` — mirroring the empty-password call at
  `enable_access.go:992`. Every other error, including the
  `db.ErrAccountModeConflict` terminal arm at line 1021, keeps its current
  path. Verify the user's next submit is not dead-ended by the
  `es.step != stepPassword || es.flow == nil` guard at `enable_access.go:970`
  (the login goroutine has exited and `es.flow` is spent by then); if the
  step cannot be safely re-armed, fall back to the phone step carrying the
  new `bad_password` copy. (depends on 10) — DoD: the audit label and the
  wording are correct in both variants, and no path leaves the user on a
  screen whose submit button leads nowhere.

- [ ] 12. Add `web.RootPostHint(mcpPath string) http.HandlerFunc` in
  `internal/web/landing.go` beside `BrowserRedirect` (`landing.go:113`):
  `405`, `Content-Type: application/json`, `Cache-Control: no-store`, and a
  JSON-RPC 2.0 error object naming the MCP path. — DoD: body is valid JSON
  containing the configured path; `GET /` is untouched.

- [ ] 13. Register `mux.Post("/", web.RootPostHint(cfg.MCPPath))` beside
  `cmd/server/main.go:409`, and hoist the `workerTokenRevocationCache` /
  `selectProvider` block (`main.go:~455-465`) above the `local-jwt` block at
  `main.go:425` so the provider can be passed as
  `ConnectConfig.Identifier` at `main.go:437-445`. (depends on 3, 12) — DoD:
  server boots in both `local-jwt` and `shared-hmac` modes;
  `internal/web/deploy_smoke_test.go` passes.

## Tests

- [ ] T1. `TestHandleConnectDone_ReusedState_RedirectsToManage`: prime a
  state via `HandleConnect`, consume it, replay the same URL with a stub
  `Identifier` returning a valid identity — expect `303` and
  `Location: /telegram/connect/manage`.

- [ ] T2. `TestHandleConnectDone_ReusedState_NoIdentity_ShowsReusedPage`:
  same replay with a nil or anonymous `Identifier` — expect `200`, the
  reused-page copy, a `Content-Security-Policy` header, and a link to
  `/telegram/connect`.

- [ ] T3. Update `TestHandleConnectDone_UnknownState`
  (`internal/web/connect_test.go:152`) and
  `TestHandleConnectDone_ExpiredSession` (line 169, including the comment at
  line 209) to the new contract, and assert `reason=unknown_state` vs
  `reason=expired_state` in the captured log output. Leave
  `TestHandleConnectDone_OIDCError` (line 220) asserting `400`.

- [ ] T4. `TestHandleConnectDone_LogsOneWarnPerBranch`: table-driven over
  missing state, unknown state, expired state and exchange failure, capturing
  `slog` into a buffer as `internal/oauth/enable_access_abandonment_test.go`
  already does — assert exactly one line per case, the expected `reason`, and
  that the body contains neither the state nor the code value.

- [ ] T5. `TestHandleConnectDone_PrefetchDoesNotConsumeState`: send
  `Sec-Purpose: prefetch`, then `Purpose: prefetch`, then the real request —
  expect `204`, `204`, then a normal success, proving the state survived.

- [ ] T6. `TestHandleTelegramCallback_ReusedState_FriendlyPage`: unknown
  state — expect `200`, HTML (not a plain-text body), and one WARN with
  `reason=unknown_state`. Cover the in-memory backend and, where the existing
  test harness allows, the `ConsumeOAuthPending` DB backend.

- [ ] T7. `TestHandleTelegramCallback_MissingState_StillFourHundred`: no
  `state` — expect `400` plus one WARN with `reason=missing_state`.

- [ ] T8. `TestHandleTelegramCallback_PrefetchDoesNotConsumeState`: mirrors
  T5, and additionally asserts the activation dispatch at `server.go:1529` is
  not reached (an activation state survives a prefetch).

- [ ] T9. `TestShortReason_BadPasswordAndAuthRestart`: the literal observed
  password error and `tgerr.New(500, "AUTH_RESTART")` map to `bad_password`
  and `auth_restart`; a table asserting every pre-existing mapping still
  returns its old token.

- [ ] T10. `TestEnablePassword_WrongPassword_AuditAndCopy`: drive
  `handleEnablePassword` with a stub login returning the password error
  (reusing the `stubLogin` helper at
  `internal/oauth/enable_access_test.go:301`) — assert an audit entry with
  `tool_name == "connect:failed:bad_password"` and the new wording in the
  rendered body. Use only the existing synthetic personas (`Alice`, `Bob`,
  `Carol`, `Dana`) and their already-committed numeric ids.

- [ ] T11. `TestEnableStart_AuthRestart_AuditLabel`: a stub login returning
  `tgerr.New(500, "AUTH_RESTART")` yields
  `tool_name == "connect:failed:auth_restart"` and the restart wording on the
  phone step.

- [ ] T12. `TestRootPostHint`: `POST /` returns `405`, a JSON body parseable
  as a JSON-RPC error object, and a message containing the configured MCP
  path; `GET /` still returns the landing page.

- [ ] T13. Full gate before opening the PR: `go fmt ./...`, `go vet ./...`,
  `golangci-lint run`, `go test ./...`. Every test above must fail when its
  production change is reverted — verify by reverting each hunk locally once.

## Rollback

Every change is in application code with no migration and no persisted
state, so rollback is a redeploy of the previous image tag
(`ghcr.io/mctlhq/mctl-telegram:0.69.0`, the version the incident was
observed on) via `mctl_rollback_service`. No data written by the new code
needs cleanup: the only new persisted artifacts are audit `tool_calls` rows
carrying the new `connect:failed:bad_password` / `connect:failed:auth_restart`
labels, which are free-text values an older binary reads without complaint.

Partial rollback, if only one change misbehaves:

- Prefetch refusal (tasks 6, 7) is the highest-risk hunk — it is the only
  change that can make a real request return nothing. Reverting `isPrefetch`
  to `return false` disables it everywhere in one line while keeping the
  logging and the recovery pages.
- The cookie-aware redirect (tasks 3, 5, 13) reverts by passing a nil
  `Identifier` from `main.go`: `alreadyConnected` then always returns false
  and users get the friendly reused page instead of the redirect, with no
  code removal.
- The classification changes (tasks 9-11) revert independently of everything
  else; a revert restores `connect:failed:unknown` for both cases.
- `POST /` (tasks 12, 13) reverts by deleting the single `mux.Post("/", ...)`
  registration, restoring chi's default bare `405`.

Monitoring after rollout: watch for a spike in
`reason=prefetch_refused` (would indicate a real client caught by the header
match) and for `303`s to `/telegram/connect/manage` immediately followed by
manage's own `401` (would indicate the stale-cookie degradation described in
design.md).
