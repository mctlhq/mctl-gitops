# Upgrade mark3labs/mcp-go to v0.52.0 to fix HTTP body leak

## Context
mctl-api's MCP server is built on `github.com/mark3labs/mcp-go`, currently at v0.31.
A previous proposal (`mcp-go-upgrade`, targeting v0.50.0) already exists; this proposal
supersedes it with the target raised to **v0.52.0** based on the 2026-05-07 analyst review.

mctl-api is 21 minor versions behind the latest release (v0.31 to v0.52.0). The most
significant fix relevant to this service is an HTTP response body leak on the Streamable HTTP
endpoint (`/mcp`): the library did not reliably close response bodies in certain error paths,
causing goroutine and memory growth under sustained MCP traffic. The streaming MCP endpoint
is the primary integration surface for Claude.ai and Claude Code sessions — a leak in this
path degrades service quality over time and can eventually cause the pod to OOM-restart.

Per ADR 0001, mark3labs/mcp-go is the chosen and locked MCP library for mctl-api. This
proposal is an in-place version upgrade. ADR 0001 also mandates that all 24 MCP tools must
be re-validated after each library bump.

## User stories
- AS a platform operator I WANT the MCP HTTP body leak to be fixed SO THAT the mctl-api pod
  does not accumulate memory over time and OOM-restart under sustained MCP traffic.
- AS a Claude.ai connector user I WANT the MCP server to handle streaming responses reliably
  SO THAT long-running tool calls do not produce stale or partial results.
- AS a developer I WANT all 24 MCP tools to be re-validated after the bump SO THAT no
  regressions are introduced silently by API changes across 21 versions.

## Acceptance criteria (EARS notation)
- WHEN `go.mod` is evaluated THEN THE SYSTEM SHALL list `github.com/mark3labs/mcp-go` at
  version `v0.52.0` or higher.
- WHEN the MCP streaming endpoint handles a sequence of 1 000 back-to-back tool calls THEN
  THE SYSTEM SHALL not show a statistically significant increase in goroutine count or heap
  allocation (verified via `pprof` or Prometheus `go_goroutines` and `go_memstats_*`
  metrics).
- WHEN the MCP Inspector is run against the staging `/mcp` endpoint THEN THE SYSTEM SHALL
  pass validation for all 24 registered tools with no schema errors and no spec violations.
- WHILE the upgraded MCP server is running THEN THE SYSTEM SHALL maintain OAuth 2.0 PKCE
  authentication for the Claude.ai connector.
- WHILE the upgraded MCP server is running THEN THE SYSTEM SHALL preserve Streamable HTTP
  transport (POST + GET) on the `/mcp` endpoint.
- IF a breaking API change in any version between v0.32 and v0.52.0 requires handler
  modifications THEN THE SYSTEM SHALL update all affected handlers before the change is
  merged to main.
- WHEN `govulncheck ./...` is executed THEN THE SYSTEM SHALL report zero findings
  attributable to mcp-go.

## Out of scope
- Replacing mark3labs/mcp-go with any other MCP library (rejected by ADR 0001 and
  `context/architecture.md`).
- Moving MCP transport to gRPC (rejected by ADR 0001).
- Adding new MCP tools beyond what is required to resolve breaking API changes.
- Upgrading other dependencies (pgx, Go toolchain, chi) — covered by separate proposals.
- Implementing full `ListPrompts` or `ListResources` business logic (stub wiring only, if
  required by the new SDK API).
