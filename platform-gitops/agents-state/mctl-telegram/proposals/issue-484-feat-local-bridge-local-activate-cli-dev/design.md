# Design: issue-484-feat-local-bridge-local-activate-cli-dev

## Current state

The server-side self-service primitives from #481-#483 exist, but #484 is not only a client/docs wiring issue anymore.

### Shipped primitives

- `local_bridge_devices` stores device public key, credential lineage, and revocation state.
- `POST /api/local-bridge/activate/start` requires a base64 Ed25519 `device_pubkey`.
- `/api/local-bridge/devices/{device_id}/nonce`, `/credential`, and `/refresh` implement PoP-gated first issuance and refresh.
- Refresh derives scopes from current `send_enabled`; first issuance remains read-only.
- Device credentials use the device audience and are excluded from legacy bearer renew.
- `/api/bridge/token` derives the websocket token and carries `DeviceID`, lineage JTI, and original-issued-at state forward.
- `set_send_consent` and `revoke_local_bridge_device` are owner-callable.
- Revocation deny-lists the lineage and attempts live bridge eviction by exact `(userID, deviceID)`.

### Client/product gaps

- `cmd/local/config.go` currently persists only an opaque `device_registration_key`; there is no Ed25519 signing identity.
- `cmd/local/activate.go` does not send `device_pubkey` and therefore cannot complete against the current server contract.
- `activate` stops after browser activation and still tells the user an operator must mint a token.
- `daemon` only knows the legacy bearer-to-bridge-token exchange and never performs PoP refresh.
- Product/docs still teach the operator-first setup path.

### Remaining merged runtime defect from #483

`internal/bridge/hub.go` still has a connection-lifecycle race. `Hub.Call` obtains a `*daemonConn` while holding `h.mu`, releases the mutex, and later sends to `dc.send`. `EvictDevice`, `Register` replacement, `Unregister`, or `UnregisterSend` can close that same channel after the reference escapes the lock. A concurrent `Call` can therefore panic with `send on closed channel` and crash the process. This is a correctness/security availability blocker for final Local Bridge completion and is part of #484 now.

## Proposed solution

### 1. Persist a real device identity

Keep the existing registration idempotency key and extend the same local identity artifact to include an Ed25519 keypair.

- Generate with `ed25519.GenerateKey(rand.Reader)` on first use.
- Persist `device_registration_key`, `private_key`, and `public_key` together.
- Store private key material at `0600` using the existing atomic write and process umask helpers.
- Reuse the identity verbatim on later `activate` runs.
- Never transmit the private key; only the public key and signatures leave the machine.

This keeps server registration idempotency and PoP identity as distinct concepts while binding repeated activation attempts to the same device identity.

### 2. Make `activate` finish credential bootstrap

`activateStartRequest` gains `device_pubkey`.

After browser consent/poll returns `device_id`, the CLI performs:

1. request a nonce for the device;
2. sign `device_id + "." + nonce` with the persisted Ed25519 private key;
3. call `/credential` with `{nonce, signature}`;
4. persist `{device_id, worker_token, expires_at, jti}` in a device-specific credential artifact;
5. print the next user action (`daemon`) rather than an operator step.

If activation succeeded but credential bootstrap fails, keep the local identity and report a retryable post-activation error. On an already-claimed lineage, transition to the device refresh path rather than treating it as an unrecoverable error.

A separate device-credential artifact is preferred over overloading the existing legacy `bridge_token.json`, because the two credential lineages have different refresh semantics and downgrade behavior must remain explicit.

### 3. Device-signed daemon refresh, including expired-access recovery

For the device path, `daemon` must treat possession of the device private key as the durable refresh authority. The previous access JWT is an output/cache of that authority, not a prerequisite for re-establishing it.

Device refresh flow:

1. obtain `/nonce` using only `device_id`;
2. sign the challenge locally;
3. call `/refresh` with PoP;
4. receive a fresh device worker credential with scopes derived from live consent state;
5. exchange it at `/api/bridge/token`;
6. connect/reconnect websocket with the new bridge token.

The flow must work even when the prior device access JWT is already expired. If the current implementation accidentally requires a valid access bearer for nonce or refresh, adjust that server boundary narrowly so PoP remains the authentication mechanism. Preserve indistinguishable failure behavior for unknown/revoked/bad-signature devices and do not reopen the nonce-capacity DoS fixed after #483.

Legacy fallback remains file/lineage based:

- device identity + device credential present -> device PoP path only;
- only legacy bearer artifacts present -> existing bearer-only bridge token renewal unchanged;
- device path present but revoked/corrupt -> fail explicitly; never silently downgrade to legacy.

### 4. Fix Hub connection lifecycle instead of recovering panics

Replace channel-close ownership with a lifecycle model that is safe for concurrent senders.

Recommended shape:

