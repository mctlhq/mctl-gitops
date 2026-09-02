# Mint send-capable Local Bridge worker tokens without hand-signing

## Context

`POST /api/mcp/worker-token` (`internal/workertoken/tokenhandler.go`) already
lets an admin mint a bounded, admin-scoped, TTL-limited MCP bearer token for a
headless worker instead of hand-crafting a JWT with `OAUTH_JWT_SIGNING_KEY`
(the key that signs every user's token and whose rotation invalidates every
user's access at once, per `SECURITY.md`). It works today, unchanged, for a
read-only worker such as the canary.

It does not work for a Local Bridge daemon. `allowedReadOnlyScopes` is a
fixed, deliberately-not-derived-from-`DCRNegotiableScopes` allowlist of
`telegram:dialogs:read` and `telegram:messages:read` only. A Local Bridge
daemon's long-lived MCP token (the one `mctl-telegram-local connect`
exchanges repeatedly for 1-hour bridge tokens, per `docs/local-bridge.md`) is
also the credential a real user's tool calls run under for that account, so
it must additionally carry `telegram:messages:send` and
`telegram:messages:pin` for `send_message`/`pin_message` (and friends) to
work — `internal/mcp/tools.go`'s `requireScope`/`id.HasScope` checks are
evaluated against exactly this token's `scopes` claim. Because the endpoint
has no way to grant those scopes today, the only way to enable send for a
pilot Local Bridge user was to hand-sign a token directly with
`OAUTH_JWT_SIGNING_KEY` — reintroducing the exact operational risk `#412`
introduced this endpoint to remove, and doing it as undocumented tribal
knowledge.

The issue is explicit that `allowedReadOnlyScopes` itself must not widen: the
comment above it explains why write scopes are excluded and why the list is
intentionally not derived from `DCRNegotiableScopes`, and that reasoning
still holds for a worker that has no business sending messages. This proposal
adds a second, explicitly-named path that a caller must opt into, so granting
send capability is a decision visible at the call site rather than a default
that silently widened.

## User stories

- AS an admin enabling a user's Local Bridge daemon I WANT to mint a
  send-and-pin-capable worker token through the same admin-mint endpoint I
  already use for read-only workers SO THAT I never need to touch
  `OAUTH_JWT_SIGNING_KEY` or hand-sign a JWT to serve one user.
- AS an admin who minted a Local Bridge token I WANT the daemon to be able to
  renew that token itself before it expires SO THAT the same 30-day
  operational chore `#412` already removed for read-only workers does not
  reappear for send-capable ones.
- AS the operator who reads `MctlBridgeDaemonsFlapping` I WANT the token's
  expiry recorded at mint (and renewal) time in a place I can check before
  the alert fires SO THAT "the MCP token expired" is a five-second check, not
  a debugging session (per `docs/runbook.md`'s "Bridge-token expiry loop"
  likely cause).
- AS a future reader of `internal/workertoken` I WANT the read-only allowlist
  to stay untouched and the send-capable path to be a distinct, explicitly
  named set SO THAT a worker minted for a read-only purpose keeps failing
  closed on write scopes, exactly as the existing package doc comment
  requires.

## Acceptance criteria (EARS)

- WHEN an admin (bearing `admin:users`) calls `POST /api/mcp/worker-token`
  with `"purpose": "local-bridge"` THE SYSTEM SHALL validate requested scopes
  (or default scopes, if omitted) against a new, explicitly-named allowlist
  that includes `telegram:messages:send` and `telegram:messages:pin` in
  addition to the existing read-only scopes.
- WHEN an admin calls `POST /api/mcp/worker-token` with no `purpose` field (or
  `purpose` omitted/empty) THE SYSTEM SHALL behave exactly as it does today:
  validate against `allowedReadOnlyScopes` only, and mint a token with
  `aud` containing `"mcp-worker-ro"`.
- WHEN an admin calls `POST /api/mcp/worker-token` with `"purpose":
  "local-bridge"` and no `scopes` field THE SYSTEM SHALL default to the full
  local-bridge scope set (read + send + pin), matching the default-to-full-
  allowlist behavior the read-only path already has.
- IF a caller supplies a scope not in the allowlist selected by `purpose`
  THEN THE SYSTEM SHALL reject the request with 400 and an error naming the
  offending scope, exactly as it does today for the read-only path.
