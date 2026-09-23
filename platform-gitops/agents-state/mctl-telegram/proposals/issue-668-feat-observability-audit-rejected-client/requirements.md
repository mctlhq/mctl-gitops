# Observability: audit rejected client registrations, attribute auth failures, show onboarding stage in the digest

## Context

A 2026-09-23 review of 48 h of production pod logs and 14 d of `audit_logs`
found four operator-visibility blind spots in `mctl-telegram`. None is a
behavioural bug: the service does the right thing in every case, but the
record it leaves behind does not let an operator tell one outcome from
another. A rejected dynamic client registration (`POST /oauth/register`)
writes no audit line at all, so 464 refused attempts from one client in 48 h
were invisible until someone read `validateRedirectURIShape` by hand. An
`auth failed` WARN carries only `err`, so a benign expired-token retry and a
credential-stuffing burst produce byte-identical lines. The daily digest
prints a flat `no session` for every row that never finished onboarding,
collapsing "never started", "hit FLOOD_WAIT eleven times" and "revoked the
session from Telegram settings" into one string. And an abandoned onboarding
— a user who walks away at the SMS-code prompt — is logged at ERROR, which
makes a real login failure unalertable.

The four items are filed and implemented together because each is a handful
of lines in a different package, and they share one motivation: make the data
the service already produces answer the question an operator actually asks.
The work is additive — new log attributes, one new counter, one new read
query, one severity reclassification. No request handling, no auth decision
and no OAuth policy changes.

## User stories

- AS an operator I WANT every `/oauth/register` refusal recorded with its
  reason, the client name and the redirect URI's scheme and host SO THAT I
  can see which clients are being locked out and why, without reading the
  validator source.
- AS an operator I WANT a graphable counter of registration outcomes SO THAT
  a regression in the redirect-URI validator that silently refuses every
  client raises an alert instead of waiting for a support ticket.
- AS an operator I WANT `auth failed` lines to carry the rejected token's
  `sub`, `client_id`, `jti` and `exp` plus the edge request id and route SO
  THAT I can tell one client re-using a stale token from many clients
  presenting invalid ones.
- AS an operator reading the daily digest I WANT each `no session` row to
  name the last onboarding step it reached SO THAT I can tell "never started"
  from "stuck at the code prompt" from "FLOOD_WAIT" without querying
  `audit_logs` by hand.
- AS an on-call engineer I WANT abandoned onboarding logged at WARN with a
  distinct message SO THAT ERROR in the login path means a genuine failure
  and can be alerted on.

## Acceptance criteria (EARS)

### 1. Rejected client registrations

- WHEN `handleClientRegistration` refuses a request for any reason other than
  rate limiting THE SYSTEM SHALL emit exactly one
  `oauth: client_registration audit` line with `outcome=rejected`, a `reason`
  token, `client_name`, `user_agent`, and — when the refusal concerns a
  redirect URI — `redirect_scheme` and `redirect_host`.
- WHILE emitting a rejection audit line THE SYSTEM SHALL NOT include the full
  redirect URI, its path, its query string or the request body.
- IF a redirect URI cannot be parsed at all THEN THE SYSTEM SHALL emit the
  audit line with `redirect_scheme` and `redirect_host` empty rather than
  falling back to logging the raw string.
- WHEN any `/oauth/register` call reaches a terminal outcome THE SYSTEM SHALL
  increment `mctl_oauth_client_registrations_total{outcome,reason}` exactly
  once, where `outcome` is one of `accepted`, `rejected`, `rate_limited`,
  `error`.
- WHILE labelling that counter THE SYSTEM SHALL draw `reason` from a closed,
  compile-time set of tokens (`ok`, `rate_limited`, `malformed_body`,
  `no_redirect_uris`, `too_many_redirect_uris`, `redirect_uri_too_long`,
  `redirect_scheme_not_allowed`, `redirect_host_not_allowed`,
  `redirect_userinfo`, `redirect_backslash`, `redirect_unparseable`,
  `persist_failed`) so a client-supplied string can never create a new label
  value.
- WHEN a registration is accepted THE SYSTEM SHALL keep emitting the existing
  `outcome=accepted` line unchanged in its existing fields.
- WHEN a registration is rate-limited THE SYSTEM SHALL keep emitting
  `outcome=rate_limited` and SHALL NOT add the caller's IP to it.

### 2. Attributed auth failures

- WHEN token verification fails *after* the HMAC signature has been verified
  (expired, wrong issuer, audience mismatch, revoked) THE SYSTEM SHALL log
  `auth failed` with `sub`, `client_id`, `jti` and `exp` taken from the
  verified claims, omitting any of those that the token did not carry.
- IF token verification fails at or before the signature check (malformed
  JWT, bad signature, malformed payload, non-Bearer scheme) THEN THE SYSTEM
  SHALL NOT log any claim value, because the payload is unauthenticated
  attacker-controlled input.
- WHEN any request fails authentication THE SYSTEM SHALL include
  `edge_request_id` and `edge_route` derived from `edgectx.FromRequest`, and
  SHALL include the request route pattern.
- WHILE logging an attributed failure THE SYSTEM SHALL NOT log the token
  itself, the raw `Authorization` header, or `tg_username`.
- WHEN an authentication failure is counted THE SYSTEM SHALL continue to use
  the existing `mctl_auth_failures_total{reason,provider}` family and SHALL
  NOT introduce a second, parallel counter.

### 3. Onboarding stage in the digest

- WHEN the daily digest renders a row whose `HasSession` is false THE SYSTEM
  SHALL append the user's most recent `connect:*` audit step and its
  timestamp, e.g. `no session — last: phone_submitted 14:28`.
