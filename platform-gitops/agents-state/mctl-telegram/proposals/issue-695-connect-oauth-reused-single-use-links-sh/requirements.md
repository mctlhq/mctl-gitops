# Observable and recoverable connect/OAuth failures

## Context

On 2026-09-27 a newly signed-up user reported that the connector "kept
failing" while the backend was healthy the whole time: every MCP tool call
returned `ok` and the canary stayed green. The user really did see error
pages, but the pod logs recorded none of them — the only trace was
Cloudflare analytics for `tg.mctl.ai`. Three separate gaps combined to
produce that: the single-use state in `HandleConnectDone`
(`internal/web/connect.go`) and `handleTelegramCallback`
(`internal/oauth/server.go`) is consumed on first use, so a refresh, a back
button, a reopened tab or a link prefetcher renders a bare 400 even though
the user is already connected; neither handler emits any log line on those
4xx branches, so the failures are invisible server-side; and
`shortReason` (`internal/oauth/enable_access.go`) has no case for a wrong
2FA password or for Telegram's `AUTH_RESTART`, so both were recorded as
`connect:failed:unknown` and the page said only "The password was not
accepted: ...".

This proposal makes those failures observable and recoverable. It is
deliberately scoped to logging, classification and friendly recovery
pages: no change to how state is minted, to PKCE, to the Telegram OIDC
exchange, or to who is authorized. The one behavioural change with
security surface — treating a prefetch GET as non-consuming — is narrowed
to the two single-use routes and gated on request headers only.

## User stories

- AS a newly connected user I WANT a reopened or refreshed connect link to
  take me to my session page SO THAT I do not conclude the service is
  broken when it has already worked.
- AS a user whose two-step verification password was wrong I WANT the page
  to say exactly that SO THAT I retype the password instead of restarting
  the whole flow.
- AS an operator I WANT every 4xx on the connect and callback routes to
  appear in the pod logs with a stable machine-readable reason SO THAT I
  can diagnose a user report without asking Cloudflare.
- AS an operator I WANT enable-login failures classified in the audit log
  SO THAT `connect:failed:bad_password` and `connect:failed:auth_restart`
  are distinguishable from a genuinely unknown failure.
- AS a user who configured a client with `https://tg.mctl.ai/` instead of
  `https://tg.mctl.ai/mcp` I WANT the response to name the correct URL SO
  THAT I can fix my own configuration.
- AS a user whose browser or a crawler prefetches my connect link I WANT
  the prefetch not to burn my single-use state SO THAT my own click still
  works.

## Acceptance criteria (EARS)

Logging

- WHEN `HandleConnectDone` rejects a request because `state` or `code` is
  absent THE SYSTEM SHALL emit exactly one WARN log line with
  `reason="missing_state"`.
- WHEN `HandleConnectDone` rejects a request because the `state` is not in
  `ConnectServer.sessions` THE SYSTEM SHALL emit exactly one WARN log line
  with `reason="unknown_state"`.
- WHEN `HandleConnectDone` rejects a request because the pending session is
  older than `codeTTL` THE SYSTEM SHALL emit exactly one WARN log line with
  `reason="expired_state"`.
- WHEN `ExchangeConnect` returns an error in `HandleConnectDone` THE SYSTEM
  SHALL emit exactly one log line with `reason="exchange_failed"`.
- WHEN `handleTelegramCallback` rejects a request for a missing, unknown or
  expired `state` THE SYSTEM SHALL emit exactly one WARN log line with
  `reason` set to `missing_state`, `unknown_state` or `expired_state`
  respectively.
- WHILE emitting any of these log lines THE SYSTEM SHALL NOT include the
  value of `code`, `state`, the `mctl_connect_token` cookie, a phone
  number or a password in any attribute.
- WHEN one of these log lines is emitted THE SYSTEM SHALL include the
  route, the `reason`, and the request's `Sec-Purpose`/`Purpose` prefetch
  classification as a boolean, and nothing that identifies the user beyond
  what the existing `internal/audit/redact.go` handler already permits.

Recovery from a reused link

- IF `/telegram/connect/done` is reached with an unknown or already-consumed
  `state` AND the request carries an `mctl_connect_token` cookie that
  verifies against the configured issuer and secret THEN THE SYSTEM SHALL
  respond `303 See Other` to `/telegram/connect/manage` instead of
  rendering a 400 page.
- IF `/telegram/connect/done` is reached with an unknown or already-consumed
  `state` AND no valid `mctl_connect_token` cookie is present THEN THE
  SYSTEM SHALL render an HTML page stating that the link was already used,
  carrying a button to `/telegram/connect`, and SHALL use status `200`
  rather than `400` so that the page is not reported as a server error by
  intermediaries.
- IF `/oauth/telegram/callback` is reached with an unknown or already-consumed
  `state` THEN THE SYSTEM SHALL render the same "this link was already
  used" HTML page (via the existing `renderEnableError` chrome) instead of
  the current `http.Error(w, "unknown or expired state", 400)` plain-text
  body.
- WHILE handling a reused-link request THE SYSTEM SHALL NOT mint a new
  authorization code, a new access token or a new refresh token, and SHALL
  NOT alter any row in `users`, `sessions` or the audit chain.

Login failure classification

