# Unified Connect Wizard: OIDC + MTProto Session Setup in One Flow

## Context

The `/telegram/connect` path currently delivers an incomplete onboarding experience
split across two independent subsystems. `internal/web/connect.go` handles the
landing page and OIDC button; `internal/oauth/enable_access.go` handles the
phone/code/2FA MTProto session setup that is triggered after the OIDC callback
inside `internal/oauth/server.go:handleTelegramCallback`. The two surfaces share
a colour palette but diverge in visual language, copy quality, and progress
communication. Users have no indication of which step they are on, no warning that
Telegram will send a "new login" device notification, and no explicit consent screen
for the `send_enabled` permission before their session is provisioned.

This proposal unifies the two surfaces into a four-step browser wizard driven by
the existing `enableSession` state machine in the oauth package, adds structured
friendly error messages for MTProto RPC failures, extends the audit chain to cover
every intermediate step of the wizard, sets a custom device model visible in
Telegram's Settings > Devices, makes the `send_enabled=false` default explicit at
INSERT time, and adds a session management page at `/telegram/connect/manage`.

## User stories

- AS a new user I WANT a step indicator on the connect page SO THAT I know how
  many steps remain and do not abandon midway.
- AS a new user I WANT to choose read-only vs read+send before entering my phone
  number SO THAT I understand exactly what capability I am granting.
- AS a new user I WANT a clear warning that Telegram will send a device notification
  SO THAT I am not alarmed and do not immediately revoke the session.
- AS a user who made a typo I WANT a human-readable error message rather than a raw
  MTProto code SO THAT I know what to fix.
- AS a user affected by rate limiting I WANT a countdown showing when I can retry
  SO THAT I do not hammer the server.
- AS a user reviewing my audit log I WANT to see every wizard step recorded SO THAT
  I can tell exactly when and how my session was provisioned.
- AS an operator debugging an incident I WANT audit entries for each intermediate
  failure SO THAT I can reconstruct what happened without log-diving.
- AS a user reviewing connected devices in Telegram I WANT a recognisable app name
  (not a build string) SO THAT I can identify the mctl session without confusion.
- AS a user who prefers read-only access I WANT `send_enabled=false` to be the
  default SO THAT sending capability is always an explicit opt-in.
- AS a connected user I WANT a manage page listing my session details SO THAT I
  can disconnect, delete, or toggle send mode without leaving the browser.

## Acceptance criteria (EARS)

### Wizard navigation

- WHEN a user lands on `GET /telegram/connect` THE SYSTEM SHALL render a landing
  card showing "Step 1 of 4 — Identity" with a "Connect with Telegram" button.
- WHEN the OIDC callback succeeds and `client_id == "mctl_self_connect"` and no
  usable MTProto session exists THE SYSTEM SHALL render a permissions screen
  labelled "Step 2 of 4 — Permissions" before the phone form.
- WHEN the user reaches the phone-number form THE SYSTEM SHALL render a step
  indicator showing "Step 3 of 4 — Session" and a bold warning banner stating that
  Telegram will send a new-login device notification and that this is expected.
- WHEN the MTProto session is successfully provisioned and the authorization code
  is redeemed at `/telegram/connect/done` THE SYSTEM SHALL render a "Step 4 of 4 —
  Done" success page with the MCP URL, a link to the manage page, and a reminder
  to verify the new entry in Telegram Settings > Privacy and Security > Active
  Sessions.

### Permissions step

- WHEN the user reaches the permissions screen THE SYSTEM SHALL present two
  choices: "Read only (recommended)" and "Read + send (with confirmation)" and
  pre-select "Read only".
- WHEN the user selects "Read + send" THE SYSTEM SHALL display an additional
  warning that the assistant will be able to send messages on their behalf.
- WHEN the user submits the permissions form THE SYSTEM SHALL record the
  `send_optin` choice into the `enableSession` and proceed to the phone form.
- WHILE the permissions step is active THE SYSTEM SHALL set `send_enabled = false`
  in `telegram_accounts` on INSERT unless the user explicitly opted into send mode.

### Structured error messages

- WHEN Telegram returns `PHONE_NUMBER_INVALID` THE SYSTEM SHALL display "Phone
  number format is invalid. Use international format, e.g. +14155551234." without
  exposing the raw MTProto error code.
- WHEN Telegram returns `PHONE_CODE_INVALID` THE SYSTEM SHALL display "That code
  did not match. Check the code in your Telegram app and try again."
- WHEN Telegram returns `PHONE_CODE_EXPIRED` THE SYSTEM SHALL display "The code
  expired. A new one has been requested." and re-render the code form pre-populated
  with an empty code field.
- WHEN Telegram returns `FLOOD_WAIT_X` (where X is a positive integer of seconds)
  THE SYSTEM SHALL display "Telegram asked us to wait X seconds. Try again after
  HH:MM:SS (UTC)." where HH:MM:SS is computed from the current server time.
- WHEN the login goroutine signals `SESSION_PASSWORD_NEEDED` THE SYSTEM SHALL
  transition to the 2FA password screen without showing an error banner.

