# Design: mcp-input-validation

## Current state
mctl-agent (see `context/architecture.md`) exposes `POST /mcp` — an MCP JSON-RPC endpoint with **6 tools**. The endpoint is served by the chi/v5 router at `https://agent.mctl.ai/mcp`. The 6 tools interact with three downstream systems:

| Tool | Downstream system | Operation |
|---|---|---|
| `create_pr` | GitHub (`mctlhq/mctl-gitops`) | Opens a fix pull request |
| `list_tickets` | SQLite tickets DB | Lists open/recent tickets |
| `get_ticket` | SQLite tickets DB | Fetches a single ticket by ID |
| `silence_alert` | AlertManager | Creates a silence for a matching alert |
| `query_alerts` | AlertManager | Queries active alerts by label selector |
| `update_ticket_state` | SQLite tickets DB | Mutates ticket status (ack/reject/resolve) |

Currently, tool arguments from the MCP JSON-RPC `params.arguments` object are extracted from the JSON payload and passed to the relevant downstream client with no systematic validation layer. Individual call sites may perform ad-hoc type assertions (e.g., checking that a string is non-empty), but there is no unified allowlist schema per tool and no guaranteed rejection path for malformed or injection-laden input.

This is consistent with the pattern identified in the 2026-04-15 MCP command-injection advisories: the absence of a structured input validation layer at the MCP handler boundary leaves downstream API calls reachable with attacker-controlled data.

## Proposed solution

**Introduce a per-tool allowlist validation layer inside the `POST /mcp` handler, executed before any downstream call.**

### Architecture

A new package `internal/mcp/validation` contains:

1. **`Schema` struct** — defines, per tool, the set of accepted fields with their types, regex allowlists, and length limits.
2. **`Validate(toolName string, arguments map[string]any) error` function** — the single entry point; returns a structured `ValidationError` on failure.
3. **`SchemaRegistry` map** — a `map[string]Schema` populated at init time, one entry per tool.

The MCP handler (`internal/mcp/handler.go` or equivalent) calls `validation.Validate` immediately after unmarshalling the JSON-RPC request and before dispatching to any tool implementation. If `Validate` returns an error, the handler writes a JSON-RPC `-32602` response and returns; the downstream system is never touched.

### Per-tool schemas (allowlist definitions)

**`create_pr`**
- `branch_name`: string, regexp `^[a-zA-Z0-9/_.-]{1,200}$`
- `title`: string, non-empty, max 256 chars
- `body`: string, max 65536 chars (empty allowed)
- `base_branch`: string, regexp `^[a-zA-Z0-9/_.-]{1,200}$`

**`list_tickets`**
- `status`: string, enum allowlist `["open", "acked", "rejected", "resolved", ""]`
- `limit`: integer, range 1–100

**`get_ticket`**
- `ticket_id`: string, regexp `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$` (UUID v4)

**`silence_alert`**
- `matchers`: array of objects, each with `name` and `value` fields; both restricted to `^[a-zA-Z0-9_]{1,64}$`; `isRegex` bool only
- `duration_seconds`: integer, range 1–86400
- `comment`: string, max 512 chars, no shell metacharacters

**`query_alerts`**
- `label_selector`: string, max 512 chars, must not contain `$`, `` ` ``, `;`, `|`, `&`, `>`, `<`, `\n`, `\r`
- `active_only`: bool

**`update_ticket_state`**
- `ticket_id`: string, UUID regexp (same as `get_ticket`)
- `new_state`: string, enum allowlist `["acked", "rejected", "resolved"]`
- `reason`: string, max 512 chars, no shell metacharacters

### Logging
Each rejection emits a `slog.Warn` structured log with fields: `tool`, `field`, `reason`, `sanitized_value` (the value with sensitive data redacted to `[REDACTED]` if it matches a secret-like pattern, otherwise the first 64 chars of the raw value).

### Why this approach
- The validation layer is purely additive — it adds no new endpoints, no new dependencies, and does not change the tool semantics.
- Placing validation in a dedicated package keeps it testable in isolation and makes the schema the single source of truth.
- An allowlist (permit known-good) is strictly safer than a denylist (block known-bad) for injection defence.
- Using Go's `regexp` package with pre-compiled patterns at init time adds negligible latency per request (sub-microsecond for typical string lengths).
- No new external dependencies are required; `regexp`, `fmt`, `strings`, and `slog` are all stdlib.

## Alternatives

**A. Use a JSON Schema validation library (e.g., `github.com/santhosh-tekuri/jsonschema`).**
A full JSON Schema library would allow schemas to be declared in JSON files (hot-reloadable) and validated against a standards-compliant validator. However, this introduces a new external dependency, increases binary size, and adds schema-loading complexity. For 6 fixed tools, the added value does not justify the dependency. Dropped.

**B. Validate at the downstream client level (in the GitHub or AlertManager client wrappers).**
Pushing validation into each client wrapper distributes the logic across multiple packages, making it easy to miss a call site or add a new tool without implementing validation. A centralised validation layer in the MCP handler ensures no downstream call is reachable without passing validation. Dropped.

**C. Use an API gateway or WAF in front of the MCP endpoint to filter injection payloads.**
A WAF can catch known-bad patterns but cannot enforce the allowlist semantics that are specific to each tool's business logic (e.g., "branch names must match this regexp"). WAF rules are also maintained separately from the code, creating drift risk. Defence-in-depth favours both layers, but the application-layer allowlist is the primary control; WAF is complementary. This proposal focuses on the application layer. Dropped as the sole control.

## Platform impact

**Migrations:**
- No database migrations. The validation layer is purely in-memory.
- The `POST /mcp` handler must be updated to call `validation.Validate` before dispatching. This is a code change only.

**Backward compatibility:**
- Valid, well-formed MCP tool calls are unaffected. The allowlist schemas are designed to accept all currently known valid inputs from the Claude API (which generates the tool arguments).
- If the Claude API sends an argument that the schema rejects, the handler returns a `-32602` error. This would surface as an error in the Claude conversation and requires schema tuning. However, since the schemas are derived from the tool definitions that Claude already uses, this risk is low.
- Any MCP client relying on passing oversized or special-character-containing fields will receive a rejection. This is intentional and expected.

**Resource impact (labs tenant):**
- The validation layer uses only pre-compiled regexp objects (compiled once at startup) and string-length checks. The per-request cost is O(n) in argument string length, typically sub-microsecond. Memory impact is the storage of 6 compiled regexp objects — negligible (kilobytes). There is no risk to the labs tenant memory limit.

**Risks and mitigations:**
- Risk: A schema is too restrictive and rejects valid inputs from the Claude API, causing MCP tool failures during normal operation. Mitigation: the schema values in each tool definition are derived from the actual argument shapes the Claude API generates; review against production logs before deploying. The `-32602` error is surfaced to the MCP client immediately, allowing rapid diagnosis.
- Risk: A new MCP tool is added in the future without a corresponding schema entry, bypassing the validation layer. Mitigation: the `Validate` function treats an unknown tool name as a validation error (reject-by-default); adding a new tool without a schema entry will cause all calls to it to fail with `-32602`, enforcing the requirement to define a schema first.
- Risk: The reject-by-default policy for unknown tools could cause an outage if a tool is renamed or the registry is misconfigured. Mitigation: the schema registry is validated at startup; a missing or empty registry entry causes the process to fail fast rather than silently pass all validation.
