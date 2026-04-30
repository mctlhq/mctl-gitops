# Design: mcp-command-injection-hardening

## Current state
As documented in `context/architecture.md`, mctl-agent exposes a `POST /mcp` JSON-RPC
endpoint that dispatches to 6 registered MCP tools. The chi v5.2.1 router routes the request
directly to the MCP handler with no intermediate validation layer. The handler trusts the
`method` field and `params` object in the incoming JSON-RPC payload without allowlist
checking, size bounding, or field sanitisation. CVE-2026-30623 shows that the MCP SDK's
stdio transport can be abused via crafted tool names and parameters to achieve command
injection on the host process. The HTTP transport used here shares the same JSON-RPC
deserialisation path that the CVE targets.

## Proposed solution
A dedicated **MCP validation middleware** is inserted into the chi handler chain for
`POST /mcp`, sitting between the router and the existing MCP handler. The middleware is
implemented as a standard `func(http.Handler) http.Handler` in a new file
`internal/mcp/validate.go`.

**Validation pipeline (in order):**

1. **Body size cap** — wrap `r.Body` with `http.MaxBytesReader(w, r.Body, 64*1024)` before
   any reads. If the read exceeds the cap, respond HTTP 413 and abort.

2. **JSON unmarshalling into a typed envelope** — define a minimal struct:
   ```go
   type mcpEnvelope struct {
       JSONRPC string          `json:"jsonrpc"`
       ID      any             `json:"id"`
       Method  string          `json:"method"`
       Params  json.RawMessage `json:"params"`
   }
   ```
   Unmarshal into this struct and verify `jsonrpc == "2.0"`. Malformed JSON returns
   JSON-RPC error `-32700` (Parse Error).

3. **Tool-name allowlist** — a compile-time `map[string]struct{}` containing exactly the 6
   registered tool names (e.g., `"tools/list"`, `"tools/call"`, and the four domain tools).
   If `Method` is not in the map, respond HTTP 400 + JSON-RPC error `-32601`.

4. **Param field length check** — unmarshal `Params` into `map[string]any` and walk every
   string value. Any string exceeding 8 KB triggers HTTP 400 + JSON-RPC error `-32602`.
   The check is shallow (top-level keys only) to avoid unbounded recursion on nested objects;
   nested-object depth is capped at 3 levels.

5. **Re-serialise sanitised envelope** — replace `r.Body` with an `io.NopCloser` wrapping
   the re-serialised validated envelope so downstream handler reads clean data.

6. **Per-request timeout** — apply `http.TimeoutHandler` at router registration time with
   `30s`, returning HTTP 408 on expiry.

All rejections emit a structured `slog.Warn` entry with fields:
`request_id`, `remote_addr`, `rejected_field`, `reason`.

The allowlist is initialised in `main.go` from a Go `const` block, not from external
configuration, so the "empty allowlist at startup" guard (requirements §6) is enforced by a
`len(allowlist) == 0` check in `NewMCPValidationMiddleware` which calls `log.Fatal`.

**Why this approach?** It is fully contained within mctl-agent's own handler layer, requires
no dependency additions, has zero memory overhead (streaming body cap releases allocation),
and leaves the MCP SDK and HTTP transport untouched — consistent with the constraint of not
swapping the transport.

## Alternatives

### Alternative A: Upgrade or replace the MCP SDK
Swap the MCP SDK for a version or fork that patches the stdio transport. Dropped because no
patched version is available as of 2026-04-30, and the stdio transport is not the vector in
our HTTP-based deployment — the risk is at the JSON-RPC deserialisation layer, which we can
address independently.

### Alternative B: Add mTLS or API-key authentication to POST /mcp
Gate the endpoint so only authorised clients can reach it at all. Dropped from this proposal
because authentication is a separate concern tracked independently; it does not mitigate a
malicious authenticated caller, and its absence should not delay closing the injection vector.

### Alternative C: Proxy all MCP traffic through a dedicated sidecar / WAF
Deploy an Envoy or similar sidecar to strip or validate MCP payloads. Dropped because it
introduces a new infrastructure component, increases `admins` namespace resource consumption,
and is architecturally disproportionate to a targeted input-validation fix.

## Platform impact

### Migrations
No database schema changes. No changes to the MCP tool implementations. The middleware is
purely additive in the handler chain.

### Backward compatibility
All well-formed requests from existing MCP clients using one of the 6 registered tool names
with params under 8 KB will pass through unchanged. The re-serialised envelope is
semantically identical to the input for compliant requests.

### Resource impact
The body cap (`MaxBytesReader`) reduces rather than increases peak memory allocation. The
param-walk allocates a single shallow `map[string]any` per request, which is immediately
GC'd. No impact on the `labs` tenant (this change is in `admins` only).

### Risks and mitigations
- **Risk:** A legitimate MCP client sends a param string exceeding 8 KB (e.g., large
  Kubernetes manifest embedded in a tool call). **Mitigation:** The 8 KB limit is tunable
  via a constant in `validate.go`; document the limit in `POST /mcp` API notes and monitor
  for HTTP 400 rates in the first week after deployment.
- **Risk:** Re-serialisation of the envelope alters byte-for-byte content that a downstream
  handler depends on. **Mitigation:** The downstream MCP handler unmarshals `Params` from
  `json.RawMessage`; re-serialisation of a validated `map[string]any` is semantically
  equivalent.
- **Risk:** `http.TimeoutHandler` cancels the context for long-running legitimate tool calls.
  **Mitigation:** The existing skill dispatcher already has internal deadlines well under
  30 s; the 30 s handler timeout is a safety net only.
