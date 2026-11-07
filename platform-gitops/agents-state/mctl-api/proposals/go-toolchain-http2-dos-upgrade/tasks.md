# Tasks: go-toolchain-http2-dos-upgrade

- [ ] 1. Bump go directive and Dockerfile builder digest to Go 1.26.9 — DoD: image builds, `go version` in build log shows 1.26.9.
- [ ] 2. `go get golang.org/x/net@v0.62.0` and tidy (depends on 1) — DoD: go.sum updated, build green.
- [ ] 3. Add govulncheck to CI (depends on 2) — DoD: CI job passes with no reachable findings.
- [ ] 4. Canary rollout via mctl-gitops (depends on 3) — DoD: error rate and latency within 10% of baseline for 24h.

## Tests
- [ ] T1. Full unit/integration suite on Go 1.26.9.
- [ ] T2. MCP Inspector smoke test across all 24 tools.
- [ ] T3. HTTP/2 malformed-frame test against staging does not crash the server.

## Rollback
Revert the gitops image tag to the previous digest; revert go.mod commit.
