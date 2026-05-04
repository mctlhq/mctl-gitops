# Design: chi-open-redirect-patch

## Current state

mctl-api declares `github.com/go-chi/chi/v5 v5.2.1` in `go.mod` (see `context/architecture.md`). chi is the sole HTTP router for all REST and MCP endpoints exposed at `https://api.mctl.ai`. The `RedirectSlashes` middleware may be active to normalize trailing slashes on REST routes.

In chi v5.2.1 the `RedirectSlashes` middleware builds the redirect `Location` value from `r.Host`, which is taken directly from the incoming request without validation. An attacker can supply `Host: evil.example.com` in a request, causing chi to issue a 301/308 redirect to `https://evil.example.com/<path>`. When this redirect occurs during the OAuth 2.0 PKCE authorization flow (endpoint `https://api.mctl.ai/mcp`), the attacker receives the authorization code appended to the redirect URL, enabling account takeover or unauthorized MCP tool execution.

GO-2026-4316 / GHSA-vrw8-fxc6-2r93 documents this flaw. It is published 2026-01-14, rated Moderate severity by the Go vulnerability database.

## Proposed solution

Bump `github.com/go-chi/chi/v5` from `v5.2.1` to `v5.2.5` in `go.mod`, then run `go mod tidy` to update `go.sum` and any transitive entries. chi v5.2.5 hardens `RedirectSlashes` to use the server's configured scheme and host rather than the raw `Host` request header, and also fixes a double-handler-invocation bug in `RouteHeaders`. The minimum Go requirement for chi v5.2.5 is Go 1.22; mctl-api targets Go 1.24, so no toolchain change is needed.

The change is intentionally scoped to a single line in `go.mod` plus the `go.sum` refresh. No application code, middleware configuration, or API surface changes. The fix is deployed through the existing mctl-gitops -> ArgoCD pipeline: a PR to update the manifest triggers a build, the image is pushed, and ArgoCD reconciles the deployment.

Why this approach over the alternatives (see below): it is the lowest-effort, lowest-risk path. The patch is a drop-in; chi's changelog explicitly marks v5.2.5 as fully backward compatible with v5.2.x.

## Alternatives

**1. Disable `RedirectSlashes` middleware entirely.**
This eliminates the vulnerable code path without a version bump. However, it changes observable API behavior (clients relying on trailing-slash normalization would receive 404s instead of redirects), it does not patch the underlying vulnerability (the code remains present), and it does not address the secondary fix in v5.2.5 (double handler invocation). Dropped because it trades a security fix for an API behavior regression.

**2. Add an upstream reverse-proxy rule to strip or validate the `Host:` header before it reaches chi.**
An ingress-level `Host:` header rewrite (e.g., in the NGINX ingress or Envoy sidecar) would prevent the crafted header from reaching chi. This is a valid defense-in-depth measure but does not fix the vulnerable dependency, leaves the CVE open in the SBOM, and adds ingress configuration complexity that is outside mctl-api's ownership boundary. Dropped as a primary fix; may be retained as defense-in-depth independently.

**3. Replace chi with another router (gorilla/mux, echo, gin).**
Would fully eliminate the chi attack surface. However, the architecture decision log and `context/architecture.md` explicitly prohibit switching the router without a strong benchmark justification. A router migration is a large-scope change for a vulnerability with a trivial one-line patch available. Dropped.

## Platform impact

**Migrations:** None. `go.mod` and `go.sum` are updated; no database schema changes, no configuration changes, no API schema changes.

**Backward compatibility:** chi v5.2.5 is a patch release. The chi maintainers guarantee no breaking changes within a minor series. All existing route definitions, middleware chains, and handler signatures remain valid.

**Resource impact (`labs` tenant):** No resource impact. The binary size change from a patch-level chi bump is negligible (well under 1 KB). No new goroutines, no new memory allocations at startup. The `labs` tenant memory budget is not affected. This proposal carries no risk flag for `labs`.

**Risks and mitigations:**

| Risk | Likelihood | Mitigation |
|---|---|---|
| chi v5.2.5 introduces an undiscovered regression in routing behavior | Very low (patch release, thoroughly tested upstream) | CI integration tests cover all registered routes; any 404/500 regression blocks merge |
| `go mod tidy` pulls in an updated transitive dependency with its own vulnerability | Low | `govulncheck ./...` runs in CI and must pass with zero findings before merge |
| ArgoCD rollout causes a brief pod restart | Expected, normal | Rolling update strategy with `maxUnavailable=0`; health checks gate traffic switchover |
| Vulnerability is exploited before the patch is deployed | Possible if deployment is slow | Treat as P1; target same-day merge and deploy; ingress `Host:` header normalization as interim mitigation if needed |
