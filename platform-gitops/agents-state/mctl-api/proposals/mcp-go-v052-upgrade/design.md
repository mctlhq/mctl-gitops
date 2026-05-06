# Design: mcp-go-v052-upgrade

## Current state

mctl-api (v4.14.0, Go 1.24) uses mark3labs/mcp-go v0.31 as described in
`context/architecture.md`. The MCP server is wired into the chi/v5 router and
serves Streamable HTTP (POST + GET) at `/mcp`. The `StreamableHTTPServer` is
constructed once at startup and its handler is mounted on the chi router.

In all versions up to v0.51, `StreamableHTTPServer` does not close response
bodies on 404 replies inside its internal retry loop. Each unclosed body keeps
the underlying TCP connection in a half-open state and holds one file
descriptor. Under normal client behaviour — where clients retry on transient
errors — the fd count climbs monotonically. On the `admins` tenant this
eventually causes `accept(2)` to fail (`EMFILE`/`ENFILE`), making the `/mcp`
endpoint unavailable. On the `labs` tenant (already near its memory limit) open
connections consume additional memory, worsening an already tight situation.

## Proposed solution

Bump the `mark3labs/mcp-go` dependency in `go.mod` / `go.sum` from v0.31 to
v0.52.0 and adapt call sites to the new API.

**Key changes in v0.52.0 that affect mctl-api:**

1. **Fd-leak fix** — `StreamableHTTPServer` now closes response bodies before
   any retry, making the fd count stable.
2. **Transport-agnostic `Handle` entry point** — v0.52.0 exposes a
   `(*StreamableHTTPServer).Handle(mux)` method (or equivalent) that registers
   both the POST and GET routes on any `http.ServeMux`-compatible router,
   removing the need for callers to hard-code individual route registrations.

**Call-site changes:**

- Replace the manual `router.Post("/mcp", ...)` / `router.Get("/mcp", ...)`
  registration pair with a single `mcpServer.Handle(r)` call (where `r` is the
  chi router sub-tree mounted at `/mcp`), using the adapter pattern already
  used for other chi sub-routers in the service.
- Adjust any constructor or option calls if v0.52.0 renames or removes
  parameters (to be confirmed during the `go get` step and reflected in tasks).

**No changes** to tool definitions, auth middleware, Prometheus metrics
instrumentation, or the OIDC/OAuth flow are required.

## Alternatives

**A. Stay on v0.31 and patch the fd leak manually.**
We could vendor mcp-go and add `resp.Body.Close()` calls ourselves. This
unblocks the fix immediately but creates a permanent fork divergence: every
future upgrade must re-apply or drop the patch. Rejected because the upstream
fix is available and vendoring a patched fork increases long-term maintenance
burden.

**B. Raise the pod `ulimit -n` and defer the upgrade.**
Increasing the Kubernetes `securityContext` fd limit would delay exhaustion but
not stop the leak. Memory consumption from half-open connections would continue
to grow, which is particularly harmful on the `labs` tenant. Rejected because
it treats the symptom, not the cause, and provides no finite safety margin.

**C. Upgrade directly to the latest mcp-go release (beyond v0.52.0).**
Skipping intermediate versions could bundle unreviewed breaking changes and
complicate root-cause analysis if a regression appears. Rejected in favour of
incremental, reviewable upgrades (one minor version per proposal, consistent
with the series mcp-go-upgrade → v0.50 → v0.51 → this proposal).

## Platform impact

### Migrations

No database schema changes. No Kubernetes manifest changes. The upgrade is
purely a Go dependency bump plus minor call-site adaptation.

### Backward compatibility

The MCP Streamable HTTP transport (POST + GET at `/mcp`) and all 24 tool
definitions remain unchanged. Existing Claude.ai connectors, CLI clients, and
AI agents continue to work without reconfiguration. The `Handle` refactor is
internal to the Go binary.

### Resource impact (especially for `labs`)

The fd-leak fix is a net positive for both tenants:

- **`admins`** — fd count stabilises; risk of `EMFILE` eliminated.
- **`labs`** — each previously leaked half-open connection holds a socket
  buffer (~4–8 KB). Under typical retry traffic (e.g., 10 retries/min × 8 h)
  this accumulates to several MB of wasted memory. Fixing the leak directly
  reduces the memory footprint of mctl-api on the `labs` tenant, moving it
  away from its memory limit rather than toward it. This proposal is therefore
  a low-risk, resource-positive change for `labs`.

No new memory allocations or CPU-intensive paths are introduced by v0.52.0.

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| v0.52.0 has breaking API changes beyond `Handle` | Low | `go get` immediately surfaces compile errors; fix before merge |
| Regression in one of the 24 MCP tools | Low | Full integration test suite (T1–T3) must pass in CI |
| The `Handle` adapter is incompatible with chi's routing | Low | Wrap with `http.HandlerFunc` shim as done for other sub-routers |
| v0.52.0 introduces a new dependency that increases binary size on `labs` | Very low | Check `go mod tidy` output; escalate if a heavyweight transitive dep appears |