### Audit trail

- WHEN the OIDC callback succeeds and redirects the browser into the wizard
  THE SYSTEM SHALL write an audit entry with `tool_name = "connect:oidc_callback"`
  and `status = "ok"`.
- WHEN the user submits a phone number THE SYSTEM SHALL write an audit entry with
  `tool_name = "connect:phone_submitted"` and `status = "ok"` or `"error"`.
- WHEN the user submits an SMS code THE SYSTEM SHALL write an audit entry with
  `tool_name = "connect:code_submitted"` and `status = "ok"` or `"error"`.
- WHEN the user submits a 2FA password THE SYSTEM SHALL write an audit entry with
  `tool_name = "connect:2fa_submitted"` and `status = "ok"` or `"error"`.
- WHEN the wizard completes successfully THE SYSTEM SHALL write an audit entry with
  `tool_name = "connect:success"` and `status = "ok"`.
- WHEN any wizard step fails fatally THE SYSTEM SHALL write an audit entry with
  `tool_name = "connect:failed:<reason>"` where reason is a short code
  (e.g. `phone_invalid`, `code_expired`, `flood_wait`, `identity_mismatch`).
- WHILE audit entries are written THE SYSTEM SHALL not include phone numbers, SMS
  codes, passwords, or session bytes in any audit field (enforced by the existing
  `internal/audit/redact.go` handler and `peer_redacted` column).

### Custom app name

- WHEN `telegram.NewClient` is called in `internal/telegram/login.go` THE SYSTEM
  SHALL set `telegram.Options.Device.DeviceModel` to `"mctl Telegram Assistant"`
  so that the device appears with that name in Telegram Settings > Active Sessions.

### Default send_enabled

- WHEN `db.Store.SaveSession` INSERTs a new `telegram_accounts` row THE SYSTEM
  SHALL explicitly include `send_enabled = false` in the column list so the default
  is source-visible and does not rely on the database schema default alone.
- IF the user explicitly opted into send mode during the permissions step THEN
  THE SYSTEM SHALL call `store.SetSendEnabled(ctx, uid, true)` after `SaveSession`
  as it does today via `startLoginFlow`.

### Session management dashboard

- WHEN an authenticated user visits `GET /telegram/connect/manage` THE SYSTEM SHALL
  render an HTML page showing: display name, connected_at, last_used_at, expires_at,
  mode (hosted/local), and send_enabled status for the active session.
- WHEN the user clicks "Disconnect" THE SYSTEM SHALL POST to
  `/api/account/disconnect` and re-render the manage page showing no active session.
- WHEN the user clicks "Delete" THE SYSTEM SHALL POST to `DELETE /api/account` and
  re-render the manage page with a confirmation.
- WHEN the user clicks "Toggle send mode" THE SYSTEM SHALL call
  `store.SetSendEnabled` and re-render the page with the updated status.
- WHILE an unauthenticated browser requests `/telegram/connect/manage` THE SYSTEM
  SHALL redirect to `GET /telegram/connect` so the user can authenticate first.

## Out of scope

- Local Bridge mode as a wizard entry point (tracked separately per the issue).
- Multi-account UX (multiple Telegram identities per user).
- WebSocket or AJAX-driven real-time countdown for FLOOD_WAIT (server-side
  computed HH:MM:SS string in the initial render is sufficient).
- Internationalisation of wizard copy.

## Open questions

1. **Manage page authentication mechanism**: `/telegram/connect/manage` needs the
   caller's `users.id`. The `/api/account` handlers rely on `*auth.Identity` from
   the localjwt Bearer-token middleware. The manage page would need either (a) a
   session cookie seeded from the OIDC callback, or (b) a redirect into the OIDC
   flow before rendering. The most reasonable interpretation is (b): if no valid
   Bearer token is present in a cookie or header, redirect to `/telegram/connect`.
   The implementer should confirm that the localjwt middleware can also accept a
   session cookie, or add a lightweight cookie-backed session for the manage page.

2. **Step indicator in the non-wizard path**: When an MCP client (not
   `mctl_self_connect`) triggers enable_access, users currently land on the phone
   form with no wizard chrome. This proposal does not change that experience.
   If the team later wants the step indicator for all enable_access flows, that is
   an additive change on top of this proposal.

3. **`PHONE_CODE_EXPIRED` re-send logic**: The gotd `auth.Flow` automatically
   calls `ResendCode` when the session's pending code expires. Whether the server
   surfaces this as a transparent retry or as an explicit "we sent a new code"
   message depends on the MTProto error path surfaced through `askCode`. The
   recommended interpretation is to show a message and re-render the code form
   rather than silently restarting the whole flow.

4. **`telegram.DeviceConfig` field availability**: The gotd `telegram.Options`
   struct uses a `Device telegram.DeviceConfig` field. The exact field names
   (`DeviceModel`, `AppVersion`, `SystemVersion`) should be verified against the
   version of `gotd/td` pinned in `go.mod` before implementation.