- WHEN `telegram.Login` fails because the two-step verification password was
  rejected THE SYSTEM SHALL record the audit `tool_name`
  `connect:failed:bad_password` and SHALL render the message "That
  two-step verification password was not accepted. Check it and try
  again." on the password screen, keeping the user on the password step
  rather than bouncing them back to the phone step.
- WHEN `telegram.Login` fails with a Telegram RPC error whose message is
  `AUTH_RESTART` THE SYSTEM SHALL record the audit `tool_name`
  `connect:failed:auth_restart` and SHALL render a message inviting the
  user to submit their phone number again, on the phone step with the
  phone field pre-filled.
- WHILE classifying a login failure THE SYSTEM SHALL keep every existing
  `shortReason` mapping (`phone_invalid`, `code_invalid`, `code_expired`,
  `flood_wait`, `timeout`, `local_mode_active`, `identity_mismatch`,
  `identity_cleanup_timeout`) unchanged.
- IF a login error matches none of the known classifications THEN THE SYSTEM
  SHALL keep recording `connect:failed:unknown`.

Root-path hint

- WHEN a request arrives as `POST /` THE SYSTEM SHALL respond with a JSON
  body naming the configured MCP path (`cfg.MCPPath`) as the correct
  endpoint, instead of chi's bare `405` with an empty body.
- WHILE answering `POST /` THE SYSTEM SHALL keep `GET /` serving the
  existing landing page from `web.Landing` unchanged.

Prefetch safety

- IF a request to `/telegram/connect/done` or `/oauth/telegram/callback`
  carries `Sec-Purpose: prefetch` (or a `Sec-Purpose` value containing
  `prefetch`) or `Purpose: prefetch` THEN THE SYSTEM SHALL NOT consume the
  pending state, SHALL NOT perform any token exchange, and SHALL respond
  `204 No Content` with `Cache-Control: no-store`.
- WHILE a prefetch request is refused THE SYSTEM SHALL emit one INFO log
  line with `reason="prefetch_refused"` and SHALL leave the pending entry
  usable by the subsequent real request.

## Out of scope

- Making connect state multi-use, or re-issuing a fresh authorization code
  from a reused link. State stays single-use; only the presentation and the
  recovery path change.
- Requiring a POST (user gesture) before state is consumed. Telegram's OIDC
  provider 302-redirects the browser to `/oauth/telegram/callback` with a
  GET, so that route cannot become POST-only without changing the
  registered redirect contract with Telegram; see Open questions.
- Any change to `/oauth/token`, `/oauth/revoke`, `/oauth/register`, PKCE
  verification, refresh-token derivation, or scope resolution.
- The two abandoned claude.ai authorizations at 18:31 and 18:34 in the
  issue (claude.ai never called `/oauth/token`). The issue itself records
  these as client-side abandonment, not a defect here.
- The `405` responses on `GET /oauth/telegram/enable_access/*`. Those
  routes are POST-only by design and are only reached by a crawler
  replaying a URL; they carry no user-visible flow.
- Attributing the shared-IP `Claude-User` traffic to a specific user. The
  issue states Anthropic IPs are shared and this is not attributable.
- Changing the `mctl_connect_token` cookie's `Path`, lifetime or flags.

## Open questions

- The exact Go error for a rejected 2FA password. The issue observed the
  string `sign in with password: invalid password`, which is a
  `gotd/td` wrapping ("sign in with password") around an inner error; the
  module source is not available in this read-only clone, so it is not
  confirmed whether the inner error is a `*tgerr.Error` with message
  `PASSWORD_HASH_INVALID` or a plain sentinel. Proceeding with a
  classification that matches both: a `tgerr` message of
  `PASSWORD_HASH_INVALID` and, as a fallback, a case-insensitive substring
  match on `invalid password`. The implementer must confirm against
  `gotd/td v0.161.0` and prefer `errors.Is`/`errors.As` on whatever
  sentinel actually exists, adding the substring arm only if no sentinel
  is exported.
- Whether `AUTH_RESTART` should transparently restart the flow server-side
  (re-issue `SendCode` without asking the user again) rather than returning
  the user to a pre-filled phone step. Transparent restart risks a silent
  second `auth.sendCode` against the shared `TG_API_ID` flood budget, which
  `LoginConfig.GlobalMiddleware` exists to protect. Proceeding with the
  explicit, user-visible restart; the issue's phrase "restart the flow
  cleanly" is satisfied by a clean phone step rather than a hidden retry.
- Whether the reused-link recovery page should be `200` or keep `400`. The
  issue only says "not on a 400 page" for the connected case. Proceeding
  with `200` for the recovery page (a correct answer to a well-formed
  request about an expired link) while keeping `400` for genuinely
  malformed requests such as a missing `state` on `/oauth/telegram/callback`.
- Whether `POST /` should be `404` with a body or a JSON-RPC error object.
  Proceeding with a JSON-RPC 2.0 error object under HTTP `405` (keeping the
  status a client can already interpret, adding the body it currently
  lacks), because the caller in the incident was an MCP client speaking
  JSON-RPC.
- Whether prefetch refusal should be `204` or a `200` HTML page. Proceeding
  with `204`: it is unambiguous to a prefetcher and cannot be cached as the
  real page.
