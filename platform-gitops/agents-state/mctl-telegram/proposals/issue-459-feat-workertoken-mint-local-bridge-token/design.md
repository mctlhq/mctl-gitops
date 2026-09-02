# Design: issue-459-feat-workertoken-mint-local-bridge-token

## Current state

`internal/workertoken` (package doc, `tokenhandler.go:1-16`) mints bounded,
admin-scoped bearer tokens for headless MCP workers. Two handlers, wired in
`cmd/server/main.go:451-467` behind `auth.Middleware(provider, true, m,
resourceMeta)` at `/mcp`'s own provider (not a dedicated bridge/agent
provider — see the doc comment on `NewHandler`, `tokenhandler.go:74-97`):

- `POST /api/mcp/worker-token` (`NewHandler`, `tokenhandler.go:98-169`):
  requires `admin:users`, target `telegram_id`, mints with
  `aud = ["mcp-worker-ro", <mcpAudience if set>]`, scopes validated against
  `allowedReadOnlyScopes` (`telegram:dialogs:read`, `telegram:messages:read`
  — `tokenhandler.go:50-53`), TTL bounded by `defaultWorkerTokenTTL` (30d) /
  `maxWorkerTokenTTL` (90d) (`tokenhandler.go:36-38`), `OriginalIssuedAt` set
  to now (anchors the renewal chain).
- `POST /api/mcp/worker-token/renew` (`NewRenewHandler`,
  `renewhandler.go:73-193`): no scope required — every privilege-carrying
  field (subject, `telegram_id`, scopes, audience) is copied from the
  presented token's re-verified claims, never from the request body
  (`decodeStrict` rejects unknown fields, so a client cannot smuggle in
  different scopes). Requires `hasAudience(claims.Audience, workerAudience)`
  (`"mcp-worker-ro"`) — this is what stops an ordinary interactive session
  from trading itself for a headless credential
  (`renewhandler.go:33-39,104-107`). As defense in depth, also refuses to
  renew a presented token that carries *any* scope outside
  `allowedReadOnlyScopes` (`renewhandler.go:112-122`) — today this branch is
  unreachable because the mint path cannot produce such a token, which is
  exactly the gap this proposal closes deliberately, not by accident.
  Renewal is bounded in aggregate by `maxRenewalChain` (365d), anchored to
  `OriginalIssuedAt` (or `IssuedAt` for tokens minted before that claim
  existed) so a leaked token cannot be renewed forever
  (`renewhandler.go:14-31,145-159`).

Minted tokens are verified by the same `localjwt.Provider` mounted at `/mcp`
(`internal/auth/localjwt/issuer.go`); nothing routes on the `mcp-worker-ro`
audience value today — it exists purely for forensic/future-proofing
identification (`tokenhandler.go:80-97`). Scopes are enforced per-tool by
`internal/mcp/tools.go`'s `requireScope`/`id.HasScope`
(`tools.go:1270-1278`), e.g. `send_message` requires
`telegram:messages:send` (`media_tools.go:341`, `tools.go:1239-1240`) and
`pin_message` requires `telegram:messages:pin` (`tools.go:659`).

Local Bridge (`docs/local-bridge.md`) uses this same MCP token in two ways:
`cmd/local`'s `connect`/`daemon` commands exchange it repeatedly at
`POST /api/bridge/token` (`internal/bridge/tokenhandler.go`) for a 1-hour
`aud=bridge` token used only to authenticate the daemon's websocket
connection at `GET /bridge` (`internal/bridge/server.go:44-76`) — that
exchange and the relay itself (`internal/bridge/hub.go`,
`internal/bridge/protocol.go`) perform no scope checks at all. The MCP token
is also the bearer credential the daemon's owner configures their assistant
connector with for actual tool calls (`docs/local-bridge.md`: "The MCP token
is issued to you by an operator... the daemon needs a credential it can keep
re-exchanging" — an ordinary 1-hour OAuth access token cannot serve this
role). So `id.HasScope("telegram:messages:send")` in `tools.go` is evaluated
directly against this worker token's `scopes` claim, and today there is no
way to mint one with `telegram:messages:send`/`telegram:messages:pin` short
of hand-signing with `OAUTH_JWT_SIGNING_KEY` — the exact operational risk
`#412` introduced this package to eliminate for the read-only case.

`internal/oauth/scopes.go`'s `DCRNegotiableScopes` already lists all four
scopes (`telegram:dialogs:read`, `telegram:messages:read`,
`telegram:messages:send`, `telegram:messages:pin`) for the DCR-advertisement
use case, but its own doc comment explains why `allowedReadOnlyScopes` is
deliberately not derived from it — coupling them would let a write scope
silently reach the read-only admin-mint allowlist if `DCRNegotiableScopes`
ever grew one.

