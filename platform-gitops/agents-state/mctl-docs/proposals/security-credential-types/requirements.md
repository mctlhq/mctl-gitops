# Requirements: accepted credential types
version-status: unverified, see commit SHA

Source: mctl-api 6849319 "federation registry (#374 slice A)"; in-repo `docs/federation.md`.

## Acceptance criteria (EARS)
- THE docs SHALL list the credential kinds mctl-api accepts: platform static tokens (service, surface, usage-writer), GitHub PAT, MCP OAuth JWT, OIDC (Dex).
- THE docs SHALL state each token is routed to at most one provider, with no fallback to other providers on failure.
- WHERE operators need to roll back THE docs SHALL mention `MCTL_FEDERATION_DISABLED`.
- THE docs SHALL state that authorization and tenant resolution are unchanged.
