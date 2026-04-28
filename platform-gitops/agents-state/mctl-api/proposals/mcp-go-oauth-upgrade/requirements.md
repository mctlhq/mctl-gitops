# Upgrade mark3labs/mcp-go to v0.49.0 (RFC 9728 OAuth + transport stability)

## Context
mctl-api v4.14.0 uses mark3labs/mcp-go v0.31.0 to serve 24 MCP tools over
Streamable HTTP with OAuth 2.0 PKCE for the Claude.ai connector. The library
has since advanced to v0.49.0, an 18-minor-version gap that delivers three
material improvements: RFC 9728 OAuth Protected Resource Metadata discovery,
client-side helpers for extracting protected resource metadata from
authorization errors, and transport stability fixes for both the SSE and
Streamable HTTP transports.

Without these fixes, Claude.ai clients that implement RFC 9728 metadata
discovery cannot reliably locate the authorization server from a cold start,
error responses on auth failures may be malformed, and accumulated transport
bugs can cause silent connection drops on the Streamable HTTP endpoint that
mctl-api relies on exclusively. Staying 18 minor versions behind also widens
the gap before the next mandatory upgrade, compounding future re-validation
effort as required by ADR 0001.

## User stories
- AS a Claude.ai connector integrator I WANT the mctl-api MCP endpoint to
  advertise OAuth Protected Resource Metadata per RFC 9728 SO THAT my client
  can discover the authorization server automatically without manual
  configuration.
- AS a Claude.ai end user I WANT OAuth error responses from mctl-api to
  include well-formed protected resource metadata SO THAT my client can
  recover from auth failures and prompt me to re-authenticate seamlessly.
- AS a platform engineer I WANT the Streamable HTTP and SSE transports to
  apply the upstream stability fixes from mcp-go v0.32–v0.49 SO THAT silent
  connection drops and malformed frames no longer require pod restarts to
  recover.
- AS a platform engineer I WANT the dependency gap between the running version
  and latest to stay small SO THAT future upgrades carry lower re-validation
  cost (per ADR 0001).

## Acceptance criteria (EARS)

### RFC 9728 metadata discovery
- WHEN a client sends a GET request to `https://api.mctl.ai/mcp` without a
  valid Bearer token THE SYSTEM SHALL return an HTTP 401 response whose
  `WWW-Authenticate` header includes a `resource_metadata` URI pointing to
  the well-known OAuth Protected Resource Metadata document, conforming to
  RFC 9728 Section 3.
- WHEN a client fetches the protected resource metadata document THE SYSTEM
  SHALL respond with a JSON object that includes at minimum `resource`,
  `authorization_servers`, and `bearer_methods_supported` fields.

### Auth error enrichment
- WHEN an MCP request is rejected due to an expired or invalid Bearer token
  THE SYSTEM SHALL include structured metadata in the error response that
  allows a compliant client to identify the authorization server and
  re-initiate the PKCE flow without user intervention beyond re-consent.

### Transport stability
- WHILE an active Streamable HTTP session is open THE SYSTEM SHALL maintain
  the connection without silent frame loss for at least the session timeout
  period defined in the server configuration.
- WHEN the mcp-go library emits a recoverable transport error THE SYSTEM SHALL
  log the error at WARN level and attempt reconnection without dropping the
  in-flight tool call.

### Tool compatibility
- WHEN mctl-api is started after the upgrade THE SYSTEM SHALL expose all 24
  MCP tools with schemas identical to those validated before the upgrade,
  verified by MCP Inspector.
- IF any tool schema, name, or input validation rule changes as a side-effect
  of the library upgrade THEN THE SYSTEM SHALL surface the discrepancy in the
  CI MCP Inspector test run and block the merge.

### Regression
- WHEN any of the 24 tools is invoked via the Claude.ai connector after the
  upgrade THE SYSTEM SHALL return a semantically correct result with no change
  in response structure compared to pre-upgrade behaviour.

## Out of scope
- Replacing mark3labs/mcp-go with a custom JSON-RPC implementation (prohibited
  by ADR 0001).
- Moving the MCP transport to gRPC (prohibited by ADR 0001 and architecture
  constraints).
- Upgrading any other dependency (chi, pgx, client-go, etc.) as part of this
  change.
- Changes to the 24 tool implementations themselves; this proposal covers only
  the library version bump and any minimal adapter code required by the new
  API surface.
- Rolling out new OAuth scopes or claims — the existing PKCE flow is retained
  as-is.
