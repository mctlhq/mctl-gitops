# Document OAuth token TTL cap, DCR registration limits, and revocation semantics

## Context
Release 4.32.5 of `mctl-api` (shipped 2026-08-16, confirmed live via
`mctl-gitops` commit `063fca6`) landed a connected, 7-commit hardening pass
over the OAuth JWT flow used by the Claude.ai native connector and other
browser-based MCP clients:

- `f9fa393` — access-token TTL is now capped server-side at **24h**
  (`OAUTH_TOKEN_TTL` cannot exceed it; the server refuses to start
  otherwise), and stale DCR registrations expire.
- `217e225` — the `/oauth/register` rate limit rose from 5/min to
  **30/min per IP**, and the DCR client registry is now bounded and
  evicting instead of growing unbounded. The old limit of 5 broke
  multi-process desktop clients (e.g. a CLI that registers once per
  process on a cold start).
- `2ef473e` / `82d75fd` — `/oauth/revoke` now rejects a request that
  carries no token, and no longer returns a false `200 OK` for a
  revocation that never actually happened.
- `ca41c90` / `7439573` / `f5e1437` — registration hardening: bounded
  `client_name` in logs, stricter body/cache-header validation, and the
  rejected `redirect_uri` is now named in the failure response.

`docs/mcp/connecting.md` documents the OAuth flow and token *types* but
says nothing about token *lifetime* or registration *limits*.
`docs/reference/troubleshooting.md` duplicates the token-type table but
has no entry for a rate-limited registration burst or an expired access
token — both of which are new, expected (not-a-bug) behavior a user could
now hit.

## User stories
- AS a developer connecting a multi-process MCP client (e.g. a CLI or IDE
  plugin that spawns several processes) I WANT to know the DCR rate limit
  SO THAT I understand a `429` on startup is a known, bounded limit and
  not a broken integration.
- AS a developer using the Claude.ai OAuth connector I WANT to know my
  access token expires within 24h and renews silently via the
  `refresh_token` grant SO THAT I'm not confused when re-auth is required
  and don't mistake it for a bug.
- AS a developer troubleshooting a rejected revocation or an
  unexpectedly-expired session I WANT a troubleshooting entry SO THAT I
  can self-diagnose instead of filing a support request.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/mcp/connecting.md` THE SYSTEM SHALL state the
  maximum OAuth access-token TTL (24h) and that clients renew silently via
  `refresh_token`.
- IF a reader's MCP client registers multiple times in a short burst
  (e.g. multi-process cold start) THEN THE SYSTEM SHALL document the DCR
  rate limit (30 requests/minute per IP) so a `429` is self-explanatory.
- WHILE describing token revocation THE SYSTEM SHALL state that a
  revocation request must include a token, and that revoking an
  invalid/already-invalid token returns an error rather than a false
  success.
- WHEN a reader hits a `429` on `/oauth/register` or an unexpectedly
  expired session THEN THE SYSTEM SHALL show a matching entry on
  `docs/reference/troubleshooting.md` that links back to
  `docs/mcp/connecting.md`.

## Out of scope
- A full request/response schema reference for `/oauth/register` and
  `/oauth/revoke` (that belongs in `docs/api/index.md` if/when a REST
  reference for these endpoints is added — not part of this proposal).
- Server-side implementation detail (eviction algorithm for the DCR
  registry, exact log redaction rules).
