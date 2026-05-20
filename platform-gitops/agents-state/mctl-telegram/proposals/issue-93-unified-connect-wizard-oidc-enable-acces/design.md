# Design: issue-93-unified-connect-wizard-oidc-enable-acces

## Current state

### Connect landing and success (internal/web/connect.go)

`ConnectServer` exposes two routes:

- `GET /telegram/connect` (`HandleConnect`): generates a PKCE verifier+challenge
  and state token, stores a `connectSession` in an in-memory map, and renders a
  single "Connect with Telegram" button that points at `/oauth/authorize`.
- `GET /telegram/connect/done` (`HandleConnectDone`): receives the OIDC
  authorization code, calls `oauthSrv.ExchangeConnect`, and renders either a
  success card or an error card. The success card shows the MCP URL and a link to
  Claude.ai settings, but does not mention Telegram device notifications.

The two pages use an inline CSS palette defined in `connectHead` / `connectFoot`
constants. There is no step indicator, no progress communication, and no awareness
of whether an MTProto session has been provisioned.

### OIDC callback and enable_access gating (internal/oauth/server.go)

`handleTelegramCallback` (lines 916-1098) is the central routing point. After
verifying the Telegram id_token it calls `s.store.CheckSessionValid`. If a valid
session exists it calls `s.issueAuthCode` directly. If not, and if the user is an
admin or client, it creates an `enableSession` with `step: stepPhone` and calls
`renderEnablePhone(w, enablePhonePage{Issuer: s.cfg.Issuer, EnableToken: esTok})`.

**The key coupling**: there is no distinction between a self-connect wizard flow
(`ClientID == "mctl_self_connect"`) and an external MCP client flow — all users
without a session land on the same phone form with no step context.

### MTProto session setup (internal/oauth/enable_access.go)

The state machine has four steps (lines 27-30):

```go
stepPhone    // awaiting phone number
stepCode     // awaiting SMS code
stepPassword // awaiting 2FA cloud password
stepDone     // session provisioned
```

Three HTTP handlers (`handleEnableStart`, `handleEnableCode`,
`handleEnablePassword`) feed inputs through channels into a background goroutine
running `telegram.Login`. The goroutine is cancelled by a `CodeTTL`-bounded
context. Error rendering uses `friendlyErr` (lines 454-468), which only
distinguishes `context.DeadlineExceeded` from all other errors — all MTProto RPC
codes are passed through raw via `err.Error()`.

There are no calls to `s.store.LogToolCall` anywhere in the enable_access
handlers, so wizard steps produce zero audit rows.

### HTML templates (internal/oauth/enable_access_page.go)

Page data structs (`enablePhonePage`, `enableCodePage`, `enablePasswordPage`) have
`Issuer`, `EnableToken`, and optionally `Error` fields. None carry a step number
or a wizard-mode flag. The `send_optin` checkbox is on the phone form but is
labelled generically; there is no standalone permissions screen.

### Telegram client options (internal/telegram/login.go, lines 36-39)

```go
client := telegram.NewClient(apiID, apiHash, telegram.Options{
    SessionStorage: sessStore,
})
```

No `Device` field is set, so gotd uses its default device model string which
includes the library version and Go version (e.g., `mctltg v0.144.0 go1.25
linux`). This appears verbatim in Telegram's active-sessions list.

### send_enabled default (internal/db/store.go, lines 282-290)

The `SaveSession` INSERT does not include `send_enabled` in its column list:

```sql
INSERT INTO telegram_accounts(user_id, telegram_user_id, display_name, username,
    session_encrypted, last_used_at, expires_at)
VALUES($1,$2,$3,$4,$5,$6,$7)
```

The value therefore falls back to the database schema default. In
`startLoginFlow` (enable_access.go lines 175-179), if `sendOptIn` is true, a
separate `store.SetSendEnabled(ctx, uid, true)` is called after `SaveSession`.

### Error catalog (internal/mcp/errorcatalog.go)

A `mtprotoErrCatalog` map (lines 20-69) already maps codes such as
`PHONE_NUMBER_INVALID`, `CHAT_FORBIDDEN`, and others to user-friendly messages,
and `floodWaitSeconds` (lines 74-92) parses `FLOOD_WAIT_X`. This catalog is
currently only consumed by `mtprotoErrResult` for MCP tool responses — not by
the enable_access handlers.

### Session management API (internal/web/account.go)

`AccountHandlers` exposes JSON endpoints under `/api/account` (GET, POST
/disconnect, DELETE, GET /audit, GET /audit/verify). These require a Bearer token
from the localjwt middleware. There is no browser-facing HTML manage page.

---

## Proposed solution

