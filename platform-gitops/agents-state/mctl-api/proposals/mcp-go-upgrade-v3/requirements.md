# mcp-go-upgrade-v3: Escalate target to mcp-go v1.1.0 (closes CVE-2026-81092 DNS rebinding + CVE-2026-27896)

## Context
This proposal **supersedes `proposals/mcp-go-upgrade-v2`** (which targets v0.54.0) and widens its
scope in response to new signal from the 2026-09-19 research cycle. `mcp-go-upgrade-v2` already
scoped a bump to close CVE-2026-27896 (case-insensitive JSON field-name validation bypass), but its
target version, v0.54.0, predates a second, independently disclosed vulnerability:
**CVE-2026-81092** (CVSS 6.8, published 2026-08-27) — `StreamableHTTPServer.ServeHTTP` and
`SSEServer.ServeHTTP` accept any Host header on a loopback-bound listener, so a browser that
resolves an attacker-controlled DNS name to `127.0.0.1` (DNS rebinding) can reach mctl-api's public
MCP endpoint, `api.mctl.ai/mcp`, and invoke any of the 24 tools — 13 of which are write tools. This
is fixed upstream in v0.56.0. Since v0.54.0 (the old target) does not include this fix,
`mcp-go-upgrade-v2` as scoped would ship a still-vulnerable version.

Rather than opening a third parallel mcp-go slug, this proposal raises the target all the way to
**v1.1.0** (released 2026-09-15, the current latest stable release, per this cycle's researcher
findings), which includes both the CVE-2026-27896 fix (already scoped in v2) and the CVE-2026-81092
fix (new), plus the intervening beta→stable stabilization work (in-process client options, roots
handler support). Once this proposal is accepted, `mcp-go-upgrade-v2` should be closed as
superseded — its acceptance criteria are a strict subset of this proposal's.

## User stories
- AS a platform security engineer I WANT mcp-go upgraded to v1.1.0 SO THAT CVE-2026-81092's
  DNS-rebinding attack surface against the public `api.mctl.ai/mcp` endpoint is closed.
- AS a platform security engineer I WANT CVE-2026-27896's JSON field-name validation bypass closed
  in the same change SO THAT we do not ship an intermediate version (e.g. v0.54.0) that fixes one
  CVE while remaining vulnerable to the other.
- AS an SRE I WANT panic-safe MCP message handling (fixed between v0.31 and v1.1.0) SO THAT a
  malformed request cannot silently drop a Claude client session.
- AS a Claude.ai connector user I WANT the server to remain on Streamable HTTP (POST + GET) SO THAT
  existing connector configuration requires no changes (ADR-0001 constraint).

## Acceptance criteria (EARS)
- WHEN mctl-api starts, THE SYSTEM SHALL import `github.com/mark3labs/mcp-go` at v1.1.0 or higher,
  as verified by `go list -m github.com/mark3labs/mcp-go`.
- WHEN a request to `StreamableHTTPServer.ServeHTTP` or `SSEServer.ServeHTTP` arrives with a Host
  header that does not match an allow-listed value for a loopback-bound listener, THE SYSTEM SHALL
  reject the request (CVE-2026-81092 mitigation), consistent with upstream's
  `server/http_localhost.go` behaviour introduced in v0.56.0.
- WHEN a Claude client sends an MCP request with case-variant JSON field names, THE SYSTEM SHALL
  reject or normalise the request and not silently bypass validation (CVE-2026-27896 mitigation).
- WHEN a malformed or truncated MCP message is received, THE SYSTEM SHALL return a JSON-RPC error
  response and not panic or crash the serving goroutine.
- WHEN all 24 MCP tools are exercised via MCP Inspector against the upgraded server, THE SYSTEM
  SHALL return correct schemas and responses for all tools with zero regressions.
- WHILE mctl-api is running, THE SYSTEM SHALL continue serving MCP traffic over Streamable HTTP
  (POST + GET) without requiring clients to reconnect or reconfigure (ADR-0001).
- WHEN the CI pipeline runs, THE SYSTEM SHALL pass all existing MCP integration tests, plus new
  regression tests for CVE-2026-81092 and CVE-2026-27896 (see `tasks.md`).
- IF `proposals/mcp-go-upgrade-v2` is still open when this proposal is accepted, THEN THE SYSTEM
  (via its human reviewers) SHALL close `mcp-go-upgrade-v2` as superseded by this proposal.

## Out of scope
- Replacing mcp-go with a custom JSON-RPC implementation (ADR-0001).
- Moving MCP to gRPC (ADR-0001 + architecture.md).
- Adopting new v1.1.0 feature surface (in-process client options, roots handler support) beyond
  what is required for the upgrade to compile and pass tests — tracked as a separate DX proposal
  if desired, per the 2026-09-19 inbox's "Dropped" section.
- Adding new MCP tools beyond the current 24-tool manifest.
- Downgrading for simplicity (ADR-0001).
