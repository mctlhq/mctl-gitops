# Record acquisition source (UTM + referrer) at sign-up

## Context

Issue mctlhq/mctl-telegram#1072. mctl-telegram records how a user authenticated (`users.identity_source = telegram_oidc`), but not how they found the service. No UTM parameter, referrer or landing page is stored anywhere. The daily digest (`internal/digest/digest.go`) reports about 5 new clients a day, but nobody can tell which post, article, directory listing or MCP client produced them. The 7-day retention figures measured on 2026-11-01 (32 sign-ups, 20 tool-call users, 10 users active on 2+ days) only become actionable once they can be sliced by source.

The source cannot be read at the OAuth callback. The sign-in round-trips through Telegram OIDC (`/oauth/authorize` -> oauth.telegram.org -> `/oauth/telegram/callback`), so the Referer at the callback is Telegram, and MCP clients often open `/oauth/authorize` with no useful referrer. The proposal therefore captures the source at the first page a human lands on (the public content pages on tg.mctl.ai), carries it in a signed first-party cookie and then in the pending-auth entry, and persists it once, only when the `users` row is created. It keeps three outcomes apart: attributed, `direct` and `unknown`. Each must be stated, never inferred from another.

## User stories

- AS the operator I WANT each new user's first-touch source (UTM, referrer host, landing path, MCP client) recorded at sign-up SO THAT I can tell which channels produce users.
- AS the operator I WANT the daily digest to show a `src=` label per new client SO THAT each day's sign-ups are attributable at a glance.
- AS the operator I WANT an admin-only query that groups 7-day sign-ups, tool-call users and 2+ active-day users by source SO THAT I can compare retention across channels.
- AS a user I WANT only coarse, non-identifying source data stored (no IP, no user agent, no referrer path), disclosed on the privacy page and erased when I delete my account SO THAT attribution does not become tracking.

## Acceptance criteria (EARS)

Capture (first touch)
- WHEN a browser GETs a public content page (landing `/`, `/docs`, `/demo`, `/security`, `/privacy`, `/terms`, `/platforms`, `/assistants`, `/local-bridge`, product updates) without a valid acquisition cookie THE SYSTEM SHALL set a signed `mctl_acq` cookie holding the five whitelisted UTM keys present on the URL, the Referer host and the landing path.
- WHILE a valid, unexpired `mctl_acq` cookie is present THE SYSTEM SHALL NOT overwrite it on later page views, including views with different UTM parameters (first touch wins).
- THE SYSTEM SHALL accept only `utm_source`, `utm_medium`, `utm_campaign`, `utm_content` and `utm_term`, strip control characters from each value and truncate each to 100 characters (runes) before signing.
- THE SYSTEM SHALL store only the referrer host, lowercased and without port, path or query. It SHALL treat a referrer whose host is the service's own public host as no referrer.
- THE SYSTEM SHALL store the landing path without its query string, truncated to 200 characters.
- THE SYSTEM SHALL record a capture with no UTM values and no external referrer as state `direct`.
- THE SYSTEM SHALL NOT store or derive an IP address, user agent or any fingerprint for acquisition.
- THE SYSTEM SHALL make the cookie first-party, `HttpOnly`, `Secure` (when the public base URL is https), `SameSite=Lax`, `Path=/`, and give it a TTL of 24 hours. It SHALL sign the cookie with HMAC-SHA256 under a key derived from the OAuth JWT secret, with a dedicated HKDF info label.

Carry through the OAuth round-trip
- WHEN `/oauth/authorize` creates a pending-auth entry THE SYSTEM SHALL attach an acquisition snapshot: the verified cookie contents with state `attributed` or `direct`, or state `unknown` when the cookie is missing, has a bad signature, is malformed, is oversized or has expired. In every case the snapshot SHALL include the bounded `mcp_client` label derived from the authorize request.
- THE SYSTEM SHALL persist the snapshot with the pending entry in both the DB-backed (`oauth_pending_auth`) and in-memory (`pendingAuth`) modes.

