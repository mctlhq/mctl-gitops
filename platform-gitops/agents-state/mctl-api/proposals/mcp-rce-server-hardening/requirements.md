# MCP Write-Tool Server-Side Hardening Against Systemic RCE

## Context
mctl-api exposes 13 write tools over the MCP Streamable HTTP endpoint (`https://api.mctl.ai/mcp`) using `mark3labs/mcp-go`. The CVE-2025-49596 family (CVSS 9.4) demonstrates protocol-level weaknesses in MCP that allow arbitrary command execution through crafted tool invocations. Anthropic has declined to fix the protocol itself, leaving server-side operators responsible for defensive mitigations.

The existing `mcp-go-upgrade-v0.50` proposal covers the library version bump and enables `WithInputSchemaValidation()`, but does not address server-side runtime controls: per-tool authorization hardening, input payload size limits, rate limiting scoped specifically to write tools, and audit logging of every write-tool invocation. Without these controls a compromised or malicious AI client that has obtained a valid bearer token can invoke any write tool without additional friction, logging, or throttling.

## User stories
- AS a platform operator I WANT every MCP write-tool call to be gated by explicit per-tool authorization checks SO THAT a token scoped to read-only operations cannot invoke write tools
- AS a security engineer I WANT all MCP write-tool invocations to produce an immutable audit log entry SO THAT I can reconstruct what was called, by whom, and with what arguments after an incident
- AS a platform operator I WANT write-tool invocations to be rate-limited independently of read tools SO THAT a runaway or malicious client cannot saturate the API with state-changing operations
- AS a platform operator I WANT incoming MCP tool payloads to be rejected if they exceed a defined size limit SO THAT oversized inputs cannot be used as a vector for memory exhaustion or injection attacks

## Acceptance criteria (EARS)

### Per-tool authorization
- WHEN an MCP write-tool is invoked THE SYSTEM SHALL verify that the caller's resolved tenant group explicitly permits that specific tool before executing it
- IF the caller's token does not grant write permission for the requested tool THEN THE SYSTEM SHALL return HTTP 403 and record a denied-invocation audit entry
- WHILE any MCP request is being processed THE SYSTEM SHALL enforce authorization checks regardless of whether `AUTH_REQUIRED` is true or false in non-production environments (production only: `AUTH_REQUIRED=false` bypasses only authentication, not authorization assertions in tests)

### Input size limits
- WHEN an MCP tool invocation payload exceeds 64 KB THE SYSTEM SHALL reject the request with HTTP 413 before the tool handler is entered
- IF any single string field within a validated tool input exceeds a per-field limit defined in the tool's schema THE SYSTEM SHALL return HTTP 422 with a machine-readable error identifying the offending field

### Rate limiting on write tools
- WHEN a caller submits more than 30 write-tool invocations per minute (per resolved identity) THE SYSTEM SHALL return HTTP 429 with a `Retry-After` header
- WHILE the rate limit for write tools is active THE SYSTEM SHALL continue to serve read-tool requests from the same identity without restriction

### Audit logging
- WHEN any MCP write-tool invocation is received (allowed or denied) THE SYSTEM SHALL write a structured log entry to Postgres containing: timestamp, caller identity, tool name, sanitized argument hash, HTTP status returned, and latency
- WHEN a write-tool invocation is denied THE SYSTEM SHALL emit a Prometheus counter `mcp_write_denied_total` labelled by `tool` and `reason`
- IF the audit log write fails THE SYSTEM SHALL still complete the tool response but emit an `mcp_audit_write_error_total` counter and a `WARN`-level log line

## Out of scope
- Changes to the MCP protocol itself or the `mark3labs/mcp-go` library internals (covered by `mcp-go-upgrade-v0.50`)
- Read-tool rate limiting (separate concern, lower urgency)
- UI or CLI surfaces for browsing the audit log (future proposal)
- Changes to authentication flows (GitHub PAT, Dex JWT, OAuth JWT) — those are unchanged
- Hardening of Argo Workflows or Backstage API write paths invoked transitively by MCP tools
