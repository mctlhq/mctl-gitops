# Issue #484 contract hardening addendum

This addendum is normative for issue `mctlhq/mctl-telegram#484` and overrides any contradictory wording in the accepted proposal files. It exists because the proposal was approved before the post-#483 hardening review completed. Implementers and reviewers MUST apply this file together with `requirements.md`, `design.md`, and `tasks.md`.

## Required overrides

### 1. Device-path daemon refreshes at startup

For a usable device-bound identity/credential path, `daemon` MUST perform one proof-of-possession refresh during startup before deriving the bridge token and connecting. Runtime refresh remains expiry-driven after startup.

The device private key is the durable refresh authority. Startup refresh re-derives scopes from current owner consent and proves the client does not depend on the previous access JWT still being valid.

Legacy bearer-only configurations retain their existing behavior.

### 2. Expired access JWT is not a refresh prerequisite

The zero-admin device path MUST obtain a PoP nonce and complete device-signed `/refresh` after the previous device access JWT has expired. No operator/admin action, manually minted bearer, or still-valid old access JWT may be required as a prerequisite.

If the current server boundary requires the old access JWT for nonce/refresh, change that boundary narrowly while preserving unknown-device, revoked-device, bad-signature, nonce replay/capacity, and authorization protections.

Required regression: expire the current device access JWT, then successfully execute nonce -> signed `/refresh` -> `/api/bridge/token` -> websocket reconnect with no valid old bearer.

### 3. Send-consent ordering

The zero-admin end-to-end contract is:

`fresh install -> init -> local Telegram login -> activate -> read -> explicit owner send consent -> device refresh -> send -> daemon reconnect/restart`

The send assertion MUST use a credential refreshed after the owner consent change. A test or implementation that places the send before refresh does not satisfy this contract.

### 4. Hub lifecycle race is a hard blocker

`Hub.Call` MUST be safe when racing all connection retirement paths: `EvictDevice`, `Register` replacement, `Unregister`, and `UnregisterSend`.

The implementation MUST NOT rely on panic recovery around a send to a potentially closed channel. Use a lifecycle primitive safe for concurrent senders, such as a `done`/cancellation signal plus a non-closing outbound queue, or an equivalent design.

Required behavior under teardown races:

- no `send on closed channel` panic;
- no permanently blocked pending call;
- no delivery to a retired/superseded daemon connection;
- racing callers receive the normal no-daemon/connection-retired error;
- exact `(userID, deviceID)` eviction semantics remain intact.

Required tests include deterministic interleavings for every close/replace path and the affected bridge tests under `go test -race`.

Issue #484 and umbrella #479 MUST NOT close while this race remains reproducible. Issue #495 may implement the fix separately, but its merged result is a mandatory closure gate.

### 5. Zero-admin is the primary product path

All user-facing Local Bridge landing/connect/onboarding surfaces MUST present `init -> login -> activate -> daemon` as the primary/default flow. Operator provisioning, manual worker-token minting, `set_account_mode`, and admin send toggles are support/recovery/migration compatibility only and MUST NOT be presented as normal fresh-user onboarding.

`docs/local-bridge.md`, its served web mirror, landing/docs pages, and `internal/bridge/DESIGN.md` must agree with the shipped runtime behavior.

### 6. Device secrets are persisted at 0600

Every local artifact containing device private key material OR bearer credential material (`worker_token`, device credential, bridge/MCP credential metadata sufficient to authenticate) MUST be written atomically and with mode `0600` on POSIX-permission-respecting filesystems. The permission regression must cover the actual credential-bearing record, not only the private-key fields.

## Closure gate

#484 is complete only when all of the following are true:

- zero-admin `init -> login -> activate -> daemon` works for a fresh Telegram identity;
- `telegram_accounts.session_encrypted` remains `NULL` throughout the local-only flow;
- startup PoP refresh works;
- refresh/reconnect works after previous access-JWT expiry without operator recovery;
- owner send consent is reflected through a subsequent device refresh before send succeeds;
- Hub lifecycle race coverage passes deterministically and under `go test -race`;
- legacy manually minted worker-token and hosted/migration paths still pass;
- product/docs surface presents zero-admin as primary;
- credential-bearing local records are protected at `0600`.

Only after those gates pass may #484 close, and only after the full E2E closure gate may #479 close.
