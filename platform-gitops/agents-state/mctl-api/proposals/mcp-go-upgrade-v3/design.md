# Design: mcp-go-upgrade-v3

## Current state
mctl-api imports `github.com/mark3labs/mcp-go` at v0.31 (per `context/architecture.md` and
ADR-0001), providing:
- Streamable HTTP transport (POST + GET) at `/mcp`, publicly reachable at `https://api.mctl.ai/mcp`
- Schema generation and validation for 24 tools (11 read + 13 write)
- OAuth 2.0 PKCE for the Claude.ai connector
- MCP spec version 2025-06-18

Two unresolved vulnerabilities exist against v0.31:
1. **CVE-2026-27896** — case-insensitive JSON-RPC field-name matching allows validation bypass.
   Already scoped for a v0.54.0 fix in `proposals/mcp-go-upgrade-v2` (unmerged).
2. **CVE-2026-81092** (new this cycle) — `StreamableHTTPServer.ServeHTTP` /
   `SSEServer.ServeHTTP` do not validate the Host header on loopback-bound listeners, allowing DNS
   rebinding attacks to reach the server. Fixed upstream in v0.56.0. **Not covered** by the v2
   proposal's v0.54.0 target.

Because mctl-api's MCP endpoint is internet-facing (`api.mctl.ai/mcp`, not merely
loopback-only-by-convention), a DNS-rebinding path that assumes "loopback = trusted" is a real risk
if any part of the request path (e.g. an internal sidecar, local dev listener, or health-check
proxy) binds to loopback and forwards Host-header-driven requests. Even where the production
topology mitigates the practical exploitability, this is a public CVE against our sole MCP library
and must be closed rather than argued away.

## Proposed solution
**Bump `github.com/mark3labs/mcp-go` from v0.31 directly to v1.1.0** (skipping the intermediate
v0.54.0 target from `mcp-go-upgrade-v2`) via:

```
go get github.com/mark3labs/mcp-go@v1.1.0
go mod tidy
```

**Key changes between v0.31 and v1.1.0 relevant to mctl-api (superset of the v2 proposal's scope):**

1. **Host header validation on loopback listeners (CVE-2026-81092)** — v0.56.0 adds
   `server/http_localhost.go`, restricting which Host headers are accepted by
   `StreamableHTTPServer.ServeHTTP` / `SSEServer.ServeHTTP` when bound to loopback interfaces. We
   will additionally set an explicit allow-list of expected Host values (`api.mctl.ai`) at the
   ingress/router layer as defense-in-depth, independent of the library fix.

2. **JSON field-name normalisation (CVE-2026-27896)** — carried over unchanged from the v2
   proposal's analysis: v0.54.0+ enforces strict lowercase field-name matching in the JSON-RPC
   dispatcher. Malformed/case-variant requests now receive a `-32600` Invalid Request error.

3. **Panic recovery in message handlers** — carried over from v2: upstream fixed goroutine cleanup
   and added per-handler recover wrappers between v0.31 and v0.54.0, retained through v1.1.0.

4. **v1.0.0 stabilization + v1.1.0 additions** — in-process client options and roots handler
   support are additive API surface; not adopted by mctl-api in this proposal (see Out of scope).
   Transport option signatures were reviewed for breaking changes in the beta→v1.0.0 transition
   (task 2 below covers auditing this explicitly, since v0.54.0→v1.1.0 spans a major version
   boundary that v2's plan did not anticipate).

5. **ADR-0001 compliance** — Streamable HTTP transport and MCP spec 2025-06-18+ are preserved. All
   24 tools must be re-validated through MCP Inspector after the bump (unchanged requirement from
   v2, re-run because the target version changed).

## Alternatives

### Ship `mcp-go-upgrade-v2`'s v0.54.0 target as-is, track CVE-2026-81092 separately
Rejected: this would require a second immediate follow-up bump within days of merging v2, doubling
the MCP Inspector re-validation effort (ADR-0001's most expensive step) for no benefit. Folding
both fixes into one bump is strictly cheaper.

### Bump only to v0.56.0 (the minimum version that fixes CVE-2026-81092)
Considered. Rejected in favor of v1.1.0: v0.56.0 is now several months behind the current stable
release, and the researcher has already confirmed v1.1.0 is a compatible stable release with no
new CVEs of its own. Landing on the current stable line avoids a third near-term re-bump.

### Patch the Host-header check locally without upgrading
Would require forking or monkey-patching `ServeHTTP`, creating a maintenance burden and diverging
from upstream. Rejected — same reasoning as v2's rejection of local-patching CVE-2026-27896.

### Replace mcp-go with the Anthropic Go SDK (if released)
ADR-0001 explicitly records this as a rejected alternative: loss of Streamable HTTP compatibility
with the Claude.ai connector. Not reconsidered here.

## Platform impact
- **Migrations:** go.mod / go.sum update. No data migrations.
- **Backward compatibility:** Streamable HTTP transport preserved; existing 24 tools unchanged.
  Well-behaved Claude clients are unaffected. Malformed requests and mismatched-Host-header
  requests now receive explicit rejections (previously they might silently bypass validation or be
  served regardless of Host header).
- **Resource impact:** Negligible; no measurable change to memory/CPU footprint expected from a
  library bump. No `labs` tenant impact — mctl-api runs only in `admins`.
- **Risks and mitigations:**
  - Risk: jumping from v0.31 across a 0.x→1.x major boundary (v0.31 → v1.1.0) may introduce
    breaking API changes in tool registration, handler signatures, or transport option functions
    beyond what `mcp-go-upgrade-v2`'s v0.54.0 analysis covered. Mitigation: explicit changelog/API
    diff audit task covering v0.54.0→v1.1.0 in addition to v0.31→v0.54.0 (task 2).
  - Risk: MCP Inspector validation (ADR-0001) surfaces regressions across 24 tools. Mitigation:
    full Inspector sweep plus existing integration test suite before promotion.
  - Risk: Host-header allow-listing at the ingress layer could reject legitimate traffic if
    `api.mctl.ai` is not the only valid Host value (e.g. internal health checks). Mitigation:
    stage the ingress-layer allow-list change separately from the library bump and verify against
    a full list of expected Host values before enabling in production.
  - Risk: two open proposals (`mcp-go-upgrade-v2` and this one) target the same `go.mod` line,
    risking a conflicting merge. Mitigation: explicitly mark `mcp-go-upgrade-v2` as superseded in
    review notes (task 1) before either merges.