The changes are surgical and avoid cross-package restructuring. The oauth package
owns the enable_access state machine and will gain the permissions step and wizard
rendering. The web package owns the connect surfaces and will gain the manage page.

### 1. Custom DeviceModel in telegram.Options

**File**: `internal/telegram/login.go` (lines 36-39)

Add a `Device` field to `telegram.Options`:

```go
client := telegram.NewClient(apiID, apiHash, telegram.Options{
    SessionStorage: sessStore,
    Device: telegram.DeviceConfig{
        DeviceModel:    "mctl Telegram Assistant",
        SystemVersion:  "Linux",
        AppVersion:     "1.0",
        SystemLangCode: "en",
        LangCode:       "en",
    },
})
```

Verify `telegram.DeviceConfig` field names against the `gotd/td` version pinned in
`go.mod` before committing. This is a one-line area of change with no interface
impact.

### 2. Explicit send_enabled=false in SaveSession INSERT

**File**: `internal/db/store.go` (`SaveSession`, lines 282-290)

Add `send_enabled` to the INSERT column list with a hardcoded `false` value:

```sql
INSERT INTO telegram_accounts(user_id, telegram_user_id, display_name, username,
    session_encrypted, last_used_at, expires_at, send_enabled)
VALUES($1,$2,$3,$4,$5,$6,$7, false)
```

The post-save `store.SetSendEnabled(ctx, uid, true)` call in
`enable_access.go:startLoginFlow` (lines 175-179) is preserved for the opt-in
path. The `cmd/login/main.go` and `cmd/local/main.go` callers of `SaveSession`
require no change because the parameter signature is unchanged.

### 3. Structured MTProto error messages

**File**: `internal/oauth/enable_access.go` (`friendlyErr`, lines 454-468)

Extend `friendlyErr` to recognise specific MTProto codes. Import `github.com/gotd/td/tgerr` (already a transitive dep via internal/mcp/errorcatalog.go). Add a small
switch before the fallback:

```go
func friendlyErr(err error) string {
    if err == nil {
        return ""
    }
    var rpc *tgerr.Error
    if errors.As(err, &rpc) {
        switch {
        case rpc.Message == "PHONE_NUMBER_INVALID":
            return "phone number format is invalid — use international format, e.g. +14155551234."
        case rpc.Message == "PHONE_CODE_INVALID":
            return "that code did not match — check the code in your Telegram app and try again."
        case rpc.Message == "PHONE_CODE_EXPIRED":
            return "the code expired — a new one has been requested."
        case strings.HasPrefix(rpc.Message, "FLOOD_WAIT_"):
            n, _ := strconv.Atoi(strings.TrimPrefix(rpc.Message, "FLOOD_WAIT_"))
            until := time.Now().UTC().Add(time.Duration(n) * time.Second).Format("15:04:05")
            return fmt.Sprintf("Telegram asked us to wait %d seconds — try again at %s UTC.", n, until)
        }
    }
    // existing fallback ...
}
```

`PHONE_CODE_EXPIRED` callers should also trigger a resend attempt by calling
`lf.codeCh <- ""` or re-entering the flow, but the simplest safe behaviour is to
re-render the code form with the friendly message and let the user re-enter (gotd
handles the actual resend inside its auth flow on the next code submission).

### 4. Audit trail in enable_access handlers

**File**: `internal/oauth/enable_access.go`

Add `s.store.LogToolCall` calls at the key points. The `uid` is available from
`es.uid`. Because `LogToolCall` is intentionally fire-and-forget (never blocking a
request), no error check is needed:

- `handleTelegramCallback` after `s.enables[esTok] = es` and the render call:
  `s.store.LogToolCall(r.Context(), uid, "connect:oidc_callback", "", "ok", "")`
- `handleEnableStart` on success (before `renderEnableCode`):
  `s.store.LogToolCall(r.Context(), es.uid, "connect:phone_submitted", "", "ok", "")`
- `handleEnableStart` on MTProto failure:
  `s.store.LogToolCall(r.Context(), es.uid, "connect:failed:"+shortReason(lf.err), "", "error", lf.err.Error())`
- `handleEnableCode` analogously with `"connect:code_submitted"` and
  `"connect:failed:code_invalid"` etc.
- `handleEnablePassword` analogously with `"connect:2fa_submitted"`.
- `finishEnable` before `s.issueAuthCode`:
  `s.store.LogToolCall(r.Context(), es.uid, "connect:success", "", "ok", "")`

Add a small `shortReason(err error) string` helper that maps known error types to
short tokens (`phone_invalid`, `code_expired`, `flood_wait`, `identity_mismatch`,
`timeout`, `unknown`) so the `tool_name` is machine-parseable without embedding
free-form text.

