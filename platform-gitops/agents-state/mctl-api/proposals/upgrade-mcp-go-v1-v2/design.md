# Design: upgrade-mcp-go-v1-v2

## Current state
See context/architecture.md (mctl-api 4.14.0, tenant admins). mcp-go 0.31.0, Streamable HTTP, per ADR 0001.

## Proposed solution
Bump go.mod to mcp-go v1.6.0, adapt to API changes, configure the allowed Host list (api.mctl.ai, localhost for dev), and re-validate all 24 tools with MCP Inspector. ADR 0001 is respected (same library). GO-2026-6911 affects only the client transport, which we do not use.

## Alternatives
- Stay on 0.31.0: leaves the Host validation gap.
- Official go-sdk: rejected by ADR 0001.

## Platform impact
- Migrations: none. Compatibility: v1 API may need code changes; verify connector. Risk: tool schema drift, mitigated by Inspector diff.
- Resource impact: negligible; no additional memory in `labs` (mctl-api runs in `admins`).
