# Design: issue-459-feat-workertoken-mint-local-bridge-token

## Current state

`internal/workertoken/tokenhandler.go` implements `POST /api/mcp/worker-token`,
mounted in `cmd/server/main.go` (lines ~447-467) behind
`auth.Middleware(provider, true, m, resourceMeta)`, the same plain MCP
`provider` mounted at `/mcp`. The handler:

- Requires `id.HasScope("admin:users")` (line 111) — 403 otherwise.
- Reads `mintWorkerTokenRequest{TelegramID, Scopes, TTLHours}` via
  `decodeStrict` (`internal/workertoken/json.go`), which rejects unknown
  fields.
- Defaults `Scopes` to package-level `allowedReadOnlyScopes` (currently
  `["telegram:dialogs:read", "telegram:messages:read"]`, lines 50-53) when
  the caller omits scopes, and rejects (400) any requested scope not in
  that list via `isAllowedReadOnlyScope` (lines 129-134, 172-179).
- Clamps `TTLHours` between `defaultWorkerTokenTTL` (30 days) and
  `maxWorkerTokenTTL` (90 days) (lines 136-142).
- Mints via `localjwt.Issuer.Mint` with
  `Audience: []string{"mcp-worker-ro", <mcpAudience if set>}` and
  `OriginalIssuedAt: time.Now().Unix()` (lines 144-158) — this is the
  human-in-the-loop anchor the renewal chain depends on.
- Logs `slog.Info("worker token minted", admin_user_id, target_tg_id,
  scopes, ttl)` (line 164) — note: TTL duration, not absolute expiry.

`internal/workertoken/renewhandler.go` implements
`POST /api/mcp/worker-token/renew`, mounted right after the mint endpoint
with the same middleware but no scope requirement — it mints only for the
identity in the bearer token already presented. It:

- Re-verifies the raw bearer via `localjwt.Verify` (lines 89-102) to recover
  claims `auth.Identity` drops.
- Requires `hasAudience(claims.Audience, workerAudience)` where
  `workerAudience = "mcp-worker-ro"` (const, line 39) — 403 otherwise. This
  is what stops an ordinary interactive session token from being renewed
  into a long-lived credential.
- Defense-in-depth loop (lines 115-122): rejects renewal (403) if
  `claims.Scopes` contains anything outside `isAllowedReadOnlyScope` — i.e.
  today, ANY non-read-only scope refuses renewal unconditionally.
- Anchors the renewal ceiling via `originAnchor(claims)` (falls back to
  `IssuedAt` for pre-`orig_iat` tokens) plus `maxRenewalChain` (365 days),
  clamping (not rejecting) the requested TTL to whatever remains
  (lines 145-159).
- Rebuilds `Audience` from configuration the same way the mint handler does
  (lines 161-169), preserving `claims.Scopes` unchanged (line 173).

Both handlers are wired in `cmd/server/main.go` only when `cfg.OAUTHJWTSecret`
is set, using `selectAgentIssuer(cfg)` as issuer and `cfg.OAUTHJWTAudience`
as the optional extra audience — identical wiring for both endpoints.

Separately, `internal/oauth/scopes.go`'s `DCRNegotiableScopes` already lists
all four scopes (`telegram:dialogs:read`, `telegram:messages:read`,
`telegram:messages:send`, `telegram:messages:pin`) for the DCR-advertisement
use case, and its doc comment explicitly says this list must NOT be reused
to derive `allowedReadOnlyScopes`, to avoid a write scope silently reaching
the read-only admin-mint allowlist if `DCRNegotiableScopes` grows one.

`cmd/local/main.go`'s `connect --token` command takes an MCP JWT via
`--token` and exchanges it at `POST /api/bridge/token`
(`internal/bridge/tokenhandler.go`) for a 1-hour bridge token, persisted to
`~/.config/mctl-telegram-local/bridge_token.json`. `cmd/local/daemon.go`
re-exchanges before the bridge token expires
(`refreshBridgeToken`, lines 58-...). Neither file changes in this proposal
— they already work with any sufficiently-scoped, sufficiently-long-lived
MCP JWT; today nothing produces one through a supported path.

`docs/runbook.md`'s `MctlBridgeDaemonsFlapping` section already documents
"there is no supported way to issue a long-lived MCP token today" as the
most likely root cause of daemon flapping — this proposal is what that
runbook entry has been waiting for.

## Proposed solution

Add a second, explicitly-named scope set and route it through a `purpose`
field on the existing mint request, rather than widening
`allowedReadOnlyScopes` or deriving it from `DCRNegotiableScopes` (both
ruled out by the issue).

### 1. `internal/workertoken/tokenhandler.go`

