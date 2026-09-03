# Design: issue-482-feat-local-bridge-self-service-device-ac

## Current state

**Identity verification.** `internal/auth/telegramoidc.Client` (`internal/auth/telegramoidc/oidc.go`)
implements the `Authenticator` interface — `AuthCodeURL(state, nonce, codeChallenge)`
and `Exchange(ctx, code, codeVerifier, expectedNonce) (*Identity, error)` — as an
OIDC Relying Party against `https://oauth.telegram.org`. `internal/oauth.Server`
(`internal/oauth/server.go`) is the only current consumer: `handleAuthorize`
(`server.go:878-972`) mints a server-side `state`/`nonce`/PKCE verifier, stores
them in `pendingAuth` (in-memory map `s.pending`, or `oauth_pending_auth` when
`useDB`), and redirects the browser to `s.tgoidc.AuthCodeURL(...)`.
`handleTelegramCallback` (`server.go:991-1075`) consumes the pending entry,
calls `s.tgoidc.Exchange(...)`, and on success calls
`store.EnsureUserByTelegramID(identity.TelegramID, ...)` to bind the verified
identity to an internal `users.id`. There is exactly one `telegramoidc.Client`
per process, constructed once at boot in `cmd/server/main.go:registerOAuth`
(`oauth.New`, which performs an OIDC discovery network call) and held as the
private field `Server.tgoidc`.

The same file already has a second, structurally similar "prove identity in a
browser, then do more work before finishing an OAuth-shaped flow" feature:
`enable_access.go`. After OIDC succeeds, `handleTelegramCallback` decides
in-line whether the user needs `enable_access` (no MTProto session yet, and
is an admin/client) or gets an authorization code immediately
(`server.go:1122-1170`). `enable_access` keys its own server-side session
(`enableSession`) in a second in-memory map, `Server.enables`, by an
unguessable token (`esTok := randomToken(32)`), independent of the original
`pendingAuth` state, and is capped/evicted the same way (`MaxPendingEnable`,
swept in `Server.sweep`, `server.go:592-631`). This proposal follows that same
shape rather than inventing a third mechanism.

**Device registry.** `internal/db/local_bridge_devices.go` (issue #481, already
merged) is exactly the surface this issue is meant to build on. Its own doc
comment says so: "Nothing in this issue reads or writes it from
internal/bridge, internal/mcp, or internal/workertoken -- it exists so a
follow-up sub-issue (activation endpoints, consent, credential issuance) has a
stable Store surface to build on" (`local_bridge_devices.go:20-22`).
`Store.RegisterDevice(ctx, userID, label, idempotencyKey)` inserts a row keyed
by a server-generated `device_id` (`dev_<32 hex chars>`), and is idempotent
per `(user_id, idempotency_key)` — a second call with the same key returns the
first call's `device_id` instead of creating a duplicate (verified by
`TestRegisterDevice_IdempotentRetry`, `local_bridge_devices_test.go:41-68`).
`Store.GetDevice`/`RevokeDevice`/`TouchDeviceLastSeen` round out the surface;
none of them are wired into any HTTP handler yet.

**Account provisioning.** `internal/db/store.go:846-864`,
`Store.ProvisionLocalAccount(ctx, userID, tgID, displayName, username)`,
inserts a `telegram_accounts` row with `mode='local'`, `session_encrypted=NULL`,
`send_enabled=false`, guarded by `WHERE NOT EXISTS (... WHERE user_id = $1 AND
revoked_at IS NULL)` — it refuses (returns `db.ErrAccountAlreadyActive`,
`store.go:822`) if the user already has *any* active row, hosted or local.
`Store.GetAccountMode(ctx, userID)` (`store.go:1202-1217`) reads the mode of
the user's current row (`ORDER BY connected_at DESC, id DESC LIMIT 1`),
defaulting to `"hosted"` when no row exists. Both of these already do exactly
the "hosted refused" / "idempotent-if-already-local" work this issue's
Definition of Done asks for — the two admin tools `provision_local_account`
and `set_account_mode` (`internal/mcp/tools.go:1011-1154`) are the only
current callers, gated by admin scope.

**Route wiring.** `cmd/server/main.go` mounts `oauthSrv.Register(mux)` and
`oauthSrv.StartSweeper(...)` only `if strings.EqualFold(cfg.AuthMode,
"local-jwt")` (`main.go:386-409`) — the same gate this proposal's routes
belong under, since self-service activation is meaningless without
Telegram-OIDC-based login already being the deployment's identity source.
None of `/api/local-bridge/activate/*` exist today; there is no handler, no
schema, and no CLI subcommand for them.