## Proposed solution

Add a second, explicitly-named allowlist and a second audience marker to
`internal/workertoken`, gated by an opt-in field on the existing mint
request — no new endpoint, no change to the existing default behavior.

**`tokenhandler.go`:**

- New var, placed immediately after `allowedReadOnlyScopes` with a comment
  cross-referencing it (mirroring how `scopes.go` cross-references
  `allowedReadOnlyScopes` today):

  ```go
  // allowedLocalBridgeScopes is the fixed allowlist for worker tokens minted
  // with purpose "local-bridge". Deliberately a separate literal from
  // DCRNegotiableScopes, for the same reason allowedReadOnlyScopes is: this
  // is an admin-mint validation list, not a DCR-advertisement list, and the
  // two must not silently drift together.
  var allowedLocalBridgeScopes = []string{
      "telegram:dialogs:read",
      "telegram:messages:read",
      "telegram:messages:send",
      "telegram:messages:pin",
  }
  ```

- New audience constant next to `workerAudience` (moved, or duplicated with a
  comment — see Alternatives) in `renewhandler.go`:
  `workerBridgeAudience = "mcp-worker-bridge"`.

- `mintWorkerTokenRequest` gains `Purpose string \`json:"purpose,omitempty"\``.
  Empty/absent means today's read-only behavior, unchanged byte-for-byte.
  `"local-bridge"` is the only other accepted value; anything else is a 400.

- `NewHandler`'s body branches once, right after decoding the request, to
  pick `(allowlist, defaultScopes, audienceMarker)` based on `req.Purpose`:
  read-only keeps `allowedReadOnlyScopes` / `"mcp-worker-ro"`; local-bridge
  uses `allowedLocalBridgeScopes` / `"mcp-worker-bridge"`. The existing
  scope-validation loop, TTL bounding, and `OriginalIssuedAt` anchoring are
  unchanged — they already operate on local variables (`scopes`, `ttl`),
  just fed from the branch instead of being hardcoded to the read-only path.
  `isAllowedReadOnlyScope` becomes `isAllowedScope(scope string, allowlist
  []string) bool` (or gains a sibling `isAllowedLocalBridgeScope`; the
  proposal prefers a parameterized helper to avoid a second near-identical
  loop).

