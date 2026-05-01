# Harden POST /mcp Endpoint Against Command Injection

## Context
On 2026-04-15, coordinated MCP command-injection advisories were publicly disclosed, highlighting that MCP servers accepting unsanitized tool arguments are vulnerable to prompt-injection and direct command-injection attacks. mctl-agent exposes a `POST /mcp` JSON-RPC endpoint with 6 tools that interact with GitHub (PR creation, branch management), AlertManager (silence, query), and internal ticket state. These tools translate MCP JSON-RPC arguments directly into downstream API calls. Without per-tool input validation and an allowlist schema, a malicious or compromised MCP client can pass crafted arguments that reach downstream systems unchecked.

The risk is compounded by the sensitivity of the downstream targets: GitHub write access to `mctlhq/mctl-gitops` allows unauthorized gitops changes; AlertManager mutation tools can silence or create alerts; ticket-state mutation tools can corrupt the operational view. Because the MCP endpoint is reachable at `https://agent.mctl.ai/mcp` (the `admins` tenant), any unauthenticated or authenticated-but-adversarial MCP client represents a direct injection path. Structured, per-tool input validation with allowlist schemas is the standard defence-in-depth control.

## User stories
- AS a security engineer I WANT every MCP tool input to be validated against a strict allowlist schema before the argument reaches any downstream API SO THAT command-injection or prompt-injection payloads are rejected at the boundary.
- AS an SRE I WANT rejected inputs to be logged with the tool name, the rejected field, and the reason SO THAT I can detect attack attempts in real time via structured log alerting.
- AS a developer I WANT the validation logic to be co-located with the tool definitions and covered by table-driven tests SO THAT adding a new MCP tool in the future requires explicit schema definition as part of the implementation.

## Acceptance criteria (EARS)

### General
- WHEN any `POST /mcp` request arrives THE SYSTEM SHALL validate all tool arguments against the tool's allowlist schema before invoking any downstream API call.
- IF a tool argument fails schema validation THEN THE SYSTEM SHALL return a JSON-RPC error response with code `-32602` (Invalid params) and a message describing which field failed and why, without invoking any downstream call.
- WHEN a validation rejection occurs THE SYSTEM SHALL emit a structured log entry at WARN level containing: tool name, field name, rejection reason, and the sanitized (non-sensitive) representation of the rejected value.
- WHILE the MCP endpoint is operational THE SYSTEM SHALL NOT pass raw, unvalidated user-supplied strings to shell commands, file paths, or external API URL parameters.

### Tool-specific
- WHEN the `create_pr` tool is invoked THEN THE SYSTEM SHALL validate that the branch name matches `^[a-zA-Z0-9/_.-]{1,200}$`, the PR title is non-empty and <= 256 characters, and the body is <= 65536 characters.
- WHEN the `list_tickets` or `get_ticket` tool is invoked THEN THE SYSTEM SHALL validate that the ticket ID matches the expected UUID format (`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`).
- WHEN the `silence_alert` tool is invoked THEN THE SYSTEM SHALL validate that the alert matcher fields contain only characters from the allowlist `[a-zA-Z0-9_=!~]` and that the duration is a positive integer of seconds not exceeding 86400 (24 hours).
- WHEN the `query_alerts` tool is invoked THEN THE SYSTEM SHALL validate that any label-selector string does not contain shell metacharacters (`$`, `` ` ``, `;`, `|`, `&`, `>`, `<`, `\n`, `\r`).
- IF any string argument to any MCP tool exceeds the maximum length defined in the tool's schema THEN THE SYSTEM SHALL reject it with a `-32602` error without truncation.
- WHILE schema validation is active THE SYSTEM SHALL apply validation to 100% of `POST /mcp` requests, with no bypass path for internal or trusted callers at the HTTP layer.

## Out of scope
- Authentication and authorisation changes to the MCP endpoint (who is allowed to call it) — this is a separate security proposal.
- Validation of AlertManager or GitHub API responses (inbound validation of responses is not the concern here).
- Adding new MCP tools beyond the existing 6 — any new tool is a separate proposal and must include its own schema.
- Changes to the three-tier skill system (builtin/YAML/remote) — this proposal only touches the MCP JSON-RPC boundary layer per decision 0001.
- Rate limiting or throttling of the MCP endpoint.
- Modifying the JSON-RPC protocol framing or the tool-listing (`tools/list`) response.