- Add `allowedBridgeScopes []string` package var, containing all four
  `DCRNegotiableScopes` values written out explicitly (not imported from
  `internal/oauth`), mirroring the existing doc-comment reasoning for
  `allowedReadOnlyScopes`: keeping this package's allowlists as local,
  literal, independently-reviewed constants means a future scope added to
  `DCRNegotiableScopes` cannot silently become mintable here, in either
  direction.
- Add `Purpose string` (json `"purpose,omitempty"`) to
  `mintWorkerTokenRequest`. Accepted values: `""` (default, today's
  read-only behavior) and `"local-bridge"`. Any other value is a 400
  ("unknown purpose"), matching the handler's existing fail-closed style.
- Branch scope validation and default-scope selection on `Purpose`:
  - `Purpose == ""`: exactly today's behavior, byte-for-byte
    (`allowedReadOnlyScopes`, `isAllowedReadOnlyScope`).
  - `Purpose == "local-bridge"`: default scopes become
    `allowedBridgeScopes` (the full send+pin+read set — a Local Bridge
    daemon needs send and pin, and there is no reason to omit read given
    it already needs `telegram:dialogs:read`/`telegram:messages:read` for
    its other tools); explicit `Scopes` must be a subset of
    `allowedBridgeScopes`, checked by a parallel `isAllowedBridgeScope`.
- Branch the `Audience` on `Purpose` too: `Purpose == "local-bridge"` mints
  with `workerBridgeAudience = "mcp-worker-bridge"` instead of
  `workerAudience = "mcp-worker-ro"` (plus `mcpAudience` as before). This is
  the load-bearing decision: the renew handler's defense-in-depth check
  needs a way to know which allowlist applies to a presented token, and the
  audience is already the mechanism (`workerAudience` const) that marks "this
  is a worker token" versus an ordinary session — extending it to also mark
  "which kind" is the smallest change that keeps the renew handler's
  guarantees intact instead of loosening them.
- Log line gets an added `expires_at` field (absolute RFC3339 timestamp,
  already computed for the response body) alongside the existing `ttl`
  field, for both purposes — this is the "record the expiry somewhere an
  operator will see" ask; `slog.Info` output is already where an admin
  running this command watches for confirmation.

### 2. `internal/workertoken/renewhandler.go`

- Replace the single `workerAudience` constant's use as the sole "is this a
  worker token" test with a check against both `workerAudience` and the new
  `workerBridgeAudience`, and remember which one matched.
- Replace the flat `isAllowedReadOnlyScope` defense-in-depth loop with a
  purpose-aware check: read-only-audience tokens keep being validated
  against `allowedReadOnlyScopes` exactly as today; bridge-audience tokens
  are validated against `allowedBridgeScopes`. A token whose audience
  matches neither is rejected with the existing 403 "token is not a worker
  token" — unchanged for anything that isn't one of these two kinds.
- Rebuild `Audience` on renewal using whichever of the two worker audiences
  the presented token carried (plus `mcpAudience` as before), so a renewed
  Local Bridge token stays renewable, and a renewed read-only token still
  cannot silently pick up send scopes it never had.
- `maxRenewalChain` (365 days) and `maxWorkerTokenTTL` (90 days) apply
  unchanged to both kinds — the issue is explicit that a send-capable
  long-lived token "deserves the bounding that already exists, not less,"
  and nothing about a 90-day-per-renewal / 365-day-chain ceiling is
  read-only-specific.
- Log line gets the same `expires_at`-alongside-`ttl` addition as the mint
  handler.

### 3. `cmd/server/main.go`

No wiring change: both handlers are already constructed with `secret,
issuer, mcpAudience` and mounted at the existing routes. The new behavior
is entirely inside the two handler functions, reachable through the
existing `POST /api/mcp/worker-token` and `.../renew` endpoints.

### 4. `docs/runbook.md`

Update the `MctlBridgeDaemonsFlapping` "Likely causes" bullet that currently
reads "there is no supported way to issue a long-lived MCP token today" to
point at the new `purpose: "local-bridge"` mint path instead, and add a
one-line diagnostic: check the mint/renew log's `expires_at` (or re-mint)
before assuming a different root cause. This keeps the runbook's own
"undocumented tribal knowledge" problem (the issue's framing) from
persisting after the fix ships.

## Alternatives

1. **Sibling endpoint (`POST /api/mcp/worker-token/bridge`) instead of a
   `purpose` field.** The issue offers this as an equally valid shape.
   Rejected in favor of the `purpose` field because the two mint paths
   share every other piece of logic (admin gate, TTL clamping, `orig_iat`
   anchoring, response shape) — a sibling endpoint would either duplicate
   that logic or immediately factor it into a shared internal function
   called by two thin wrappers, which is more surface area than a single
   `if Purpose == "local-bridge"` branch for the same net behavior. A
   `purpose` field also keeps one endpoint to document, gate, and rate-limit
   ops-side. The tradeoff — a reviewer scanning the handler for "can this
   mint send scopes" has to read the branch instead of the route table — is
   why this is recorded as an open question rather than a closed decision:
   a reviewer who weighs that differently can redirect to the sibling-route
   shape without changing any acceptance criterion in requirements.md.

2. **Widen `allowedReadOnlyScopes` to include send/pin, gated by a
   separate scope check.** Rejected outright — the issue explicitly forbids
   this ("Do not widen `allowedReadOnlyScopes`"), and the existing doc
   comment's reasoning (a read-only mint must fail closed, not depend on a
   second gate remembering to run) still holds.