## Proposed solution

### Server: extend `internal/oauth.Server`, do not create a new package

`telegramoidc.Authenticator.AuthCodeURL` always redirects to the single
`RedirectURL` baked into the `telegramoidc.Client` at construction
(`TELEGRAM_OIDC_REDIRECT_URL`, which points at `/oauth/telegram/callback`
today). Reusing "the existing `internal/auth/telegramoidc.Authenticator`"
(the issue's own wording) therefore means reusing the existing `*Client`
instance owned by `oauth.Server` — there is no way to redirect the Telegram
leg to a different path without registering a second redirect URI with
Telegram, which this repo does not control (see Open Questions). Consequently
the activation feature is implemented as new files inside `internal/oauth`
(`internal/oauth/local_bridge_activate.go` + a template file for the result
page), extending `Server` with a third piece of transient state alongside
`pending` and `enables`, and it is the existing `handleTelegramCallback` that
learns to recognize an activation's `state` and branch into it — mirroring
exactly how it already branches into `enable_access`.

**New `Server` fields** (in `server.go`, next to `enables`):
```go
activations        map[string]*localBridgeActivation // keyed by device_code
activationsByState map[string]*localBridgeActivation // keyed by the Telegram-leg OIDC state
```

**New type**, `local_bridge_activate.go`:
```go
type localBridgeActivation struct {
    deviceCode     string
    claimedTGID    int64
    deviceRegKey   string // CLI-supplied device_registration_key; ONLY ever RegisterDevice's idempotencyKey.
                          // Never the registry device_id -- that is server-generated and lives in resultDeviceID.
    deviceLabel    string
    createdAt      time.Time

    // set once the browser starts the Telegram leg
    oidcState, oidcNonce, oidcVerifier string

    // mutated once, by finishActivation, under s.mu
    status         string // "pending" | "denied" | "done"
    denialReason   string
    resultDeviceID string
}
```

**`POST /api/local-bridge/activate/start`** (unauthenticated, mirrors
`handleAuthorize`'s cap/evict pattern using a new `MaxPendingActivations`
config field): validates `telegram_id > 0` and `device_registration_key != ""`, mints
`device_code := randomToken(32)`, stores a `pending`-status
`localBridgeActivation`, returns:
```json
{
  "device_code": "...",
  "verification_uri": "https://tg.mctl.ai/local-bridge/activate",
  "verification_uri_complete": "https://tg.mctl.ai/local-bridge/activate?device_code=...",
  "expires_in": 600,
  "interval": 5
}
```

**`GET /local-bridge/activate?device_code=...`** (unauthenticated browser
page): looks up the activation; if missing/expired/already-resolved, renders a
"start over" page (no OIDC round trip, no store call). Otherwise mints a fresh
`nonce`/PKCE verifier/`oidcState` exactly like `handleAuthorize` does
(reusing the package's existing `randomToken`/`pkceChallenge` helpers),
records them on the activation, indexes it into `activationsByState`, and
302-redirects to `s.tgoidc.AuthCodeURL(oidcState, nonce, tgChallenge)`. No
`users`/`telegram_accounts`/`local_bridge_devices` row is touched yet.

**`handleTelegramCallback`** (existing function, minimally extended): right
after extracting `serverState := q.Get("state")`, before the existing
`pendingAuth` lookup, add:
```go
s.mu.Lock()
act, isActivation := s.activationsByState[serverState]
if isActivation {
    delete(s.activationsByState, serverState)
}
s.mu.Unlock()
if isActivation {
    s.finishActivation(w, r, act, q)
    return
}
```
Everything below this (the existing `pendingAuth`/`enable_access`/auth-code
path) is untouched — a request whose `state` was minted by `handleAuthorize`
never appears in `activationsByState`, so this is a pure addition with no
behavioral change to existing logins. `finishActivation` (new function) does:

1. `error=`/missing `code=` → `denyActivation(act, "telegram sign-in was not completed")`, render result page, **return**. No store call at all.
2. `s.tgoidc.Exchange(ctx, code, act.oidcVerifier, act.oidcNonce)` → identity, or `err` → `denyActivation(act, "telegram verification failed")`, render, **return**. Still no store call.
3. `identity.TelegramID != act.claimedTGID` → `denyActivation(act, "telegram account mismatch")`, render a page that says the approving account did not match the device's request, **return**. This is the T2 path: the entire function up to this point has made zero `store.*` calls, satisfying "refused with no database mutation at all."
4. Only past this point — identity is proven **and** matches the claim — call `store.EnsureUserByTelegramID(ctx, identity.TelegramID, identity.Username, ...)` to get `uid`.
5. `store.ProvisionLocalAccount(ctx, uid, identity.TelegramID, displayName, username)`:
   - `nil` → brand-new local account, continue.
   - `errors.Is(err, db.ErrAccountAlreadyActive)` → `store.GetAccountMode(ctx, uid)`; if not `db.ModeLocal`, `denyActivation(act, "hosted account")` and render — no `local_bridge_devices` write follows. If it *is* `db.ModeLocal`, this is an idempotent retry (T1): fall through without erroring.
   - any other error → internal error page, activation left `pending` so the CLI's poll keeps returning `pending` until TTL rather than falsely reporting `denied` for a transient DB error.
6. `store.RegisterDevice(ctx, uid, act.deviceLabel, act.deviceRegKey)` — `act.deviceRegKey` (the CLI-supplied `device_registration_key`, never a device id) is passed as the idempotency key, so a second `start`+browser-approve for the same device on the same account collapses onto the same `local_bridge_devices` row (T1), reusing #481's existing `(user_id, idempotency_key)` uniqueness rather than reimplementing idempotency here.
7. Mark `act.status = "done"`, `act.resultDeviceID = deviceID` under `s.mu`, audit via `store.LogToolCall(ctx, uid, "local_bridge_activate", "", "ok", "", "")` (same audit call the rest of the package already uses), render a "you can close this tab" success page.

**`POST /api/local-bridge/activate/poll`** (unauthenticated): looks up
`s.activations[device_code]`; unknown/expired → HTTP 400 (a distinct error
shape so the CLI can tell "give up and restart" from "keep polling"); else
returns `{"status": act.status}` plus `reason` when `denied` or the server-generated registry
`device_id` from `act.resultDeviceID` (no other credential) when `done` --
never the CLI's `device_registration_key`.

**Sweeping**: extend the existing `Server.sweep` (`server.go:592-631`, already
run by `StartSweeper` on a 1-minute ticker) with a loop over `s.activations`
using the same `s.cfg.CodeTTL`-style cutoff (new `ActivationTTL` config,
defaulted like `MaxPendingEnable`), deleting from both `activations` and
`activationsByState`.

**Config**: add `MaxPendingActivations int` and `ActivationTTL time.Duration`
to `oauth.Config`, defaulted in `oauth.New` the same way `MaxPendingAuth` and
`MaxPendingEnable` are today.

**Wiring** (`Register(mux)`):
```go
mux.Post("/api/local-bridge/activate/start", s.handleActivateStart)
mux.Get("/local-bridge/activate", s.handleActivateVerify)
mux.Post("/api/local-bridge/activate/poll", s.handleActivatePoll)
```
No change to `cmd/server/main.go` beyond these being covered by the existing
`oauthSrv.Register(mux)` call already made under `AUTH_MODE=local-jwt`.

### CLI (`cmd/local`)

Out of this proposal's core server work but needed for the feature to be
reachable end-to-end: a new `activate` subcommand (alongside `init`, `login`,
`connect`, `daemon`) that (a) generates or loads a persistent local
`device_registration_key` (a random opaque string written under
`~/.config/mctl-telegram-local/`, analogous to how `init` already persists
`config.json`), (b) POSTs `/api/local-bridge/activate/start` with the
Telegram id the user types in and that key, (c) prints the
`verification_uri_complete` for the user to open, (d) polls
`/api/local-bridge/activate/poll` at the returned `interval` until `denied`
(print the reason, exit non-zero) or `done` (print success + a reminder that
an operator/`connect` step is still needed for a working daemon, per this
issue's explicit scope cut). This does not require server-side design changes
beyond the JSON contracts above, and ships in the same PR as the server
change so the DoD ("start returns...", "poll returns...") is exercised by a
real client rather than curl in a test.

## Alternatives

1. **A brand-new package/redirect URI** (`internal/localbridgeactivate`, its
   own `telegramoidc.Client` pointed at
   `/local-bridge/activate/telegram/callback`). Cleaner separation from
   `internal/oauth`, but requires a second registered redirect URI with
   Telegram/BotFather that this repo cannot provision or verify, and a second
   OIDC discovery call at boot for no functional benefit. Dropped; noted as a
   possible follow-up if Telegram is confirmed to support multiple redirect
   URIs per client (Open Questions).
2. **A second, independent identity check** (e.g. re-verify via the legacy
   HMAC Telegram Login Widget, or trust the CLI's claimed id outright and
   defer verification to `connect`). Both are exactly what the issue says not
   to do ("reusing the existing ... Authenticator rather than introducing a
   second identity path") and the second would let a claimed-id-only client
   provision an account for any Telegram id without proof — a direct
   violation of "the identity bound to a device is the one OIDC proves, never
   the one the client claims." Dropped.
3. **Persist activation state to a new DB table** (`local_bridge_activations`)
   instead of an in-memory map, for multi-replica correctness. Rejected for
   this proposal because `internal/bridge/DESIGN.md` already documents "The
   relay must run at one replica" as a current, accepted constraint, and
   `enable_access` — the closest existing analog, also a multi-step
   browser-driven flow — is in-memory-only with no `useDB` path at all.
   Matching that precedent keeps this change small; if/when the deployment
   moves to multiple replicas, `pending`/`enables`/`activations` would all
   need the same externalization at once, which is a separate, larger
   project. Flagged as a platform-impact risk below, not silently accepted.
4. **Reuse `pendingAuth`/`oauthCtx` directly** by adding a `Purpose` field
   instead of a sibling map. Rejected because `pendingAuth`/`oauthCtx` model
   an MCP OAuth *client* request (`ClientID`, `RedirectURI`,
   `CodeChallenge`) that has no meaning for a CLI hitting `/activate/start`
   directly — forcing activation through that shape would mean populating
   OAuth-specific fields with placeholder values and adding conditionals
   through `handleToken`/`issueAuthCode` that have nothing to do with
   activation. A sibling map (mirroring `enables`) keeps the two concerns
   separate the same way `enables` already keeps `enable_access` separate
   from plain login.

## Platform impact

- **Migrations**: none. This proposal adds zero schema — it only calls
  `Store.EnsureUserByTelegramID`, `Store.ProvisionLocalAccount`,
  `Store.GetAccountMode`, and `Store.RegisterDevice`, all of which already
  exist and are already tested for the exact refusal/idempotency semantics
  this issue's DoD asks for.
- **Backward compatibility**: fully additive. New routes, new `Server`
  fields, one new `if isActivation { ...; return }` branch at the top of
  `handleTelegramCallback` that is a no-op for every `state` not minted by
  `/local-bridge/activate`. Existing `/oauth/authorize` and `enable_access`
  behavior is unchanged (regression risk mitigated by keeping existing
  `oauth` package tests green and adding activation-specific tests rather
  than editing the shared callback's existing assertions).
- **Resource impact**: negligible. Two more bounded in-memory maps on the
  existing `oauth.Server`, capped and swept the same way `pending`/`enables`
  already are; no new goroutines beyond the existing sweeper tick doing
  slightly more work.
- **Risk: unauthenticated write-adjacent endpoint.** `/activate/start` is
  unauthenticated by design (that is the point of the issue) and causes a
  `users`/`telegram_accounts`/`local_bridge_devices` write *if and only if*
  the browser leg later proves Telegram OIDC ownership of the claimed id —
  so an attacker who only calls `/start` repeatedly can grow the
  `activations` map (mitigated by `MaxPendingActivations` + TTL, identical
  mitigation to `MaxPendingAuth`) but cannot cause any database mutation
  without also completing a real Telegram sign-in as the claimed account.
  Mitigation: cap + TTL + no store writes before identity match, as designed
  above.
- **Risk: single-replica assumption.** If mctl-telegram is ever scaled beyond
  one replica without externalizing `oauth.Server`'s in-memory state, an
  `/activate/start` handled by pod A followed by a browser callback landing
  on pod B would fail to find the activation. This is not a new risk
  introduced here — it already applies to `pending` and `enables` — but this
  proposal adds a third instance of it. Mitigation: none required now
  (mirrors `internal/bridge/DESIGN.md`'s existing "relay must run at one
  replica" acceptance), but called out so a future multi-replica project
  scopes all three maps together, not just the two that predate this issue.
- **Risk: activation-result page as an oracle.** The result page must not let
  a caller distinguish "no such account" from "hosted account" from "wrong
  Telegram id" beyond what `provision_local_account`'s existing error message
  already exposes to admins today, since this endpoint is public. Mitigation:
  the mismatch and hosted-refusal reasons are deliberately generic user-facing
  copy (task 6 below); only the poll response's machine-readable `reason`
  string needs to distinguish them for the CLI's own error messages, and that
  string is only visible to whoever is holding the `device_code`, which is as
  unguessable as the existing `es`/`state` tokens.
