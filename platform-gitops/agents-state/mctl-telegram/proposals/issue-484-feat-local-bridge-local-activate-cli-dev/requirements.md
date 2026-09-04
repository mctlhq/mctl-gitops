# Local Bridge: self-service `activate` CLI, device-signed daemon refresh, and the docs split

## Context

Issue #479 asked for zero-admin Local Bridge onboarding. It was split into four
sub-issues: #481 (device registry + owner send-consent tools), #482
(browser-driven activation endpoints), #483 (self-service, proof-of-possession
device credential issuance/refresh endpoints), and this one, #484, which is
supposed to close #479's ask by wiring the CLI up to what #481-#483 already
built and rewriting the two documents that describe the feature.

Reading the clone shows the server side is in fact done and tested:
`internal/oauth/local_bridge_activate.go` requires an Ed25519 `device_pubkey`
on `POST /api/local-bridge/activate/start` and rejects a request without one
(`devicePubkeyRequiredMessage`, `local_bridge_activate.go:607-658`);
`internal/oauth/local_bridge_credential.go` implements the unauthenticated,
PoP-gated `/nonce`, `/credential` and `/refresh` endpoints that turn a signed
nonce into an hours-scale device-bound worker token whose scopes are derived
fresh from `IsSendEnabled` on every refresh; `internal/mcp/tools.go` already
exposes `set_send_consent` (owner-gated, not admin-gated — see
`internal/mcp/local_bridge_owner_tools_test.go`) and
`revoke_local_bridge_device`; and `internal/bridge/hub.go` has an
`EvictDevice(userID, deviceID)` that force-drops a live daemon connection on
revocation.

The CLI has not caught up. `cmd/local/activate.go`'s `loadOrCreateDeviceKey`
(`cmd/local/config.go:121-158`) generates a 32-byte **opaque** key, not an
Ed25519 keypair, and `activateStartRequest`'s JSON body
(`cmd/local/activate.go:193-201`) never sends `device_pubkey`. Against the
server code actually in this clone, every real `activate` invocation would be
rejected with HTTP 400 and `devicePubkeyRequiredMessage` —
`cmd/local/activate_test.go` only passes because its fake server does not
enforce that field. On a successful poll, `runActivate` prints "An operator
still needs to issue this device a token" (`activate.go:110`) and stops;
it never calls `/nonce` or `/credential`. `cmd/local/daemon.go`'s
`refreshBridgeToken` (`daemon.go:59-96`) and `runDaemon`
(`daemon.go:103-138`) only know the bearer-only path: re-presenting a stored
`MCPToken` to `POST /api/bridge/token`. Nothing in `cmd/local` generates,
signs with, or persists an Ed25519 private key, and nothing calls the device
`/refresh` endpoint. `docs/local-bridge.md` and `internal/bridge/DESIGN.md`
both still describe `activate` as "does not by itself make the daemon
runnable" and list minting a worker token and turning on sending as operator
steps — which was true before #483 landed a self-service path for both, and
is now stale prose sitting next to code that already does the opposite.

This proposal closes that gap: make the CLI generate and use a real Ed25519
device identity, make `activate` walk all the way to a working credential
with zero operator calls, make `daemon` refresh itself the same way while
keeping the bearer-only path alive for existing manually-minted tokens, and
rewrite the two documents so they describe the shipped architecture instead
of the pre-#483 one.

## User stories

- AS a new Local Bridge user I WANT `init && login && activate && daemon` to
  complete onboarding on its own SO THAT I never have to ask an operator for
  anything to get a read-only daemon running.
- AS a Local Bridge user I WANT my device's private key to never leave my
  machine and my daemon credential to refresh itself automatically SO THAT I
  do not have to manually re-run `connect` before every token expiry.
- AS a Local Bridge user I WANT to grant send permission myself via
  `set_send_consent` and have my daemon's next refresh pick it up SO THAT I
  do not need an operator to flip a flag before my first real send.
- AS an operator I WANT the legacy manually-minted worker-token path to keep
  working unmodified SO THAT accounts onboarded before this change are not
  broken by it.
- AS a documentation reader I WANT `docs/local-bridge.md` and
  `internal/bridge/DESIGN.md` to describe the same, currently-shipped
  behavior SO THAT I do not follow instructions that no longer match what the
  server or the CLI actually do.

## Acceptance criteria (EARS)

