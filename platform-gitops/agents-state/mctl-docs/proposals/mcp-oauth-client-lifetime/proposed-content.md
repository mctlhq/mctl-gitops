# Proposed content: mcp-oauth-client-lifetime

> **Apply to:** `mctl-docs/docs/mcp/connecting.md` (UPDATE)
> **Apply to:** `mctl-docs/docs/reference/troubleshooting.md` (UPDATE)
> **Source:** mctl-api@f9fa393, mctl-api@217e225, mctl-api@2ef473e, mctl-api@82d75fd, mctl-api@ca41c90, mctl-api@7439573, mctl-api@f5e1437

---

## File 1: `docs/mcp/connecting.md`

### Before

```markdown
## Token Types

MCTL accepts three token types. The API auto-detects the type:

| Token format | Type | How to get |
|---|---|---|
| No dots (e.g. `ghp_abc123`) | GitHub PAT | GitHub Settings > Tokens |
| 2 dots, external issuer | Dex JWT | SSO login at `ops.mctl.ai` |
| 2 dots, self-issued | OAuth JWT | OAuth flow on this page (sign in above) |

## Troubleshooting
```

### After

```markdown
## Token Types

MCTL accepts three token types. The API auto-detects the type:

| Token format | Type | How to get |
|---|---|---|
| No dots (e.g. `ghp_abc123`) | GitHub PAT | GitHub Settings > Tokens |
| 2 dots, external issuer | Dex JWT | SSO login at `ops.mctl.ai` |
| 2 dots, self-issued | OAuth JWT | OAuth flow on this page (sign in above) |

## Token Lifetime & Client Registration

If you're using the OAuth JWT flow (the Claude.ai native connector, or any
client that does its own dynamic client registration), a few limits apply:

- **Access tokens expire within 24 hours at most.** Clients renew silently
  using the `refresh_token` grant — you shouldn't need to re-run the
  sign-in flow just because time passed. If you *are* asked to sign in
  again unexpectedly, that's a real re-auth requirement, not a token
  expiring on schedule.
- **Client registration (`/oauth/register`) is rate-limited to 30
  requests per minute per IP address.** This is sized for clients that
  register from multiple processes on a cold start (common for desktop
  MCP clients that fan out across several processes). If you hit a `429`
  here, see [Troubleshooting](/reference/troubleshooting).
- **Revoking a token requires the token itself.** A revocation request
  with no token, or for a token that was never valid, returns an error —
  not a false success.

## Troubleshooting
```

---

## File 2: `docs/reference/troubleshooting.md`

### Before

```markdown
For OAuth tokens (Claude.ai connector): disconnect and reconnect the MCP server.

### "Forbidden" on tenant operations
```

### After

```markdown
For OAuth tokens (Claude.ai connector): disconnect and reconnect the MCP server.

OAuth access tokens are capped at 24 hours. If you're prompted to sign in
again, that's either a normal `refresh_token` renewal (silent, no action
needed) or your session genuinely expired — either way, re-running the
sign-in flow from the [Connecting](/mcp/connecting) page resolves it.

### "429 Too Many Requests" on client registration

If your MCP client fans out across multiple processes on startup (some
desktop clients do this by design), each process may register itself with
MCTL's OAuth server independently. Registration is capped at 30 requests
per minute per IP address.

- A single burst from one client during a cold start is expected and
  should succeed — the limit is sized for that pattern.
- A sustained `429` past startup usually means something is retrying
  registration in a loop rather than reusing its already-registered
  client. Check your client's OAuth configuration for a stale or missing
  `client_id`.

### "Forbidden" on tenant operations
```

---
