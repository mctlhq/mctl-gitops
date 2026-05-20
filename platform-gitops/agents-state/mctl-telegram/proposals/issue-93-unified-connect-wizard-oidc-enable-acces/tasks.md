# Tasks: issue-93-unified-connect-wizard-oidc-enable-acces

## Implementation tasks

- [ ] 1. **Custom DeviceModel in telegram.Options**
  File: `internal/telegram/login.go` lines 36-39.
  Add `Device: telegram.DeviceConfig{DeviceModel: "mctl Telegram Assistant", SystemVersion: "Linux", AppVersion: "1.0", SystemLangCode: "en", LangCode: "en"}` to the `telegram.Options` literal.
  Verify field names against `gotd/td` version in `go.mod` (`github.com/gotd/td`).
  DoD: `go build ./...` succeeds; a manual login attempt shows "mctl Telegram Assistant" as the device name in Telegram Settings > Active Sessions.

- [ ] 2. **Explicit send_enabled=false in SaveSession INSERT** (no dependency)
  File: `internal/db/store.go`, `SaveSession` function (lines 282-290).
  Add `send_enabled` to the INSERT column list with value `false`.
  DoD: `go vet ./internal/db/...` passes; existing `TestSaveSession_*` tests pass; a new unit test asserts `IsSendEnabled` returns false after `SaveSession` without a subsequent `SetSendEnabled` call.

- [ ] 3. **Structured MTProto error messages in friendlyErr** (no dependency)
  File: `internal/oauth/enable_access.go`, `friendlyErr` function (lines 454-468).
  Import `github.com/gotd/td/tgerr` and `strconv` (already in the module). Add a `tgerr.Error` type switch handling `PHONE_NUMBER_INVALID`, `PHONE_CODE_INVALID`, `PHONE_CODE_EXPIRED`, and `FLOOD_WAIT_X` before the existing fallback. Add `shortReason(err error) string` helper mapping known error types to tokens (`phone_invalid`, `code_expired`, `flood_wait`, `identity_mismatch`, `timeout`, `unknown`).
  DoD: `go test ./internal/oauth/...` passes; new table-driven unit tests cover each MTProto code producing the correct friendly string; `FLOOD_WAIT_30` produces a string containing `"30 seconds"` and a UTC time.

- [ ] 4. **Audit trail for enable_access handlers** (depends on none; DoD-independent of 5)
  File: `internal/oauth/enable_access.go` and `internal/oauth/server.go`.
  Add `s.store.LogToolCall` calls at:
  - `server.go:handleTelegramCallback` after `s.enables[esTok] = es` with `"connect:oidc_callback"` and `"ok"`.
  - `enable_access.go:handleEnableStart` on success path (before `renderEnableCode`) with `"connect:phone_submitted"`.
  - `enable_access.go:handleEnableStart` on each error path with `"connect:failed:"+shortReason(err)`.
  - `enable_access.go:handleEnableCode` on success and error paths with `"connect:code_submitted"` / `"connect:failed:..."`.
  - `enable_access.go:handleEnablePassword` on success and error paths with `"connect:2fa_submitted"` / `"connect:failed:..."`.
  - `enable_access.go:finishEnable` before `s.issueAuthCode` with `"connect:success"` and `"ok"`.
  `shortReason` is introduced in task 3; task 4 may be implemented in the same PR.
  DoD: integration test or table test asserts that a complete wizard flow inserts audit rows with the correct `tool_name` values in order; a failed phone attempt inserts a `"connect:failed:phone_invalid"` row with `status = "error"`.

