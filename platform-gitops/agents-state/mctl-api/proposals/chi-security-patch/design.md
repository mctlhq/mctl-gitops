# Design: chi-security-patch

## Current state
According to `context/architecture.md`, mctl-api uses `chi/v5 5.2.1` as the HTTP router for all endpoints: REST API, the MCP endpoint (`/mcp`, Streamable HTTP POST+GET) and `/metrics`. The router handles inbound requests on the public address `https://api.mctl.ai`. Version 5.2.1 lags the latest (5.2.5) by 4 patch versions; the intermediate releases include a security fix in the `RedirectSlashes` middleware and a bugfix for double handler invocation in `RouteHeaders`.

## Proposed solution
Targeted bump of the `github.com/go-chi/chi/v5` dependency from `v5.2.1` to `v5.2.5` in `go.mod`.

Why exactly this:
- v5.2.5 is the latest stable with the minimum Go requirement (Go 1.22, we are on 1.24 — compatible).
- chi/v5 patch versions contain no breaking changes in the public Router API — the mctl-api code requires no edits.
- The security fix is isolated in the `RedirectSlashes` middleware; if the middleware is not used explicitly, the fix still applies as a defensive measure for any future enablement.
- The double-call bugfix in `RouteHeaders` removes a potential source of unexpected behaviour when conditional routing is used.

Steps:
1. `go get github.com/go-chi/chi/v5@v5.2.5`
2. `go mod tidy`
3. Run unit + integration tests for all routes.
4. Deploy via ArgoCD to the `admins` tenant.

## Alternatives

**A. Upgrade to v5.2.2, v5.2.3 or v5.2.4 instead of v5.2.5.**
All intermediate versions are subsumed by v5.2.5. There is no reason to stop on an intermediate patch when the final latest is available. Dropped.

**B. Explicitly disable or avoid the RedirectSlashes middleware and stay on v5.2.1.**
Does not eliminate the vulnerability as such — on accidental enablement or in the future, the code is vulnerable again. Dropped as an incomplete solution.

**C. Replace chi with another router (gin, echo, httprouter).**
Explicitly forbidden by the principles in `context/architecture.md` without strong benchmarks. Effort is incomparably higher (full rework of the middleware stack), and there is no justification for such a change. Dropped.

## Platform impact

**Migration:** Not required. The routing scheme, the middleware stack and the API contracts do not change.

**Backward compatibility:** chi/v5 patch versions are fully backward compatible. All code using chi v5.2.1 Router, Middleware, and Context API runs unchanged on v5.2.5.

**Resource impact:** The change concerns only router and middleware logic. Memory and CPU consumption do not change. The `labs` tenant is not affected — mctl-api runs in `admins`.

**Risks and mitigations:**
- Risk: a behavioural change of `RedirectSlashes` in v5.2.5 could affect clients relying on the current (potentially vulnerable) redirect. Mitigation: integration tests cover routing; verify that slash-redirect tests pass correctly.
- Risk: the `RouteHeaders` bugfix changes the handler invocation count from 2 to 1, which may surface hidden side effects in existing handlers. Mitigation: code-review the diff of routes using `RouteHeaders`; tests with an assertion on a single invocation.
