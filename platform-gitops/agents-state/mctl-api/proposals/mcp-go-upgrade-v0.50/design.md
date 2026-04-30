# Design: mcp-go-upgrade-v0.50

## Current state
mctl-api (v4.14.0) declares `github.com/mark3labs/mcp-go v0.31` in `go.mod` (see `context/architecture.md`). The MCP server exposes 24 tools over Streamable HTTP at `https://api.mctl.ai/mcp`. Tool schemas are defined in Go code using the mcp-go schema DSL, but `WithInputSchemaValidation()` was not available in v0.31; tool arguments are passed directly to handler functions without library-level JSON Schema enforcement. The 13 write tools (e.g., `trigger_workflow`, identity management) accept arguments that may be only partially validated inside the handler. ADR-0001 governs this library choice and explicitly permits version upgrades.

v0.50.0 (released 2026-04-30) introduces:
- `WithInputSchemaValidation()` server option — validates all tool call arguments against their registered JSON Schema before invoking the handler; rejects invalid calls with a JSON-RPC error.
- `santhosh-tekuri/jsonschema/v6` as a new transitive dependency (the validation engine).
- `ListPrompts` and `ListResources` server methods (out of scope for this proposal).

CVE-2026-27896 (confirmed in `modelcontextprotocol/go-sdk`) describes Go's `encoding/json` case-insensitive key matching allowing a field like `"paramſ"` to unmarshal into the `params` field of a JSON-RPC request. mcp-go uses `encoding/json` for request parsing; whether it is susceptible requires code-level review of the v0.50.0 source.

## Proposed solution

### Step 1 — Upgrade the dependency
Bump `github.com/mark3labs/mcp-go` to v0.50.0 in `go.mod` and run `go mod tidy`. Resolve any conflicts introduced by the new `santhosh-tekuri/jsonschema/v6` transitive dependency.

### Step 2 — Enable `WithInputSchemaValidation()`
Add `mcp.WithInputSchemaValidation()` to the server initialisation call. Audit all 24 tool schema definitions to verify they are complete and correct; fix any schema gaps discovered (e.g., missing `required` fields, incorrect types). Malformed tool calls will now be rejected at the framework layer before reaching handler code.

### Step 3 — Investigate CVE-2026-27896 applicability
Review the mcp-go v0.50.0 source at the JSON-RPC request parsing layer (specifically the struct that receives `params`). Determine whether Go's case-insensitive JSON key matching can cause a smuggled field name to overwrite `params`. Document the outcome in the PR:
- If reproducible: add a pre-parse normalisation step or open a follow-on proposal for an upstream fix.
- If not reproducible (e.g., mcp-go uses a custom parser or explicit key check): record formal risk acceptance in `context/decisions/` as a follow-on ADR.

### Step 4 — MCP Inspector validation
Exercise all 24 tools through MCP Inspector against a staging deployment. Record pass/fail per tool. Merge only when all 24 pass.

### Why this approach
Enabling `WithInputSchemaValidation()` is a zero-cost hardening: the schemas are already declared and the validation runs before handlers are called, so there is no latency impact on valid calls. The 19-version gap means there may be subtle behaviour changes; the MCP Inspector gate ensures regressions are caught before production.

## Alternatives

**1. Enable schema validation only for write tools**
Selectively validate the 13 write tools and leave read tools unvalidated. Rejected: `WithInputSchemaValidation()` is a server-level option in v0.50.0, not per-tool. Partial enforcement would require a custom wrapper and would leave read tools as a potential pivot path for malformed inputs that could cause handler panics.

**2. Implement schema validation inside each handler (without upgrading mcp-go)**
Write argument-validation logic in every handler using a JSON Schema library directly. Rejected: this duplicates work that the upgraded library provides centrally, increases per-handler complexity, and does not address the 19-version gap in upstream fixes. It also does not resolve CVE-2026-27896 applicability.

**3. Replace mcp-go with `modelcontextprotocol/go-sdk`**
The official SDK is where CVE-2026-27896 was confirmed fixed. Rejected: ADR-0001 explicitly prohibits replacing mcp-go with a custom or alternative implementation. The go-sdk is also younger and less proven in production against Streamable HTTP transport.

## Platform impact

**Migrations:** None to data or schema. The MCP wire protocol is unchanged; existing Claude.ai connector and Claude Code sessions continue to function.

**Backward compatibility:** mcp-go follows semver; a 19-minor-version gap may include non-obvious API changes. Risk is mitigated by the full MCP Inspector validation gate (all 24 tools). Any tool schema corrections are additive (adding `required` constraints), not breaking, from the client's perspective because previously accepted invalid calls will now be rejected — which is the desired behaviour.

**Resource impact:** `santhosh-tekuri/jsonschema/v6` adds a new transitive dependency and a small per-request validation cost for invalid calls (valid calls short-circuit immediately). Memory footprint increase is expected to be negligible (schema objects compiled at startup). The `labs` tenant is not affected; mctl-api runs under `admins`.

**Risks and mitigations:**
- Risk: A tool's schema definition is incorrect; `WithInputSchemaValidation()` causes previously working calls to be rejected. Mitigation: schema audit (Step 2) and MCP Inspector validation (Step 4) are required gates before merge.
- Risk: CVE-2026-27896 is reproducible in mcp-go v0.50.0. Mitigation: the investigation in Step 3 is a merge blocker; the PR must document either a mitigation or a formal risk acceptance before it can land.
- Risk: The 19-version gap includes a breaking change not caught by tests. Mitigation: all 24 tools must pass MCP Inspector; CI must be green. If any tool fails, the tool's schema or handler is fixed in this PR before merging.
- Risk: New transitive dependency (`santhosh-tekuri/jsonschema/v6`) carries its own vulnerabilities. Mitigation: Trivy scan of the final image is a required CI step.
