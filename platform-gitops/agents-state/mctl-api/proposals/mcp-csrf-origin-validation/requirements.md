# CSRF via Missing Origin Header Validation on MCP Streamable HTTP Transport

## Context
CVE-2026-33252 demonstrates that Streamable HTTP MCP transports do not validate the `Origin` header on incoming POST requests. Because browsers automatically include cookies and auth headers on cross-origin POST requests when credentials are present, a malicious website can silently trigger MCP tool calls on behalf of any authenticated user whose session is active in the browser.

Our MCP server at `https://api.mctl.ai/mcp` exposes 13 write tools — including `trigger_workflow` and several identity management tools — over the Streamable HTTP transport backed by mark3labs/mcp-go v0.31. Without Origin validation any page loaded in a victim's browser can craft a cross-site POST to `/mcp` and execute write operations under the victim's identity. Given that the `admins` tenant operates Kubernetes, Vault, ArgoCD and Argo Workflows integrations, the blast radius of a successful CSRF is high.

## User stories
- AS a platform administrator I WANT the MCP endpoint to reject cross-origin POST requests from untrusted origins SO THAT malicious websites cannot execute write tool calls on my behalf.
- AS a security engineer I WANT an explicit origin allowlist configured via environment variable SO THAT the allowed origins can be changed per environment without code changes.
- AS a Claude.ai connector user I WANT legitimate cross-origin MCP requests (from Claude.ai) to continue working SO THAT my workflow is not disrupted by the new control.

## Acceptance criteria (EARS)
- WHEN a POST or GET request arrives at `/mcp` and the `Origin` header is absent THE SYSTEM SHALL allow the request (CLI/server-side callers do not send Origin).
- WHEN a POST or GET request arrives at `/mcp` and the `Origin` header is present and the origin matches an entry in `MCP_ALLOWED_ORIGINS` THE SYSTEM SHALL allow the request to proceed to the MCP handler.
- WHEN a POST or GET request arrives at `/mcp` and the `Origin` header is present and the origin does not match any entry in `MCP_ALLOWED_ORIGINS` THE SYSTEM SHALL respond with HTTP 403 and a JSON error body `{"error":"forbidden_origin"}` without invoking the MCP handler.
- WHILE the service starts up THE SYSTEM SHALL parse `MCP_ALLOWED_ORIGINS` (comma-separated list of scheme+host strings) and fail fast with a startup error if the variable is set but contains a malformed origin.
- IF `MCP_ALLOWED_ORIGINS` is not set THE SYSTEM SHALL default to an empty allowlist and log a warning at startup, treating all browser-sourced Origins as forbidden.
- WHEN the middleware rejects a request THE SYSTEM SHALL emit a structured log entry at WARN level containing the offending origin and the request ID.
- WHEN the middleware rejects a request THE SYSTEM SHALL increment the Prometheus counter `mcp_csrf_rejected_total` labelled by `origin_domain`.

## Out of scope
- Full CORS preflight (`OPTIONS`) handling beyond rejecting disallowed origins — that is covered separately in the mcp-go v0.51 upgrade proposal.
- Changes to the REST endpoints outside `/mcp`.
- CSRF token-based protection (not applicable to API clients).
- Authentication or authorisation logic changes.
