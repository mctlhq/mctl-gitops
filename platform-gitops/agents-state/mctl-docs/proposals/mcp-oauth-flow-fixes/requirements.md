# Document refresh-token rotation, the grace window, and reuse detection for the OAuth flow

## Context
On 2026-09-18, `mctl-api` shipped a three-commit hardening pass on the
OAuth 2.0 PKCE / dynamic-client-registration (DCR) flow used by browser and
MCP clients (Claude.ai native connector, other OAuth-based MCP clients):

- `da6192d` — widened the refresh-token rotation **grace window** from
  30 seconds to 2 minutes. The grace window exists so a client that
  rotated its refresh token but never received the rotation *response*
  (e.g. a dropped connection) can retry on its next refresh cycle
  (observed in production: retries up to ~10 minutes apart) and still get
  the already-issued successor token, instead of being treated as a
  replay attack. Outside the grace window, replaying an already-rotated
  refresh token revokes the **entire token family** — every client sharing
  that refresh lineage gets `invalid_grant` and must re-authenticate. This
  was observed live on 2026-09-18: one legitimate client's retry, arriving
  just outside the old 30s window, triggered a full-family revocation.
- `ea2194b` — bounded two caller-controlled values (`client_id`,
  `client_name`) that get echoed into server logs on a failed token
  exchange, and fixed a `client_name=""` vs. "no such client" log
  ambiguity. Internal logging/diagnostics hardening — no change to any
  response a client receives.
- `3a88f82` — moved client-registration state out of the (attacker-writable)
  `client_name` field into its own internal boolean. Also internal
  logging/diagnostics hardening — no response-shape change.

Of these three, only `da6192d`'s grace-window widening changes behavior a
user can actually observe: a client that previously would have been
logged out (whole token family revoked) by a retried refresh just outside
the old 30-second window now tolerates that retry. The other two commits
are server-side logging correctness fixes with no user-visible effect.

Checked against current content: neither `docs/mcp/connecting.md` nor
`docs/security/authentication.md` currently describes refresh-token
rotation, the grace window, or family-wide revocation on replay at all —
so nothing on those pages is factually wrong today (this is **not** a
"stale/incorrect" gap, contrary to the inbox's initial "possibly stale"
flag). It is an **omission**: a real, already-observed-in-production
failure mode (unexpected full re-authentication after a refresh replay)
has no explanation anywhere a user would look, and `docs/reference/troubleshooting.md`'s
"Unauthorized" entry doesn't mention it either.

## User stories
- AS a developer whose OAuth-connected MCP client was unexpectedly asked
  to re-authenticate, I WANT to know that MCTL rotates refresh tokens on
  every use and revokes the whole token family if an already-used refresh
  token is replayed outside a short grace window SO THAT I understand this
  is expected security behavior, not a bug, and know the fix is to
  reconnect (not to keep retrying the same refresh token).
- AS a developer implementing a custom OAuth-based MCP client, I WANT to
  know refresh tokens rotate on each use and that retrying a refresh
  request within roughly two minutes of the previous attempt is tolerated
  (in case the rotation response was lost) SO THAT I don't accidentally
  build a client that retries far outside that window and gets
  permanently logged out on transient network errors.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/security/authentication.md`'s OAuth JWT section
  THE SYSTEM SHALL state that refresh tokens rotate on every use, and
  that replaying an already-used refresh token outside a short grace
  window revokes the entire token family.
- WHEN a reader opens `docs/reference/troubleshooting.md` THE SYSTEM SHALL
  contain an entry for "unexpectedly logged out of the MCP portal / OAuth
  connector" that names refresh-token rotation and replay as a cause and
  says the fix is to reconnect.
- IF a reader wants exact numeric detail (the grace window's current
  value) THEN THE SYSTEM SHALL state that it is on the order of a couple
  of minutes without committing to an exact figure as a guaranteed
  contract, since the commit message explicitly frames the value as
  tunable based on incident evidence rather than a fixed spec.
- WHILE this is server-side, security-relevant behavior with no
  client-configurable option THE SYSTEM SHALL make clear there is nothing
  for the reader to configure — only to understand.

## Out of scope
- Documenting `client_registered`, the echoed-field length bound, or any
  other internal logging/diagnostics detail from `ea2194b` / `3a88f82` —
  these have no user-visible effect and are not part of any documented
  contract.
- Re-documenting DCR rate limits, access-token TTL, or `/oauth/revoke`
  semantics — already covered by `proposals/mcp-oauth-client-lifetime/`
  (a separate, already-drafted proposal from an earlier commit set).
  Cross-link to it rather than duplicating.
- A sequence diagram of the full PKCE + DCR + refresh-rotation flow (a
  reasonable future addition, but bigger in scope than what these three
  commits justify on their own).