- [ ] 5. **Permissions step: new step constant, wizard-mode helper, handler, template**
  Files: `internal/oauth/enable_access.go`, `internal/oauth/enable_access_page.go`, `internal/oauth/server.go`.

  5a. Add `stepPermissions enableStep = iota` as the first constant, pushing `stepPhone` to 1 and so on.

  5b. Add `func (es *enableSession) isWizardMode() bool { return es.oc.ClientID == ConnectClientID }` to `enable_access.go`.

  5c. In `server.go:handleTelegramCallback` at line 1097, replace the unconditional `renderEnablePhone` call with a branch: wizard mode -> set `es.step = stepPermissions`, call `renderEnablePermissions`; else -> set `es.step = stepPhone`, call `renderEnablePhone`.

  5d. Add `handleEnablePermissions(w, r)` to `enable_access.go`: look up `enableSession`, TryLock, verify `es.step == stepPermissions`, read `send_optin` form value, set `es.sendOptIn`, advance `es.step = stepPhone`, render phone form.

  5e. Add `POST /oauth/telegram/enable_access/permissions` registration to `server.go:Register`.

  5f. Add `enablePermissionsPage` struct and `enablePermissionsTemplate` in `enable_access_page.go` with:
    - Step 2 of 4 header and step indicator.
    - Two radio buttons: "Read only (recommended)" (value `"readonly"`) and "Read + send" (value `"send"`).
    - On selecting "Read + send" a visible warning paragraph (static HTML, no JS required: use a separate `<details>` or conditional rendering via the form).
    - Submit button labelled "Continue".
  DoD: a wizard flow with `client_id = "mctl_self_connect"` shows the permissions screen between the OIDC callback and the phone form; a non-wizard MCP-client flow skips directly to the phone form as before; `go test ./internal/oauth/...` passes.

- [ ] 6. **Step indicator and wizard chrome in enable_access page templates** (depends on 5)
  File: `internal/oauth/enable_access_page.go`.
  Add `WizardMode bool` and `WizardStep int` fields to `enablePhonePage`, `enableCodePage`, `enablePasswordPage`.
  Update `enableHead` to include CSS for `.steps` list (`display:flex; gap:8px; list-style:none; margin:0 0 20px; padding:0`; active step bold, inactive grey).
  Add a `{{if .WizardMode}}<ol class="steps">...</ol>{{end}}` fragment to each template.
  Add a `{{if .WizardMode}}<div class="notice">...</div>{{end}}` banner to `enablePhoneTemplate` with the "Telegram will send a device notification" warning text.
  Remove `send_optin` checkbox from `enablePhoneTemplate` when `WizardMode` is true (`{{if not .WizardMode}}...{{end}}`).
  Update handler call sites in `enable_access.go` to pass `WizardMode: es.isWizardMode()` and the appropriate `WizardStep` value (2 for permissions, 3 for phone/code/2FA).
  DoD: a rendered phone-form response in wizard mode contains the step indicator HTML and the device-notification banner; a non-wizard phone form contains neither; all template tests pass.

- [ ] 7. **Landing page and success page wizard chrome** (depends on 6)
  File: `internal/web/connect.go`.
  Update `connectLandingTemplate` to include the step indicator showing Step 1 of 4 active.
  Update `connectSuccessTemplate` to show "Step 4 of 4 — Done", add a reminder paragraph about Telegram Settings > Active Sessions and the "mctl Telegram Assistant" device name, and add a link to `/telegram/connect/manage`.
  DoD: `GET /telegram/connect` response body contains "Step 1" and "Step 4" is absent; `GET /telegram/connect/done` (mocked exchange success) response body contains "Step 4" and the Devices reminder.

- [ ] 8. **Session management dashboard** (depends on 7; authentication mechanism must be confirmed per open question 1)
  New file: `internal/web/manage.go`.
  Define `ManageServer` struct holding `store *db.Store`, `pool AccountCloser`, and `issuer string`.
  `GET /telegram/connect/manage`: call `auth.From(r.Context())` — if nil, redirect to `/telegram/connect`; else call `store.GetActiveAccount` and render an HTML card (using the same `connectHead` CSS) showing display_name, connected_at, last_used_at, expires_at, mode, send_enabled, and a link to the audit log. Include a form POST to `./disconnect` and a form POST to `./toggle-send`.
  `POST /telegram/connect/manage/disconnect`: call `pool.RemoveAtomic` + `store.RevokeActiveSession("disconnect")`; redirect back to `GET /telegram/connect/manage`.
  `POST /telegram/connect/manage/toggle-send`: read current `send_enabled` from `store.GetActiveAccount`, toggle, call `store.SetSendEnabled`; redirect back.
  Register routes via `ManageServer.Register(mux Router)` and mount in `cmd/server/main.go` behind the same auth middleware as `/api/account`.
  DoD: `go build ./...` passes; a logged-in user can see their session details and disconnect without using the JSON API; an unauthenticated GET redirects to `/telegram/connect`.

---

## Tests

