## Accepted credential types

mctl-api verifies every bearer token through a provider registry. A token is routed to at most one provider; if that provider rejects it the request is refused (no fallback to another provider).

| Credential | Used by |
|---|---|
| MCP OAuth JWT (issued by the platform OAuth server) | MCP clients, web sessions |
| GitHub personal access token | CLI / CI (e.g. deploy jobs) |
| OIDC token (Dex or another configured issuer) | SSO users |
| Platform static tokens (service, surface, usage-writer) | Platform components only |

Authorization is unchanged: access is still decided by your groups and admin status (see [Authorization](/security/authorization)).

::: tip Operators
Setting `MCTL_FEDERATION_DISABLED` restores the previous verification chain.
:::
