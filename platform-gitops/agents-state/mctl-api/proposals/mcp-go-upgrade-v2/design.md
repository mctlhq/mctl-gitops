# Design: mcp-go-upgrade-v2

## Current state
Per `context/architecture.md` and ADR `decisions/0001-mcp-go-library-choice.md`, mctl-api
exposes 24 MCP tools over Streamable HTTP (`POST /mcp`, `GET /mcp`) using
**mark3labs/mcp-go v0.31.0**. The library handles JSON-RPC 2.0 framing, server-sent events,
tool schema registration, and OAuth 2.0 PKCE for the Claude.ai connector.

The service is 21 minor versions behind v0.52.0 (the latest release as of 2026-05-07).
The critical defect addressed in this range is an HTTP response body leak in the Streamable
HTTP transport handler: in error paths, `resp.Body` was not closed before returning, leading
to goroutine accumulation and heap growth proportional to MCP traffic volume.

A prior proposal (`mcp-go-upgrade`) targeted v0.50.0. That proposal is superseded by this
one, which raises the target to v0.52.0 to include all fixes released since v0.50.0.

## Proposed solution
Upgrade `github.com/mark3labs/mcp-go` from **v0.31** to **v0.52.0** in place:

1. **Dependency bump**: `go get github.com/mark3labs/mcp-go@v0.52.0 && go mod tidy`.
2. **Compile and remediate**: run `go build ./...` immediately after the bump to surface all
   breaking API changes introduced across 21 minor versions. Expected change areas based on
   the library's changelog: tool registration function signatures, server option structs,
   transport initialisation, and possibly the `CallToolResult` type. Fix compile errors
   before proceeding.
3. **Re-validate all 24 tool schemas**: per ADR 0001, every tool must be re-validated after a
   bump. For each tool, confirm that the registered `InputSchema` accurately describes
   accepted parameters. Enable server-side schema validation if available in v0.52.0 (the
   feature was introduced as opt-in in v0.50.0 per SEP-1303).
4. **Memory regression test**: run a load test against the staging `/mcp` endpoint sending
   1 000 sequential tool calls; observe `go_goroutines` and `go_memstats_heap_inuse_bytes`
   in Prometheus. The goroutine count must return to baseline after the test.
5. **OAuth 2.0 PKCE validation**: confirm the Claude.ai connector PKCE flow is unaffected in
   staging.
6. **MCP Inspector**: run the upstream MCP Inspector against staging; all 24 tools must pass.
7. **Deploy via ArgoCD** to production once staging is green.

The external contract — `/mcp` endpoint URL, Streamable HTTP transport, OAuth 2.0 PKCE — is
unchanged. This is an internal library version upgrade.

## Alternatives

### A: Custom JSON-RPC / Streamable HTTP implementation
Eliminates the external dependency entirely. Requires re-implementing SSE, JSON-RPC 2.0
framing, schema generation, and PKCE — a multi-sprint effort with high compatibility risk
against the Claude.ai connector. **Rejected in ADR 0001.**

### B: Upgrade only to v0.50.0 (the previous proposal target)
v0.50.0 contains the HTTP body leak fix. However, v0.51.0 and v0.52.0 ship additional
stabilisation patches for the same transport layer. Stopping at v0.50.0 would require another
bump within weeks. Upgrading directly to v0.52.0 — the latest stable tag — is more efficient
and aligns with the "upgrade to latest patch" principle used for pgx. **Dropped.**

### C: Switch to anthropics/sdk-go (official Anthropic MCP SDK)
Mentioned as a future alternative in ADR 0001. A library switch is a larger scope than a
version bump and is out of bounds for a targeted defect fix. **Dropped**: re-evaluate only
if mark3labs/mcp-go becomes unmaintained.

## Platform impact

### Migrations
No external API or database migrations. Tool schemas may require corrections to pass
server-side validation, but the schemas exposed to callers become more accurate, not
differently shaped. The `/mcp` endpoint URL and transport remain unchanged.

### Backward compatibility
The upgrade is internal to the mctl-api binary. Claude.ai connectors and Claude Code sessions
will transparently reconnect to the upgraded server with no client-side changes required.

### Resource impact
The HTTP body leak fix is expected to reduce steady-state goroutine count and heap usage
under MCP traffic — a net positive. No memory or CPU increase is anticipated. The `labs`
tenant does not run mctl-api and is not affected. However, the memory improvement means this
proposal actually reduces risk for the `admins` tenant pod's memory footprint.

### Risks and mitigations
| Risk | Mitigation |
|------|------------|
| 21-version gap introduces multiple breaking API changes requiring significant handler rewrites | Run `go build ./...` as the first step; triage the compile errors to estimate scope before committing. Timebox to one sprint. |
| Server-side schema validation rejects currently accepted (but technically invalid) tool call arguments from existing clients | Enable validation incrementally per tool; keep a feature flag or per-tool opt-in until all clients are confirmed compliant |
| OAuth 2.0 PKCE flow broken by transport-layer changes between v0.31 and v0.52 | Explicit staging test of the Claude.ai connector PKCE flow before production deploy |
| Memory leak fix changes buffering behaviour, affecting streaming latency | Run streaming latency benchmark in staging and compare P99 with the previous version |
| Previous proposal (`mcp-go-upgrade` at v0.50.0) may have partially been merged | Verify `go.mod` before starting; if already at v0.50.x, the compile + schema steps still apply and the bump target becomes v0.52.0 |
