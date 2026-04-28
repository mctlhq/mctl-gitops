# Design: mcp-go-oauth-upgrade

## Current state
mctl-api v4.14.0 (see `context/current-version.md`) depends on
`github.com/mark3labs/mcp-go v0.31.0` (see `context/architecture.md` and
ADR `context/decisions/0001-mcp-go-library-choice.md`). The library provides:

- Streamable HTTP transport (POST + GET on `/mcp`)
- OAuth 2.0 PKCE support for the Claude.ai connector
- JSON-RPC 2.0 request/response framing and schema validation for 24 tools

At v0.31.0 the library does not implement RFC 9728 Protected Resource Metadata
discovery. When a client hits `/mcp` without a token it receives a bare 401
with no machine-readable hint about where to obtain one. Auth-error responses
do not carry the structured metadata that RFC 9728-compliant clients use for
automatic re-authorization. Known transport bugs in v0.31 (fixed between
v0.32–v0.49) can cause silent frame loss on long-lived Streamable HTTP
connections.

## Proposed solution

### Version bump
Update `go.mod` and `go.sum` to pin `github.com/mark3labs/mcp-go` at
`v0.49.0`. Run `go mod tidy` to resolve any transitive dependency changes.

### RFC 9728 Protected Resource Metadata
v0.49.0 ships a built-in handler for `/.well-known/oauth-protected-resource`.
mctl-api must supply the configuration struct that mcp-go exposes for this
purpose (exact type name confirmed from the v0.49.0 release notes and source).
The struct fields to populate are:

| Field | Value |
|---|---|
| `Resource` | `https://api.mctl.ai/mcp` |
| `AuthorizationServers` | `["https://ops.mctl.me/api/dex"]` |
| `BearerMethodsSupported` | `["header"]` |

The server initialization block in `internal/mcp/server.go` (or equivalent)
is updated to pass this configuration when constructing the `mcp.Server`
instance. No new HTTP routes need to be registered manually; the library
registers the well-known endpoint automatically.

### WWW-Authenticate header on 401
v0.49.0 also enriches the 401 response with a `WWW-Authenticate: Bearer
resource_metadata="<url>"` header. mctl-api's existing auth middleware must
not strip or overwrite this header. A review pass is required to confirm no
middleware currently overwrites `WWW-Authenticate`.

### Transport stability
No application-level code changes are required for the transport fixes; they
are part of the library internals. The upgrade alone delivers them.

### API surface changes
The mcp-go changelog for v0.32–v0.49 includes minor API additions (new option
types, new OAuth helper functions). If any existing call sites use function
signatures that changed between v0.31 and v0.49 the compiler will surface them
immediately. Expected scope: initialization options and possibly the
`SSEServer` option struct — both are internal to `internal/mcp/`. No public
REST API surface of mctl-api changes.

### No changes to tool implementations
All 24 tool handler functions live outside the library boundary. They are
unchanged by this proposal.

## Alternatives

### A. Stay on v0.31.0 and implement RFC 9728 manually
Write a custom `/.well-known/oauth-protected-resource` handler and enrich 401
responses in middleware. This avoids the re-validation cost imposed by ADR 0001
but duplicates logic the library now provides, creates a maintenance burden,
and does not deliver the transport stability fixes. Dropped: the effort is
comparable to the upgrade but yields no transport benefit.

### B. Upgrade to the latest patch of the nearest minor (e.g., v0.31.x)
If a v0.31.x patch series existed it would minimize re-validation scope. It
does not — v0.31.0 is the last release on that minor. There is no intermediate
stopping point that provides RFC 9728 support without going to at least v0.49.
Dropped: not viable.

### C. Upgrade in two steps (v0.31 → v0.40 → v0.49)
Splitting the bump reduces the delta reviewed at each step but doubles the
ADR 0001 re-validation cycles (2 full 24-tool MCP Inspector passes instead of
one). The intermediate v0.40 snapshot provides no user-visible value on its
own. Dropped: higher total cost, no benefit.

## Platform impact

### Migrations
None. No database schema changes, no Kubernetes manifest changes, no Vault
secret changes. The upgrade is a pure Go dependency bump compiled into the
existing binary.

### Backward compatibility
The MCP protocol version exposed by mctl-api remains `2025-06-18` (the spec
version mcp-go has targeted since v0.31). Existing Claude.ai connector
configurations do not need to change. The new well-known endpoint is additive;
clients that do not implement RFC 9728 ignore it.

### Resource impact (labs tenant)
mcp-go is a library compiled into the mctl-api binary. The additional code
from v0.32–v0.49 (OAuth metadata handler, client helpers) will increase the
binary size by an estimated 100–300 KB. At runtime the RFC 9728 handler adds
one in-memory JSON document (~200 bytes) and one additional HTTP route. Memory
delta is negligible (well under 1 MB). mctl-api runs in the `admins` tenant,
not `labs`. However, if any `labs` workload embeds mcp-go transitively, flag
for review: the increase is small and unlikely to push labs over its limit, but
should be confirmed before merging. Risk level: LOW.

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|---|---|---|
| Breaking API change in mcp-go between v0.31–v0.49 breaks compilation | Medium | Compilation error surfaces immediately in CI; fix call sites before merge |
| Tool schema drift causes MCP Inspector failures | Low–Medium | ADR 0001 re-validation gate in CI blocks merge on any schema discrepancy |
| New transport behaviour changes observable timing of responses | Low | Load test against staging with the Claude.ai connector before promoting to production |
| labs memory limit breached by transitive dependency | Very low | Confirm with `go mod graph` that labs workloads do not transitively depend on mctl-api's mcp-go |
