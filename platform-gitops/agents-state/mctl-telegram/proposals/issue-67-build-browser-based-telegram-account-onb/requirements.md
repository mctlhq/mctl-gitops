# Browser-Based Telegram Account Onboarding Flow (/telegram/connect)

## Context

New users of mctl-telegram currently must run the `cmd/login` CLI tool inside a
running pod (requiring a PTY and `kubectl exec`) to authenticate their Telegram
account via MTProto. This is a hard blocker for self-service client onboarding:
operators cannot hand a URL to a user and have them connect autonomously.

The service already implements a complete Telegram OIDC authorization code flow
in `internal/oauth/server.go` and an in-browser MTProto session setup wizard
(phone number + SMS code + optional 2FA cloud password) in
`internal/oauth/enable_access.go`. These components are wired as part of the
Claude.ai MCP connector OAuth handshake; there is no standalone entry point a
user can reach without Claude.ai already being configured. This proposal adds
`GET /telegram/connect` as that entry point, making the full onboarding
self-contained in a browser.

## User stories

- AS a new client user I WANT to open a URL in my browser and connect my
  Telegram account SO THAT I can complete onboarding without CLI access or
  operator assistance.
- AS an operator I WANT to share a single URL (`/telegram/connect`) with new
  users SO THAT I do not need to schedule a kubectl-exec session for each one.
- AS a user I WANT to see a clear success or error state after connecting SO
  THAT I know whether I should proceed to Claude.ai or try again.
- AS a user with Telegram two-step verification enabled I WANT the browser flow
  to accept my 2FA cloud password SO THAT I am not blocked from connecting.

## Acceptance criteria (EARS)

### Landing page
- WHEN a user navigates to `GET /telegram/connect` THE SYSTEM SHALL render an
  HTML page (no JavaScript required) that explains the connection process and
  presents a single "Connect with Telegram" button.
- WHEN the connect page is rendered THE SYSTEM SHALL generate a server-side
  PKCE verifier + challenge pair and a random state token, store them in
  memory keyed by state, and embed the resulting `/oauth/authorize` URL in
  the button's href so that clicking it initiates the OIDC flow.
- WHILE `AUTH_MODE` is not `local-jwt` THE SYSTEM SHALL respond to
  `GET /telegram/connect` with HTTP 404 (the route is only meaningful when the
  OAuth issuer is active).

### OIDC and MTProto session setup
- WHEN the user clicks "Connect with Telegram" THE SYSTEM SHALL redirect the
  browser to `/oauth/authorize` using the built-in `mctl_self_connect` client
  id and a `redirect_uri` of `{issuer}/telegram/connect/done`.
- WHEN Telegram OIDC returns successfully and the user has no active MTProto
  session THE SYSTEM SHALL display the existing enable_access phone-number
  screen (rendered by `renderEnablePhone` in `internal/oauth/enable_access_page.go`).
- WHEN Telegram OIDC returns successfully and the user already has a valid
  MTProto session THE SYSTEM SHALL redirect directly to
  `{issuer}/telegram/connect/done` without entering the enable_access wizard.
- WHEN the user submits a valid phone number via the enable_access form THE
  SYSTEM SHALL send the Telegram login code and show the code-entry screen.
- WHEN the user submits the correct SMS code THE SYSTEM SHALL finalize the
  MTProto session and redirect to `{issuer}/telegram/connect/done`.
- IF the user's Telegram account has two-step verification enabled THEN THE
  SYSTEM SHALL show the 2FA cloud-password screen before finalizing the
  session.

### Success and error pages
- WHEN the user reaches `GET /telegram/connect/done` with a valid state and
  authorization code THE SYSTEM SHALL exchange the code for an access token
  (using the stored PKCE verifier), confirm success, and render an HTML page
  that tells the user their account is connected and provides a link to the
  Claude.ai connector setup page.
- WHEN the user reaches `GET /telegram/connect/done` with an unknown or
  expired state THE SYSTEM SHALL render the enable_access error page with a
  message directing the user to restart the flow.
- IF the Telegram OIDC callback returns an error parameter THEN THE SYSTEM
  SHALL render the error page with a human-readable message and a link back
  to `/telegram/connect`.
- IF the MTProto login fails at any step (bad code, bad password, network
  timeout) THE SYSTEM SHALL display the existing enable_access error
  messaging and allow the user to start again.

### Security and invariants
- WHILE a connect session is pending THE SYSTEM SHALL enforce the same
  PKCE-S256 requirement as `handleAuthorize` in `internal/oauth/server.go`.
- WHILE a connect session is pending THE SYSTEM SHALL bound pending sessions
  with the same `CodeTTL` window used by the main OAuth authorize flow
  (default 10 minutes).
- THE SYSTEM SHALL apply `Content-Security-Policy: default-src 'none'` (or
  a nonce-scoped variant for any inline script) to all pages in the connect
  flow, matching the policy in `renderEnable` in
  `internal/oauth/enable_access_page.go`.
- THE SYSTEM SHALL NOT log the user's phone number, SMS code, or 2FA password
  (enforced by the existing `internal/audit/redact.go` handler and by
  `telegram.Login` never embedding them in error strings).
- WHEN a connect session has been consumed or has expired THE SYSTEM SHALL
  delete it from the in-memory map so it cannot be replayed.

## Out of scope

- Issuing a persistent access token or refresh token to the browser; the connect
  flow only provisions the MTProto session — token issuance is for Claude.ai.
- Building a new MTProto authentication mechanism; the existing
  `telegram.Login` function in `internal/telegram/login.go` is used unchanged.
- Connecting a local-mode account via the Local Bridge websocket; that path is
  for daemon registration, not initial MTProto authentication.
- Any operator-facing admin UI for approving connected accounts; the existing
  `users.access_tier` column and admin MCP tools handle that out-of-band.
- Changes to the Claude.ai-driven OAuth flow; all existing routes remain
  unmodified.

## Open questions

1. **Local Bridge mention in the issue.** The issue body says the MTProto
   session setup should happen "via the local-bridge websocket (already
   implemented)". The bridge package (`internal/bridge/`) is for routing MCP
   tool calls to a local daemon; it is not the authentication mechanism. The
   existing `enable_access` flow in `internal/oauth/enable_access.go` is the
   correct in-browser session provisioner for hosted-mode accounts. This
   proposal interprets the issue as describing the enable_access flow and
   ignores the bridge reference. If hosted-mode MTProto sessions are
   intentionally out of scope and only local-mode (bridge-connected) accounts
   should onboard via `/telegram/connect`, the design changes significantly
   and requires clarification from the issue author.

2. **Claude.ai link target on the success page.** The issue asks for "a link
   back to Claude.ai connector setup" but does not specify the URL. This
   proposal links to `https://claude.ai/settings/integrations` as the most
   likely destination; the operator may want this configurable.

3. **Access tier gate.** Today, `handleTelegramCallback` directs users who
   will receive no scopes straight to `issueAuthCode` rather than to
   enable_access. A user who is neither an admin nor in the client tier can
   complete Telegram OIDC but cannot use any MCP tools. Should `/telegram/connect`
   still provision their MTProto session (so they are ready when an operator
   grants them a tier), or should it show an "access not granted" page? This
   proposal assumes the same logic as the existing callback: everyone who is
   not a scoped user skips enable_access and the success page tells them to
   contact the operator for access.
