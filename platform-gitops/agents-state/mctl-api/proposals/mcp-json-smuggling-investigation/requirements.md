# Investigate CVE-2026-27896 JSON-RPC Field-Name Smuggling in mark3labs/mcp-go

## Context

CVE-2026-27896 exploits Go's `encoding/json` case-insensitive field-matching
behaviour to smuggle JSON-RPC fields past WAF rules and application-level
validators. The attack works by sending canonically-cased field names (e.g.
`"Method"` instead of `"method"`) that WAFs treat as unknown but that
`encoding/json` silently maps to the correct struct field. The vulnerability was
confirmed in `modelcontextprotocol/go-sdk` and fixed in v1.3.1. mctl-api uses
`mark3labs/mcp-go` v0.31, a different library, but both use Go's standard
`encoding/json` for request deserialization, so exposure is unresolved.

mctl-api's MCP server exposes 13 write tools — including `trigger_workflow`,
identity management tools, and tenant-scoped operations — at
`https://api.mctl.ai/mcp`. A successful field-smuggling exploit against any of
these tools could allow an attacker to bypass WAF-level access controls and
invoke write operations without detection, with a potential cross-tenant blast
radius. Because this is an investigation-first proposal, the scope is: audit
whether `mcp-go`'s request-dispatching and tool-parameter deserialization are
affected, produce a reproducible proof-of-concept or a clear not-affected
verdict, and — if affected — apply a targeted patch. Per ADR 0001,
`mark3labs/mcp-go` must not be replaced with a custom JSON-RPC implementation.

## User stories

- AS a security engineer I WANT a definitive verdict on whether mctl-api's
  MCP endpoint is vulnerable to CVE-2026-27896 field-name smuggling SO THAT I
  can accurately report exposure status and prioritise remediation.
- AS a platform engineer I WANT any confirmed vulnerability patched at the
  deserialization layer SO THAT write tools cannot be invoked via smuggled
  field names without proper authorization.
- AS an on-call engineer I WANT the MCP endpoint's authorization behaviour to
  be unchanged for legitimate clients after any patch SO THAT existing Claude
  integrations continue to work without reconfiguration.

## Acceptance criteria (EARS)

- WHEN the audit of `mcp-go` v0.31 request-dispatching code is complete, THE
  SYSTEM SHALL produce a written finding stating either "affected" or
  "not affected" with line-level evidence.
- WHEN a crafted MCP request with a smuggled field name (e.g. `"Method"` for
  `"method"`, `"Params"` for `"params"`) is replayed via MCP Inspector against
  the staging endpoint, THE SYSTEM SHALL record the observed behaviour
  (dispatch, reject, or ignore) for each variant.
- IF the audit concludes mctl-api IS affected by CVE-2026-27896, THEN THE
  SYSTEM SHALL enforce strict case-sensitive JSON field matching in the MCP
  request-deserialization layer before the change is merged.
- IF strict case-sensitive parsing is implemented, THEN THE SYSTEM SHALL
  reject any MCP request whose JSON-RPC envelope contains field names that
  do not exactly match the lowercase canonical form (`method`, `params`,
  `id`, `jsonrpc`), returning a JSON-RPC parse-error response.
- WHILE strict parsing is active, THE SYSTEM SHALL continue to correctly
  dispatch all 24 MCP tools (11 read + 13 write) for requests that use
  canonical lowercase field names.
- WHEN the audit concludes mctl-api is NOT affected, THE SYSTEM SHALL
  document the specific code path in `mcp-go` that prevents the attack and
  add a comment in the codebase pinning that assumption to the library version.
- IF a future upgrade of `mark3labs/mcp-go` is proposed, THEN the CI pipeline
  SHALL replay the field-smuggling payloads as part of the upgrade validation.

## Out of scope

- Replacing `mark3labs/mcp-go` with a custom JSON-RPC implementation
  (prohibited by ADR 0001).
- Auditing non-MCP REST endpoints for JSON field-smuggling (separate
  attack surface; tracked separately).
- Remediating CVE-2026-27896 in the upstream `modelcontextprotocol/go-sdk`
  library (not used by mctl-api).
- Changes to WAF rules or network-layer controls (complementary, not
  a substitute for fixing the deserialization layer).
- Any schema changes to MCP tool definitions or changes to the tool
  authorization model.
