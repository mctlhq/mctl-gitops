# Local Bridge: self-service device activation via Telegram OIDC

## Context
Local Bridge (M4, see `internal/bridge/DESIGN.md`) lets a user run their Telegram
MTProto session on their own machine instead of on tg.mctl.ai. Turning the mode
on is still an operator action: `docs/local-bridge.md` step 1 requires an
operator to call the admin-only `provision_local_account` or `set_account_mode`
MCP tool before a user can run `connect`/`daemon`. Issue #479 tracked making
onboarding fully self-service; it was split into four sub-issues, and this is
sub-issue 2 (#482), which removes exactly that operator step for the identity
and device-registration part of onboarding. It depends on #481 (already
merged), which added the `local_bridge_devices` table and
`Store.RegisterDevice`/`GetDevice`/`RevokeDevice`/`TouchDeviceLastSeen`, built
specifically so this issue would have "a stable Store surface to build on"
(`internal/db/local_bridge_devices.go:22`).

The issue asks for two things: (1) an identity-matching design that reuses
`internal/auth/telegramoidc.Authenticator` — the same OIDC Relying Party
`internal/oauth.Server` already uses for the ordinary Telegram sign-in at
`/oauth/authorize` + `/oauth/telegram/callback` — instead of inventing a second
way to prove someone controls a Telegram account; and (2)
`POST /api/local-bridge/activate/start` / `POST /api/local-bridge/activate/poll`
plus the browser page(s) that carry out the actual Telegram sign-in. Credential
issuance (minting something the CLI can use to call `connect`) is explicitly
sub-issue 3 and stays out of scope here: this issue only gets a user from "I
have a phone and a CLI" to "I have a `telegram_accounts` row in local mode and a
`local_bridge_devices` row", with `send_enabled=false` throughout.

## User stories
- AS a new mctl-telegram user with no existing hosted account AS I WANT to run
  the Local Bridge CLI and approve my own device from my phone/browser SO THAT
  I do not have to find an operator and hand them my Telegram id before I can
  start.
- AS an operator I WANT self-service activation to be impossible to complete
  for the wrong Telegram account, and to leave zero trace when it is refused,
  SO THAT I do not have to audit failed activation attempts for data leakage
  or orphaned rows.
- AS a user retrying a failed or interrupted activation (bad network, closed
  browser tab) I WANT to run the same CLI command again SO THAT I get exactly
  one account and one device, not duplicates.

## Acceptance criteria (EARS)
- WHEN a client calls `POST /api/local-bridge/activate/start` with a claimed
  `telegram_id` and a `device_id`, and no bearer token, THE SYSTEM SHALL
  accept the request and return a `device_code`, a `verification_uri` (and a
  `verification_uri_complete` that embeds the code), an `expires_in`, and a
  poll `interval`, without requiring any worker token, bridge token, hosted
  session, or authenticated MCP session.
- WHEN a browser opens the verification URL, THE SYSTEM SHALL redirect it
  through `internal/auth/telegramoidc.Authenticator`'s Authorization
  Code + PKCE flow against Telegram's own OIDC provider — the identical
  code path `internal/oauth.Server` uses for `/oauth/authorize` — rather than
  a second, bespoke identity check.
- WHEN the Telegram OIDC callback returns a verified identity whose
  `TelegramID` differs from the `telegram_id` the CLI claimed at `start`, THE
  SYSTEM SHALL mark the activation `denied` and SHALL NOT write, update, or
  delete any row in `users`, `telegram_accounts`, or `local_bridge_devices`.
- WHEN the verified identity matches the claimed `telegram_id` and that
  Telegram id already has an active **hosted** `telegram_accounts` row, THE
  SYSTEM SHALL refuse the activation (`denied`, reason identifies the account
  as hosted) and SHALL NOT create or modify any `telegram_accounts` or
  `local_bridge_devices` row.
- WHEN the verified identity matches the claimed `telegram_id` and no active
  `telegram_accounts` row exists for it, THE SYSTEM SHALL create exactly one
  `telegram_accounts` row with `mode='local'`, `session_encrypted=NULL`, and
  `send_enabled=false`, and exactly one `local_bridge_devices` row for that
  user.
- WHEN the same `device_id` is used to retry `start` after a first activation
  already completed (or after a network failure before the CLI learned the
  outcome) for the same Telegram identity, THE SYSTEM SHALL NOT create a
  second `telegram_accounts` row or a second `local_bridge_devices` row for
  that device — the retry resolves to the same rows.
- WHEN a client calls `POST /api/local-bridge/activate/poll` with a
  `device_code` whose activation has not yet reached a browser outcome, THE
  SYSTEM SHALL respond `{"status":"pending"}`.