- WHEN that most recent step is an error row THE SYSTEM SHALL render the full
  `connect:failed:<reason>` suffix, e.g. `no session — last: failed:flood_wait`.
- IF a `no session` row has no `connect:*` audit rows at all THEN THE SYSTEM
  SHALL render `no session — last: never started`.
- WHEN a `no session` row's most recent `telegram_accounts` row was revoked
  with a recorded reason THE SYSTEM SHALL append ` — session revoked (<reason>)`.
- WHILE building the digest THE SYSTEM SHALL issue at most one additional
  database query beyond the existing `ListIdentities` scan, keyed by the
  Telegram ids of the rows actually being rendered.
- IF that additional query fails or times out THEN THE SYSTEM SHALL log a
  warning and send the digest with the pre-existing plain `no session` text
  rather than skipping the send.
- WHILE rendering the digest THE SYSTEM SHALL NOT include any audit row's
  `peer_redacted` or `error` column, only the `tool_name` step and its time.

### 4. Abandoned onboarding is not an ERROR

- WHEN the `startLoginFlow` goroutine terminates because its `CodeTTL`
  deadline expired while waiting for a user-supplied code or password THE
  SYSTEM SHALL log `enable: onboarding abandoned` at WARN with `uid`,
  `step` and `elapsed`.
- WHEN that goroutine terminates because a later `/start` re-submission
  cancelled it THE SYSTEM SHALL log `enable: login flow superseded` at INFO
  with `uid` and `step`, not an error.
- IF the goroutine terminates with any other non-nil error THEN THE SYSTEM
  SHALL keep logging `enable: telegram login failed` at ERROR with its
  existing fields.
- WHEN the goroutine terminates successfully THE SYSTEM SHALL keep logging
  `enable: telegram login succeeded` at INFO unchanged.
- WHILE tracking the step reached THE SYSTEM SHALL write it only from the
  login goroutine itself, so no synchronisation primitive is required.

## Out of scope

- Deciding whether private-use URI schemes from native clients (RFC 8252
  §7.1, e.g. `cursor://`) should be accepted at registration. This proposal
  makes the current refusal *visible and countable*; it does not change
  `validateRedirectURIShape` or `validateImplicitRedirectURI` policy by one
  character. That decision is the issue's own stated open question for the
  owner.
- Persisting rejected registrations as `audit_logs` rows. `/oauth/register`
  is unauthenticated and has no `user_id`, and `LogToolCall` is a
  per-user hash-chained writer — an unauthenticated caller must not be able
  to append to any user's chain. Rejections stay in the structured pod log
  plus the Prometheus counter.
- Adding correlation columns to `connect:*` audit rows. `LogToolCall`'s
  documented contract is that NULL correlation means "not an MCP call
  through the portal path"; wiring the OAuth web handlers into `edgectx` is
  a separate change with its own decision (see the comment at
  `internal/db/store.go:1723`).
- Alert rules in `deploy/alerts/mctl-telegram.rules.yaml`. The new counter is
  made available and documented; choosing thresholds is a follow-up once a
  baseline exists.
- Any change to the digest's schedule, recipients, reachability suffix, or
  the `ListIdentities` query itself.
- Backfilling the new `telegram_accounts.revoked_reason` column for sessions
  revoked before this change.

## Open questions

- **Metric naming.** The issue proposes `mctl_telegram_oauth_registrations_total`
  and `mctl_telegram_auth_failures_total`. Neither matches this repository's
  convention: `internal/metrics/metrics.go` reserves the `mctl_telegram_`
  prefix for MTProto-subsystem metrics (`mctl_telegram_client_pool_size`,
  `mctl_telegram_flood_wait_events_total`) and uses a bare `mctl_` prefix for
  everything else (`mctl_oauth_pending_auth_size`, `mctl_auth_failures_total`).
  This proposal therefore uses **`mctl_oauth_client_registrations_total`** and
  reuses the existing `mctl_auth_failures_total`. If the operator wants the
  literal names from the issue, say so before implementation — renaming an
  exported metric after it ships costs a dashboard migration.
- **The auth-failures counter already exists.** `mctl_auth_failures_total{reason,provider}`
  is already incremented at `internal/auth/middleware.go:98` with a
  nine-value `reason` set from `classifyAuthError`. Item 2's counter request
  is therefore already satisfied; only the *log attribution* half is new.
  Proceeding on that reading.
- **`revoked_reason` does not exist on `telegram_accounts`.** The column
  lives on `oauth_refresh_tokens` and `local_bridge_devices`
  (`internal/db/db.go:594`, `:627`), not on `telegram_accounts`
  (`internal/db/db.go:551-564`). `RevokeSessionByID` already *accepts* a
  `reason` argument and discards it except as a metric label
  (`internal/db/store.go:899`). Item 3's "session revoked" suffix therefore
  needs a column added via the existing `addColumnIfMissing` migration helper
  plus a one-line persist in the three revoke paths. Proceeding on that
  reading; the suffix renders for post-change revocations only.
- **`no session` rows outside the 24 h window.** The digest only ever renders
  rows created in the last 24 h, so the connect-step lookup is bounded by
  that set. If the operator later wants the suffix on the full identity list
  (`list_telegram_identities`), that is a separate, unbounded query and is
  not assumed here.
- **Rendering the step's timestamp.** The issue's example shows `14:28` —
  a bare UTC `HH:MM`. Adopted, since every digest row is by construction
  inside the last 24 h so a date adds nothing.
