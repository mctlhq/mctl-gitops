# Design: issue-479-feat-local-bridge-make-onboarding-fully

## Goal

Make Local Bridge onboarding fully self-service for a brand-new user while
preserving the privacy boundary that the MTProto session never leaves the
user's machine. Normal onboarding must require zero operator/admin actions.
Existing hosted accounts, hosted-to-local migration, and manually provisioned
Local Bridge installs remain supported as compatibility/support paths.

## Existing building blocks

The repository already has the primitives needed for this design:

- `internal/auth/telegramoidc` provides a server-verified Telegram identity
  without requiring a hosted MTProto session.
- `Store.ProvisionLocalAccount` can create `mode='local'` accounts with
  `session_encrypted=NULL` and `send_enabled=false`.
- `Store.SetSendEnabled` is the existing account send flag used by both admin
  and hosted self-service flows.
- `internal/auth/localjwt`, `internal/workertoken`, and
  `internal/bridge/tokenhandler.go` already provide JWT mint/verify,
  revocation, bridge-token exchange, and daemon renewal patterns.
- `cmd/local` already owns the local Telegram login/session and daemon
  lifecycle.

The change should reuse these primitives rather than introduce a parallel
identity or token system.

## Target flow

The fresh-user happy path is:

```text
mctl-telegram-local init
mctl-telegram-local login
mctl-telegram-local activate
mctl-telegram-local daemon
```

`login` remains fully local. The server never receives MTProto session bytes.
`activate` bootstraps server-side ownership/account/device state and returns a
short-lived Local Bridge access credential.

### 1. Activation bootstrap and trust boundary

`activate` starts a device-authorization-style transaction with only:

- the Telegram id learned from the already-authenticated local MTProto login;
- a generated `device_id`;
- the device public key.

The CLI MUST NOT need a pre-existing worker token, bridge token, hosted
Telegram session, or authenticated MCP session to start activation. Requiring
one would make self-service bootstrap circular.

The server returns a short-lived device code and verification URL. The user
opens that URL and completes the existing Telegram OIDC flow. OIDC is the
server-side authority for Telegram ownership. The server compares the
OIDC-proven Telegram id with the id reported by the local client. A mismatch
fails closed with no account/device mutation.

After a successful match the server creates or reconciles the local account:

```text
mode = local
session_encrypted = NULL
send_enabled = false
```

Activation is idempotent for the same owner/device/account. An existing hosted
account is never silently migrated; the existing operator-mediated
`set_account_mode` path remains the supported migration mechanism.

### 2. Device binding

Add `local_bridge_devices` as the durable device identity and revocation
anchor. It stores at minimum:

```text
device_id
user_id
telegram_user_id
public_key
created_at
last_refreshed_at / last_seen_at
revoked_at
```

The client generates an Ed25519 keypair locally. The private key never leaves
the device and is persisted using the same restrictive local-secret handling
used by existing `cmd/local` configuration (`0600`, atomic write; encrypted
where the existing local secret storage supports encryption).

### 3. Read-only activation and owner-controlled send consent

Activation ALWAYS finishes read-only. It does not accept a shortcut that
turns `send_enabled=true` as part of account creation.

Sending is enabled only by a distinct explicit owner action after activation.
The owner may later revoke that consent through the same self-service surface.
Both grant and revoke are audited and operate only on the caller's own account.

The existing admin `set_account_send` remains available for support/recovery,
but it is never a mandatory onboarding step.

This separation makes the invariant easy to reason about and test:

```text
activation -> read works, send_enabled=false
owner grant -> send_enabled=true
owner revoke -> send_enabled=false
```

### 4. Automatic short-lived credentials

Successful activation automatically mints a device-bound Local Bridge access
credential. The credential lifetime is measured in hours, not the current
30-90 day worker-token range. The exact TTL is a configuration/tuning choice;
the daemon must refresh automatically before expiry.

Existing manually minted `purpose="local-bridge"` worker tokens remain valid
for a migration/support window and keep their current legacy renewal behavior.
They are not used in the new happy path.

### 5. Proof-of-possession refresh

A device-bound refresh cannot rely on bearer possession alone.

Preferred protocol:

```text
client -> request short-lived single-use nonce
server -> nonce
client -> Ed25519.Sign(device_private_key, nonce)
client -> refresh(device_id, signature)
server -> verify public key + device/account state -> mint new access token
```

Nonce expiry and replay protection are mandatory.

Most importantly, refresh MUST NOT copy authorization scopes blindly from the
old credential. The server loads current account/device state on every refresh
and derives the new scopes from the current `send_enabled` value. Therefore:

```text
owner grants send -> next refresh gains send scope
owner revokes send -> next refresh loses send scope
```

This prevents stale JWT scopes from overriding the current consent state.

### 6. Revocation semantics

Revoking a device/account immediately blocks all subsequent refresh attempts
and all new bridge authentication for that device.

For an already-open `/bridge` websocket the implementation must choose and
document one of two explicit contracts:

1. preferred: revocation actively disconnects the device's current Hub
   connection; or
2. bounded fallback: the active connection may live only until a documented,
   tested maximum revocation latency no greater than the derived bridge-token
   lifetime.

The proposal must not claim "immediate revocation" while relying silently on
an unspecified eventual token expiry.

### 7. Audit and redaction

Activation, device registration/revocation, send-consent grant/revoke, and
credential mint/refresh/revoke produce distinguishable audit events.

Token values, activation codes, private keys, nonces, and signatures must
never appear in logs or audit records. New sensitive field names must be added
to `internal/audit/redact.go` and covered by tests.

## Backward compatibility

The following existing mechanisms remain unchanged and available for
support/recovery/migration:

- `provision_local_account`;
- `set_account_mode`;
- `set_account_send`;
- `POST /api/mcp/worker-token`;
- legacy worker-token renewal;
- existing hosted login/account flows.

A user who never adopts `activate` continues to work exactly as before.

## Documentation contract

Documentation is part of this implementation, not a follow-up.

`docs/local-bridge.md` must make the zero-admin path the primary setup:

```text
init -> login -> activate -> daemon
```

It must split **Client / owner actions** from **Operator: support and recovery
only**, document read-only-by-default activation, the separate owner send
consent flow, short-lived credential refresh/device binding/revocation, and
label manually minted worker tokens as legacy/support compatibility.

`internal/bridge/DESIGN.md` must be updated in the same implementation PR to
close the "No self-serve enablement" gap and record the final bootstrap,
credential, consent, refresh, and revocation contracts.

## E2E invariant

The acceptance E2E sequence is:

```text
fresh install
-> local Telegram login
-> self-service activation
-> read call
-> explicit owner send grant
-> send call
-> automatic credential refresh
-> daemon reconnect
```

At every stage the server-side `telegram_accounts.session_encrypted` value for
that user remains `NULL`, and no operator action is required.

## Out of scope

- Removing admin/support tools.
- Automatically migrating hosted accounts to local mode.
- Changing the Local Bridge websocket protocol itself unless required solely
  to enforce the chosen active-connection revocation contract.
- Adding unsupported Local Bridge Telegram tools.
- Portal device-management UI.
- Broader Windows ACL hardening.