- `daemonConn` owns a dedicated `done`/cancellation signal.
- Transport teardown closes/cancels `done` exactly once.
- `Hub.Call` selects between enqueueing work and connection completion; it never sends to a channel that another goroutine may close underneath it.
- Outbound queue ownership must be single-owner or remain unclosed; closure signaling belongs to `done`/context.
- `Register` replacement, `Unregister`, `UnregisterSend`, and `EvictDevice` all use the same teardown primitive.
- Pending call cleanup happens when the connection is canceled so callers do not hang indefinitely.
- `EvictDevice` keeps exact device targeting and immediate revocation semantics.

Do not use `recover` as the primary fix. The invariant is: once a connection is retired, new/in-flight calls observe cancellation or a normal error, never process panic or delivery to a superseded daemon.

### 5. Product onboarding becomes self-service first

Update the user-facing Local Bridge landing/connect/onboarding surface, not only markdown docs.

Primary path shown to a fresh user:

`init -> login -> activate -> daemon`

Then explain:

- first device credential is read-only;
- owner explicitly grants send through `set_send_consent`;
- daemon picks up send scopes on next PoP refresh;
- revocation kills future refresh/reconnect and evicts the live device connection;
- no hosted MTProto session is created/stored for the self-service path.

Operator/manual-token steps are moved under support/recovery/migration. The UI must not imply `provision_local_account`, `set_account_mode`, `set_account_send`, or manual worker-token minting is required for a fresh Local Bridge user.

### 6. Documentation alignment

`docs/local-bridge.md`:

- split **Client / owner actions** from **Operator: support and recovery only**;
- make self-service setup the first path;
- document device key, PoP refresh, expired-access recovery, owner send consent, revocation, legacy compatibility, and no hosted session;
- keep every command/flag/route aligned with actual CLI behavior.

`internal/bridge/DESIGN.md`:

- close "No self-serve enablement";
- distinguish device-bound self-service credentials from legacy manually minted worker tokens;
- document bootstrap trust, first issuance vs refresh, stable lineage, live-state scope derivation, derived bridge tokens, denylist and live eviction;
- explicitly document the safe `daemonConn` lifecycle after the Hub race fix;
- state the final revocation SLA and failure semantics.

## Security invariants

1. Device private key never leaves the client machine.
2. Unknown/revoked/bad-signature PoP failures stay externally indistinguishable.
3. Bogus device IDs cannot consume bounded pending nonce state or evict legitimate nonces.
4. Device refresh scopes are derived from current DB state, never copied from stale JWT scopes.
5. Device audience cannot use the legacy bearer renew endpoint.
6. Credential lineage JTI remains stable across device refresh so one revocation kills the full lineage.
7. DeviceID propagates into bridge token and websocket registration so revocation targets the correct live daemon.
8. Hub teardown cannot race with `Call` into `send on closed channel` or route to a superseded connection.
9. Device-signed refresh remains possible after prior access JWT expiry.
10. Fresh self-service onboarding never creates/stores a hosted MTProto session.

## Tests

### T7 zero-admin E2E

Fresh config -> `init` -> local Telegram `login` -> `activate` -> read -> owner `set_send_consent` -> forced refresh -> send -> daemon reconnect/restart. Assert `telegram_accounts.session_encrypted IS NULL` throughout and assert no operator/admin endpoints/tools are invoked.

### T8 hosted/migration regression

Existing hosted fresh-user and hosted->local migration behavior remains unchanged.

### T9 legacy bearer regression

Operator-minted legacy worker token still supports `connect`, daemon bridge-token refresh, and reconnect.

### T10 activation idempotency

Repeated activation reuses the same registration key/keypair/device and handles already-claimed lineage via refresh semantics.

### T11 product/docs contract

CLI examples are executable/flag-valid and the landing/connect/onboarding surface presents self-service first. Legacy/admin content is support/migration only.

### T12 Hub lifecycle race

Add deterministic concurrency tests for `Hub.Call` racing each close/replace path (`EvictDevice`, `Register` replacement, `Unregister`, `UnregisterSend`). No panic, no send-to-closed, no stuck pending call, no request delivered to a retired connection. Run affected package under `go test -race`.

### T13 expired-access PoP refresh

Issue a device credential, expire/advance beyond its JWT expiry, then prove that nonce -> signed refresh -> bridge-token exchange -> reconnect succeeds with no valid old bearer and no operator action.

### T14 live consent scope derivation

Toggle owner send consent, force device refresh, and verify new credential scopes reflect current DB state while the old credential remains unchanged.

### T15 local key permissions

Private identity artifact is `0600` and reused on restart.

## Rollback

- Protocol changes should remain additive.
- Reverting #484 may remove the new CLI/device path; legacy bearer recovery remains available.
- No DB rollback is expected unless the narrow expired-access fix requires an additive server change; such a change must remain backward-compatible.
- Documentation/product onboarding rolls back with the code to avoid advertising unavailable behavior.
- The Hub lifecycle fix is safe to retain independently because it corrects a general process-crash race shared by existing close paths.

## Closure

#484 is not complete until T7, T11, T12, and T13 are green. #479 must remain open until #484 is merged and the final zero-admin E2E is green.