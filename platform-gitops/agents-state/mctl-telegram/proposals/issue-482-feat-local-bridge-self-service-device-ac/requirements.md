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
- AS a Telegram user who is sent an unsolicited "connect your account" link I
  WANT signing in to be insufficient to register anything SO THAT clicking a
  stranger's link and logging in as myself cannot silently attach that
  stranger's device to my account.
- AS a user retrying a failed or interrupted activation (bad network, closed
  browser tab) I WANT to run the same CLI command again SO THAT I get exactly
  one account and one device, not duplicates.

## Acceptance criteria (EARS)
- WHEN a client calls `POST /api/local-bridge/activate/start` with a claimed
  `telegram_id` and a `device_registration_key`, and no bearer token, THE SYSTEM SHALL
  accept the request and return a `device_code`, a short human-typable
  `user_code`, a `verification_uri`, an `expires_in`, and a poll `interval`,
  without requiring any worker token, bridge token, hosted session, or
  authenticated MCP session.
- THE SYSTEM SHALL NOT return, and the browser flow SHALL NOT accept, any URL
  that carries the `device_code` or the `user_code` as a query parameter —
  there is no `verification_uri_complete`. The `verification_uri` SHALL be a
  constant path with no activation-identifying parameter, and the only way to
  bind a browser session to an activation SHALL be the user typing the
  `user_code` their own CLI printed. Rationale: a link that carries the code
  is a link an attacker can send to a victim, which is precisely the
  phishing vector this flow must not have.
- WHEN a browser opens the verification URL, THE SYSTEM SHALL render a form
  asking for the `user_code` and SHALL NOT start any Telegram OIDC leg until
  a `user_code` matching a live `pending` activation has been submitted.
- WHEN a submitted `user_code` matches a live `pending` activation, THE
  SYSTEM SHALL redirect the browser through
  `internal/auth/telegramoidc.Authenticator`'s Authorization Code + PKCE flow
  against Telegram's own OIDC provider — the identical code path
  `internal/oauth.Server` uses for `/oauth/authorize` — rather than a second,
  bespoke identity check.
- WHEN the Telegram OIDC callback returns a verified identity that matches
  the claimed `telegram_id`, THE SYSTEM SHALL render a consent page naming
  the device and the account, and SHALL NOT create, update, or delete any row
  in `users`, `telegram_accounts`, or `local_bridge_devices` until the signed-in
  browser submits an explicit, CSRF-protected approval from that page.
  Completing the Telegram sign-in SHALL NOT by itself constitute approval:
  proving who you are and agreeing to register someone's device on your
  account are two separate acts, and only the second one authorises a write.
- IF the consent page is declined, or abandoned until the activation's TTL
  expires, THEN THE SYSTEM SHALL mark the activation `denied` and SHALL leave
  the database untouched.
- THE SYSTEM SHALL rate-limit **failed** `user_code` submissions server-side,
  keyed by client IP, and SHALL reject further submissions from an exhausted
  key with the same generic message it returns for a wrong code. The limit
  SHALL NOT be a per-activation counter (a wrong guess matches no activation,
  so there is nothing to decrement) nor a per-browser-session counter (an
  attacker discards the session).
- THE SYSTEM SHALL resolve a submitted `user_code`, and likewise a submitted
  consent form, to its activation in constant time, without scanning the set
  of pending activations, so that repeated invalid submissions cannot become
  lock contention against unrelated OAuth and poll traffic. The rate limit on
  failed submissions SHALL cover the consent endpoint as well as the code
  form.
- WHEN the browser is redirected to Telegram OIDC for an activation, THE
  SYSTEM SHALL bind that redirect to the browser that submitted the
  `user_code` — via a `HttpOnly`, `Secure`, `SameSite=Lax` cookie carrying
  the OIDC `state` (or a hash of it) — and SHALL refuse an activation
  callback whose cookie is missing or does not match the `state` in the URL.
  Without this the `user_code` step is bypassable: the attacker types their
  own code in their own browser, captures the resulting Telegram
  authorization URL, and forwards *that* to the victim, whose sign-in then
  lands on the attacker's activation having never seen the code form.
- WHEN an activation is resolved (`done` or `denied`), THE SYSTEM SHALL make
  it unreachable from the browser while keeping it pollable by
  `device_code` until its TTL expires, so the CLI can still read the outcome
  and collect its `device_id`. A resolved activation SHALL NOT be reported to
  `poll` as unknown.
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
- WHEN the same `device_registration_key` is used to retry `start` after a first
  activation already completed (or after a network failure before the CLI learned
  the outcome) for the same Telegram identity, THE SYSTEM SHALL NOT create a
  second `telegram_accounts` row or a second `local_bridge_devices` row for
  that device — the retry resolves to the same rows, and `poll` returns the
  same `device_id` as the first activation.
