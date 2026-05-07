# Design: anthropic-sdk-v141-upgrade

## Current state
mctl-agent v1.5.0 integrates with the Anthropic API in two places (see
`context/architecture.md`):

1. **LLMDiagnosis builtin skill** (`internal/skill/builtin/`) — calls the Claude API to
   produce a natural-language diagnosis for alerts that no other skill matches. Uses the
   Anthropic SDK (vendored or direct HTTP) with a custom request builder.
2. **MCP endpoint** (`POST /mcp`) — exposes 6 tools over JSON-RPC 2.0. The tool
   registry, schema marshalling, dispatcher, and (if present) webhook signature
   verification are custom-written scaffolding not covered by the SDK.

The custom MCP scaffolding is functional but carries ongoing maintenance cost: any
change to the MCP protocol or tool schema requires editing the hand-rolled JSON-RPC
layer rather than updating a dependency.

## Proposed solution
Bump `anthropic-sdk-go` to v1.41.0 in `go.mod` / `go.sum` and migrate the MCP
scaffolding to use the SDK's new first-class MCP helpers:

### 1. Dependency bump
```
go get github.com/anthropics/anthropic-sdk-go@v1.41.0
go mod tidy
```
Vendored dependencies (if used) are updated accordingly.

### 2. MCP tool registration
Replace the hand-rolled JSON-RPC tool registry with the SDK's `mcp.Tool` builder and
`mcp.Server` (or equivalent type provided by v1.41.0). The 6 existing tools are
re-registered with identical names and input schemas; only the internal wiring changes.

### 3. Webhook handling
Replace any custom Anthropic webhook signature-verification middleware with the SDK's
built-in `webhook.ValidateRequest` (or equivalent). The chi route for MCP requests
wraps the handler with the SDK validator, removing bespoke HMAC logic.

### 4. LLMDiagnosis call sites
Review `LLMDiagnosis` call sites and update any deprecated SDK method signatures to
their v1.41.0 equivalents. No functional behaviour change — same model, same prompt
structure, same timeout.

### 5. Test parity
For every custom scaffolding code path removed, a corresponding unit test using the
SDK's test helpers (if provided) or a table-driven stub is added to confirm output
equivalence.

The chi HTTP router (`chi/v5 5.2.1`) is unchanged. SQLite, go-github, and uuid
dependencies are unaffected.

## Alternatives

### Option A: Keep the current custom scaffolding indefinitely
Continue maintaining the hand-rolled MCP JSON-RPC layer without adopting SDK helpers.
Dropped because the maintenance surface grows with each new MCP tool, and the SDK
helpers are now stable (v1.41.0 is a non-alpha release) — the cost of not adopting
them increases over time.

### Option B: Replace the Anthropic SDK with direct HTTP calls throughout
Remove the SDK dependency entirely and call the Anthropic REST API directly with
`net/http`. Dropped because ADR 0001 explicitly references the Anthropic SDK as part of
the remote-skill extensibility roadmap, and direct HTTP would lose the managed-agents
and streaming helpers that v1.41.0 introduces.

### Option C: Upgrade to the latest available SDK version beyond v1.41.0
Use the most recent SDK release rather than pinning to v1.41.0. Dropped because the
analyst finding specifically targets v1.41.0 as the version introducing stable MCP tool
helpers; a further bump is a separate proposal to be evaluated once v1.41.0 is
production-stable in mctl-agent.

## Platform impact

### Migrations
`go.mod` and `go.sum` are updated. If dependencies are vendored, `vendor/` is
regenerated with `go mod vendor`. No database schema changes. No Kubernetes manifest
changes.

### Backward compatibility
The `POST /mcp` endpoint URL, JSON-RPC protocol version, and all 6 tool names/schemas
remain identical. Remote skills registered via `POST /api/v1/skills/register` are
unaffected. Existing Telegram and AlertManager webhook routes are unaffected.

### Resource impact (labs tenant)
The analyst finding explicitly states no memory increase is expected. The SDK upgrade
replaces in-process custom scaffolding of similar size; there is no new persistent data
structure or background goroutine introduced. The `labs` tenant memory budget is safe.
This proposal is flagged LOW RISK for `labs`.

### Risks and mitigations
| Risk | Mitigation |
|---|---|
| SDK v1.41.0 introduces a breaking change in the diagnose call path | Review the upstream changelog before bumping; run the full test suite including LLMDiagnosis integration tests |
| MCP tool schema drift between custom implementation and SDK-generated schema | Pin exact JSON schema output in tests; compare observed vs expected for each of the 6 tools in CI |
| Webhook signature verification rejects valid events after migration | Validate HMAC secret configuration against SDK docs; add an integration test with a known-good signed payload |
| labs tenant memory unexpectedly increases | Monitor RSS before and after deploy in a staging namespace; if RSS increases by >10 MB roll back |
