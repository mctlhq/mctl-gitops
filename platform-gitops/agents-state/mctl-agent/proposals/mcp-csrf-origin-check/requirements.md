# MCP Endpoint CSRF Protection via Origin Header Validation

## Context
mctl-agent exposes a `POST /mcp` endpoint that implements the Streamable HTTP MCP transport and provides access to 6 MCP tools capable of mutating tickets, registering skills, and triggering diagnoses. CVE-2026-33252 documents that this transport is vulnerable to cross-site request forgery (CSRF): a malicious web page can instruct a victim's browser to issue a credentialed `POST /mcp` request, causing arbitrary MCP tool execution under the victim's session context. No Origin validation or Content-Type enforcement currently exists on this route.

The blast radius is high. A single forged request could create or resolve tickets, register a rogue remote skill, or kick off an LLM-backed diagnosis cycle against production workloads. The remediation is narrow in scope: a dedicated chi middleware applied only to `POST /mcp` that rejects requests whose `Origin` header is absent or not in a configurable allowlist, and that enforces `Content-Type: application/json`. This fully addresses CVE-2026-33252 with minimal code surface and no impact on legitimate MCP clients.

## User stories
- AS a platform engineer I WANT the `POST /mcp` endpoint to validate the `Origin` header SO THAT cross-site requests from malicious websites are rejected before any tool logic executes.
- AS an MCP client developer I WANT a configurable allowlist of permitted origins SO THAT I can add my client's origin without modifying source code.
- AS an on-call engineer I WANT rejected CSRF requests to return a structured JSON error SO THAT I can identify and alert on attack attempts in logs and metrics.
- AS a security reviewer I WANT the CSRF check to be isolated to `/mcp` SO THAT other API routes are unaffected and the change surface is minimal.

## Acceptance criteria (EARS notation)

### Origin validation
- WHEN a `POST /mcp` request arrives with an `Origin` header value that is present in `MCP_ALLOWED_ORIGINS` THE SYSTEM SHALL forward the request to the MCP handler.
- WHEN a `POST /mcp` request arrives with an `Origin` header that is absent or not in `MCP_ALLOWED_ORIGINS` THE SYSTEM SHALL return HTTP 403 with a JSON body `{"error":"forbidden","reason":"origin not allowed"}` and not invoke any MCP tool.
- WHILE `MCP_ALLOWED_ORIGINS` is set to the special value `*` THE SYSTEM SHALL allow all `Origin` values and skip the allowlist check (development/test mode only).
- IF `MCP_ALLOWED_ORIGINS` is not set or is empty THE SYSTEM SHALL treat the allowlist as empty and reject all requests that carry an `Origin` header.

### Content-Type enforcement
- WHEN a `POST /mcp` request arrives with a `Content-Type` header that does not begin with `application/json` THE SYSTEM SHALL return HTTP 415 with a JSON body `{"error":"unsupported_media_type","reason":"Content-Type must be application/json"}` and not invoke any MCP tool.
- WHEN a `POST /mcp` request arrives without a `Content-Type` header THE SYSTEM SHALL return HTTP 415 with the same JSON body.

### Scope isolation
- WHILE a request targets any endpoint other than `POST /mcp` THE SYSTEM SHALL NOT apply the Origin or Content-Type CSRF checks introduced by this proposal.
- WHEN a valid `POST /mcp` request passes both the Origin and Content-Type checks THE SYSTEM SHALL pass the unmodified request body to the existing MCP handler.

### Logging
- WHEN the middleware rejects a request THE SYSTEM SHALL emit a structured `slog` warning log entry containing the remote address, the received `Origin` value, and the rejection reason.

## Out of scope
- CSRF protection for `POST /api/v1/alerts`, `POST /api/v1/telegram`, or any other non-MCP route.
- Authentication or authorization changes (API keys, JWT, mTLS).
- Rate limiting or DDoS protection on the MCP endpoint.
- Changes to MCP tool implementations or their permission model.
- Browser-side Same-Site cookie configuration (the service issues no cookies).
- Removal or replacement of the Streamable HTTP MCP transport.
