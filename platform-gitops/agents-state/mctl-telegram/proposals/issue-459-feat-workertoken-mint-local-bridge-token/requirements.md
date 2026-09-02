# Mint send-capable Local Bridge worker tokens without hand-signing

## Context

`POST /api/mcp/worker-token` (`internal/workertoken/tokenhandler.go`) already
lets an admin mint a bounded, audited, renewable JWT for a headless MCP
worker — it exists specifically to replace hand-signing a token with
`OAUTH_JWT_SIGNING_KEY`, the deployment-wide key whose rotation invalidates
every user's session (`SECURITY.md`). Today the endpoint only ever mints
read-only tokens: `allowedReadOnlyScopes` is a fixed list of
`telegram:dialogs:read` and `telegram:messages:read`, and both the mint
handler and the renew handler (`internal/workertoken/renewhandler.go`)
reject any other scope.

A Local Bridge daemon (`cmd/local/`) is a different kind of worker: it needs
`telegram:messages:send` and `telegram:messages:pin` to implement its tools,
and it re-exchanges its stored MCP token for a 1-hour bridge token
indefinitely (`internal/bridge/tokenhandler.go`, `cmd/local/daemon.go`). A
normal OAuth access token lives at most 24 hours, so a Local Bridge daemon
configured with one stops working within a day — the exact failure mode
`docs/runbook.md`'s `MctlBridgeDaemonsFlapping` section already documents as
"there is no supported way to issue a long-lived MCP token today." The
pilot's workaround was to hand-sign an HS256 JWT with
`OAUTH_JWT_SIGNING_KEY` pulled from `secret/platform/mctl-telegram/oauth`
and deliver it out of band — putting the platform's most sensitive secret on
an operator's laptop to serve one user, and doing it as undocumented tribal
knowledge.

This proposal closes that gap the same way #412 closed it for the canary:
add a second, explicitly-named mint path through the existing worker-token
endpoint that is allowed to include send/pin scopes, gated the same way the
read-only path is gated (admin scope, TTL ceiling, `orig_iat`-anchored
renewal chain), and reachable only when the caller explicitly asks for it.
The read-only path itself does not change.

## User stories

- AS an admin operator I WANT to mint a Local Bridge worker token with send
  and pin scopes through the existing worker-token endpoint SO THAT I never
  need to hand-sign a JWT with `OAUTH_JWT_SIGNING_KEY` to provision a Local
  Bridge daemon.
- AS an admin operator I WANT the send-capable mint to require the same
  `admin:users` scope and to be visibly distinct at the call site from the
  read-only mint SO THAT granting send capability is a decision I make
  deliberately, not a default that drifts.
- AS a Local Bridge daemon operator I WANT my worker token to be renewable
  and bounded by an anchored renewal chain, exactly like the read-only
  worker token SO THAT a leaked send-capable token cannot outlive the
  bound the platform already enforces for read-only ones.
- AS an on-call responder I WANT the expiry of a newly minted or renewed
  Local Bridge token to be visible in the mint/renew response and logs SO
  THAT I can check it before `MctlBridgeDaemonsFlapping` fires, instead of
  only after.

## Acceptance criteria (EARS)

- WHEN an authenticated caller with `admin:users` scope POSTs to
  `/api/mcp/worker-token` with a field that names the Local Bridge purpose
  (e.g. `"purpose": "local-bridge"`) THE SYSTEM SHALL mint a token whose
  scopes may include `telegram:messages:send` and `telegram:messages:pin`
  in addition to the existing read-only scopes.
- WHEN a caller POSTs to `/api/mcp/worker-token` without naming the Local
  Bridge purpose THE SYSTEM SHALL preserve today's behavior exactly:
  `allowedReadOnlyScopes` remains the allowlist, and a request for
  `telegram:messages:send` or `telegram:messages:pin` is rejected with 400,
  unchanged.
- IF a caller without `admin:users` scope requests a Local Bridge-purpose
  mint THEN THE SYSTEM SHALL reject it with 403, identical to the existing
  read-only path's admin gate.
