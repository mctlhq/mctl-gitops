# mint_worker_token MCP tool

## Context

Local Bridge (#458, shipped 0.56.0) lets an operator move a user's Telegram
account to local mode via `set_account_mode`, an MCP tool an admin session
can call directly. The other half of enabling Local Bridge for that user —
minting the daemon's long-lived credential — is only reachable as
`POST /api/mcp/worker-token` with `purpose: "local-bridge"`
(`internal/workertoken/tokenhandler.go`, wired at `cmd/server/main.go:470`).
An operator has to hand-assemble a curl call carrying an admin bearer token
to reach it. That is a strict improvement over hand-signing with
`OAUTH_JWT_SIGNING_KEY` (the problem #459 solved), but it still splits one
operator task — "turn a user on for Local Bridge" — across two different
interfaces, and the half that produces a months-long credential is the
least convenient of the two to do carefully.

This proposal adds `mint_worker_token`, an admin-only MCP tool that mints a
worker token the same way `POST /api/mcp/worker-token` does, so an operator
never leaves the MCP session to issue one. The issue is explicit that this
must not become a second implementation of the mint policy: the scope
allowlists, TTL ceiling, audience marker, and `orig_iat` renewal anchor in
`internal/workertoken/tokenhandler.go` are security policy, and letting the
tool re-derive them would let the two paths drift apart silently.

## User stories

- AS an admin operator I WANT to mint a Local Bridge worker token from the
  same MCP session I use to flip a user to local mode SO THAT enabling
  Local Bridge for a user is one workflow instead of an MCP call plus a
  hand-built curl carrying an admin bearer token.
- AS an admin operator I WANT the minted token's expiry returned and logged
  SO THAT a months-long credential is not something only visible once, in a
  response body nobody keeps.
- AS a security reviewer I WANT the MCP tool and the HTTP endpoint to be
  provably running the same allowlist/TTL/audience policy SO THAT the two
  surfaces cannot silently diverge in what they are willing to issue.

## Acceptance criteria (EARS)

- WHEN `mint_worker_token` is called by an identity holding `admin:users`
  THE SYSTEM SHALL mint a worker token for the requested `telegram_id`
  using the same allowlist, default scopes, TTL bounds, and audience
  marker that `POST /api/mcp/worker-token` uses for the same `purpose`.
- WHEN `mint_worker_token` is called by an identity that lacks
  `admin:users` THE SYSTEM SHALL refuse the call without minting a token.
- WHEN a call to `mint_worker_token` is refused for any reason (missing
  scope, invalid `telegram_id`, unknown `purpose`, scope outside the
  purpose's allowlist) THE SYSTEM SHALL record an audit entry for the
  refusal, matching `toolSetAccountMode`'s refuse-is-audited pattern
  (`internal/mcp/tools.go:1042-1052`, the #462 fix).
- WHEN a worker token is minted successfully THE SYSTEM SHALL return a
  structured result containing at least `telegram_id`, `purpose`,
  `scopes`, and `expires_at`, and SHALL record an audit entry and a log
  line carrying `purpose`, `scopes`, `ttl`, and `expires_at` — mirroring
  `NewHandler`'s `slog.Info("worker token minted", ...)` at
  `internal/workertoken/tokenhandler.go:219-220`.
- IF the caller omits `purpose` THEN THE SYSTEM SHALL mint a read-only
  token (`allowedReadOnlyScopes`) and SHALL NOT grant
  `telegram:messages:send` or `telegram:messages:pin` — naming
  `purpose: "local-bridge"` explicitly is the only way to obtain a
  send/pin-capable token.
- IF `purpose` is neither empty nor `"local-bridge"` THEN THE SYSTEM SHALL
  refuse the call (mirroring the HTTP handler's 400 on unknown purpose)
  and audit the refusal.
- IF the caller supplies `scopes` that are not a subset of the allowlist
  selected by `purpose` THEN THE SYSTEM SHALL refuse the call and audit
  the refusal.
- IF `ttl_hours` exceeds the TTL ceiling THEN THE SYSTEM SHALL clamp to
  the ceiling rather than reject the call, matching
  `tokenhandler.go`'s existing clamp behavior.
- WHILE the worker-token signer is not configured (no `OAUTH_JWT_SIGNING_KEY`,
  mirroring the `secret == ""` gate `cmd/server/main.go:470` puts around
  mounting `POST /api/mcp/worker-token`) THE SYSTEM SHALL either omit the
  tool from registration or return a clear configuration error, and SHALL
  NOT panic or silently mint with a zero-value key.
- WHEN the tool's mint path and the HTTP endpoint's mint path are given
  identical inputs (`telegram_id`, `purpose`, `scopes`, `ttl_hours`) THE
  SYSTEM SHALL produce policy-identical results (same allowlist
  acceptance/rejection, same clamped TTL, same audience markers) because
  both call one shared, factored-out policy implementation rather than
  two copies of the same constants.

## Out of scope

- Widening `allowedReadOnlyScopes` — rejected in #459, not reopened here.
- A renewal tool for operators; the daemon renews itself via
  `POST /api/mcp/worker-token/renew` (`internal/workertoken/renewhandler.go`).
- Moving `SESSION_TTL_EXEMPT_TG_IDS` out of gitops config
  (`internal/config/config.go:315`, `internal/db/store.go:63-72`) —
  deliberately a manual, reviewed step per the issue.
- Changing the HTTP endpoint's request/response shape, its auth gate, or
  its route.

## Open questions

- Should the returned token's raw JWT be echoed back verbatim in the tool
  result (as `POST /api/mcp/worker-token` does in its JSON body), or should
  the tool return only metadata (`expires_at`, `scopes`, `purpose`) and
  point the operator at a follow-up step to fetch the secret? The issue's
  "Acceptance" section says "the result includes the token's `expires_at`"
  but does not say the raw token must be withheld, and the whole point of
  the tool is to replace the curl call that returns the token — withholding
  it would leave minting through MCP strictly less useful than the HTTP
  path. Interpretation used here: return the token in the structured
  result, exactly as the HTTP endpoint does, and do not put it in any log
  line (the existing `slog.Info` in `tokenhandler.go` already omits it).
- Should `mint_worker_token` be unconditionally registered like every other
  tool in `internal/mcp/server.go`'s `HTTPHandler`, with a runtime "signer
  not configured" error when `OAUTH_JWT_SIGNING_KEY` is unset, or should it
  be registered only when the server is constructed with a signer? This
  proposal follows the existing pattern (every tool is unconditionally
  registered; `s.addTool` only filters on `ToolFilter`) and returns a clear
  tool-level error when unconfigured, matching `workertoken.NewHandler`'s
  own `signerErr` check at request time.
- Exact field names of the tool's structured result are not specified by
  the issue. This proposal follows the naming already used by sibling
  tools (`setAccountModeResult`, `workerTokenResponse`) — see design.md.