- WHEN the account owner grants send consent THE SYSTEM SHALL let the next
  send from an already-running daemon succeed without the owner waiting for
  a scheduled credential refresh, restarting the daemon, or re-running
  `activate`.
- WHILE send consent is not granted THE SYSTEM SHALL bound the daemon's
  out-of-band refresh to at most one per refused send, and SHALL retry the
  send only when the refreshed credential actually gained the scope, so a
  refusal cannot be turned into an unbounded refresh loop by whoever caused
  the send attempt.
- IF the repair path's refresh does not return a well-formed credential THEN
  THE SYSTEM SHALL exit non-zero without writing a credential file.
- IF a credential already on disk names a different device than the one being
  written THEN THE SYSTEM SHALL replace it regardless of its recorded expiry,
  so a stale credential cannot veto the credential that supersedes it.
- IF the daemon finds device signing key material it cannot use THEN THE
  SYSTEM SHALL stop with a message naming the command that repairs it, and
  SHALL NOT regenerate the identity itself — re-registering a device is the
  owner's action, not a background service's.
- WHILE an activation is in progress on a machine THE SYSTEM SHALL refuse to
  start a second one on the same configuration directory, and SHALL hold the
  same exclusion against a running daemon's credential write, while neither
  holds that exclusion across a wait for human interaction, and each writer
  re-reads the device identity under that exclusion and abandons its write if
  the identity is no longer the one it acted for, so the device
  identity and the credential issued against it cannot be written by
  different runs and left mismatched.
- WHEN device signing key material is regenerated THE SYSTEM SHALL also
  rotate the device registration key, so re-registration produces a new
  device rather than returning the existing row bound to the old public
  key.
- IF a device identity file exists without USABLE signing key material —
  absent, undecodable, or of the wrong length — THEN THE SYSTEM SHALL
  regenerate it in place rather than treating either the file's presence or
  the field's presence as proof the identity is usable, and SHALL NOT pass
  unvalidated key material to a primitive that panics on a malformed key.
- WHILE a configuration directory holds a device identity but no device
  credential THE SYSTEM SHALL continue to use the legacy bearer refresh
  path, so an interrupted activation never breaks a daemon that was
  working.
- IF `activate` receives a lineage-already-claimed response and no USABLE
  device credential is on disk — absent, or present but unparseable or
  missing the fields the daemon needs — THEN THE SYSTEM SHALL obtain one
  through the proof-of-possession refresh path and persist it before reporting success,
  and SHALL NOT exit successfully leaving the machine unable to connect.
- WHEN the account owner revokes send consent THE SYSTEM SHALL refuse the
  next real send from that account, without waiting for any credential to
  expire or refresh, and the documentation SHALL describe it that way.
- WHEN this work ships THE SYSTEM SHALL contain no user-facing page that
  states Local Bridge requires an operator to enable it per account, or that
  it is not self-serve. Those claims become false with this change, and they
  are currently made on the public landing page and the public docs page —
  not only in the setup guide the issue names.
- WHILE `docs/local-bridge.md` is the single source THE SYSTEM SHALL keep
  `internal/web/local-bridge.md` byte-identical to it, since that mirror is
  what the site actually serves.
- WHEN `mctl-telegram-local activate --telegram-id <id>` runs for the first
  time THE SYSTEM SHALL generate an Ed25519 keypair, persist the private key
  at `0600`, and send the base64-encoded public key as `device_pubkey` on
  `POST /api/local-bridge/activate/start`.
- WHEN activation polling reports `status: "done"` THE SYSTEM SHALL call
  `POST /api/local-bridge/devices/{device_id}/nonce`, sign
  `device_id + "." + nonce` with the persisted Ed25519 private key, call
  `POST /api/local-bridge/devices/{device_id}/credential` with that
  `{nonce, signature}`, and persist the returned `worker_token`, `expires_at`,
  `jti` and `device_id` to disk at `0600` before exiting.
- IF the credential-issuance step fails after a successful activation THEN
  THE SYSTEM SHALL report the device as activated, explain that the
  credential step can be retried, and exit non-zero rather than silently
  discarding the device registration.
- WHEN `mctl-telegram-local daemon` starts or its current credential is
  within `tokenRefreshAdv` of expiry, AND a device private key and a
  device-issued credential are present THE SYSTEM SHALL refresh by minting a
  fresh PoP nonce, signing it, calling
  `POST /api/local-bridge/devices/{device_id}/refresh`, and exchanging the
  result for a bridge token via `POST /api/bridge/token`.