- WHEN a client polls a `device_code` whose activation was refused, THE SYSTEM
  SHALL respond `{"status":"denied", ...}` with a reason that does not leak
  whether the mismatch was "wrong Telegram account" vs. some other refusal in
  a way that would help an attacker fingerprint valid `telegram_id`s beyond
  what the hosted/local distinction already exposes.
- WHEN a client polls a `device_code` whose activation completed, THE SYSTEM
  SHALL respond `{"status":"done", "device_id": ...}` and SHALL NOT include
  any bearer token, worker token, or other credential capable of sending a
  message (out of scope; see below).
- WHILE `local-bridge/activate/start` has not been followed by a matching
  browser approval, THE SYSTEM SHALL leave `send_enabled=false` and
  `session_encrypted=NULL` for the account (no code path in this proposal
  ever sets either to anything else).
- IF a `device_code` or the browser verification link is older than its TTL,
  THEN THE SYSTEM SHALL treat it as expired: `poll` returns an error the CLI
  can distinguish from `pending`/`denied`/`done`, and the browser page shows a
  "start over" message instead of silently accepting a stale code.
- IF the Telegram OIDC exchange itself fails (network error, invalid code,
  user cancelled), THEN THE SYSTEM SHALL mark the activation `denied` with no
  database mutation beyond the activation's own transient in-memory state.

## Out of scope
- Minting any credential (worker token, bridge token, or otherwise) as part of
  `start`/`poll`/the browser flow — that is sub-issue 3 ("send consent and
  credential issuance"). After this issue, a self-service-activated account
  exists in local mode with a registered device, but the CLI still cannot
  `connect`/`daemon` until an operator (or, once sub-issue 3 ships,
  self-service) issues it a token.
- Turning `send_enabled` on. It stays `false` for every account this flow
  touches, matching `provision_local_account`'s existing default.
- Binding a device public key to the `local_bridge_devices` row. The issue
  text mentions the CLI supplying "a device id / public key"; today's schema
  (issue #481) has no column for a public key and no acceptance criterion here
  requires verifying a signature. See Open Questions.
- Any change to the existing `/oauth/authorize` MCP-client login flow's
  observable behavior for `pending.Purpose`-less requests, or to
  `enable_access`. Both are extended structurally (new sibling state next to
  `s.pending`/`s.enables`) but their own request/response contracts are
  untouched.
- A `mctl-web`/portal UI for activation. The browser surface here is a plain
  server-rendered page in `internal/oauth` (or `internal/web`), matching how
  `/telegram/connect` and the `enable_access` wizard are already rendered.
- Multi-replica correctness for the transient activation state (see design.md
  Platform impact) — this mirrors the existing, documented, single-replica
  limitation of `internal/oauth.Server`'s `pending`/`enables` maps.

## Open questions
- **Device public key.** The issue's scope line says the CLI starts activation
  with "a device id / public key". `local_bridge_devices` (issue #481) has no
  public-key column, and no Definition-of-Done item in #482 requires verifying
  a signature anywhere in this flow. Interpretation taken here: `device_id` is
  an opaque, CLI-chosen local identifier reused verbatim as the
  `RegisterDevice` idempotency key (so a retried `start` collapses onto the
  same device row); any public-key/challenge-response binding is deferred to
  a later issue. Flagged rather than silently dropped.
- **Redirect URI reuse.** `telegramoidc.Authenticator.AuthCodeURL` always
  redirects back to the single `RedirectURL` baked into the `telegramoidc.Client`
  at boot (`TELEGRAM_OIDC_REDIRECT_URL` today points at
  `/oauth/telegram/callback`). This proposal therefore routes the activation's
  Telegram-leg callback through that *same* existing endpoint (correlated by
  the OIDC `state`) rather than registering a second callback path, since
  minting a second `telegramoidc.Client` with a different `RedirectURL` would
  require registering a second redirect URI with Telegram/BotFather, which is
  outside this repo's control and unverified. If Telegram OIDC does support
  multiple redirect URIs per client, a dedicated
  `/local-bridge/activate/telegram/callback` would be a cleaner long-term
  separation from the MCP login path — left as a follow-up, not a blocker.
- **Short human-typable code.** RFC 8628 device flows normally pair a long
  `device_code` (machine-to-machine) with a short `user_code` (for manual
  entry when a QR/link isn't available). This proposal's `verification_uri_complete`
  embeds the long `device_code` directly and does not add a separate short
  code, to keep the surface area small. If manual entry turns out to matter in
  practice, adding a short code is additive and does not change `poll`'s
  contract.
- None of the above blocks implementation; each has a concrete default taken
  in design.md.