3. **Derive the new send-capable allowlist from `DCRNegotiableScopes`
   directly (`oauth.DCRNegotiableScopes` imported into `workertoken`).**
   Rejected: `internal/oauth/scopes.go`'s own doc comment says the two
   lists are intentionally decoupled so a future DCR-scope addition can't
   silently reach the admin-mint allowlist. Importing it for the new
   bridge-purpose allowlist would reintroduce exactly that coupling one
   allowlist over from where the original comment warns about it. Keeping
   `allowedBridgeScopes` a literal, local list costs four lines of
   duplication and buys the same drift-safety `allowedReadOnlyScopes`
   already has.

4. **New standalone package (e.g. `internal/bridgetoken`) instead of
   extending `internal/workertoken`.** Rejected: the issue frames this as
   "most of the machinery already exists" in `workertoken` and asks for a
   second allowlist reachable through it, not a parallel implementation.
   `tokenhandler.go`'s own package doc already explains why worker-token
   minting is its own package separate from `internal/agentapi` and
   `internal/bridge`'s token handlers; splitting Local Bridge minting into
   yet another package would recreate the same "should this really be
   separate" question the doc comment already resolved once, for no
   security or clarity gain — the two purposes share every invariant that
   matters (admin gate, TTL ceiling, anchored renewal).

## Platform impact

- **Migrations**: none. No schema or persisted-state change; tokens remain
  stateless bearer JWTs.
- **Backward compatibility**: fully additive. `Purpose` is
  `omitempty`/optional and defaults to today's read-only behavior; existing
  callers (including the canary, which already uses this endpoint's
  read-only path per its own comments in `cmd/canary/main.go` and
  `cmd/canary/renew.go`) see no behavior change. The renew handler's
  audience check widens from "equals `mcp-worker-ro`" to "equals
  `mcp-worker-ro` OR `mcp-worker-bridge`" — strictly additive, no existing
  token stops renewing.
- **Resource impact**: negligible — no new dependencies, no new
  goroutines, no new storage. One extra string comparison per request.
- **Risks + mitigations**:
  - *Risk*: a send-capable long-lived token is a materially bigger
    credential than a read-only one; a bug in the purpose branch could let
    a read-only request slip into the bridge allowlist or vice versa.
    *Mitigation*: mirror the existing test structure exactly —
    `tokenhandler_test.go` already has `TestNewHandler_RejectsWriteScope`
    for the read-only path; add its Local Bridge-purpose counterpart
    (`TestNewHandler_BridgePurposeAllowsSendScope`,
    `TestNewHandler_DefaultPurposeStillRejectsSendScope`) so both branches
    are independently pinned. Same pairing for `renewhandler_test.go`.
  - *Risk*: the renew handler's defense-in-depth loop, once purpose-aware,
    could regress into effectively trusting the presented token's audience
    without validating scopes against the matching allowlist — reopening
    the exact escalation the original loop existed to prevent.
    *Mitigation*: keep the loop unconditional (every renewal path always
    revalidates every scope against its matching allowlist; there is no
    "trust the audience, skip the scope check" branch), and add a test
    that a bridge-audience token carrying a scope outside
    `allowedBridgeScopes` (e.g. a hypothetical future scope) is refused
    renewal exactly like today's `TestRenew_RejectsScopeOutsideAllowlist`.
  - *Risk*: an admin mistakenly mints a send-capable token for an account
    that should stay read-only, because `purpose` is easy to set without
    thinking. *Mitigation*: this is the tradeoff the issue explicitly
    accepts ("granting send is a decision someone made rather than a
    default that drifted") — the mitigation is that it requires a
    deliberate non-default field, `admin:users` scope, and lands in the
    existing structured log (`admin_user_id`, `target_tg_id`, `scopes`)
    for audit, same as every other admin mint.
  - *Risk*: rollout risk is low because the feature is opt-in per request;
    a deployment upgrading to this version changes no existing behavior
    until an admin passes `purpose: "local-bridge"`.