- IF a Local Bridge-purpose mint request supplies a scope outside the new,
  explicitly-named send-capable allowlist THEN THE SYSTEM SHALL reject it
  with 400, the same fail-closed behavior `allowedReadOnlyScopes` already
  has.
- WHEN a Local Bridge-purpose token is minted THE SYSTEM SHALL set
  `OriginalIssuedAt` (`orig_iat`) exactly as the read-only mint does, so the
  renewal chain is anchored from the human-in-the-loop mint moment.
- WHEN a Local Bridge-purpose token is presented to
  `POST /api/mcp/worker-token/renew` THE SYSTEM SHALL renew it, preserving
  its send/pin scopes, subject to the same `maxRenewalChain` (365 days from
  `orig_iat`) and `maxWorkerTokenTTL` (90 days per renewal) bounds the
  read-only path already enforces.
- IF a token presented to the renew endpoint carries a scope outside both
  the read-only allowlist and the new send-capable allowlist THEN THE
  SYSTEM SHALL refuse renewal with 403, preserving the existing
  defense-in-depth behavior for tokens that should never have been issued.
- WHILE a worker token (read-only or Local Bridge) is valid THE SYSTEM
  SHALL continue to distinguish it from an ordinary interactive session by
  audience, so the renew endpoint cannot be used to launder a normal user
  session into a long-lived credential.
- WHEN a worker token is minted or renewed THE SYSTEM SHALL log the
  absolute expiry timestamp (not only the TTL duration) at a level an
  operator monitoring mint/renew activity will see, so an expiring Local
  Bridge credential can be caught before `MctlBridgeDaemonsFlapping` fires.

## Out of scope

- Changing or widening `DCRNegotiableScopes` or `allowedReadOnlyScopes`
  themselves — the issue explicitly asks to preserve both as-is.
- Any change to how the Local Bridge daemon (`cmd/local/`) discovers,
  stores, or exchanges its token — this proposal only changes what the
  mint/renew endpoints will issue when asked. `cmd/local/main.go`'s
  `connect --token` flow keeps working unmodified once an admin hands it a
  Local Bridge-purpose token instead of a hand-signed one.
- Issue #454 (`--token-file`, keeping the token out of argv) — related but a
  separate change to `cmd/local`.
- Issue #458 (the other manual half of enabling Local Bridge mode) — a
  separate proposal.
- Proactive alerting/paging on approaching worker-token expiry (e.g. a new
  Prometheus metric or a scheduled expiry-check job). This proposal makes
  expiry visible in the synchronous mint/renew response and logs; wiring
  that into monitoring is a follow-up if the operational need persists.
- A UI/dashboard for minting worker tokens — the endpoint remains
  API-only, consistent with today.

## Open questions

- Exact request shape for naming the purpose: the issue offers two options,
  a `purpose: "local-bridge"` field on the existing request or a sibling
  endpoint. This proposal picks the `purpose` field (see design.md
  Alternatives for why) as the most reasonable interpretation; a reviewer
  who prefers a sibling endpoint can redirect at review time without
  changing the acceptance criteria above.
- Exact audience value for the new token kind (this proposal proposes
  `mcp-worker-bridge`, parallel to the existing `mcp-worker-ro`): not
  specified by the issue. Any distinct, non-empty value satisfies the
  requirements; the concrete string is an implementation detail.
- Whether the send-capable allowlist should also include any future
  telegram write scope not yet in `DCRNegotiableScopes`: out of scope until
  such a scope exists. When one is added, both `DCRNegotiableScopes` and
  this new allowlist need a maintainer's explicit decision, mirroring the
  existing comment on `allowedReadOnlyScopes` about staying in lockstep
  with `DCRNegotiableScopes`.
- Whether "record the expiry somewhere an operator will see" (issue's
  phrasing) should extend beyond structured logs to a Prometheus gauge like
  the canary's `mctl_telegram_canary_token_expires_in_seconds`. This
  proposal treats the log line as sufficient for a human-triggered,
  infrequent admin action; a metric is called out as explicitly out of
  scope above rather than assumed.
