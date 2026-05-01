# Design: mcp-rce-server-hardening

## Current state
`mctl-api` uses `mark3labs/mcp-go 0.31` to expose 24 tools (11 read + 13 write) at `https://api.mctl.ai/mcp` over Streamable HTTP (see `context/architecture.md`). Auth is enforced at the HTTP layer: all three bearer types (GitHub PAT, Dex JWT, OAuth JWT) are resolved to a caller identity and tenant groups before the request reaches any handler. However, once a caller clears the authentication gate, all 24 tools are equally accessible — there is no per-tool authorization layer, no payload size cap below Go's default, no write-specific rate limit, and no durable audit trail for write invocations.

The `httprate 0.15` middleware currently applies a single global rate limit across all endpoints. The CVE-2025-49596 family underscores that MCP's protocol-level design permits tool-invocation payloads to carry arbitrary nested structures; without a size guard these can be weaponized for memory exhaustion.

## Proposed solution

### 1. Per-tool authorization middleware
Introduce a `WriteTool` wrapper type that registers each of the 13 write tools with an associated `requiredPermission` string (e.g., `"mcp:write:trigger_workflow"`). A new `MCPAuthzMiddleware` function, invoked before the mcp-go handler dispatches to the tool implementation, looks up the resolved `TenantGroups` on the request context (already populated by the existing auth middleware) and checks them against a permission map loaded from a static config file (`config/mcp-tool-permissions.yaml`). On denial it returns a structured JSON error and increments `mcp_write_denied_total`.

This keeps authorization logic outside mcp-go internals and makes it easy to audit in a single YAML file.

### 2. Payload size enforcement
Add a `MaxBytesReader` wrapper (standard library `http.MaxBytesReader`) on the MCP endpoint handler before mcp-go reads the body — capped at 64 KB. Per-field limits are enforced inside each tool handler via a shared `validate.StringMaxLen(field, limit)` helper added to `internal/validate`. These are deliberately outside mcp-go to remain library-version-independent.

### 3. Write-tool rate limiter
Extend the existing `httprate` setup to register a second rate-limit store keyed on `(identity, tool_class=write)`. Read tools bypass this store entirely. The per-identity limit is 30 requests per 60-second window, returning HTTP 429 with `Retry-After: <seconds>`. The limit is tunable via environment variable `MCP_WRITE_RATE_LIMIT` (default 30).

### 4. Audit log
Add a new Postgres table `mcp_write_audit` (schema below). A post-handler middleware records every write-tool invocation — whether allowed or denied — asynchronously via a buffered channel feeding a background goroutine. The tool argument value is not stored verbatim; instead a SHA-256 of the JSON-encoded arguments is stored alongside a `size_bytes` field, preventing the audit log itself from becoming a data store for injected content. If the background writer is behind (channel full), the event is dropped and `mcp_audit_write_error_total` is incremented.

```sql
CREATE TABLE mcp_write_audit (
    id            BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    identity      TEXT NOT NULL,
    tool_name     TEXT NOT NULL,
    args_sha256   CHAR(64) NOT NULL,
    args_size_bytes INT NOT NULL,
    http_status   SMALLINT NOT NULL,
    latency_ms    INT NOT NULL,
    denied_reason TEXT
);
CREATE INDEX mcp_write_audit_identity_idx ON mcp_write_audit (identity, created_at DESC);
CREATE INDEX mcp_write_audit_tool_idx     ON mcp_write_audit (tool_name,  created_at DESC);
```

### Permission config
`config/mcp-tool-permissions.yaml` maps each write tool name to the minimum group(s) required:

```yaml
tool_permissions:
  trigger_workflow:   ["admins", "operators"]
  delete_service:     ["admins"]
  create_identity:    ["admins", "operators"]
  # ... remaining 10 write tools
```

## Alternatives

### Option A: Use mcp-go middleware hooks once available in v0.50+
The `mcp-go-upgrade-v0.50` proposal enables `WithInputSchemaValidation()` and may expose pre-dispatch hooks. Waiting for those hooks couples this security fix to a library upgrade and delays hardening. Rejected: the CVE family severity (9.4) does not permit deferral to a library feature that may change its API.

### Option B: Enforce all controls at the Kubernetes ingress / API gateway level
A WAF or gateway policy could enforce size limits and rate limits. However, per-tool authorization and semantic audit logging require knowledge of the decoded tool name, which is inside the MCP JSON body — not available to a generic gateway without deep inspection. Rejected: too much logic in infrastructure, loses auditability at the application layer.

### Option C: Disable all write tools until hardening is complete
Zero-risk from an exploitation standpoint, but renders the MCP server non-functional for legitimate operators. Rejected: disproportionate and does not result in a sustainable state.

## Platform impact

### Migrations
One new Postgres table (`mcp_write_audit`) and one index pair. Migration is additive; no existing tables are altered. Runs as a numbered migration via the existing `migrations/` directory.

### Backward compatibility
No changes to the MCP protocol wire format or tool schemas. Existing clients that hold valid tokens with write-group membership are unaffected. Clients that were previously able to invoke write tools without explicit group membership will begin receiving HTTP 403 — this is intentional and expected.

### Resource impact
The `admins` tenant runs mctl-api. The audit log buffer is a fixed-size in-memory channel (default 512 entries, ~150 bytes each = ~75 KB). The Postgres write path is async and batched; estimated additional DB write volume is low (< 100 write-tool calls/minute at peak). No impact on the `labs` tenant.

### Risks and mitigations
- **Risk:** Rate limit misconfiguration locks out legitimate automation. **Mitigation:** `MCP_WRITE_RATE_LIMIT` env var allows tuning without redeployment; default 30/min is well above observed legitimate usage.
- **Risk:** Audit buffer overflow drops events under attack conditions. **Mitigation:** `mcp_audit_write_error_total` Prometheus counter alerts on-call when drops exceed threshold.
- **Risk:** Permission YAML misconfiguration grants excess access. **Mitigation:** CI linter validates that every registered write tool has an entry; missing entries cause startup failure via `log.Fatal`.
