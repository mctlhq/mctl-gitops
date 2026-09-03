# Design: issue-479-feat-local-bridge-make-onboarding-fully

## Current state

**Account modes and schema.** `telegram_accounts.mode` (`'hosted'|'local'`,
default `'hosted'`) is the live switch (`internal/db/db.go:316-328` sqlite,
`:392-404` postgres). `session_encrypted` was made nullable specifically so a
local-only row can exist with no server-held session
(`internal/db/db.go:208-223`). `SweepIdleSessions`/`SweepAbsoluteSessions`
already carry `AND mode <> 'local'` so local rows are immune to the idle/TTL
sweepers unconditionally (`internal/db/db.go:231-257`).

**Creating a local account today is admin-only.** Two MCP tools write
`mode='local'`, both gated by `requireScope(id, "admin:users")`:
- `provision_local_account` (`internal/mcp/tools.go:1093-1156`) calls
  `Store.EnsureUserByTelegramID` then `Store.ProvisionLocalAccount`
  (`internal/db/store.go:824-864`), which inserts
  `(user_id, telegram_user_id, ..., session_encrypted=NULL, mode='local',
  send_enabled=false)` guarded by `WHERE NOT EXISTS (... revoked_at IS
  NULL)` and returns `ErrAccountAlreadyActive` if one exists.
- `set_account_mode` (`internal/mcp/tools.go:1011-1086`) flips an existing
  hosted row via `Store.SetAccountMode`.