- THE SYSTEM SHALL treat `device_registration_key` and `device_id` as two
  distinct values that are never interchangeable: `device_registration_key` is
  chosen by the CLI and is only ever `RegisterDevice`'s idempotency key, while
  `device_id` is the server-generated registry identifier (`dev_<32 hex>`,
  minted inside `RegisterDevice` from `crypto/rand`) that `poll` returns. No
  request field SHALL be named `device_id`, and no response SHALL echo the
  client's key back under that name.
- WHEN a client calls `POST /api/local-bridge/activate/poll` with a
  `device_code` whose activation has not yet reached a browser outcome, THE
  SYSTEM SHALL respond `{"status":"pending"}`.
- WHEN a client polls a `device_code` whose activation was refused, THE SYSTEM
  SHALL respond `{"status":"denied", ...}` with a reason that does not leak
  whether the mismatch was "wrong Telegram account" vs. some other refusal in
  a way that would help an attacker fingerprint valid `telegram_id`s beyond
  what the hosted/local distinction already exposes.
- WHEN a client polls a `device_code` whose activation completed, THE SYSTEM
  SHALL respond `{"status":"done", "device_id": ...}` where `device_id` is the
  server-generated registry identifier returned by `Store.RegisterDevice` — not
  the `device_registration_key` the CLI supplied — and SHALL NOT include
  any bearer token, worker token, or other credential capable of sending a
  message (out of scope; see below). This is the value the CLI persists and the
  value issue #483 binds credentials and proof-of-possession refresh to.
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
- THE SYSTEM SHALL read and write every field of an activation's shared state
  under the same `Server` mutex that already guards `pending` and `enables`.
  No handler SHALL read or mutate an activation without holding it — the
  activation is reachable concurrently from `poll`, from the browser leg, and
  from the sweeper, so an unsynchronised access is a data race, not a
  theoretical one.
- THE SYSTEM SHALL resolve each activation at most once: a transition to
  `done` or `denied` SHALL be applied only if the activation is still
  unresolved when the mutex is held, and a second browser leg arriving for an
  already-resolved activation SHALL be refused without touching the database.
- WHEN an approval is accepted, THE SYSTEM SHALL claim the activation — mark
  it in-progress and invalidate the consent token — while still holding the
  mutex, before performing any database call, so that a double-clicked
  approval or a concurrently replayed token results in exactly one
  provisioning run and one device row.
- THE SYSTEM SHALL carry the whole OIDC-verified identity on the activation,
  not merely the verified Telegram id, because the approval arrives as a
  separate request; an account SHALL NOT be provisioned with empty username
  or display name because those fields were left behind in the callback.
- WHEN a browser leg is started for an activation that already has an
  in-flight OIDC `state`, THE SYSTEM SHALL either refuse the new leg or remove
  the superseded `activationsByState` entry before recording the new one, so
  that no map entry is left behind to be swept only by TTL.
- THE SYSTEM SHALL have its activation tests run under the Go race detector
  in CI, including at least one test that drives `poll` concurrently with the
  browser leg.

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
  a signature anywhere in this flow. **Resolved by the operator:** the
  CLI-supplied value is an opaque idempotency key and is named
  `device_registration_key` on the wire, *not* `device_id` — reusing that name
  for two different values would hand issue #484's CLI two candidates for "the
  device id" to persist, and #483 binds proof-of-possession to the registry id
  specifically. The registry `device_id` stays server-generated, as
  `RegisterDevice` already implements it on main. Any public-key /
  challenge-response binding is deferred to #483, which also adds the
  public-key column (`addColumnIfMissing`); nothing here verifies a signature.
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
- ~~**Short human-typable code.**~~ **Resolved — the `user_code` is
  mandatory, and `verification_uri_complete` is removed.** The earlier draft
  of this proposal embedded the long `device_code` in a
  `verification_uri_complete` and skipped the short code "to keep the surface
  area small". That was wrong, and it was a security hole, not a UX
  simplification: since `start` is unauthenticated by design, an attacker
  could call it with a *victim's* `telegram_id` and the attacker's own
  `device_registration_key`, then send the victim the resulting
  `verification_uri_complete`. The victim opens it, is redirected straight
  into Telegram OIDC, signs in successfully — and because the verified
  identity then equals the claimed `telegram_id`, the proposal's
  "mismatch → zero writes" guard never fires. There is no mismatch. The
  attacker's device ends up registered on the victim's account, and once
  issue #483 binds credentials and proof-of-possession refresh to that
  `device_id`, that is durable account takeover.
  The short `user_code` is the actual defence, and it is why RFC 8628 has
  one: the code lives on the screen of the person who started the flow, so an
  attacker cannot put their code in front of a victim. Combined with the
  explicit consent step above (identity proof and authorisation are separate
  acts), the flow now requires the victim to both possess the attacker's code
  and knowingly approve an unfamiliar device. See design.md for the shape.
- None of the above blocks implementation; each has a concrete default taken
  in design.md.
