# Requirements: whoami-tenant-bound-tokens
version-status: verified (tool description in live MCP server); commit 4dd2ece in mctl-api

## Acceptance criteria (EARS)
- THE authentication page SHALL explain that an agent token can be bound to one tenant.
- WHEN a token is tenant-bound, THE page SHALL state it can act only on that tenant and that `mctl_whoami` reports the bound tenant.
- THE tools reference entry for `mctl_whoami` SHALL list user ID, team memberships, admin status, accessible namespaces and bound tenant.
- THE docs SHALL tell agent authors to pass the bound tenant as `team`/`tenant` to other tools.
