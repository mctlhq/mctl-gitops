# Read-only statistics MCP App

version-status: unverified, see commit SHA (mctl-api 4.181.0 inferred from mctl-gitops 6665a00; gitops ca969b7/91f34d9 raised portal allowlist to 83/123 tools)

## Context
mctl-api added a read-only statistics MCP App exposed via MCP resources (db5757f). Follow-ups fixed multi-team scoping, decimal memory quantities, the app handshake and closed-incident counting by resolver/resolution day (39a0453, e8f7898, 8308e83, 77dd77e, 754b897). There is no page for it in docs.mctl.ai.

## User stories
- AS a tenant owner I WANT to open a statistics dashboard from my MCP client SO THAT I see platform stats without queries.
- AS a member of several teams I WANT to know how scoping works SO THAT I interpret the numbers.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/mcp/stats-app.md` THE SYSTEM SHALL explain what the app is, that it is read-only and delivered through MCP resources.
- WHEN a reader wants to know how incidents are counted THE SYSTEM SHALL state that closed incidents are counted by resolver and resolution day (754b897 or sibling; `<TODO: confirm with author of db5757f>`).
- WHEN a reader belongs to several teams THE SYSTEM SHALL describe multi-team scoping `<TODO: confirm behaviour with author of 39a0453>`.
- IF a reader wants to open the app THEN THE SYSTEM SHALL provide the resource URI / client steps `<TODO: confirm with author of db5757f>`.
- WHEN a reader opens `docs/mcp/overview.md` or `tools-reference.md` THE SYSTEM SHALL link to the new page.
- WHILE version is unverified THE SYSTEM SHALL NOT claim a release number.

## Out of scope
- Telegram MCP Apps (needs author clarification), screenshots, localisation.