- [ ] T1. **`TestFriendlyErr_KnownMTProtoCodes`** (`internal/oauth/enable_access_test.go`): table-driven test covering `PHONE_NUMBER_INVALID`, `PHONE_CODE_INVALID`, `PHONE_CODE_EXPIRED`, `FLOOD_WAIT_30`; assert friendly strings; assert raw pass-through for unknown codes.

- [ ] T2. **`TestShortReason`** (`internal/oauth/enable_access_test.go`): verify `shortReason` returns expected tokens for each mapped error type.

- [ ] T3. **`TestSaveSession_SendEnabledDefaultFalse`** (`internal/db/store_test.go`): create a new user, call `SaveSession` (without subsequent `SetSendEnabled`), call `IsSendEnabled` — assert false.

- [ ] T4. **`TestWizardAuditTrail`** (`internal/oauth/enable_access_test.go`): using the existing stub login infrastructure from `enable_access_test.go:23`, run a complete wizard flow via HTTP test handlers; assert that `store.ListAuditFor` returns rows with `tool_name` values `connect:oidc_callback`, `connect:phone_submitted`, `connect:code_submitted`, `connect:success` in order.

- [ ] T5. **`TestPermissionsStepWizardMode`** (`internal/oauth/server_chi_test.go` or new file): POST to `/oauth/telegram/enable_access/permissions` with a wizard-mode `enableSession`; assert the response renders the phone form (step 3); assert `es.sendOptIn` is set correctly for each radio button value.

- [ ] T6. **`TestPermissionsStepSkippedForNonWizard`** (`internal/oauth/server_chi_test.go`): create an `enableSession` with a non-`mctl_self_connect` client ID; simulate the callback; assert the response is the phone form directly (not the permissions screen).

- [ ] T7. **`TestStepIndicatorInWizardMode`** (`internal/oauth/enable_access_test.go`): render `enablePhonePage{WizardMode: true, WizardStep: 3}` via the template, assert the response body contains "Step 3".

- [ ] T8. **`TestStepIndicatorAbsentNonWizard`** (same file): render `enablePhonePage{WizardMode: false}`, assert the response body does not contain "Step 3 of 4".

- [ ] T9. **`TestNotificationBannerWizardOnly`** (same file): assert the device-notification warning text appears when `WizardMode: true` and is absent when `WizardMode: false`.

- [ ] T10. **`TestManagePageRedirectsUnauthenticated`** (`internal/web/manage_test.go`): issue an unauthenticated GET to `/telegram/connect/manage`; assert 302 redirect to `/telegram/connect`.

- [ ] T11. **`TestManagePageShowsSession`** (same file): issue a GET with a valid auth identity in context; assert the response body contains the display name and a "Disconnect" form.

---

## Rollback

The changes are additive with one minor breaking change in semantics (the
`stepPermissions` iota shift). Rollback procedure:

1. **Deploy the previous image**: any in-flight `enableSession` values will expire
   within the `CodeTTL` (10 minutes default). No in-flight sessions are persisted,
   so there is no data to clean up.

2. **Audit rows**: The new `connect:*` audit event kinds are stored as plain
   `tool_name` strings in `audit_logs`. Rolling back the code does not remove them.
   They are inert — `get_my_audit_log` will surface them to users, but they carry
   no operational harm. If they are undesired they can be removed with:
   ```sql
   DELETE FROM audit_logs WHERE tool_name LIKE 'connect:%';
   ```
   This is purely cosmetic and optional.

3. **send_enabled INSERT change**: if the previous schema default was already
   `FALSE`, there is no observable difference in stored data. If the schema default
   was somehow truthy, new rows written during the deployment window would need a
   corrective `UPDATE telegram_accounts SET send_enabled = FALSE WHERE ...` scoped
   to the deployment window. Verify the schema default before deploying.

4. **Telegram DeviceModel**: existing sessions are not affected by the device
   name change. New sessions provisioned during the deployment window will show
   "mctl Telegram Assistant" in Telegram's device list. These sessions continue to
   function after rollback; the device name visible in Telegram's UI cannot be
   retroactively changed for already-provisioned sessions.

5. **`/telegram/connect/manage`**: removing the route causes 404 for any bookmarked
   manage URL. The link on the success page would need to be reverted alongside
   the route removal. Both files touch the same PR, so reverting the PR reverts both.
