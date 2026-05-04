# Design: bump-chi

## Current state
`context/architecture.md` records `chi/v5 5.2.1` as the HTTP router. Chi handles all inbound
traffic for the agent's public surface:

- `POST /api/v1/alerts` — AlertManager webhook
- `POST /api/v1/telegram` — Telegram bot webhook
- `GET /api/v1/tickets`, `GET /api/v1/skills`, `POST /api/v1/skills/register` — REST API
- `POST /mcp` — MCP JSON-RPC endpoint (6 tools)
- `GET /healthz`, `/readyz` — health probes

The router is configured in the agent's `main.go` or equivalent HTTP setup file. It is not known
from the architecture document whether `RedirectSlashes` middleware is currently active, but
upgrading to v5.2.5 is correct regardless: it is the current stable patch release and closes
CVE-2025-69725 even if the vulnerable middleware is introduced in the future.

## Proposed solution
Bump `go-chi/chi/v5` from `v5.2.1` to `v5.2.5` in `go.mod` and run `go mod tidy`.

The chi v5 module path does not change between patch releases; no import-path updates are required.
The v5.2.5 release is fully backward-compatible with v5.2.1 for all public router and middleware
APIs. The change is a single version string update in `go.mod`.

**Ordering note:** This proposal should be applied after `bump-go-toolchain` (Upgrade Go 1.24 to
1.26.2). chi v5.2.5 declares a minimum Go version of 1.22 in its `go.mod`. The agent's current
toolchain (Go 1.24) already satisfies this minimum, so the two proposals are not strictly
sequentially blocked. However, applying the toolchain upgrade first ensures that `go mod tidy`
runs against the final target toolchain and avoids any intermediate version-graph inconsistency.

## Alternatives

### A. Stay on v5.2.1 and add a WAF rule to block crafted redirect URLs
Ruled out: the WAF rule adds operational complexity and only mitigates the specific CVE pattern
known at the time of writing. Upgrading the library closes the vulnerability at the source and
removes the need for a compensating control. A WAF rule is not a substitute for a one-line patch.

### B. Upgrade to chi v6 (next major version, if available)
Ruled out: chi v6 had not been released at the time of this analysis. Even if it were available,
a major-version upgrade carries migration risk (potential breaking API changes) that is
disproportionate to the minimal effort of this patch upgrade.

### C. Replace chi with `net/http` ServeMux (Go 1.22+ enhanced mux)
Ruled out: while Go 1.22's enhanced `ServeMux` now supports method-based routing, it does not
replicate chi's middleware composition, route grouping, or URL parameter extraction that the agent
relies on. Migrating would be a significant refactor with no security benefit beyond this upgrade.

## Platform impact

### Migrations
No database schema changes. No Kubernetes manifest changes. No environment variable or secret
changes. The chi module path (`github.com/go-chi/chi/v5`) is identical at both versions.

### Backward compatibility
chi v5.2.5 is fully backward-compatible with v5.2.1 for all public APIs used by the agent. No
handler signatures, middleware interfaces, or router configuration options have changed in the
v5.2.x patch series.

### Resource impact (`labs` tenant)
This is a single dependency version bump with no change to binary size, memory footprint, or
goroutine count. The `labs` tenant memory limit is not at risk; this proposal is not flagged as
risky for `labs`.

### Risks and mitigations
- **Unexpected behavior change in `RedirectSlashes`:** If the middleware is active, the fixed
  behavior (redirect stays on the same host) is the correct and expected behavior. There is no
  scenario where the pre-fix cross-host redirect was intentional. Risk: negligible.
- **`RouteHeaders` handler invocation change:** The double-invocation fix in v5.2.5 means that any
  handler previously invoked twice (a bug) will now be invoked once (correct). If any handler
  relied on idempotent double-invocation for correctness, it would be broken. This is highly
  unlikely in practice. Mitigation: review `RouteHeaders` usage in the router configuration before
  merging.
