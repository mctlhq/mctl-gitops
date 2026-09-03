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

    userCode       string // short, human-typable; the ONLY way a browser binds
                          // to this activation. Never appears in any URL.
    codeAttempts   int    // bounded; exhausting the budget denies the activation

    // set once the browser starts the Telegram leg
    oidcState, oidcNonce, oidcVerifier string

    // set once Telegram OIDC has proven the identity, cleared on resolution.
    // Holding this is what makes the consent POST authorised; its presence
    // means "identity proven, approval still outstanding".
    consentToken   string
    verifiedTGID   int64

    // mutated once, under s.mu, only while status is still "pending"
    status         string // "pending" | "awaiting_consent" | "denied" | "done"
    denialReason   string
    resultDeviceID string
}
```

**Every field above is read and written only under `s.mu`** — the same mutex
that already guards `pending` and `enables`. `poll`, the browser leg, and the
sweeper all reach the same `*localBridgeActivation` concurrently, so any
unsynchronised access here is a real data race. `poll` copies the fields it
needs while holding the lock and formats its response after releasing it;
it never hands the pointer to a caller.

**Single resolution.** `denyActivation` and the success path both re-check
`act.status` under the lock and return without effect unless it is still
`pending`/`awaiting_consent`. A second browser leg arriving for an already
resolved activation is refused before any store call.

**`user_code` and the absence of a complete URL.** `start` mints a short
`user_code` (Crockford base32, `crypto/rand`, in the RFC 8628 shape
`XXXX-XXXX`) alongside the long `device_code`. The `verification_uri` is the
constant `https://tg.mctl.ai/local-bridge/activate` with **no query
parameter**: there is deliberately no `verification_uri_complete`. The CLI
prints the `user_code`; the user types it into the page. This is the
load-bearing anti-phishing property — see requirements.md's resolved open
question — and it must not be "simplified" back into a clickable link.

**`POST /api/local-bridge/activate/start`** (unauthenticated, mirrors
`handleAuthorize`'s cap/evict pattern using a new `MaxPendingActivations`
config field): validates `telegram_id > 0` and `device_registration_key != ""`, mints
`device_code := randomToken(32)` and a short `user_code`, stores a
`pending`-status `localBridgeActivation`, returns:
```json
{
  "device_code": "...",
  "user_code": "K7QP-3ZM4",
  "verification_uri": "https://tg.mctl.ai/local-bridge/activate",
  "expires_in": 600,
  "interval": 5
}
```

**`GET /local-bridge/activate`** (unauthenticated browser page): takes **no
parameters** and renders a form asking for the `user_code`. It performs no
lookup, no OIDC round trip and no store call.

**`POST /local-bridge/activate`** (the form target): looks up the activation
by submitted `user_code` under `s.mu`. Unknown/expired/already-resolved, or
an activation whose `codeAttempts` budget is exhausted, re-renders the form
with a single generic "that code is not valid" message (no oracle
distinguishing "unknown" from "expired") and increments the per-session
attempt counter. On a match, mints a fresh `nonce`/PKCE verifier/`oidcState`
exactly like `handleAuthorize` does (reusing the package's existing
`randomToken`/`pkceChallenge` helpers). If the activation already carries an
`oidcState` — a browser leg is in flight — the handler **deletes the
superseded `activationsByState` entry before recording the new one**, so no
orphan key survives to be cleaned up only by TTL. Then 302-redirects to
`s.tgoidc.AuthCodeURL(oidcState, nonce, tgChallenge)`. No
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
4. Identity is proven **and** matches the claim — but that is *not* yet
   authorisation. `finishActivation` stops here: under `s.mu` (and only if the
   activation is still `pending`) it records `act.verifiedTGID`, mints
   `act.consentToken = randomToken(32)`, sets `act.status =
   "awaiting_consent"`, and renders the **consent page**. That page names the
   device (`act.deviceLabel`), names the Telegram account that just signed in,
   shows the `user_code` so the user can check it against their own terminal,
   and offers Approve / Deny — Approve being a `POST /local-bridge/activate/consent`
   carrying `consentToken` as the CSRF token. **No `store.*` call has been made
   at any point in `finishActivation`.**

   Why this step exists: `start` is unauthenticated by design, so an attacker
   can open an activation naming a *victim's* `telegram_id` with the
   attacker's own `device_registration_key`. Without a consent step, the
   victim merely completing a Telegram sign-in satisfies
   `identity.TelegramID == act.claimedTGID` — there is no mismatch for the
   guard in step 3 to catch — and the attacker's device is registered on the
   victim's account. Signing in proves who you are; it must never by itself
   mean "yes, attach this device."