- The `slog.Info("worker token minted", ...)` call gains an `"expires_at"`
  field (computed the same way the response body's `ExpiresAt` already is)
  so mint-time expiry is visible in logs without recomputing `iat + ttl` —
  this is the concrete piece of "record the expiry somewhere an operator
  will see" the issue asks for. Same addition to the `"worker token
  renewed"` log line in `renewhandler.go`.

**`renewhandler.go`:**

- `NewRenewHandler` currently hardcodes: (a) requiring `workerAudience`, and
  (b) validating every claimed scope against `allowedReadOnlyScopes`. Both
  become audience-driven: after re-verifying the token, check
  `hasAudience(claims.Audience, workerAudience)` OR
  `hasAudience(claims.Audience, workerBridgeAudience)`; reject (403,
  unchanged message) if neither is present. Then select the matching
  allowlist (`allowedReadOnlyScopes` for `workerAudience`,
  `allowedLocalBridgeScopes` for `workerBridgeAudience`) for the
  defense-in-depth per-scope check at `renewhandler.go:112-122`, and rebuild
  the audience list on re-mint using whichever marker was present (mirroring
  today's "always include the worker marker, rebuild mcpAudience from
  config" comment at `renewhandler.go:161-169`).
- `maxRenewalChain`, the `OriginalIssuedAt` anchoring, and the TTL clamp to
  the remaining chain window are untouched and apply identically to both
  purposes — the issue asks to *keep* this bounding for the more powerful
  credential, not relax it, and this proposal does not introduce a separate,
  looser chain for local-bridge tokens (see Open Questions in
  requirements.md for whether that should change later).

**Wiring (`cmd/server/main.go`):** no change. Both handlers are already
constructed with `(secret, issuer, mcpAudience)` at `main.go:451-467`; the
new behavior is entirely inside the request body / claims the existing
handlers process.

**Docs:** `docs/local-bridge.md`'s `connect` step and
`docs/runbook.md`'s `MctlBridgeDaemonsFlapping` "Likely causes" /
"Bridge-token expiry loop" section get a short pointer: mint a local-bridge
token with `{"telegram_id": ..., "purpose": "local-bridge"}` instead of
hand-signing, and check the mint/renew log line's `expires_at` field before
assuming the daemon itself is broken.

## Alternatives

1. **Widen `allowedReadOnlyScopes` to include send/pin.** Explicitly
   rejected by the issue: the existing comment block explains at length why
   write scopes are excluded, and a read-only-intent mint should keep
   failing closed. Also would silently grant send capability to every
   existing/future caller of the plain (no-`purpose`) request shape — a
   default that drifted rather than a decision made at the call site, which
   is precisely what the issue says to avoid.

2. **A sibling endpoint, `POST /api/mcp/worker-token/local-bridge`
   (separate handler function).** Considered because it makes the
   capability boundary maximally visible in routing/wiring, matching the
   issue's "a `purpose: "local-bridge"` field on the request, or a sibling
   endpoint" phrasing. Dropped in favor of the `purpose` field because: (a)
   the mint and renew logic (admin gate, TTL bounding, `OriginalIssuedAt`
   anchoring, `decodeStrict`) would otherwise need to be duplicated or
   factored into a shared internal helper anyway — a field-driven branch
   inside the existing handler achieves the same sharing with less surface;
   (b) `NewRenewHandler` already has to branch on which allowlist to use
   based on the *presented token's* audience regardless of how the token was
   minted, so a second mint endpoint would not simplify the renew side at
   all; (c) the wiring in `main.go` stays a two-route pair
   (`worker-token`, `worker-token/renew`), unchanged, which is one fewer
   thing for an operator to learn about when reading the route table.

3. **Derive the local-bridge allowlist from `DCRNegotiableScopes` (i.e.
   reuse that list directly instead of a new literal).** Rejected for the
   same reason `allowedReadOnlyScopes` itself is not derived from it today
   (`scopes.go`'s own comment): `DCRNegotiableScopes` is scoped to the
   DCR-advertisement use case, and coupling admin-mint validation to it
   would let a future scope added there reach this allowlist without a
   deliberate decision. A second small literal costs little and preserves
   the "explicitly-named set" property the issue asks for.

4. **A single unified allowlist plus a `write: bool` request field** instead
   of a `purpose` string. Rejected because it generalizes past what is
   needed today (there is exactly one write-capable purpose, local-bridge)
   and a boolean does not self-document *why* write scopes are being
   requested the way a named purpose does — the issue's own framing
   ("granting send is a decision someone made") reads more naturally as a
   named purpose than a flag.

## Platform impact

- **Migrations:** none. No schema change; `internal/db` is untouched.
- **Backward compatibility:** the default (no `purpose` field) mint and
  renew paths are byte-for-byte unchanged — same allowlist, same audience,
  same error messages, same defaults. Existing callers (the canary,
  `cmd/canary/renew.go`) are unaffected. The renew handler's audience check
  changes from `== workerAudience` to `workerAudience OR
  workerBridgeAudience`, which only widens what is *accepted*, never what
  was previously accepted — no existing token becomes unrenewable.
- **Resource impact:** negligible — one more `var` slice, one more string
  field, one more branch per request. No new dependencies, no new
  goroutines, no new external calls.
- **Risks + mitigations:**
  - *Risk:* a caller sets `purpose: "local-bridge"` by mistake (e.g. copy-
    pasted from an example) and mints a send-capable token for a worker that
    should have stayed read-only. *Mitigation:* the field is opt-in and
    named for its intended use; the mint response and log line surface
    `scopes` explicitly (`tokenhandler.go:164`, unchanged) so the minted
    scopes are visible immediately, the same review surface that exists
    today for the read-only path.
  - *Risk:* the renew handler's widened audience check accidentally lets a
    read-only token be renewed as if it were local-bridge, or vice versa.
    *Mitigation:* the allowlist used for the defense-in-depth scope check
    and the audience rebuilt on re-mint are both selected from *which*
    marker was present on the *presented* token, not from any caller input
    — the same "every privilege-carrying field comes from verified claims,
    never the request body" property `renewhandler.go`'s doc comment
    already asserts, extended to cover which-of-two allowlists rather than
    only whether-allowlisted.
  - *Risk:* a send-capable worker token leaks. *Mitigation:* unchanged from
    today's read-only case — bounded TTL (max 90 days per mint/renewal),
    `maxRenewalChain` (365 days aggregate), and the fact that this remains
    an admin-gated mint (`admin:users`) with an audit log line
    (`admin_user_id`, `target_tg_id`, `scopes` — extended with
    `expires_at`). This is a materially bigger credential than a read-only
    worker token, which is exactly why the issue insists the same bounding
    apply, not weaker bounding — this proposal does not invent a longer
    leash for it.
  - *Risk:* the new `expires_at` log field is redundant with the existing
    `ttl` field and just adds log volume. *Mitigation:* accepted as a minor,
    worthwhile cost — the issue specifically asks for expiry to be visible
    to an operator without recomputation, and `ttl` alone requires reading
    the log's own timestamp and doing arithmetic under incident pressure.
