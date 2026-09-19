# Proposed content: mcp-oauth-flow-fixes

> **Source:** mctl-api@da6192d (behavior change), mctl-api@ea2194b, mctl-api@3a88f82 (internal logging hardening, cited for completeness — no user-visible content below is drawn from these two)

This proposal touches two locations. Each block below states its own
**Apply to** target and mode.

---

## Block 1

> **Apply to:** `mctl-docs/docs/security/authentication.md` (UPDATE)
> **Source:** mctl-api@da6192d

**Before** (excerpt):

```markdown
## OAuth JWT

OAuth 2.0 PKCE flow for browser-based clients. Tokens are issued by `mctl-api` itself and signed with HMAC-SHA256.

**Used by**: Claude.ai native connector, mctl.ai web flows

The flow:
1. Client initiates OAuth PKCE flow via `mctl.ai/api/github/login`
2. User authenticates with GitHub
3. MCTL issues a JWT with the user's identity and groups
4. The token is redeemed via `POST /api/github/session` (never placed in a URL)

## Auth Bypass (Development)
```

**After:**

```markdown
## OAuth JWT

OAuth 2.0 PKCE flow for browser-based clients. Tokens are issued by `mctl-api` itself and signed with HMAC-SHA256.

**Used by**: Claude.ai native connector, mctl.ai web flows

The flow:
1. Client initiates OAuth PKCE flow via `mctl.ai/api/github/login`
2. User authenticates with GitHub
3. MCTL issues a JWT with the user's identity and groups
4. The token is redeemed via `POST /api/github/session` (never placed in a URL)

### Refresh Token Rotation

Refresh tokens rotate on every use: each refresh request invalidates the
refresh token that was presented and issues a new one. If a client never
receives the rotation response (e.g. a dropped connection) and retries
shortly afterward, that retry is tolerated within a short grace window —
the already-issued successor token is re-issued, as long as it is still
the live, unused tip of that token's lineage.

Outside the grace window, presenting an already-rotated refresh token is
treated as **reuse** (a sign the token may have been intercepted), and the
entire token family is revoked: every client sharing that refresh lineage
gets `invalid_grant` on its next refresh and must re-authenticate. This is
deliberate — it is the mechanism that limits the blast radius of a leaked
refresh token — not a bug. See
[Troubleshooting → Unexpectedly logged out](/reference/troubleshooting#unexpectedly-logged-out-refresh-token-errors)
if you hit it.

For OAuth token TTL, dynamic-client-registration limits, and revocation
semantics, see [Connecting](/mcp/connecting).

<!-- <TODO: confirm with author of da6192d whether the exact grace-window
     value (2 minutes as of this writing, widened from 30s) should be
     published as a number here, or intentionally left unspecified since
     the commit frames it as a tunable retune target rather than a fixed
     contract. Leaving it unspecified above pending that confirmation.> -->

## Auth Bypass (Development)
```

---

## Block 2

> **Apply to:** `mctl-docs/docs/reference/troubleshooting.md` (UPDATE)
> **Source:** mctl-api@da6192d

**Before** (excerpt):

```markdown
For OAuth tokens (Claude.ai connector): disconnect and reconnect the MCP server.

### "Forbidden" on tenant operations
```

**After:**

```markdown
For OAuth tokens (Claude.ai connector): disconnect and reconnect the MCP server.

### Unexpectedly logged out / refresh token errors

MCTL rotates OAuth refresh tokens on every use. If your client's retry of a
refresh request lands outside a short grace window after the previous
attempt (for example, after a longer network interruption), the server
treats it as a possible replay and revokes the entire token family —
every client sharing that refresh lineage is signed out and must
re-authenticate.

This is expected security behavior, not a bug. The fix is the same as for
an "Unauthorized" error above: disconnect and reconnect the MCP server
(or sign in again from the [Connecting](/mcp/connecting) page). See
[Authentication → Refresh Token Rotation](/security/authentication) for
why this happens.

### "Forbidden" on tenant operations
```

---
