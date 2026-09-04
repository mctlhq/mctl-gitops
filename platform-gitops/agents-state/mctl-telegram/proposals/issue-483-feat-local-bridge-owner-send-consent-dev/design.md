# Design: issue-483-feat-local-bridge-owner-send-consent-dev

## Current state

**Consent / send gate.** `telegram_accounts.send_enabled` (`internal/db/db.go:323,443`)
is a single boolean per active account row, already mode-agnostic (used by
both hosted and local accounts). `internal/db/store.go` exposes
`IsSendEnabled`/`SetSendEnabled`/`ToggleSendEnabled`, all keyed by an
arbitrary `userID` parameter with no built-in ownership check — the caller
is trusted to have already authorized itself. Today the only writers are:
the admin `set_account_send` MCP tool (`internal/mcp/tools.go:1079`, gated
on `admin:users`) and the in-browser `enable_access` opt-in checkbox
referenced in `store.go:759`'s comment. There is no owner-facing MCP tool.

**Device registry.** `internal/db/local_bridge_devices.go` (landed in #481)
defines the `local_bridge_devices` table and `RegisterDevice`/`GetDevice`/
`RevokeDevice`/`TouchDeviceLastSeen`. The table's doc comment says plainly:
"nothing reads or writes it from `internal/bridge`, `internal/mcp`, or
`internal/workertoken` — it exists so a follow-up sub-issue (activation
endpoints, consent, credential issuance) has a stable Store surface to build
on." #482 wired `RegisterDevice` into activation's consent-approval path
(`internal/oauth/local_bridge_activate.go:1038`, `approveActivation`).
`RevokeDevice` is defined but **nothing calls it yet** — that is this
issue's job. The row today carries no public key or credential-linkage
column.

**Worker-token / credential infrastructure (from #481).**
`internal/auth/localjwt.Claims` already carries `Jti`, `OriginalIssuedAt`,
and an unused `DeviceID` field, with a comment that it exists precisely for
"a future sub-issue [to] mint a device-scoped credential without changing
Mint/Verify again" (`issuer.go:61-69`). `internal/workertoken.Minter.Mint`
mints purpose-scoped tokens (`""` = read-only, `"local-bridge"` = read+send+pin,
`internal/workertoken/tokenhandler.go:61-76`), stamping a fresh `jti` and
`OriginalIssuedAt` anchor. `POST /api/mcp/worker-token`
(`internal/workertoken/tokenhandler.go:133`) is the admin-only HTTP mint,
gated on `admin:users` and `auth.Middleware(provider, true, m)` — the same
plain MCP provider mounted at `/mcp`. `POST /api/mcp/worker-token/renew`
(`internal/workertoken/renewhandler.go:81`) lets a bearer holder renew its
*own* token with identity/scopes copied verbatim from the presented claims,
bounded by `maxRenewalChain` (1 year from `OriginalIssuedAt`) — this is
exactly the "copy scopes forward from a presented JWT" pattern the issue
calls out as the bug PoP refresh must not repeat, and it is why refresh
cannot simply be "renew, but for local-bridge purpose".

Revocation already has a generic, tested backbone:
`internal/db/worker_token_revocations.go` (`RevokeWorkerToken`,
`RevokeWorkerTokensForTelegramID`, `IsWorkerTokenRevoked`,
`ListWorkerTokenRevocations`) and `internal/auth/localjwt.RevocationCache`
— an in-memory, TTL-bounded (`MaxRevocationCacheTTL = 15s`) cache consulted
by `Provider.Authenticate` whenever a token's shape says it needs the check
(`needsRevocationCheck`, covering any jti-bearing token and its `bridge`/
`agent`-audience derivatives). `RevocationCache.Refresh` already documents
the Local-Bridge-eviction-then-reconnect race as the scenario a forced
(non-TTL-bound) refresh exists to close (`revocation.go:118-124`) — written
before this issue, evidently anticipating it.

**Bridge transport.** `internal/bridge/Hub` (`hub.go`) is keyed by
`user_id` only, with the invariant "at most one active daemon per user_id;
a new Register evicts the previous one." `NewBridgeHandler`
(`server.go:50`) authenticates via a provider requiring `aud="bridge"`,
checks `telegram_accounts.mode == "local"`, and calls `hub.Register(id.UserID)`
— it has no notion of *which device* is connected. Bridge tokens themselves
are minted by `POST /api/bridge/token` (`internal/bridge/tokenhandler.go`)
from an already-authenticated identity, 1-hour TTL, and deliberately carry
the parent credential's `Jti`/`OriginalIssuedAt` forward so that revoking
the parent worker token also makes the bridge token's *renewal* fail — but
an already-open websocket connection is not itself re-verified per frame,
so revoking the parent does nothing to a socket that is already open.

**Activation (#482).** `internal/oauth/local_bridge_activate.go` implements
the RFC-8628-shaped device flow: `POST /api/local-bridge/activate/start`
(unauthenticated, device-code + human `user_code`), a browser consent page
gated by Telegram OIDC + a binding cookie, and `POST
/api/local-bridge/activate/consent` as the only write path, calling
`EnsureUserByTelegramID` → `ProvisionLocalAccount` → `RegisterDevice`. The
CLI side (`cmd/local/activate.go`) already generates and persists a local
"device key" via `loadOrCreateDeviceKey()`, but that value is only ever
used as `RegisterDevice`'s **idempotency key** — it is an opaque retry
token, not a cryptographic keypair, and it is never used for proof of
possession. `cmd/local/activate.go`'s own success message says the next
step is exactly this issue: "An operator still needs to issue this device a
token (or, once available, a self-service credential step lands in a later
release, issue #483)."

## Proposed solution

### 1. Consent: `set_send_consent` MCP tool (task 5)

Add a new, non-admin MCP tool, `set_send_consent`, in `internal/mcp/tools.go`
next to `toolSetAccountSend`. Unlike `set_account_send` it takes **no
`telegram_id` argument** — it always acts on `auth.From(ctx).UserID`, the
caller's own account, so there is no target to get wrong and no scope check
beyond "authenticated at all". Implementation is a thin wrapper over the
already-target-agnostic `s.Store.SetSendEnabled(ctx, id.UserID, enabled)` —
no new Store method, no schema change. Every call is audited under the tool
name `"set_send_consent"`, distinct from `"set_account_send"`, satisfying
T10's "distinguishable audit row" requirement by construction (the audit
row's `tool_name` column already exists and already discriminates by the
string passed to `s.audit`). `set_account_send` is untouched: same file,
same scope gate, same tests, same tool name.

This intentionally reuses the exact mechanism the in-browser `enable_access`
opt-in checkbox already uses (`store.go:759`), so a Local Bridge owner and a
hosted-mode owner now have parity: both flip the same column through a
same-session action, neither needs an operator.

### 2. Issuance: self-service device credential mint (task 6)

Add a new file, `internal/oauth/local_bridge_credential.go`, in the same
package as activation (`internal/oauth`) so it can reuse `Server`'s existing
transient-state machinery: the `s.mu`-guarded map pattern, `clientIP`,
the failure-budget limiter, and the sweeper goroutine already built for
activation. Two new unauthenticated-but-`device_id`-scoped endpoints:

- `POST /api/local-bridge/devices/{device_id}/nonce` — mints a fresh,
  single-use, short-lived (30s) nonce for that device_id and returns it.
  Stored in an in-memory map (`s.deviceNonces map[string]*deviceNonce`,
  same shape/eviction-cap discipline as `s.activations`), never a database
  table — nonces live for seconds, so a lost nonce on pod restart costs one
  retried call, matching the "Nonce storage" open question's reasoning.
- `POST /api/local-bridge/devices/{device_id}/credential` — the
  self-service issuance path. Body: `{nonce, signature}` where `signature`
  is Ed25519 over `device_id + "." + nonce` using the device's private key.
  Server-side: look up the device (`store.GetDevice`), refuse if not found
  or already revoked; consume the nonce (single lookup + delete, refusing
  replay or wrong-device-id); verify the signature against
  `local_bridge_devices.device_pubkey` (new column, see Platform impact);
  on success, mint via a **new, narrower** path — not `workertoken.Minter`
  directly, because that type's TTL ceiling (30d default / 90d max) and its
  `renew` semantics do not fit "hours-scale, always read-only at issuance."
  Add `workertoken.MintForDevice(req DeviceMintRequest) (*Minted, error)` in
  `internal/workertoken/minter.go`, sharing `allowedLocalBridgeScopes` and
  the `Claims`/`Jti`/`OriginalIssuedAt`/`Audience` construction logic with
  `Mint`, but: always restricted to `allowedReadOnlyScopes` regardless of
  the account's `send_enabled` (matching T3's "read-only" requirement for
  the *initial* credential), TTL clamped by a new, smaller ceiling pair
  (`defaultDeviceCredentialTTL = 6h`, `maxDeviceCredentialTTL = 24h`,
  distinct constants from `defaultWorkerTokenTTL`/`maxWorkerTokenTTL`), and
  it sets `Claims.DeviceID = device.DeviceID` — the field #481 added and
  left unused for exactly this.

  **The `jti` is minted once per device and then carried forward.** At first
  issuance `MintForDevice` generates a `jti` (as `Mint` does) and writes it
  to a new `local_bridge_devices.current_jti` column. Every later PoP
  refresh for that device REUSES that stored value rather than generating a
  new one.

  **First issuance claims the slot atomically, or loses.** Reading
  `current_jti`, finding it empty and then writing a freshly generated one is
  a check-then-act: two concurrent first-issuance requests for the same
  device both see NULL, both mint, and whichever write lands second orphans
  the other credential for the rest of its TTL -- exactly the unrevocable
  credential this section exists to prevent, reintroduced at the one
  boundary where `current_jti` is not yet set. Issuance therefore claims the
  slot with a single conditional statement:

  ```sql
  UPDATE local_bridge_devices
     SET current_jti = $1, credential_issued_at = $2
   WHERE device_id = $3 AND current_jti IS NULL AND revoked_at IS NULL
  ```

  Zero rows affected means the slot was already claimed (or the device was
  revoked in the meantime, which the same predicate catches -- closing the
  issuance-versus-revocation race along with it) and the request is refused
  with 409; the device retries and takes the refresh path, which is
  idempotent with respect to the stored `jti`. The row is the lock: nothing
  here relies on the two requests reaching the same process. This is not a detail: `Mint`'s own comment states the property
  the whole revocation story rests on — "Jti is generated here and carried
  forward unchanged by every renewal, so revoking it revokes the whole
  lineage" (`minter.go:123-124`). A refresh that minted a fresh `jti` would
  break it. The previous credential would remain valid for the rest of its
  six-hour TTL, would no longer be named by `current_jti`, and could
  therefore be used to open a NEW `/bridge` websocket after the owner
  revoked the device — Hub eviction only closes connections that are already
  open. `MintForDevice` therefore takes the `jti` to stamp as an input, and
  the caller passes the stored one on refresh and the newly generated one
  only at first issuance.

  **`OriginalIssuedAt` is likewise set once, at first issuance**, and is
  persisted next to the `jti` as `local_bridge_devices.credential_issued_at`
  so a derived bridge token keeps pointing at the same anchor. It has to be
  stored, not recovered: PoP refresh presents no previous JWT to read it
  back from, so without a column the only two things an implementer can do
  are invent one anyway or quietly reset the anchor to `time.Now()` on every
  refresh -- which would leave the claim looking correct while meaning
  nothing. It does NOT gate
  PoP refresh: `maxRenewalChain` exists because a human admin is in the loop
  at mint time for worker tokens, and this credential's continued validity is
  gated by live device and account state instead, which is a stronger check
  than a one-year wall clock.

  **The device credential must not be renewable through
  `POST /api/mcp/worker-token/renew`.** That handler accepts any token
  carrying `workerAudience` or `workerBridgeAudience`, and deliberately
  copies identity and scopes forward from the presented token —
  "identity and privileges are copied from the presented token and cannot be
  influenced by the caller" (`renewhandler.go:51-55`) — with
  `allowedLocalBridgeScopes` including `telegram:messages:send`. If a device
  credential carried `workerBridgeAudience`, a device whose owner has just
  revoked send consent could keep that scope indefinitely by calling renew
  instead of refresh, and every state-driven guarantee in this design would
  be reachable around. `MintForDevice` therefore stamps a distinct audience
  marker (`workerDeviceAudience = "mcp-worker-device"`), which
  `NewRenewHandler`'s audience switch does not match, so renew answers 403
  "token is not a worker token" and PoP refresh is the only way forward for
  a device. The renew handler itself is not modified.

This never touches `POST /api/mcp/worker-token` or its handler, satisfying
"the admin worker-token mint endpoint is not reachable by an end user
through any new path added here" by construction: the new endpoints live in
`internal/oauth`, are gated by device PoP instead of `admin:users`, and call
a new `workertoken.MintForDevice` function that the admin HTTP handler never
calls.

### 3. Refresh: PoP-gated, state-derived scopes (task 7)

`POST /api/local-bridge/devices/{device_id}/refresh` reuses the identical
nonce-mint-then-sign flow as issuance (same nonce endpoint, same signature
verification) — one PoP primitive, two callers, per requirements.md's
resolved approach. The difference from issuance is entirely in what
authorizes the mint and what scopes come out:

- No previously-issued JWT is presented or trusted at all. The device
  authenticates purely by proving possession of its Ed25519 private key
  against the `device_pubkey` on file for `device_id`. This sidesteps the
  "copy scopes forward from a presented JWT" bug class structurally: there
  is no presented JWT in the refresh request to copy anything from.
- **Refresh refuses a device that has never issued.** If `current_jti` is
  NULL the handler rejects with 409 and mints nothing. Without that check a
  client can simply skip `/credential` and call `/refresh` first: both
  `current_jti` and `credential_issued_at` are still NULL, so the credential
  would be stamped with an empty `jti` and an empty anchor — and
  `revoke_local_bridge_device`, which denylists `current_jti` when set,
  would silently skip the denylist step and leave that credential valid and
  unrevocable for its whole TTL. First issuance is the only path that claims
  the slot, so it is the only path that may create a lineage.
- On each refresh, the handler does a **live** `store.GetDevice` (revoked
  check) and `store.IsSendEnabled(ctx, device.UserID)` read, and derives
  scopes fresh every time: `allowedReadOnlyScopes` always, plus
  `telegram:messages:send`/`telegram:messages:pin` if and only if
  `send_enabled` is true *at refresh time*. A grant takes effect on the
  device's next refresh; so does a revoke. This is `workertoken.MintForDevice`
  called with `Scopes` computed by the caller rather than left to the
  purpose default, still going through the same TTL ceiling and `DeviceID`
  stamping as issuance.
- Rejection cases map directly to T4's list: missing nonce/signature (400),
  wrong key (signature verification fails — 403, generic message, no
  "your key doesn't match" oracle), wrong device (nonce belongs to a
  different `device_id`, or `device_pubkey` lookup for the presented
  `device_id` doesn't match the signature — both refused identically),
  expired nonce (TTL check before lookup, same as activation's
  `ActivationTTL` pattern), nonce replay (delete-on-consume, so a second
  presentation finds nothing).

### 4. Revocation: device-scoped, wired into refresh and the bridge (task 8)

Add a new owner-scoped MCP tool, `revoke_local_bridge_device` (input:
`device_id`), in `internal/mcp/tools.go`. It first confirms the device
belongs to the caller (`store.GetDevice(ctx, deviceID).UserID == id.UserID`)
— refusing otherwise without disclosing whether the id exists at all for a
different account — then performs, in order:

1. `store.RevokeDevice(ctx, deviceID, reason)` — sets `revoked_at`. Any
   subsequent nonce/issuance/refresh call for this `device_id` fails the
   live `GetDevice` check added in step 3 above, **immediately** (no cache,
   no TTL — satisfies "refresh must fail immediately after revocation").

   **Steps 1 and 2 are one database transaction, and the whole path is
   idempotent.** Marking the row revoked and denylisting its `jti` are two
   halves of one decision: if a crash or a transient error lands between
   them, the device is revoked while its live credential is not denylisted,
   which is the worst of both states — the owner is told the device is gone
   and it can still open connections until its TTL lapses. Worse, a retry
   would find the device already revoked and could reasonably treat the
   whole call as a no-op, wedging that state permanently. So: both writes
   commit together, and re-running the tool on an ALREADY-revoked device
   still denylists `current_jti`, still forces the cache refresh, and still
   evicts — it repairs a partial failure rather than reporting success over
   one. Steps 3 and 4 are outside the transaction by necessity (a cache and
   a websocket are not transactional) and are therefore written to be safe
   to repeat.
2. If the device row's new `current_jti` column is non-empty,
   `store.RevokeWorkerToken(ctx, jti, telegramID, reason, revokedBy)` — this
   denylists the device's entire credential lineage in one call, which is
   sound only because the `jti` is carried forward by every refresh rather
   than regenerated (see the issuance section above); it also covers any
   bridge token minted from it, since `bridge.tokenhandler` copies
   `Jti`/`OriginalIssuedAt` into the child (`tokenhandler.go:87`).
   Then call `localjwt.RevocationCache.Refresh(ctx)` synchronously (not
   waiting for the TTL) — the exact mechanism `RevocationCache.Refresh`'s
   doc comment already names this scenario for.
3. `hub.EvictDevice(userID, deviceID)` (new `Hub` method, see below) —
   actively closes any live `/bridge` websocket for this device, rather
   than waiting out the 1-hour bridge-token TTL.

**Hub device tracking.** `Hub.Register` currently takes only `userID`.
Extend it to `Register(userID int64, deviceID string) chan Envelope`,
storing `deviceID` on `daemonConn`. Add:

```go
func (h *Hub) EvictDevice(userID int64, deviceID string) bool
```

which closes and removes the connection only if the currently-registered
`daemonConn.deviceID` matches — mirroring `UnregisterSend`'s
"only touch the entry if it's still the one we mean" discipline, so a
revoke racing a legitimate reconnect from a *different, non-revoked* device
of the same user cannot evict the wrong session. Plumbing `deviceID` from
the authenticated request into `NewBridgeHandler`'s `hub.Register` call
requires the connecting identity to carry it: add `DeviceID string` to
`auth.Identity` (`internal/auth/identity.go`) and set it in
`localjwt.Provider.Authenticate` from `c.DeviceID` (already decoded, just
not copied today) — a one-line addition next to the existing `Jti`/
`OriginalIssuedAt` copy at `issuer.go:297-307`. `internal/bridge/server.go`
then calls `hub.Register(id.UserID, id.DeviceID)`.

**Revocation SLA (the explicit either/or the issue asks for).** This design
picks **active Hub disconnect as the primary mechanism**, not merely a
documented latency bound, because the deployment already runs the relay at
a single replica (`internal/bridge/DESIGN.md`'s "Status in one line" /
"correctness gap 4" — Hub eviction is reliable precisely because there is
only ever one process holding the websocket). The bounded-latency fallback
is kept as a documented backstop, not the primary control: if `EvictDevice`
ever loses a race (e.g., a reconnect using a not-yet-revoked jti lands
between steps 1-3, or a future multi-replica rollout invalidates the
single-Hub assumption), worst-case exposure is bounded by two independent,
already-existing numbers — `localjwt.MaxRevocationCacheTTL` (15s) before no
*new* bridge token can be minted from the revoked jti, and the existing
1-hour `bridgeTokenTTL` before any already-open connection's underlying
grant would have expired on its own regardless. Both numbers predate this
issue and are unchanged by it.

### 5. Redaction (task 11)

Add to `sensitiveKeys` in `internal/audit/redact.go`: `"user_code"`,
`"device_code"`, `"consent_token"`, `"nonce"`, `"signature"`,
`"device_registration_key"`, `"worker_token"`, `"bridge_token"`. All are
matched case-insensitively against `slog` attribute keys, same as every
existing entry — no new redaction mechanism, just list growth, per the
package's own stated design ("new sensitive field names must be added
there" — CLAUDE.md's Safety rules section). `device_pubkey` is
**deliberately not added**: it is a public key, logging it is not a
disclosure, and redacting it would make debugging device-mismatch reports
(T4's "wrong key"/"wrong device" cases) harder for no security benefit —
this is called out explicitly in code comments at the point it is logged,
so a future reviewer does not "fix" it into the redaction set by reflex.

## Alternatives

1. **Let a device call `POST /api/mcp/worker-token/renew` directly, once
   it somehow obtains a first read-only worker token out of band.**
   Rejected: `renew` copies scopes forward from the *presented* token by
   design (`renewhandler.go:203-210` builds `Claims.Scopes: claims.Scopes`)
   — it is the mechanism the issue's "Security constraints" section singles
   out as "the bug this design exists to prevent." Renew is also
   TTL-ceilinged for a human-administered credential (`maxRenewalChain` =
   1 year), the wrong order of magnitude for "hours-scale."
2. **Loosen `POST /api/mcp/worker-token`'s scope check to allow a caller to
   mint a `purpose=local-bridge` token for their own `telegram_id`, keeping
   the admin path as the only mint path.** Rejected by the issue text
   itself ("without exposing the admin worker-token mint endpoint to the
   user") and because it has no device binding at all — any authenticated
   session, not a specific device, could mint, which fails T3 ("device-bound
   ... credential") outright.
3. **Static per-device shared secret (e.g., an HMAC key baked in at
   activation) instead of asymmetric Ed25519 PoP.** Rejected: the issue's
   security constraints explicitly ask for "Ed25519 (or an equivalent
   reviewed primitive)"; a shared secret sent over the network on every
   refresh (even over TLS) is a weaker property than a signature that never
   requires transmitting the private key, and it complicates key rotation
   (revoking a leaked shared secret and a leaked signing key are the same
   operation with Ed25519, but a leaked shared secret used for both
   direction can't easily distinguish "prove it's you" from "here is the
   secret").
4. **Persist PoP nonces in a database table instead of in-memory.**
   Rejected for now (see requirements.md's "Nonce storage" open question):
   the relay already runs single-replica, activation's identical in-memory
   pattern is proven in production, and a DB round-trip on every nonce
   mint/consume adds latency to a path meant to run every few hours per
   device at low volume.

## Platform impact

**Migrations (additive, backward compatible, all new columns nullable):**

- `local_bridge_devices.device_pubkey` (BLOB/BYTEA, nullable) — Ed25519
  public key registered at activation. Existing rows (none yet, since
  #482 is the only writer and this table is new) are unaffected; a device
  row without a `device_pubkey` simply cannot complete issuance/refresh,
  which only matters if activation somehow completed without submitting
  one — validated by rejecting such `activate/start` requests once this
  ships, same style as the existing field-length/positivity checks in
  `handleActivateStart`.

  **Making the field mandatory is a breaking change for an already-shipped
  client, and is accepted deliberately.** #482 is merged, so a
  `mctl-telegram-local` binary already exists that calls `activate/start`
  without a `device_pubkey`; once this validation lands, that binary's
  activation fails outright. That is the correct trade-off — a device row
  with no public key can never obtain a credential, so admitting it only
  moves the failure later and leaves an unusable row behind — but it must be
  surfaced, not discovered: the rejection SHALL name the required client
  upgrade rather than returning a generic 400, and the release notes for
  this change SHALL state that `activate` requires the matching client
  version. Any device row registered by the older client is unusable and its
  owner re-runs `activate`; there are no such rows in production today.
- `local_bridge_devices.device_pubkey_algo` (TEXT, default `'ed25519'`) —
  future-proofs the "or an equivalent reviewed primitive" allowance without
  a second migration if that ever changes.
- `local_bridge_devices.current_jti` (TEXT, nullable) — the ONE jti of this
  device's credential lineage, claimed atomically at first issuance (see the
  conditional UPDATE above) and thereafter read, not written, by refresh.
  Used by `revoke_local_bridge_device` to find what to denylist, and by
  refresh to stamp the credential it mints.
- `local_bridge_devices.credential_issued_at` (TIMESTAMP, nullable) — the
  `OriginalIssuedAt` anchor for that lineage, written in the same
  conditional UPDATE as `current_jti` and read by every refresh. Refresh
  presents no previous JWT, so this column is the only place the anchor can
  come from.

Both `internal/oauth/local_bridge_activate.go`'s `activateStartRequest` (add
`device_pubkey`) and `RegisterDevice`'s signature (add a `pubkey []byte`
param, threaded from `approveActivation`) need small, additive changes.
`cmd/local/activate.go` needs to generate an Ed25519 keypair (new file,
e.g. `cmd/local/devicekey.go`, alongside the existing `loadOrCreateDeviceKey`
idempotency-token helper — the two remain deliberately distinct: one is a
retry-idempotency string, the other is a persistent signing keypair) and
submit the public key at `activate/start`, storing the private key
`0600`-permissioned next to `bridge_token.json`, inheriting the same
Windows-ACL gap already tracked in `internal/bridge/DESIGN.md` (explicitly
out of scope here, not newly introduced by this change — the daemon already
stores comparably sensitive bearer tokens the same way).

**Resource impact:** the new in-memory nonce map is bounded the same way
`s.activations` is (`MaxPendingActivations`-style cap + TTL sweep), so
memory growth is capped regardless of unauthenticated request volume
against the nonce-mint endpoint (which, like `activate/start`, is
unauthenticated by necessity — `device_id` is a 128-bit `crypto/rand`
value, unguessable, so this is "possession of the id", not "no auth at
all", matching the existing risk posture documented for `RegisterDevice`'s
idempotency key).

**Risks + mitigations:**

- *Device private key loss (reinstall, disk wipe).* No recovery: the user
  re-runs `activate`, which registers a fresh device row and a fresh
  keypair; the old device can be revoked by its owner once the new one
  works. Documented in requirements.md's Out of scope.
- *Nonce-endpoint abuse (flood to grow memory or churn a device's failure
  budget).* Same rate-limiting posture as activation: per-IP nonce
  request caps, sharing `Server.clientIP`'s trusted-proxy-aware derivation
  and the existing failure-window limiter shape.
- *A revoked device's already-open websocket surviving despite `EvictDevice`
  (race, or the connection is on a code path that predates the deviceID
  plumbing during a rolling deploy).* Covered by the documented ≤15s /
  ≤1h backstop above — not a silent gap, a named and bounded one.
- *`current_jti` going stale if a device is refreshed by a compromised
  duplicate of its private key before revocation runs.* Inherent to any
  PoP scheme once the private key itself is copied; out of scope the same
  way a stolen TLS client cert is out of scope for mTLS designs — the
  private key never leaving the device's disk is the daemon's
  responsibility, unchanged by this issue.