**Enabling send is a separate admin-only flip.** `set_account_send`
(`internal/mcp/tools.go:948-1005`) calls `Store.SetSendEnabled`. New accounts
(including `provision_local_account`'s) start `send_enabled=false`, and a
disabled account's `send_message` returns a *successful* dry-run
(`docs/local-bridge.md`'s "gets missed, and it fails quietly" note) — so the
opt-in mechanism matters for UX, not just security.

**The daemon's credential chain today.** `POST /api/mcp/worker-token`
(`internal/workertoken/tokenhandler.go`) is admin-only
(`id.HasScope("admin:users")`), mints an HS256 JWT via
`internal/auth/localjwt.Issuer` with `purpose="local-bridge"` granting
`allowedLocalBridgeScopes` (`telegram:dialogs:read`, `telegram:messages:read`,
`telegram:messages:send`, `telegram:messages:pin`), default TTL 30 days, max
90 days, audience `mcp-worker-bridge`. `cmd/local/main.go`'s `connect`
subcommand (`main.go:221-...`) takes that token via `--token`, calls
`POST /api/bridge/token` (`internal/bridge/tokenhandler.go`) to exchange it
for a 1-hour `aud=["bridge"]` JWT, and persists **both** tokens in
`~/.config/mctl-telegram-local/bridge_token.json`
(`cmd/local/config.go`'s `bridgeTokenFile`). The daemon re-exchanges the
long-lived worker token for a fresh bridge token before the 1-hour one
expires (`internal/bridge/DESIGN.md:111-114`) and can renew the worker token
itself via `POST /api/mcp/worker-token/renew`
(`internal/workertoken/renewhandler.go`) — but only because it already holds
the long-lived one, and renewal is bearer-possession-only, bounded by
`maxRenewalChain = 365 * 24h` anchored on `OriginalIssuedAt`
(`renewhandler.go:14-31,244-255`).

**`GET /bridge` enforcement.** `internal/bridge/server.go` requires
`aud="bridge"`, looks up the account by `tg_id` in the bridge JWT's claims,
and refuses unless `telegram_accounts.mode == 'local'`
(`server.go:42-75`). This does not change.

**Proving Telegram identity without MTProto already exists.**
`internal/auth/telegramoidc` (`oidc.go`) is a full OIDC Relying Party against
`https://oauth.telegram.org`: `AuthCodeURL`/`Exchange` verify a JWKS-signed
`id_token` and return `Identity{TelegramID, Sub, Username, ...}` — no MTProto
connection, no session bytes. `internal/oauth/enable_access.go`'s in-browser
wizard already consumes this as the *first* step
(`wantTgID` passed into `startLoginFlow`, `enable_access.go:99-101,170-189`)
before ever touching phone/SMS/2FA, and rejects the flow if the subsequent
hosted login resolves to a different Telegram id than the OIDC-proven one
("identity binding" comment, `enable_access.go:170-189`). It also already has
a self-service, no-operator, explicit send-consent step:
`stepPermissions`/`sendOptIn` (`enable_access.go:257-292`), gating
`Store.SetSendEnabled(bgCtx, uid, true)` (`enable_access.go:207-212`), driven
entirely by the authenticated end user through
`ConnectClientID = "mctl_self_connect"` (`internal/oauth/server.go:446`) — a
pre-registered, no-DCR-needed OAuth client used specifically for this
built-in flow.

**What is missing, concretely.** There is no path that (a) proves Telegram
identity via OIDC, (b) creates the `telegram_accounts` row directly as
`mode='local'` (skipping hosted login entirely), (c) captures send consent
the same way `enable_access.go` already does for hosted, and (d) hands back
a bridge-usable credential — all without `admin:users`. And there is no
device-bound, short-lived, self-renewing credential; the daemon's only
non-operator identity artifact today is the copyable long-lived worker-token
bearer JWT.

## Proposed solution

### Workstream A + B: self-service activation endpoint/flow

Add a new, small handler file `internal/oauth/activate_local.go` alongside
`enable_access.go` (same package, same `Server`, same `oauthCtx`/session
machinery style, but deliberately not folded into `enableSession`'s
phone/SMS state machine — that machine's steps are hosted-login-specific and
forcing local activation through it would couple two orthogonal flows).

1. **New store method**, additive next to `ProvisionLocalAccount`:
   `Store.ActivateLocalAccount(ctx, userID, tgID, deviceID, devicePubKey,
   displayName, username) (existing bool, err error)`. Semantics differ from
   `ProvisionLocalAccount` precisely where the issue requires idempotency:
   - If no active `telegram_accounts` row exists for the user: insert exactly
     as `ProvisionLocalAccount` does today (`mode='local'`,
     `session_encrypted=NULL`, `send_enabled=false`), then insert or
     `ON CONFLICT` upsert the device-binding row (see below). Returns
     `existing=false`.
   - If an active row exists **and** `mode='local'` **and** it belongs to
     the same `user_id`/`tgID`: no-op on `telegram_accounts`, upsert the
     device-binding row keyed on `(user_id, device_pubkey)` so re-running
     `activate` from the same device is a pure idempotent reconciliation.
     Returns `existing=true`.
   - If an active row exists with `mode='hosted'`: return
     `ErrAccountAlreadyActive` unchanged (same sentinel
     `provision_local_account` already surfaces), so the caller is pointed
     at `set_account_mode` — this is the "do not silently migrate hosted
     users to local" requirement.
   This reuses `ProvisionLocalAccount`'s existing `WHERE NOT EXISTS` /
   `ErrAccountAlreadyActive` machinery rather than replacing it, so the
   admin-only tool's behavior and tests are untouched.

2. **New table** `local_bridge_devices` (migrated the same
   `addColumnIfMissing`/`CREATE TABLE IF NOT EXISTS` way as every other
   schema change in `internal/db/db.go`):
   `device_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
   telegram_user_id INTEGER NOT NULL, public_key BLOB NOT NULL,
   created_at TIMESTAMPTZ NOT NULL, last_refreshed_at TIMESTAMPTZ,
   revoked_at TIMESTAMPTZ`. `device_id` is client-generated (random, like
   `generateJti`) at `init` time, not server-assigned, so `init` can run
   fully offline. This is the durable revocation anchor the issue's "Device
   binding / threat model" section asks for — revoking a row here is
   independent of any single token's `jti`.

3. **New HTTP endpoints**, mounted the same way `internal/bridge` and
   `internal/workertoken` mount theirs in `cmd/server/main.go`:
   - `POST /api/local-bridge/activate` — body carries the device's public
     key, an optional `send_consent: bool` (defaults `false`), and is
     authenticated by a short-lived, single-use "activation code" that the
     browser leg of the flow (below) hands to the CLI. Internally this is
     the same code-for-token exchange shape `enable_access.go`'s
     `finishEnable` → `issueAuthCode` already uses, reusing
     `oauthCtx`/PKCE rather than inventing a second code format.
   - Browser leg: `GET /telegram/activate` starts a Telegram OIDC round trip
     (reusing the existing `telegramoidc.Authenticator` wired into
     `internal/oauth.Server`) exactly like `enable_access.go`'s entry point,
     then renders a `stepPermissions`-style page (adapted copy: "Allow this
     device to send messages?" checkbox) and, on submit, calls
     `ActivateLocalAccount` and mints the activation code the CLI is
     long-polling for (device-code-grant shape: the CLI printed a short code
     the user copies/confirms in the browser, matching the issue's
     "browser/device activation step"). This is new code, but it is a thin
     wrapper: OIDC proof + consent checkbox + `ActivateLocalAccount` call +
     code mint, no phone/SMS/2FA state machine.
   - `POST /api/local-bridge/send-consent` — lets the owner grant or revoke
     send consent later without re-running activation, calling
     `Store.SetSendEnabled` under the caller's own proven identity (no
     `admin:users` needed, unlike `set_account_send`) and writing an audit
     row that distinguishes `local:consent:grant` /
     `local:consent:revoke` from the operator path's `set_account_send`
     audit entries.

   All three handlers sit behind the *existing* `auth.Middleware` chain (the
   caller must already hold a valid OIDC-proven identity/session the same
   way `enable_access.go`'s handlers do via `s.lookupEnable`/`oc`), so no new
   authentication primitive is introduced — only a new authorization
   decision (self-service instead of `admin:users`) layered on the existing
   one.

### Workstream C: automatic, device-bound credential issuance and rotation

Add `internal/localbridgecred`, a new package parallel to
`internal/workertoken` (same reasoning `workertoken`'s own doc comment gives
for being its own package: distinct audience/scope shape, distinct handler,
same "admin mints a scoped JWT" family as `internal/bridge`'s token
handler — this one is "device proves itself, gets a scoped JWT").

- **Mint (inside `activate`)**: on successful `ActivateLocalAccount`, mint an
  `aud=["local-bridge-access"]` `localjwt.Claims` JWT carrying `TelegramID`,
  the fixed local-bridge scope set (mirroring
  `allowedLocalBridgeScopes`/`allowedReadOnlyScopes` depending on
  `send_consent`), a new `DeviceID` claim, `Jti` = the device row's key, and
  a short TTL (open question: ~4h). This token is what the daemon presents
  to `POST /api/bridge/token` in place of today's hand-minted worker token —
  `internal/bridge/tokenhandler.go` needs no change: it already mints from
  "the standard MCP JWT", and this is simply a new *kind* of MCP JWT with a
  new `aud` value the `/mcp`-mounted `localjwt.Provider` already accepts
  (audience checking there is opt-in via `OAUTH_JWT_AUDIENCE`, same as the
  worker-token audiences today).
- **Refresh (`POST /api/local-bridge/refresh`)**: rather than
  `workertoken.NewRenewHandler`'s bearer-possession-only model, the daemon
  must sign a server-issued nonce with the device's Ed25519 private key.
  Request: `{device_id, nonce_signature}` where `nonce` was obtained from a
  `GET /api/local-bridge/refresh/nonce?device_id=...` call (short-lived,
  single-use, stored in-process the same way `enableSession` is — see
  `Server.enables` map pattern in `enable_access.go`). The handler looks up
  `local_bridge_devices` by `device_id`, verifies the signature against the
  stored `public_key`, checks `revoked_at IS NULL`, and mints a fresh
  short-TTL `local-bridge-access` token with the same scopes/telegram id as
  before (never widened — same "cannot escalate" property
  `workertoken.NewRenewHandler` already documents, now enforced by
  signature instead of bearer possession). This makes a copied bearer token
  alone insufficient to keep a daemon's credential chain alive past its TTL
  — exactly the "credential theft less useful" goal in the issue.
- **Revoke**: extend the existing revoke pattern
  (`internal/mcp/revoke_worker_token_test.go`'s tool,
  `internal/db/worker_token_revocations.go`) with a new admin tool
  `revoke_local_bridge_device` that sets `local_bridge_devices.revoked_at`
  and additionally calls the same jti-denylist path
  (`internal/auth/localjwt/revocation.go`) for the device's current token,
  so revocation is effective immediately (denylist) and durably (refresh is
  refused from then on because `revoked_at IS NOT NULL`). `GET /bridge`'s
  existing `mode='local'` + `Hub` singleton-per-user check already drops a
  connected daemon once its bridge token stops renewing; no change needed
  there.
- **`cmd/local` changes**: `init` (`cmd/local/main.go:100`) additionally
  generates an Ed25519 keypair and persists the private key encrypted the
  same way the session DB key is (Argon2id-derived key, `0600`,
  `writeFileAtomic`, same file-permission discipline documented in
  `docs/local-bridge.md`'s "Security notes"). New `activate` subcommand
  drives the device-code exchange against `/telegram/activate` and
  `/api/local-bridge/activate`, printing a short user code and a URL exactly
  like the CLI UX the issue's illustrative example implies, then writes the
  first `local-bridge-access` token into `bridge_token.json` (same file,
  extended with `device_id`). `daemon` (`daemon.go`) is changed to prefer a
  `local-bridge-access` token when present: call
  `POST /api/local-bridge/refresh/nonce` + `/refresh` on its own schedule
  instead of `POST /api/mcp/worker-token/renew`, falling back to the
  existing worker-token renewal path when `bridge_token.json` only has a
  legacy worker token (backward compatibility, see below). `connect` is
  kept unchanged and undeprecated for the manual/legacy path.

### Why the send-consent default stays `false`

Both the operator tool (`set_account_send`) and `ProvisionLocalAccount`
already default `send_enabled=false`; `ActivateLocalAccount` preserves that
default and only sets it `true` when the browser step's checkbox (or an
equivalent `--send` flag surfaced through the device-code flow) is
explicitly submitted. This keeps the "default remains safe" acceptance
criterion true by construction — no new default to get wrong — and reuses
`enable_access.go`'s already-shipped UX pattern instead of inventing a new
consent model.

## Alternatives

1. **Let the daemon keep using `POST /api/mcp/worker-token` with a
   self-service, non-admin-gated version of that same endpoint** (just drop
   the `admin:users` check for `purpose="local-bridge"` when the caller is
   the account owner). Rejected: the issue explicitly asks to move away from
   a "manually issued long-lived bearer token" model toward short-lived,
   device-bound credentials with proof-of-possession refresh
   (`internal/bridge/DESIGN.md`'s own gap #4 language "hand-signing an HS256
   token" is exactly the anti-pattern being removed). Dropping the scope
   check alone would keep the 30-90 day copyable-bearer-token threat model
   the issue calls out by name ("avoid introducing a new permanent secret
   that is simply another long-lived bearer token under a different name").

2. **Fold local activation into `enable_access.go`'s existing state machine**
   as a new `enableStep` (e.g. `stepLocalOrHosted`) chosen at the start.
   Rejected: `enableSession`'s `loginFlow` goroutine machinery
   (`startLoginFlow`, `askCode`/`askPassword` channels) exists specifically
   to drive `telegram.Login`'s multi-round-trip MTProto handshake across
   HTTP requests. Local activation has no MTProto round trip to drive at
   all — forcing it through that state machine would mean threading a large
   amount of dead state (`phone`, `flow`, `stepCode`, `stepPassword`)
   through a path that never uses it, and every future change to hosted
   login risks an accidental behavior change to local activation. A sibling
   file reusing the OIDC/consent/code-issuance building blocks, not the
   phone-login machinery, keeps the two flows independently testable and
   independently changeable — matching this repo's existing convention of
   splitting `internal/bridge/tokenhandler.go` from
   `internal/workertoken/tokenhandler.go` despite both being "mint a scoped
   JWT" (see `workertoken`'s own package doc comment on why).

3. **Server-generated device keypair, downloaded once by the CLI**, instead
   of the CLI generating the keypair locally. Rejected: it would require the
   private key to transit the network at least once, which is the exact
   "copyable secret" shape the device-binding design exists to avoid — a
   server that never sees the private key cannot leak it, and Ed25519
   keygen is cheap and already available via `crypto/ed25519` in the Go
   stdlib the daemon already depends on.

## Platform impact

- **Migrations**: one new table (`local_bridge_devices`), no destructive
  change to `telegram_accounts` or any existing table. Added the same
  `addColumnIfMissing`/`CREATE TABLE IF NOT EXISTS` way every prior schema
  change in `internal/db/db.go` was made, so it is safe to apply against a
  live database with existing rows (same pattern as the `mode` column
  itself, `db.go:116-127`).
- **Backward compatibility**: `provision_local_account`, `set_account_mode`,
  `set_account_send`, `POST /api/mcp/worker-token`, and
  `POST /api/mcp/worker-token/renew` are all left in place, unmodified,
  still admin-gated, for support/recovery use exactly as the issue's
  "Backward compatibility" section requires. `POST /api/bridge/token`
  accepts either an old-style worker token or a new `local-bridge-access`
  token — both are just MCP JWTs with different `aud`/`Jti` provenance — so
  a daemon that never upgrades keeps working through `connect` +
  `POST /api/mcp/worker-token/renew` unchanged. `docs/local-bridge.md`'s
  existing operator checklist becomes the documented *support/recovery*
  path rather than being deleted.
- **Resource impact**: one new table, a handful of new low-traffic
  endpoints (activation is a one-time-per-device call; refresh happens on
  an hours-scale cadence, materially less frequent than today's 1-hour
  bridge-token exchange). No change to the `Hub`'s in-process,
  single-replica constraint (`internal/bridge/DESIGN.md`'s "Correctness
  gaps" #4, already a known, separate issue, untouched here).
- **Risks and mitigations**:
  - *Abuse of self-service activation to claim someone else's Telegram
    id.* Mitigated the same way `enable_access.go` already mitigates it for
    hosted login: the Telegram id is never caller-supplied, it comes only
    from a verified OIDC `id_token`. This proposal does not weaken that
    property anywhere.
  - *A stolen device private key is used to keep refreshing forever.*
    Mitigated by revocation (`revoked_at`) taking effect on the very next
    refresh attempt, plus keeping the credential TTL itself hours-scale so
    an un-revoked leak has a short blast radius by default — an explicit
    improvement over today's 30-90 day worker-token exposure window.
  - *Two competing local-activation requests race on the same
    not-yet-existing account* (the same residual race
    `ProvisionLocalAccount`'s own comment already names and accepts,
    `internal/db/store.go:836-845`). Unchanged risk, same accepted
    mitigation (self-service activation is now a normal user action taken
    occasionally per device rather than "once per account by an operator",
    which if anything narrows the window rather than widening it, since
    device rows are keyed independently). A future partial unique index is
    still the real fix and remains out of scope here, as it already was for
    `ProvisionLocalAccount`.
  - *New endpoints expand the unauthenticated/lightly-authenticated attack
    surface.* Mitigated by putting every new endpoint behind the same
    `auth.Middleware` + OIDC-proof chain `enable_access.go` already uses in
    production, and by keeping the nonce/challenge for refresh short-lived
    and single-use, mirroring `enableSession`'s existing TTL/expiry
    handling (`lookupEnable`, `s.cfg.CodeTTL`).