The `peer_redacted` argument is always empty for wizard audit entries — phone
numbers must not appear there, and `audit/redact.go` protects the error field
against accidental leakage via the slog handler.

### 5. Permissions step in the wizard flow

**Files**: `internal/oauth/enable_access.go`, `internal/oauth/enable_access_page.go`,
`internal/oauth/server.go`

#### 5a. New step constant

```go
const (
    stepPermissions enableStep = iota // new: awaiting permission choice (wizard only)
    stepPhone                          // awaiting phone number
    stepCode                           // awaiting SMS code
    stepPassword                       // awaiting 2FA cloud password
    stepDone                           // session provisioned
)
```

Renumbering iota is safe because `enableStep` values are never persisted.

#### 5b. Wizard-mode detection

Add a helper to `enableSession`:

```go
func (es *enableSession) isWizardMode() bool {
    return es.oc.ClientID == ConnectClientID
}
```

#### 5c. Modified handleTelegramCallback

In `server.go:handleTelegramCallback`, replace the existing call at the bottom
(`renderEnablePhone(w, enablePhonePage{...})`) with:

```go
if es.isWizardMode() {
    es.step = stepPermissions
    renderEnablePermissions(w, enablePermissionsPage{
        Issuer: s.cfg.Issuer, EnableToken: esTok,
    })
} else {
    es.step = stepPhone
    renderEnablePhone(w, enablePhonePage{Issuer: s.cfg.Issuer, EnableToken: esTok})
}
```

#### 5d. New permissions handler

In `enable_access.go`, add `handleEnablePermissions`:

```go
func (s *Server) handleEnablePermissions(w http.ResponseWriter, r *http.Request) {
    es, esTok, ok := s.lookupEnable(r)
    // ... standard TryLock + expiry check ...
    if es.step != stepPermissions {
        // replay phone form if already past permissions
        renderEnablePhoneStep(...)
        return
    }
    es.sendOptIn = r.FormValue("send_optin") != ""
    es.step = stepPhone
    renderEnablePhone(w, enablePhonePage{
        Issuer: s.cfg.Issuer, EnableToken: esTok, WizardMode: true, WizardStep: 3,
    })
}
```

Register at `POST /oauth/telegram/enable_access/permissions` in `server.go:Register`.

#### 5e. Remove send_optin checkbox from phone form

The permissions screen now owns the opt-in choice. Remove the `send_optin`
checkbox from `enablePhoneTemplate` in `enable_access_page.go` and from the
`enablePhonePage` struct when `WizardMode` is true. For non-wizard flows (external
MCP clients) keep the checkbox as-is, controlled by a template `{{if
not .WizardMode}}` block.

### 6. Step indicator and wizard chrome

**File**: `internal/oauth/enable_access_page.go`

Add `WizardMode bool` and `WizardStep int` to `enablePhonePage`,
`enableCodePage`, `enablePasswordPage`, and the new `enablePermissionsPage`.

In every page data struct derivation inside the handlers, set:

```go
WizardMode: es.isWizardMode(),
WizardStep: 3, // or 2 for permissions, etc.
```

In `enableHead` / `connectHead`, add a CSS class `.steps` for the indicator. The
indicator is a simple `<ol class="steps">` with `<li class="active">` on the
current step, rendered with a template `{{if .WizardMode}}...{{end}}` block.
Because the CSS is inline and the CSP allows `style-src 'unsafe-inline'`, no CDN
dependency is introduced.

