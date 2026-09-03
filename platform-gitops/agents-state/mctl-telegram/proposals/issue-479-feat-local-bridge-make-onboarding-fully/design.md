# Design: issue-479-feat-local-bridge-make-onboarding-fully

## Current state

**Identity and account model.** `telegram_accounts` (`internal/db/db.go:316`)
is keyed by `user_id` and carries `telegram_user_id`, `mode`
(`'hosted'|'local'`), `send_enabled`, `session_encrypted` (nullable since
issue #468). `users` (`internal/db/db.go:309`) carries `telegram_login_id` —
the identity a login proved — separately from any `telegram_accounts` row.
`Store.EnsureUserByTelegramID` (`internal/db/store.go:183`) is, in its own
words, "the canonical identity-binding call for the localjwt provider and the
OAuth Login Widget callback" — it is already how a browser login binds a
`users.id` to a Telegram id without touching `telegram_accounts` at all.
`Store.UserIDByTelegramID` (`internal/db/store.go:238`) is the read-only
counterpart, used by every admin tool today.

**Existing self-service identity proof.** `internal/auth/telegramoidc`
(`oidc.go`) is a full OIDC Relying Party against `https://oauth.telegram.org`:
authorization code + PKCE, JWKS-verified `id_token`, yielding a server-trusted
`Identity{TelegramID, Sub, Username, ...}`. This is already wired into
`internal/oauth` as part of the interactive OAuth authorize flow. Critically,
`internal/oauth/enable_access.go`'s `startLoginFlow`
(`enable_access.go:101-189`) already performs the exact identity-binding check
Workstream A needs: it runs an MTProto login (phone/SMS/2FA) driven from the
browser and then asserts `tgID != wantTgID` where `wantTgID` is the
OIDC-proven identity — refusing and revoking if the freshly-logged-in Telegram
account does not match the one OIDC already proved. That pattern (OIDC proves
identity, a second local proof must agree with it) is the direct precedent
for local-bridge activation, except the "second proof" is the daemon's local
MTProto login instead of a browser-driven one.

**What today's fresh-user hosted path looks like without an operator.** A
brand-new *hosted* user does not need an operator: connecting an MCP client
redirects through Telegram OIDC, then (if no session exists) through
`enable_access`'s phone/SMS/2FA wizard, and a token is issued at the end.
*Local* mode has no equivalent — the only ways to get `mode='local'` are the
admin tools `provision_local_account` (`internal/mcp/tools.go:1093-1156`) and
`set_account_mode` (`internal/mcp/tools.go:1011-1086`), both gated on
`admin:users` via `requireScope` (`internal/mcp/tools.go:975`,`:1039`,`:1124`).
`Store.ProvisionLocalAccount` (`internal/db/store.go:846`) is otherwise
exactly the primitive Workstream A needs: it inserts a `mode='local'` row with
`session_encrypted=NULL`, guarded by `NOT EXISTS ... WHERE revoked_at IS
NULL` so a second call is safely refused with `ErrAccountAlreadyActive`
(`store.go:822`) rather than duplicating a row.

**Send consent.** `send_enabled` defaults to `false` on every new row
(`ProvisionLocalAccount` passes `false` explicitly). Today only the admin tool
`set_account_send` (`internal/mcp/tools.go:951-1005`, `Store.SetSendEnabled`,
`store.go:765`) or the hosted wizard's `sendOptIn` flag
(`enable_access.go:207-212`, `Store.SetSendEnabled` again) can flip it. There
is also `Store.ToggleSendEnabled` (`store.go:870`), used elsewhere for an
authenticated self-toggle — i.e. there is already a precedent in this codebase
for a non-admin, self-service send toggle guarded only by `actionableAccount`
(`store.go:816`, which matches the caller's own active row by `user_id`).

**Credential issuance today.** `POST /api/mcp/worker-token`
(`internal/workertoken/tokenhandler.go`) is `admin:users`-gated
(`tokenhandler.go:142`) and mints an HS256 JWT via `localjwt.Issuer.Mint`
with `Purpose:"local-bridge"` selecting `allowedLocalBridgeScopes`
(`tokenhandler.go:71-76`) and `workerBridgeAudience` (`renewhandler.go:47`),
default TTL 30 days (`defaultWorkerTokenTTL`, `tokenhandler.go:47`), max 90
days. `POST /api/mcp/worker-token/renew` (`renewhandler.go:81-242`) already
lets the *bearer* — no scope required — trade a still-valid worker token for a
fresh one, bounded by `maxRenewalChain` (365 days from `OriginalIssuedAt`,
`renewhandler.go:31`) and re-validated against the purpose's own allowlist
(`renewhandler.go:112-144`) so renewal can never escalate scope or identity.
Revocation is `jti`- or `telegram_id`-scoped via `worker_token_revocations`
(`db.go:370`) and cached by `internal/auth/localjwt.RevocationCache`. This
mint+renew+revoke machinery is exactly the shape Workstream C needs; what is
missing is (a) a non-admin entry point to the *first* mint, (b) an
hours-scale default TTL for that entry point, and (c) proof-of-possession on
renewal instead of bearer-only.

**Bridge token exchange.** `POST /api/bridge/token`
(`internal/bridge/tokenhandler.go`) exchanges an authenticated MCP JWT (which
must already carry `tg_id`) for a 1-hour `aud="bridge"` JWT; `GET /bridge`
(`internal/bridge/server.go`) upgrades to a websocket, requires
`aud="bridge"`, and enforces `telegram_accounts.mode='local'` before letting
the daemon register with the `Hub` (`hub.go`). None of this needs to change —
it already works with any correctly-scoped local-jwt bearer, including one
minted by a new self-service path instead of `POST /api/mcp/worker-token`.

**Daemon CLI.** `cmd/local/main.go` dispatches `init`, `login`, `connect`,
`daemon` (`main.go:78-92`). `connect` (`main.go:221-296`) currently requires
`--token` (a pre-minted MCP worker token) and `--server`, then calls
`POST /api/bridge/token` and persists both tokens to
`bridge_token.json` (`config.go:59` `bridgeTokenFile`, written `0600`).
`login` (`main.go:155-219`) performs an ordinary local MTProto login and
writes the encrypted session to the local store — the server is never
contacted during `login`. There is no `activate` subcommand and no local
device-keypair concept anywhere in `cmd/local` today.

**Audit.** `audit_logs` (`db.go:332`) plus the hash-chain in `store.go`
records every admin tool call and every `enable_access` step
(`s.store.LogToolCall`, e.g. `enable_access.go:412,432,445,515,525,532,...`).
`internal/audit/redact.go` redacts attribute values by key-name match — any
new claim/secret name this work introduces (device secret, activation code)
must be added to its matcher.

## Proposed solution

Reuse every piece named above; add the minimum new surface to close the three
workstreams.

### Workstream A — self-service identity bootstrap ("activate")

Add a device-authorization-style flow, modeled directly on the
OIDC-proves-identity / local-login-must-agree pattern already implemented in
`enable_access.go`:

1. **New daemon subcommand `activate`** (`cmd/local`, alongside `init` /
   `login` / `connect` / `daemon` in `main.go`'s dispatch). Preconditions:
   `login` has already completed (a local MTProto session exists), so the
   daemon can read the authenticated Telegram user id directly from `gotd/td`
   without any new local-login logic.
2. Daemon calls a new unauthenticated endpoint, e.g.
   `POST /api/local-bridge/activate/start` with `{telegram_id, device_pubkey}`
   (device keypair generated once, on first `activate`, and persisted next to
   `config.json`). Server returns a short device code + a verification URL
   (`https://tg.mctl.ai/activate?code=...`), and starts polling — the same
   shape as `enable_access`'s "es" token / polling model, and structurally
   identical to RFC 8628 device authorization, which keeps the CLI story
   ("go to this URL") familiar without inventing new UX vocabulary.
3. User opens the URL; the page runs the **existing**
   `internal/auth/telegramoidc` OIDC flow against `oauth.telegram.org` (no new
   code in that package). On success the server has an OIDC-proven
   `telegram_id`.
4. Server compares the OIDC-proven `telegram_id` to the one the daemon
   claimed in step 2 — the same mismatch-refusal shape as
   `enable_access.go:176-189` (`tgID != wantTgID`). On mismatch, refuse and
   record nothing.
5. On match: `EnsureUserByTelegramID` resolves/creates the `users` row (same
   call `enable_access` and the localjwt provider already use), then
   `ProvisionLocalAccount(ctx, uid, tgID, ...)` is called — the exact function
   `provision_local_account` calls today. `ErrAccountAlreadyActive` is treated
   as success (idempotent retry), not as failure — this is the one behavior
   change needed in the caller, not in `Store`, satisfying the "re-running
   activation is idempotent" requirement.
6. This same request/session also carries device binding (see Workstream C)
   and, optionally, send consent (Workstream B) before the daemon's poll
   returns "done".
7. Daemon polls `POST /api/local-bridge/activate/poll`; on completion it
   receives the first Local Bridge access credential directly (no separate
   `connect` step needed for a brand-new account — see Workstream C) and
   writes `bridge_token.json` itself, same as `connect` does today.

No hosted session is ever created: nothing in this path touches
`session_encrypted` or calls `telegram.Login`'s server-side variant.

`set_account_mode`/`provision_local_account` remain unchanged and keep
serving the operator migration and recovery paths.

### Workstream B — owner-controlled send consent

Add a `send_consent` boolean choice to the activation web page (rendered
alongside the existing OIDC step, structurally parallel to
`enable_access.go`'s `handleEnablePermissions`/`stepPermissions` screen that
already collects `sendOptIn` for the hosted wizard). On activation completion,
if consent was granted, call the same `Store.SetSendEnabled(ctx, uid, true)`
that `set_account_send` and the hosted wizard both already call — no new
store method. Add a corresponding CLI flag (`activate --send`) for headless/
non-browser setups, which the daemon passes to `activate/start` so the
browser step can skip re-asking. Revocation reuses `Store.SetSendEnabled(...,
false)` through a new, non-admin, self-authenticated endpoint (or MCP tool)
gated only on "this is your own account" (matching `actionableAccount`'s
existing `user_id`-scoped predicate, the same guard `ToggleSendEnabled`
already relies on) — not on `admin:users`. `set_account_send` keeps working
unchanged for operator override.

Every grant/revoke, self-service or admin, is audited via the existing
`s.audit`/`LogToolCall` path with a distinguishable actor (self vs. admin
`user_id`) so audit records "distinguish activation, consent, token lifecycle"
per the acceptance criteria.

### Workstream C — automatic credential issuance, device binding, rotation

**New table `local_bridge_devices`** (migration alongside the existing
`addColumnIfMissing`/schema-array pattern in `internal/db/db.go`):

```
id, user_id (FK users), telegram_user_id,
device_pubkey (the Ed25519/X25519 public key generated by cmd/local),
label, created_at, last_seen_at, revoked_at, revoked_reason
```

This is new schema, not a repurposing of the existing but dead
`telegram_accounts.bridge_token_hash` column
(`internal/bridge/DESIGN.md` flags that column as write-never dead code) —
device binding is a device concept, not a per-token hash, and conflating the
two would resurrect the ambiguity the DESIGN doc already calls out. Whether to
finally wire up or drop `bridge_token_hash` is left to the implementer as a
small independent cleanup, not a dependency of this feature.

**Mint.** On successful activation, the server mints a worker token using the
exact code path `workertoken.NewHandler` uses today
(`localjwt.Issuer.Mint` with `Purpose:"local-bridge"`,
`allowedLocalBridgeScopes` filtered by the granted consent — read-only scopes
only if send was not granted, matching "a read-only activation works without
granting send"), but through a new internal call, not through the
admin-gated HTTP handler. TTL default is hours-scale (proposed 8h, see Open
Questions), a new constant alongside `defaultWorkerTokenTTL`, not a change to
that constant (admin-minted tokens for canaries/support keep their existing
30-day default). `OriginalIssuedAt` and `Jti` are set exactly as
`NewHandler` does, so revocation-by-`jti` and the `maxRenewalChain` ceiling
apply identically to self-service-minted tokens.

**Refresh with proof of possession.** Extend
`POST /api/mcp/worker-token/renew` (or add a sibling
`/api/local-bridge/refresh` if the claims-shape diverges enough to warrant
it) to additionally accept a signature over a server-issued nonce, verified
against the `device_pubkey` row matching the presented token's device
binding (a new `device_id`/`cnf`-style claim added to `localjwt.Claims`,
analogous to how `Jti`/`OriginalIssuedAt` were added incrementally to that
struct for workertoken's needs). A token/device pairing that fails the
signature check is refused even if the bearer JWT itself still verifies —
this is what makes a copied `bridge_token.json` alone insufficient, unlike
today's model where the file's contents are the entire credential.

**Revocation.** Revoking a device sets `local_bridge_devices.revoked_at`;
the refresh handler checks it (new `SELECT ... WHERE device_pubkey = $1 AND
revoked_at IS NULL`) in addition to the existing `worker_token_revocations`
jti/telegram_id checks, so refresh stops immediately. `GET /bridge`'s
existing `mode='local'` + JWT checks already reject a daemon whose account
mode was flipped back to hosted; the new device check adds "this specific
device" granularity without touching `internal/bridge/server.go`'s core
gate — the JWT itself simply stops being mintable/renewable for a revoked
device, so the daemon's next reconnect (after its short-lived credential
expires) fails at `/api/bridge/token` or at `/bridge` for the same reason
an expired/invalid JWT fails today.

**Compatibility.** `POST /api/mcp/worker-token` remains available and
unchanged for operators (support/recovery/migration, per non-goals). A
manually minted token carries no `device_id` claim; the refresh handler
treats an absent `device_id` as "legacy, bearer-only" and applies today's
behavior unchanged (no signature required) — this is the migration window
the acceptance criteria ask for. A future proposal can decide whether/when to
sunset bearer-only renewal for new mints; this proposal does not change
`NewHandler`'s admin path at all.

### Documentation

Rewrite `docs/local-bridge.md`'s "What the operator has to do" section (the
table at lines 72-94) into two sections: **Client / owner actions** (`init`,
`login`, `activate` — replacing steps 1-3 of `Set up`) and **Operator
actions: none required for normal onboarding; support, recovery, and explicit
revocation only** (migration via `set_account_mode`, emergency
`set_account_send`/token revocation, `provision_local_account` kept
documented as a recovery/backfill tool, not the default path). The existing
warning about `send_enabled=false` producing a silent-looking dry-run stays,
reframed as "if you skipped consent during activate, run `activate --send`
(or the send-consent toggle) rather than asking an operator."

## Alternatives

1. **Let the daemon self-report `telegram_id` with no independent server-side
   proof, gated only by "first activation for this id wins."** Rejected: this
   is exactly the trust gap the issue's threat-model section warns against —
   anyone who learns another user's Telegram id could claim it first. The
   OIDC-based proof is not optional scaffolding; it is the only
   server-independent identity check this codebase already has, and skipping
   it would leave `EnsureUserByTelegramID`/`ProvisionLocalAccount` open to
   being called with an unverified id.
2. **Route activation entirely through the existing `/oauth/authorize` +
   `enable_access` machinery, adding a "local" branch to
   `startLoginFlow` instead of a new endpoint pair.** Considered because it
   reuses the most code. Rejected as the primary shape because
   `enable_access` is architecturally an *OAuth authorization-code flow*
   (`oauthCtx`, `issueAuthCode`) driven by an MCP client's redirect — it
   assumes the browser session ends in minting an OAuth access/refresh token
   pair for that MCP client, not a Local Bridge device credential polled by a
   CLI. Forcing device-authorization polling semantics into that flow would
   complicate the one piece of this codebase that already has a large,
   carefully-commented state machine (`enableStep`, per-step locking). A
   sibling flow that reuses `telegramoidc` and the identity-match pattern,
   without reusing `oauthCtx`, keeps both flows independently reasoned about.
3. **Give the daemon a permanently valid, non-expiring device-bound token
   instead of short-lived-plus-refresh.** Rejected: the issue explicitly asks
   for hours-scale credentials with refresh, and this codebase already
   deliberately moved away from "long-lived bearer token" once
   (`internal/workertoken`'s own doc comment: "replace hand-signing a
   year-long JWT"). Repeating that mistake with a device-bound token instead
   of a bearer one is still the same mistake at a longer TTL.
4. **Store the device private key server-side too ("server holds a copy for
   recovery").** Rejected: defeats the point of proof-of-possession (the
   server could then forge refreshes) and contradicts the "avoid introducing
   a new permanent secret" guidance in the issue. Recovery is instead: lose
   the device key, re-run `activate` (new device row, old one manually
   revoked by the operator if the user cannot reach it themselves).

## Platform impact

- **Migrations.** One new table (`local_bridge_devices`) and one new nullable
  claim (`device_id` on `localjwt.Claims`, empty for every existing token).
  Both are additive; no existing column changes type or nullability. Follows
  the existing `sqliteSchema()`/`pgSchema()` dual-definition pattern in
  `internal/db/db.go`.
- **Backward compatibility.** Hosted accounts, hosted->local migration
  (`set_account_mode`), and manually minted worker tokens all keep working
  through paths that are untouched by this proposal (see "Compatibility"
  above). No default behavior changes for an account that never calls
  `activate`.
- **Resource impact.** One new short-polling HTTP endpoint pair
  (`activate/start`, `activate/poll`) with the same server-side session-map
  shape `enable_access` already uses (`s.enables`, TTL-bounded, in-memory) —
  no new infrastructure dependency. Device-bound signature verification adds
  one Ed25519 verify per refresh call, negligible cost.
- **Risks and mitigations.**
  - *Risk:* a new unauthenticated `activate/start` endpoint is a fresh attack
    surface. *Mitigation:* it only ever produces a pending, unconfirmed
    device code — no `telegram_accounts` mutation happens until the OIDC
    step independently proves identity, mirroring `enable_access`'s existing
    "es" token pattern which has the same unauthenticated entry shape today.
  - *Risk:* the new device-bound refresh path is genuinely new crypto in this
    codebase (no prior Ed25519/challenge-response code exists). *Mitigation:*
    keep the primitive minimal (sign-a-server-nonce), test it as thoroughly
    as `internal/auth/localjwt/revocation_test.go` tests today's revocation
    cache, and keep the legacy bearer-only path fully intact so a bug in the
    new path degrades to "self-service issuance unavailable," not "all Local
    Bridge auth broken."
  - *Risk:* silently duplicating `EnsureUserByTelegramID`'s or
    `ProvisionLocalAccount`'s residual concurrent-insert race (documented at
    `store.go:836-845`) under a new, more-automated caller that might retry
    more aggressively than an operator would. *Mitigation:* treat
    `ErrAccountAlreadyActive` as the expected idempotent-retry outcome (per
    Workstream A step 5) rather than adding new locking; the existing
    residual race is unchanged in kind, only in expected call frequency.
  - *Risk:* documentation drift between the new happy path and the still-true
    operator recovery path. *Mitigation:* the doc rewrite keeps the recovery
    table rather than deleting it, explicitly labeled "support/recovery
    only," so an operator following an old bookmark still finds accurate
    instructions.
