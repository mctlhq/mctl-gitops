# Local Bridge: owner send consent, device-bound credentials, PoP refresh and revocation

## Context

Issue #483 is sub-issue 3 of 4 splitting #479 (Local Bridge / M4), and is
explicitly framed as the security core of that effort: "a mistake here is a
credential-replay bug, not a UX bug." It depends on #481 (worker-token
minting, jti/revocation infrastructure, `internal/db/local_bridge_devices`
schema and `RegisterDevice`/`RevokeDevice`/`GetDevice` primitives) and #482
(self-service device *activation*: a phishing-resistant, browser-consent-gated
flow that ends with a registered `local_bridge_devices` row and
`send_enabled=false`, and explicitly stops there — see
`internal/oauth/local_bridge_activate.go`'s package comment and
`cmd/local/activate.go`'s post-activation message: "An operator still needs
to issue this device a token ... (or, once available, a self-service
credential step lands in a later release)").

Today, after activation, a Local Bridge account is stuck: it is
`mode='local'`, `send_enabled=false`, has a registered device row, but no
usable credential except one an operator hand-mints via the admin-only
`POST /api/mcp/worker-token` (`internal/workertoken/tokenhandler.go`), and
no owner-facing way to ever turn sending on (`set_account_send` is
`admin:users`-gated — `internal/mcp/tools.go:1079`). This issue closes that
gap end to end: a non-admin owner can grant/revoke their own send capability,
a device can obtain its own bounded, device-bound credential without
touching the admin mint path, that credential can be refreshed with proof of
possession instead of being copied forward unchanged, and revoking a device
takes effect immediately rather than only at the next natural token expiry.

The `internal/auth/localjwt` and `internal/workertoken` packages already
carry forward-looking, currently-unused seams for exactly this: `Claims`
has a `DeviceID` field described as existing "so a future sub-issue can mint
a device-scoped credential" (`issuer.go:61-69`), and
`RevocationCache.Refresh`'s doc comment describes "the concrete case ...
Local Bridge: the revoke path evicts a connected daemon, the daemon
reconnects within seconds" as the exact scenario a forced cache refresh
exists to close (`revocation.go:118-124`). This design fills in those seams
rather than inventing a parallel mechanism.

## User stories

- AS the owner of a Local Bridge account I WANT to grant or revoke my own
  device's ability to send messages SO THAT I do not depend on an operator
  for a decision that only concerns my own data.
- AS a Local Bridge daemon that has just been activated I WANT to obtain a
  short-lived, device-bound credential myself SO THAT I do not need an
  operator to hand-mint one before `connect`/`daemon` work.
- AS a Local Bridge daemon with a live credential I WANT to refresh it by
  proving possession of my device key SO THAT a stolen or copied token
  cannot be renewed by anyone but the device that minted it.
- AS the owner of a Local Bridge account I WANT to revoke a specific device
  SO THAT a lost or compromised laptop stops being able to send or read my
  Telegram messages, promptly and verifiably.
- AS a security reviewer I WANT every consent, issuance, refresh and
  revocation transition to leave a distinguishable audit row SO THAT a
  credential-replay or consent-bypass incident is reconstructable after the
  fact.
- AS an operator I WANT the existing admin worker-token mint endpoint
  (`POST /api/mcp/worker-token`) to be completely unaffected by this work
  SO THAT no new path lets an end user reach it.

## Acceptance criteria (EARS)

- WHEN self-service activation (#482) completes THE SYSTEM SHALL leave
  `telegram_accounts.send_enabled=false`, unchanged from today.
- WHEN the account owner calls the new send-consent grant path for their own
  account THE SYSTEM SHALL set `send_enabled=true` for their active account
  row and record a distinguishable audit row (tool name distinct from
  `set_account_send`).
- WHEN the account owner calls the new send-consent revoke path for their
  own account THE SYSTEM SHALL set `send_enabled=false` and record a
  distinguishable audit row.
- IF a caller without an authenticated identity for the target account
  invokes the send-consent path THEN THE SYSTEM SHALL refuse it; the path
  SHALL NOT accept a `telegram_id` parameter naming a different account (no
  admin-style "target" argument exists on this tool).
- WHILE `set_account_send` is unmodified in behavior, scope gate
  (`admin:users`), and tests THE SYSTEM SHALL continue to serve it as the
  admin support/recovery path.
- WHEN a registered, unrevoked device requests its first credential through
  the new self-service issuance path, presenting valid device-bound proof of
  possession THE SYSTEM SHALL mint an hours-scale-TTL, device-bound,
  read-only-only credential — never carrying send/pin scope regardless of
  the account's current `send_enabled` value.
- IF a caller attempts self-service issuance for a `device_id` that does not
  exist, is revoked, or fails proof-of-possession verification THEN THE
  SYSTEM SHALL refuse with no credential issued and no information
  disclosed beyond "invalid or revoked device".
- WHEN a device requests a nonce for proof-of-possession THE SYSTEM SHALL
  issue a short-lived, single-use nonce scoped to that `device_id`.
- IF a nonce is presented a second time, presented after its TTL, or
  presented for a `device_id` it was not issued to THEN THE SYSTEM SHALL
  reject the refresh/issuance request.
- IF a signature does not verify against the `device_id`'s stored public key
  THEN THE SYSTEM SHALL reject the request, regardless of whether the nonce
  itself was valid.
- WHEN a device presents a valid nonce and a valid Ed25519 signature over it
  for PoP refresh THE SYSTEM SHALL load the device's current revocation
  state and the account's current `send_enabled` value from the database at
  refresh time and derive the new credential's scopes from that live state
  — THE SYSTEM SHALL NOT copy scopes forward from the previously presented
  or previously issued credential.
- WHEN the account owner grants send consent and the device next refreshes
  THE SYSTEM SHALL include send/pin scope in the refreshed credential.
- WHEN the account owner revokes send consent and the device next refreshes
  THE SYSTEM SHALL omit send/pin scope from the refreshed credential.
- WHEN the account owner revokes a specific device THE SYSTEM SHALL mark
  that device's `local_bridge_devices` row revoked, immediately reject any
  subsequent PoP issuance/refresh for that `device_id`, and immediately
  reject that device's worker-token lineage (jti) for every other endpoint
  that consults the worker-token revocation denylist.
- WHEN the revoked device has a live `/bridge` websocket connection THE
  SYSTEM SHALL actively disconnect it through the Hub as part of handling
  the revocation, rather than waiting for the connection's bridge-token TTL
  to lapse.
- WHILE the Hub eviction path is unavailable or races a concurrent reconnect
  THE SYSTEM SHALL still guarantee that no new bridge token can be issued to
  the revoked device beyond `localjwt.MaxRevocationCacheTTL` (15 s) after
  the revocation is recorded, bounding worst-case exposure of an
  already-open connection to the existing 1-hour bridge-token TTL — see
  Design's "Revocation SLA" for why this is the documented backstop rather
  than the primary mechanism.
- WHEN any of activation, consent grant, consent revoke, self-service
  issuance, PoP refresh (success or failure), or device revocation occurs
  THE SYSTEM SHALL write an audit row whose tool/event name distinguishes it
  from every other transition in this list (T10).
- WHEN audit or application logs record a request touching an activation
  code, a PoP nonce, a PoP signature, device secret material, or a minted
  worker/bridge token string THE SYSTEM SHALL redact that value before it
  reaches the log sink.
- IF a caller attempts to reach the admin worker-token mint endpoint
  (`POST /api/mcp/worker-token`) through any new route, tool, or parameter
  added by this issue THEN THE SYSTEM SHALL refuse it — no new path may
  reach that handler without the existing `admin:users` scope.

## Out of scope

- The mctl-portal "connected daemons" UI (tracked separately in
  `internal/bridge/DESIGN.md`'s cross-repo section).
- Multi-replica Hub support; this design continues to assume the documented
  single-replica (`strategy: Recreate`) deployment.
- Windows ACL hardening for on-disk device key material
  (`cmd/local/umask_windows.go` remains a no-op; tracked as its own gap in
  `internal/bridge/DESIGN.md`).
- Changing `set_account_send`'s behavior, scope gate, or tests.
- Changing the five tools that remain unsupported over the bridge
  (`edit_message`, `delete_messages`, `forward_messages`, `search_messages`,
  `set_reaction`) or the `fetch_media` restriction.
- A UI/tool for an owner to list or manage devices beyond revoke-by-id (a
  `list_local_bridge_devices` read tool is a natural, low-risk follow-up but
  is not required by #483's acceptance criteria).
- Rotating a device's Ed25519 keypair in place; losing the private key means
  re-running `activate` to register a new device (and, if desired, revoking
  the old device row).

## Open questions

- **Exact TTL/ceiling numbers for the self-service device credential.**
  The issue only says "hours-scale". This design proposes default 6h /
  ceiling 24h (distinct from the admin mint's 30-day default / 90-day
  ceiling in `internal/workertoken/tokenhandler.go`), chosen so the daemon
  refreshes often enough that a revoke-then-refresh window stays tight, but
  not so often that a laptop asleep overnight is forced through a fresh
  PoP flow before its first tool call resumes it. Proceeding with 6h/24h;
  trivially tunable constants if reviewers want different numbers.
- **Whether send-consent grant should route through a browser confirmation
  page (like activation's consent step) rather than a bare MCP tool call.**
  Activation added a browser consent step specifically to defend against a
  *third party* naming the victim's `telegram_id` from outside the victim's
  own session. Send-consent has no such third-party angle — the caller is
  already the authenticated owner's own MCP session — so this design treats
  it as parallel to the existing `enable_access` checkbox
  (`internal/db/store.go:759`'s doc comment), i.e. a same-session action, not
  a separate identity-proving step. If reviewers want the extra ceremony
  (e.g. because a prompt-injected AI client could call the tool without a
  human actually reading a confirmation), it can be layered on later as a
  stricter successor tool without breaking this one's contract.
- **Whether device revocation should also be reachable by an admin for a
  device the admin does not own**, mirroring `set_account_send` /
  `set_account_mode`'s admin-recovery pattern. The issue frames revocation
  as "owner-controlled" like consent; this design ships the owner path only
  and leaves an admin-initiated device revocation (e.g. for abuse response)
  as a follow-up, since `RevokeDevice` in `internal/db/local_bridge_devices.go`
  already accepts an arbitrary `deviceID` and needs no schema change to
  support that later.
- **Nonce storage: in-memory vs. persisted.** This design keeps PoP nonces
  in-memory (mirroring `localBridgeActivation`'s transient-state pattern in
  `internal/oauth/local_bridge_activate.go`) rather than adding a database
  table, since nonces live for seconds and a lost nonce on pod restart only
  costs the daemon one retried refresh. If the relay is ever run at more
  than one replica (out of scope here, and already a known constraint per
  `internal/bridge/DESIGN.md`), in-memory nonces would need to move to a
  shared store at the same time the Hub singleton assumption is revisited.
