# Upgrade mcp-go to v0.50.0 and enable input schema validation

## Context
mctl-api (v4.14.0) uses `mark3labs/mcp-go` v0.31 to expose 24 tools (11 read + 13 write) over the Streamable HTTP MCP endpoint at `https://api.mctl.ai/mcp`. The library is 19 minor versions behind the current release (v0.50.0, released 2026-04-30). The most significant security improvement in the gap is opt-in `WithInputSchemaValidation()`, which enforces JSON Schema constraints on every tool's arguments before the handler executes. Without this, malformed or adversarially crafted arguments reach handler code unchecked, expanding the attack surface of the 13 write tools (which can trigger workflows, manage identities, and mutate platform state).

Additionally, CVE-2026-27896 discloses a JSON-RPC field-name smuggling vulnerability (Go's `encoding/json` case-insensitive key matching) confirmed in `modelcontextprotocol/go-sdk`; applicability to `mark3labs/mcp-go` is unconfirmed and must be investigated during this upgrade. ADR-0001 (`context/decisions/0001-mcp-go-library-choice.md`) explicitly accepts mcp-go as the chosen library and permits upgrades; it does not require an ADR for a version bump.

## User stories
- AS a security engineer I WANT all 24 MCP tool arguments validated against their JSON Schemas before handler execution SO THAT malformed or adversarially crafted inputs are rejected at the framework layer rather than reaching write-tool business logic.
- AS a platform operator I WANT the mcp-go library to be at a current, supported version SO THAT the service benefits from upstream bug fixes and the MCP spec compliance improvements delivered in the 19-version gap.
- AS a developer I WANT the applicability of CVE-2026-27896 to mcp-go to be definitively assessed SO THAT any field-name smuggling risk is either mitigated or formally accepted.
- AS an operator I WANT all 24 tools to be verified through MCP Inspector after the upgrade SO THAT no tool regression is shipped silently to production.

## Acceptance criteria (EARS)
- WHEN mctl-api starts after the upgrade THEN THE SYSTEM SHALL load all 24 MCP tools with `WithInputSchemaValidation()` enabled and report readiness to the health endpoint.
- WHEN a MCP client submits a tool call with arguments that violate the tool's JSON Schema THEN THE SYSTEM SHALL return a JSON-RPC error response and SHALL NOT invoke the tool handler.
- WHEN a MCP client submits a valid tool call THEN THE SYSTEM SHALL invoke the handler and return the correct result, with no regression in response structure or content.
- WHILE the upgrade investigation is in progress THE SYSTEM SHALL document whether CVE-2026-27896 field-name smuggling is reproducible against the mcp-go JSON-RPC parser; if reproducible, a mitigation or formal risk acceptance SHALL be recorded before the PR is merged.
- WHEN all 24 tools are exercised via MCP Inspector after deployment THEN THE SYSTEM SHALL produce correct responses for every tool with no tool returning an unexpected error.
- IF a tool's existing argument schema requires correction to pass the new validation layer THEN THE SYSTEM SHALL update that schema as part of this change before enabling `WithInputSchemaValidation()`.

## Out of scope
- Replacing `mark3labs/mcp-go` with a custom implementation or an alternative library (explicitly prohibited by ADR-0001).
- Adding new tools or modifying existing tool handler logic beyond schema corrections.
- Upgrading any dependency other than `mark3labs/mcp-go` and its transitive requirements.
- Implementing `ListPrompts` or `ListResources` server methods introduced in v0.50.0 (they may be explored in a follow-on proposal).