Persist at user creation
- WHEN `EnsureUserByTelegramCapture` creates a new `users` row and an acquisition snapshot is supplied THE SYSTEM SHALL insert exactly one `user_acquisition` row for that user, in the same transaction as the user INSERT.
- WHEN `EnsureUserByTelegramCapture` finds an existing user THE SYSTEM SHALL NOT insert or update any `user_acquisition` row.
- IF the `user_acquisition` insert fails THEN THE SYSTEM SHALL log the failure without the cookie value or UTM values, increment a failure counter, keep the user row, complete the sign-in, and leave the acquisition row absent. It SHALL never write `direct` in its place.
- THE SYSTEM SHALL NEVER write state `direct` for a sign-up whose cookie was missing or invalid, and SHALL NEVER write state `unknown` for a sign-up whose capture ran and observed no source.
- WHEN a Local Bridge activation creates a user THE SYSTEM SHALL write a `user_acquisition` row with state `unknown` and `mcp_client = local-bridge`.

Reporting
- WHEN the daily digest renders a new client THE SYSTEM SHALL append `src=<label>`. The label is `utm_source` if set, else `referrer_host`, else `direct`, `unknown`, or `unknown (pre-capture)` when the user predates the capture epoch and has no row. Any other user with no row is labelled `unknown (not recorded)`.
- THE SYSTEM SHALL sanitize every acquisition value before rendering it in the digest or an admin tool. It SHALL strip control characters and bidi overrides and bound the length, and SHALL emit JSON-encoded output from the admin tool.
- WHEN an admin with scope `admin:users` or `admin:users:read` calls `get_acquisition_report` THE SYSTEM SHALL return, per source label, for users created in the window (default 7 days, max 90): sign-ups, users with at least one tool call, and users with tool calls on 2 or more distinct UTC days.
- IF the caller lacks those scopes THEN THE SYSTEM SHALL refuse the call with the existing `requireAnyScope` error.

Deletion and disclosure
- WHEN `HardDeleteAccount` runs for a user THE SYSTEM SHALL delete that user's `user_acquisition` row in the same transaction.
- THE SYSTEM SHALL declare `user_acquisition.user_id` with `REFERENCES users(id) ON DELETE CASCADE`.
- THE SYSTEM SHALL update `internal/web/privacy.html` in the same PR to disclose the `mctl_acq` cookie and the stored fields, and to correct the current statement that no cookies are set for analytics.

## Out of scope

- Third-party analytics scripts or pixels. The existing self-hosted Umami is unchanged.
- Backfilling historical users. They have no row and report as `unknown (pre-capture)`.
- Per-request tracking after sign-up, and any update of the acquisition row after creation.
- Capturing on `/oauth/enable*` and `/telegram/connect` pages. These run after the user row already exists, so a capture there could never reach the creation write (see design.md).
- Parsing a Telegram bot `start` payload. No bot-start sign-up path exists in the current code.

## Open questions

- Cookie TTL. The issue says "short TTL" without a number. This proposal uses 24 hours so that a reader who lands from a post and connects an MCP client later the same day keeps attribution. A shorter TTL (for example 1 hour) moves more sign-ups into `unknown`.
- `mcp_client` source. The issue says "from the authorize client_id". The proposal reuses `connectfunnel.ClientLabel(redirect_uri)`, the bounded label already used by `connect_first_call`. Recording raw CIMD client_id URLs would be unbounded and is not done.
- The issue says "same transaction" and also "failed write must not fail sign-in". The proposal reconciles the two with a SAVEPOINT around the acquisition insert. If the reviewer prefers a separate best-effort statement after the user INSERT, the observable contract is the same, but a crash between the two statements leaves the row absent.
- Users created by the non-capture paths (`EnsureUserByTelegramID` in `internal/auth/localjwt`, the worker-token path, `internal/mcp/tools.go`) get no row and report as `unknown (not recorded)`. Wiring them is not proposed.
- The sanitized cookie bytes still go to the browser. Signing prevents forgery, but a user can always clear the cookie and re-land with chosen UTM values. This is an accepted limit of client-carried attribution.
