# Upgrade anthropic-sdk-go to v1.41.0 for MCP tool helpers and webhook handling

## Context
mctl-agent v1.5.0 uses the Anthropic SDK (vendored or via direct HTTP calls, see
`context/architecture.md`) for its LLM diagnose phase, and exposes its own MCP endpoint
at `POST /mcp` with 6 registered tools. The current integration relies on custom
scaffolding to marshal MCP tool definitions, handle JSON-RPC dispatch, and route
incoming webhook events from the Anthropic platform.

anthropic-sdk-go v1.41.0 ships first-class MCP tool helpers and webhook handling that
can replace this bespoke glue code. Adopting the SDK's built-in MCP support aligns with
ADR 0001's remote-skill extensibility roadmap (the remote tier is described as "the
future — mctl-agents may become a remote skill source"), reduces the maintenance surface,
and positions mctl-agent to leverage managed-agents features as they mature in subsequent
SDK releases. The upgrade introduces no memory increase in the `labs` tenant.

## User stories
- AS a developer maintaining mctl-agent I WANT the Anthropic SDK's native MCP tool
  helpers to replace custom JSON-RPC scaffolding SO THAT I spend less time maintaining
  boilerplate and more time improving skill logic.
- AS a platform engineer I WANT the `POST /mcp` endpoint to handle webhook events via
  the SDK's built-in webhook handler SO THAT event signature verification and dispatch
  are covered by the upstream library rather than hand-rolled code.
- AS a remote skill author I WANT mctl-agent's MCP endpoint to remain stable and
  backward-compatible after the upgrade SO THAT existing registered remote skills
  continue to function without re-registration.

## Acceptance criteria (EARS notation)
- WHEN anthropic-sdk-go is updated to v1.41.0 in `go.mod` THE SYSTEM SHALL compile
  without error (`go build ./...` exits 0).
- WHEN a valid MCP JSON-RPC tool call is received at `POST /mcp` THE SYSTEM SHALL
  dispatch it to the correct tool handler and return a well-formed JSON-RPC response,
  identical in structure to the response produced before the upgrade.
- WHEN an incoming Anthropic webhook event is received THE SYSTEM SHALL verify its
  signature using the SDK's built-in webhook handler and reject events with an invalid
  or missing signature with HTTP 401.
- WHILE the SDK upgrade is deployed THE SYSTEM SHALL continue to expose all 6 existing
  MCP tools with the same names, input schemas, and output formats as before.
- IF a custom scaffolding code path is removed as part of the migration THE SYSTEM SHALL
  have a corresponding test proving that the SDK-provided replacement produces equivalent
  output for the same input.
- WHEN the diagnose phase calls the Anthropic API via the upgraded SDK THE SYSTEM SHALL
  complete within the existing timeout budget with no increase in baseline memory usage.

## Out of scope
- Upgrading the Anthropic SDK beyond v1.41.0 — version is pinned by this proposal.
- Adding new MCP tools beyond the existing 6 — a separate proposal if desired.
- Migrating to managed-agents or Anthropic-hosted skill orchestration — ADR 0001
  positions this as a future possibility; this proposal only adopts the SDK helpers.
- Changes to YAML skills or builtin Go skills other than the LLMDiagnosis skill's SDK
  call sites.
- Changing the `POST /mcp` URL path or JSON-RPC protocol version.