The step map:
- Step 1 — Identity (rendered by `internal/web/connect.go`'s landing page)
- Step 2 — Permissions (new `enablePermissionsPage`)
- Step 3 — Session (phone / code / password screens; `WizardStep: 3`)
- Step 4 — Done (rendered by `internal/web/connect.go:connectSuccessTemplate`)

The landing page in `connect.go` already shows the OIDC button — update
`connectLandingTemplate` to show the step indicator with Step 1 active.

Add the "Telegram will notify you" warning banner to `enablePhoneTemplate` inside
a `{{if .WizardMode}}` block so it only appears on the wizard path.

### 7. Done page update (internal/web/connect.go)

Update `connectSuccessTemplate` to add a paragraph reminding the user to check
Telegram Settings > Privacy and Security > Active Sessions (or Devices > Active
Sessions in newer clients) to find the new "mctl Telegram Assistant" entry and
verify it looks correct. Add a link to `/telegram/connect/manage`.

### 8. Session management dashboard (internal/web/manage.go, new file)

A new `ManageServer` struct in the `web` package, constructed similarly to
`ConnectServer`. It exposes:

- `GET /telegram/connect/manage` — renders an HTML card with the active account
  info from `store.GetActiveAccount`. If the request carries no valid auth
  identity (checked via `auth.From(r.Context())`), redirect to
  `/telegram/connect`.
- `POST /telegram/connect/manage/disconnect` — calls
  `pool.RemoveAtomic(uid, store.RevokeActiveSession)` then redirects back.
- `POST /telegram/connect/manage/toggle-send` — calls `store.SetSendEnabled` with
  the toggled value then redirects back.

The manage page is mounted behind the same localjwt auth middleware as
`/api/account`. The auth middleware must be configured to accept both Bearer tokens
and, if a session cookie strategy is adopted, the cookie. Authentication mechanism
for browser sessions is the primary open question; the implementation should follow
the path of least resistance given the existing middleware setup.

The HTML uses the same card CSS palette already present in `connectHead` so the
page visually matches the rest of the wizard.

---

## Alternatives

### A. Move the entire enable_access flow into internal/web

Merging `oauth/enable_access.go` into `web/connect.go` would give the wizard full
control of the HTML. Rejected because `oauth/server.go:handleTelegramCallback`
already creates and owns `enableSession`, and moving it would create a large
import-cycle or require a heavy refactor of the state-machine channel plumbing.
The conditional wizard-mode approach achieves the same UX with no structural
disruption.

### B. Use a redirect from oauth back to web/connect for the permissions step

After `handleTelegramCallback` creates the `enableSession`, redirect the browser to
a new `GET /telegram/connect/permissions?es=<esTok>` route handled by
`ConnectServer`. The permissions form would POST back to `ConnectServer`, which
would then redirect into the enable_access phone endpoint.

Rejected because it splits the session token across two packages, requiring
`ConnectServer` to call into the oauth package to look up the `enableSession` by
token. That would either create an import cycle or require a new interface. The
in-package permissions step avoids this coupling.

### C. Extend `SaveSession` signature with a `sendEnabled bool` parameter

Pass `sendEnabled` directly into `SaveSession` and write it in the INSERT, removing
the separate `SetSendEnabled` call. Cleaner transaction semantics, but requires
updating three call sites (`enable_access.go`, `cmd/login/main.go`,
`cmd/local/main.go`) and every test that calls `SaveSession`. Recommended as a
follow-up refactor once this feature lands, but not required for the issue's
stated goal of an explicit `false` default.

---

## Platform impact

### Migrations

No schema migration is required. The `send_enabled` column already exists in
`telegram_accounts` with an implicit `DEFAULT FALSE`. Adding it explicitly to the
INSERT column list is a code-only change. The new audit event kinds
(`connect:oidc_callback`, `connect:phone_submitted`, etc.) fit the existing
`audit_logs.tool_name` VARCHAR column with no width issues.

### Backward compatibility

- `SaveSession` signature is unchanged; all three call sites compile without
  modification.
- `enableStep` iota values change by +1 (new `stepPermissions` at position 0).
  These values are only held in in-memory `enableSession` structs that are swept or
  expire within `CodeTTL` (10 minutes). There is no persistence or serialisation of
  step values, so renumbering is safe across a rolling restart.
- The new `POST /oauth/telegram/enable_access/permissions` route is additive. Old
  sessions that were created before deployment (within the 10-minute TTL window)
  will have `step == stepPhone` (now 1) rather than `stepPermissions` (now 0); the
  existing `handleEnableStart` guard `if es.step != stepPhone` will reject them
  with "please start again", which is the same behaviour as today for expired
  sessions.
- The `telegram.DeviceConfig` change applies only to new `Login` calls. Existing
  persisted sessions are unaffected.

### Resource impact

- Six new audit rows per successful wizard completion (oidc_callback,
  phone_submitted, code_submitted, success) and up to one per failed step. At
  current scale this is negligible.
- One new in-memory struct (`enablePermissionsPage`) per in-flight wizard session.
  This is bounded by `MaxPendingEnable` (default 256).

### Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| `telegram.DeviceConfig` field names differ from gotd version in go.mod | Verify against go.mod before implementation; compile-time error if wrong |
| Non-wizard users (MCP clients) accidentally land on permissions step | `isWizardMode()` check gates the new step; non-wizard flows use the existing phone form unchanged |
| Audit entries for failed phone/code steps expose PII via the error field | `error` field passed to `LogToolCall` is scrubbed by the `RedactingHandler`; `peer_redacted` is always empty for wizard entries |
| Session cookie strategy for `/telegram/connect/manage` is undefined | Open question documented in requirements.md; if unresolved, manage page can require a fresh OIDC flow to obtain a Bearer token stored in a short-lived cookie |
