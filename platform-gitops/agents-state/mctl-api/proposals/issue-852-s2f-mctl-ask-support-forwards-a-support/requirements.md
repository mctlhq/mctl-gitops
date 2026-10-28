# mctl_ask_support forwards a minted support-audience token instead of the caller's API token

## Context

`mctl_ask_support` and `mctl_get_support_task` (`internal/mcp/support.go`) send
the caller's own bearer to mctl-support unchanged. `supportDo` reads it with
`s.effectiveToken(ctx)` and puts it in `Authorization`. An MCP client's token
always has `aud` set to the API audience: `/mcp` refuses support-audience tokens
since #849 (`internal/api/support_audience_gate.go`). Once mctl-support sets
`SUPPORT_AUDIENCE_ENFORCEMENT=enforce`, it refuses every API-audience token, and
both tools stop working for every MCP client. That includes the S2 pilot: the
platform owner's Claude against tenant karabu.

The fix: mctl-api mints a short-lived access token for the same principal, with
`aud` set to `OAUTH_SUPPORT_RESOURCE`, and sends only that token to mctl-support.
The minted token is never renewable, never persisted, never logged and never
returned. It adds no authority: it carries only the caller's principal, and a
support-audience token can reach only the four allowlisted routes. If the token
cannot be minted, the tools fail closed. They never fall back to forwarding the
API token.

## User stories

- AS the platform owner using Claude (claude.ai / Claude Code) I WANT `mctl_ask_support(tenant=karabu, ...)` to keep working after mctl-support enforces its audience SO THAT the S2 pilot can run.
- AS a security reviewer I WANT mctl-support never to receive a token valid for the full mctl-api surface SO THAT a compromised or buggy support agent cannot replay the caller's API token against mctl-api.
- AS an operator I WANT every support-token mint to be recorded in the audit log, with principal, tenant and `jti` but never the token SO THAT I can link a support request to the caller who caused it.

## Acceptance criteria (EARS)

- WHEN an authenticated human caller invokes `mctl_ask_support` and passes the tenant check THE SYSTEM SHALL mint one access token with `iss` = the OAuth issuer, `aud` = the configured `OAUTH_SUPPORT_RESOURCE` (single string), `pid` = the caller's `PrincipalID()`, a fresh random `jti`, no `groups` entries, and `exp` <= mint time + min(`SUPPORT_ASK_WAIT` + 60s, 5m).
- WHEN `mctl_ask_support` sends `POST /message:send` or polls `GET /tasks/{id}` THE SYSTEM SHALL send `Authorization: Bearer <minted token>` and SHALL NOT send the caller's token in any header or body.
- WHEN an authenticated human caller invokes `mctl_get_support_task` THE SYSTEM SHALL mint one support-audience token with `exp` <= mint time + min(`SUPPORT_REQUEST_TIMEOUT` + 60s, 5m) and send only that token.
- WHILE a tool call is in progress THE SYSTEM SHALL reuse the single token minted for that call for the send and all its polls, and SHALL NOT mint again or resend after an error.
- THE SYSTEM SHALL NOT issue a refresh token, write a refresh session or flow-store row, or persist the minted token anywhere.
- THE SYSTEM SHALL NOT include the minted token or the caller's token in any log line, audit entry, metric label, tool result or error message.
- WHEN a support token is minted THE SYSTEM SHALL write one audit entry with operation `support.token_mint` and with `UserID`, `PrincipalID`, `Tenant` (the tool's tenant argument, empty for `mctl_get_support_task`) and parameters `tool`, `jti`, `aud`, `exp`. It SHALL write nothing else derived from the token.
- IF `OAUTH_SUPPORT_RESOURCE` is set empty THEN THE SYSTEM SHALL return the tool error `support_audience_not_configured`, SHALL make no request to mctl-support, and SHALL NOT forward the caller's token.
- IF no token minter is wired, which covers stdio mode (`cmd/mcp`) and the in-process server without an OAuth server, THEN THE SYSTEM SHALL return the tool error `support_token_unavailable` and SHALL make no request to mctl-support.
- IF no support-mint auditor is wired THEN THE SYSTEM SHALL refuse the call with `support_token_unavailable` and SHALL make no request to mctl-support.
- IF the caller is an agent run principal (`IsAgent()`, scoped or unscoped, including any tenant-bound run), a service principal, a surface principal, a relayed request (`ViaPrincipalID() != ""`), or has no resolved principal (`PrincipalID() == ""` or `PrincipalUnresolved()`) THEN THE SYSTEM SHALL refuse the mint with `support_token_refused` and SHALL make no request to mctl-support.
- IF the principal check (`checkMintPrincipal`) reports the principal disabled or unknown THEN THE SYSTEM SHALL refuse the mint and SHALL make no request to mctl-support.
- WHILE a scoped agent run token calls either tool THE SYSTEM SHALL keep refusing it exactly as today: `supportTools` is unchanged, and the receipt gate `mctl-api/agent-receipt-gate/v2` still governs `mctl_ask_support`.
- WHEN the minted token is presented back to mctl-api by mctl-support THE SYSTEM SHALL verify it as a support-audience token (`payload.support`), so it reaches only the four allowlisted routes and `/mcp` answers 401.
- THE SYSTEM SHALL keep every other access token byte-identical to today: the new `jti` claim is emitted only by the support mint.

## Out of scope

- The mctl-gitops change that sets `SUPPORT_AUDIENCE_ENFORCEMENT=enforce` on mctl-support. It follows this release.
- `message:stream` over MCP.
- Any change to `/oauth/authorize` or `/oauth/token` resource handling (#849).
- A tenant-binding claim in OAuth access tokens. It is not needed, because every tenant-bound caller is refused before minting (see Open questions).
- Changes to mctl-support.

## Open questions

- **Bound-tenant callers.** The issue asks that "a bound-tenant caller gets a token bound to the same tenant". In this codebase only agent run principals have a bound tenant: `User.BoundTenant()` returns false unless `IsAgent()` is true and the scope is `BoundTenant`. OAuth access tokens also have no tenant-binding claim. This proposal refuses every agent principal before minting, which is strictly narrower than the issue's requirement. So the acceptance test becomes "a bound-tenant run token is refused and nothing is minted or sent". If the reviewer wants agent principals to mint, a tenant claim and a verification rule would have to be designed first.
- **Audit trail (S0c).** No per-call audit row exists today for a human caller's MCP tool call. `AuditScopedToolCall` covers audited agent scopes only. This proposal adds a dedicated `support.token_mint` row, written through the same `Handlers.logAuditCtx`. Audit writes are best-effort, as everywhere in `audit.Logger.Log`. The proposal fails closed only when the auditor is not wired at all, not when a single write fails.
- **TTL versus mctl-support's use of the token.** The token lives for at most `SUPPORT_ASK_WAIT` + 60s (120s by default). If mctl-support uses the forwarded bearer after that, for example to call `POST /api/v1/agent-run-tokens` late in a long task, those calls will 401. This needs confirming against mctl-support#24 and S1b/S1c before the enforce flip. The 5m cap is the knob if it must grow.
- **Relayed surface requests.** These are refused (`ViaPrincipalID() != ""`). No surface is known to call these tools through a relay today. This is recorded in case one does.
- **Live acceptance.** Checking `support_audience_mismatch_total` and the grounded karabu answer can only happen after release and the enforce flip. This investigation cannot observe it.