4b. **`POST /local-bridge/activate/consent`** (new handler) validates the
   `consentToken` against the activation under `s.mu`, requires
   `act.status == "awaiting_consent"`, and only then proceeds. A Deny (or TTL
   expiry with no submission) calls `denyActivation` and returns; nothing is
   written. Everything from here on runs in this handler, not in the OIDC
   callback:

5. `store.EnsureUserByTelegramID(ctx, act.verifiedTGID, identity.Username, ...)` to get `uid`.
6. `store.ProvisionLocalAccount(ctx, uid, identity.TelegramID, displayName, username)`:
   - `nil` → brand-new local account, continue.
   - `errors.Is(err, db.ErrAccountAlreadyActive)` → `store.GetAccountMode(ctx, uid)`; if not `db.ModeLocal`, `denyActivation(act, "hosted account")` and render — no `local_bridge_devices` write follows. If it *is* `db.ModeLocal`, this is an idempotent retry (T1): fall through without erroring.
   - any other error → internal error page, activation left `pending` so the CLI's poll keeps returning `pending` until TTL rather than falsely reporting `denied` for a transient DB error.
7. `store.RegisterDevice(ctx, uid, act.deviceLabel, act.deviceRegKey)` — `act.deviceRegKey` (the CLI-supplied `device_registration_key`, never a device id) is passed as the idempotency key, so a second `start`+browser-approve for the same device on the same account collapses onto the same `local_bridge_devices` row (T1), reusing #481's existing `(user_id, idempotency_key)` uniqueness rather than reimplementing idempotency here.
8. Mark `act.status = "done"`, `act.resultDeviceID = deviceID` under `s.mu`, audit via `store.LogToolCall(ctx, uid, "local_bridge_activate", "", "ok", "", "")` (same audit call the rest of the package already uses), render a "you can close this tab" success page.

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
mux.Get("/local-bridge/activate", s.handleActivateForm)     // user_code entry form
mux.Post("/local-bridge/activate", s.handleActivateVerify)  // user_code submit -> OIDC leg
mux.Post("/local-bridge/activate/consent", s.handleActivateConsent)
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
`verification_uri` **and the `user_code`**, telling the user to open the URL
and type the code — the CLI must not print or construct any URL that carries
the code, (d) polls
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
  the browser leg later proves Telegram OIDC ownership of the claimed id
  **and** the signed-in browser then explicitly approves the named device —
  so an attacker who only calls `/start` repeatedly can grow the
  `activations` map (mitigated by `MaxPendingActivations` + TTL, identical
  mitigation to `MaxPendingAuth`) but cannot cause any database mutation
  without also completing a real Telegram sign-in as the claimed account.
  Mitigation: cap + TTL + no store writes before identity match, as designed
  above.
- **Risk: activation phishing (the reason the consent step and `user_code`
  exist).** Because `/start` is unauthenticated, the claimed `telegram_id` is
  attacker-controlled. An attacker can open an activation naming a victim's
  Telegram id with the attacker's own `device_registration_key`. If the flow
  ended at "the signed-in identity matches the claimed id", the victim simply
  completing a Telegram sign-in would register the attacker's device on the
  victim's account — the mismatch guard never fires, because there is no
  mismatch. Escalation: issue #483 binds credentials and proof-of-possession
  refresh to a registered `device_id`, so this would become durable account
  takeover, not a nuisance. Mitigation, both parts load-bearing and neither
  optional: (1) the browser can only reach an activation by the user typing a
  `user_code` printed on their own machine, so the attacker cannot put their
  code in front of the victim, and there is no code-carrying link to send;
  (2) even having reached it, a successful sign-in only advances the
  activation to `awaiting_consent` — the write requires a separate, explicit
  approval of a page that names the device. Any future change that
  reintroduces a `verification_uri_complete`, or that treats the OIDC
  callback as approval, reopens this hole.
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
