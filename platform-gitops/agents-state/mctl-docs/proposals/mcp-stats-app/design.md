# Design: mcp-stats-app

version-status: unverified, see commit SHA

## Source commits
- mctl-api:db5757f — feat(mcp): add a read-only statistics MCP App
- mctl-api:39a0453, e8f7898, 8308e83, 77dd77e, 754b897 — fixes: multi-team scoping, decimal memory quantities, app handshake, closed-incident counting
- mctl-gitops:ca969b7, 91f34d9 — portal allowlist raised to 83/123 tools (rollout evidence)

## Current state of documentation
Page missing. Propose `docs/mcp/stats-app.md`. `docs/mcp/overview.md` and `docs/mcp/tools-reference.md` exist per docs-tree snapshot but do not mention it.

## Proposed solution
CREATE `docs/mcp/stats-app.md`; add link sections to overview and tools-reference; add sidebar entry under MCP in `.vitepress/config`. Content kept to confirmed facts with TODOs.

## Alternatives
- Section inside overview.md: dropped, deserves its own reference.
- Delay until details confirmed: dropped; TODOs mark gaps.

## Impact
- Sidebar: yes (MCP group).
- Mermaid: none needed.
- Versioning: main.
