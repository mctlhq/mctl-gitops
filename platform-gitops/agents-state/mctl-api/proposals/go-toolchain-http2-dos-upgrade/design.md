# Design: go-toolchain-http2-dos-upgrade

## Current state
Go 1.24 modules (see context/architecture.md). Stdlib net/http serves HTTP/2 directly or behind ingress; x/net is a transitive dependency.

## Proposed solution
Bump `go` directive and Dockerfile builder image (pinned by digest) to Go 1.26.9, `go get golang.org/x/net@v0.62.0`, run `go mod tidy`, fix any build breaks, add `govulncheck ./...` to CI. Roll out via mctl-gitops/ArgoCD with the normal rollout; verify via /metrics.

## Alternatives
- Go 1.25.13 only: smaller jump but shorter support runway; rejected as default, acceptable fallback.
- Disable HTTP/2 on the server: removes exposure but hurts clients and does not fix the transport/client side.
- Wait for ingress-level mitigation: does not cover in-cluster traffic.

## Platform impact
- Migrations: none.
- Backward compatibility: Go 1.26 stdlib behavior changes possible; covered by test suite.
- Resource impact: admins only; negligible, no effect on `labs` memory.
- Risks: dependency incompatibilities (client-go 0.32, mcp-go 0.31) — mitigated by running full tests and canary.