- IF a caller supplies an unrecognized `purpose` value THEN THE SYSTEM SHALL
  reject the request with 400 rather than silently falling back to
  read-only.
- WHILE minting a `purpose: "local-bridge"` token THE SYSTEM SHALL apply the
  same admin gate (`admin:users`), the same `defaultWorkerTokenTTL` /
  `maxWorkerTokenTTL` bounds, and the same `OriginalIssuedAt` anchoring as
  the read-only path — no weaker bounding for the more powerful credential.
- WHEN a `purpose: "local-bridge"` token is presented to
  `POST /api/mcp/worker-token/renew` THE SYSTEM SHALL renew it (subject to
  the existing `maxRenewalChain` ceiling anchored on `OriginalIssuedAt`),
  preserving its send/pin scopes, the same way the read-only path is renewed
  today.
- IF a token minted for one purpose (its audience marker) carries a scope
  outside that purpose's allowlist THEN THE SYSTEM SHALL refuse renewal,
  exactly as the current defense-in-depth check does for the read-only path
  today.
- WHEN a worker token (either purpose) is minted or renewed THE SYSTEM SHALL
  log the token's absolute expiry (`expires_at`), not just its TTL, so an
  operator scanning logs for a flapping daemon can see the expiry without
  recomputing `iat + ttl`.
- WHILE `allowedReadOnlyScopes` is defined THE SYSTEM SHALL NOT be modified
  by this proposal — the local-bridge allowlist is a new, separate variable.

## Out of scope

- Widening `allowedReadOnlyScopes` itself. Explicitly rejected by the issue.
- Automatic pre-expiry alerting/paging (e.g. a scheduled job that warns N
  days before a worker token expires). The issue asks only that expiry be
  recorded somewhere an operator will see it at mint time, not that the
  platform build new alerting infrastructure.
- Changes to `#454` (`--token-file`, argv exposure) and `#458` (the other
  manual half of enabling local mode) — related but separate issues.
- Any change to how the Local Bridge relay (`internal/bridge`) or daemon
  (`cmd/local`) itself works. This proposal only changes what scopes an
  admin-minted worker token can carry and how that is logged; it does not
  touch the bridge protocol, the websocket relay, or `set_account_mode`.
- Per-tool scope changes in `internal/mcp/tools.go`. `requireScope` /
  `id.HasScope` already gate `send_message`/`pin_message` on
  `telegram:messages:send`/`telegram:messages:pin`; this proposal only makes
  it possible for an admin-minted token to legitimately carry those scopes.
- A Prometheus metric/gauge for worker-token expiry. A structured log field
  is the concrete, minimal deliverable this proposal implements; whether a
  metric is also warranted is recorded below as an open question.

## Open questions

- Should the local-bridge scope default be the full set (read + send + pin)
  or send/pin only (forcing an admin to explicitly request read scopes too)?
  This proposal defaults to the full set, mirroring the existing read-only
  path's "omit scopes to get the sensible default" behavior and matching
  what a Local Bridge daemon actually needs end-to-end.
- Should `maxRenewalChain` (currently 365 days, applied uniformly) be
  shortened specifically for send-capable tokens, given they are a bigger
  credential? The issue only asks to "keep" the existing anchoring, not to
  tighten it further, so this proposal reuses the same constant for both
  purposes and records the option to differentiate later if this is judged
  insufficient.
- Is a structured log line sufficient for "recording the expiry somewhere an
  operator will see... before the alert does," or does this warrant a
  Prometheus gauge (e.g. per-target-`telegram_id` expiry, mirroring the
  canary's own client-reported expiry metric in `cmd/canary/main.go`)? This
  proposal implements the log line as the concrete, low-risk deliverable and
  leaves a gauge as a follow-up if log-based visibility proves insufficient
  in practice — a server-side gauge over admin-minted tokens has cardinality
  and staleness considerations (a token that is later revoked or superseded
  needs its series retired) that deserve their own design pass.
- Naming: this proposal uses `"purpose": "local-bridge"` as the request field
  and `"mcp-worker-bridge"` as the new audience marker, following the
  issue's suggested shape and the existing `"mcp-worker-ro"` naming
  convention. Not derived from any existing constant, so it is open to
  bikeshedding at review time, but the behavior it gates is unambiguous.
