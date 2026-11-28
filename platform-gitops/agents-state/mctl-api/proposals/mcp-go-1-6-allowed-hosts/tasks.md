# Tasks: mcp-go-1-6-allowed-hosts

- [ ] 1. Bump mark3labs/mcp-go to v1.6.0 and fix compile breaks — DoD: build and unit tests pass.
- [ ] 2. Add MCP_ALLOWED_HOSTS config and WithAllowedHosts wiring (depends on 1) — DoD: startup fails on empty prod allowlist.
- [ ] 3. Add gitops value for api.mctl.ai (depends on 2) — DoD: deployed to admins.
- [ ] 4. Re-validate 24 tools via MCP Inspector and Claude.ai connector (depends on 3) — DoD: all pass.

## Tests
- [ ] T1. Wrong Host -> 403; right Host -> 200.
- [ ] T2. Duplicate in-flight ID rejected.
- [ ] T3. OAuth PKCE flow end to end.

## Rollback
Revert image and gitops value; remove MCP_ALLOWED_HOSTS.