- IF no device private key is present, but a legacy `bridge_token.json` with
  an `mcp_token` is THEN THE SYSTEM SHALL fall back to the existing
  bearer-only refresh against `POST /api/bridge/token`, unchanged.
- WHILE the daemon is connected to `/bridge` THE SYSTEM SHALL NOT require any
  operator action for the credential that connection depends on to keep
  renewing, when that credential originated from `activate`.
- WHEN an account's send consent is toggled via `set_send_consent` THE SYSTEM
  SHALL reflect the new scope on the device's next `/refresh` call, without
  requiring re-activation.
- WHEN a user runs `init && login && activate && daemon` end to end for a
  brand-new Telegram id THE SYSTEM SHALL complete onboarding to a connected,
  read-only daemon with zero calls to `provision_local_account`,
  `set_account_mode`, `mint_worker_token`/`POST /api/mcp/worker-token`, or
  `set_account_send`.
- WHILE `telegram_accounts.session_encrypted` is inspected at any point in
  that end-to-end flow THE SYSTEM SHALL show it as `NULL` for an account
  provisioned purely through self-service activation.
- WHEN `docs/local-bridge.md` is read top to bottom THE SYSTEM SHALL present
  `init -> login -> activate -> daemon` as the primary, zero-admin path, with
  a distinct "Operator: support and recovery only" section covering
  `connect --token`, `mint_worker_token`/`POST /api/mcp/worker-token`,
  `set_account_mode`, and `provision_local_account`.
- WHEN `internal/bridge/DESIGN.md` is read THE SYSTEM SHALL no longer list
  "No self-serve enablement" as a remaining gap, and SHALL document the
  device-bound credential lifecycle, scope derivation from live consent
  state, revocation semantics (denylist-on-refresh plus `EvictDevice` for a
  live connection), and the legacy worker-token path's compatibility-only
  status.
- IF a manually minted legacy worker token (issued via
  `mint_worker_token`/`POST /api/mcp/worker-token`) is presented to `connect`
  and `daemon` THEN THE SYSTEM SHALL continue to authenticate, connect and
  self-renew exactly as it does today.

## Out of scope

- Any change to the server-side activation, credential-issuance, or
  send-consent endpoints themselves (#481, #482, #483) — this proposal
  consumes them as-is.
- Windows ACL hardening for the device private key file (tracked separately
  in `internal/bridge/DESIGN.md`'s existing "Windows file protection is
  unsolved" gap); the new private-key file gets the same `0600` +
  `restrictUmask()` treatment as every other file in `cmd/local`, no more and
  no less.
- Signing/notarizing released binaries.
- A `mctl-portal` "connected daemons" UI.
- Removing or deprecating the legacy `connect --token` / bearer-only refresh
  path — it must keep working through the migration window (T9).
- Rotating or re-issuing the device keypair (e.g. a `rotate-device-key`
  subcommand); a compromised device is handled today via
  `revoke_local_bridge_device` followed by a fresh `activate` run, which
  produces a new device id and keypair.

## Open questions

- Where exactly the new device-signed-credential file should live on disk
  (a new `device_credential.json`, or folding `worker_token`/`jti`/
  `device_id` into the existing `bridge_token.json` shape) is not specified
  by the issue. This proposal keeps `bridge_token.json` as the legacy
  bearer-path artifact untouched and introduces a separate file for the
  device-signed path, so the two flows never share mutable state and a
  daemon started against an old config directory unambiguously falls back to
  the legacy path. Recorded as an implementation decision, not blocked on.
- The issue does not say what `activate` should do if it is re-run after a
  device credential already exists (idempotent re-issuance vs. requiring
  `/refresh`). `POST /api/local-bridge/devices/{device_id}/credential`
  already answers this server-side: a second issuance attempt loses the
  atomic lineage claim and returns 409 telling the caller to use `/refresh`
  instead. `activate` is designed to surface that 409 as "already activated,
  run `daemon` — it will refresh automatically" rather than as a hard error.
- Whether `daemon` should proactively call `/refresh` once at startup even
  when the current device credential is not close to expiry (to pick up a
  `set_send_consent` change immediately rather than waiting for the existing
  `tokenRefreshAdv` window) is not specified. This proposal does not add that
  — it is a UX nicety, not part of #479's zero-admin closure — and records it
  here rather than silently deciding either way.
