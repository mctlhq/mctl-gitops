# Tasks: go-1-26-11-toolchain-xnet

- [ ] 1. Bump go.mod go/toolchain to 1.26.11 and Dockerfile builder digest — DoD: build passes.
- [ ] 2. Bump golang.org/x/net >= 0.63.0, go mod tidy (depends on 1) — DoD: go.sum updated, build passes.
- [ ] 3. Run govulncheck (depends on 2) — DoD: no reachable findings.
- [ ] 4. Deploy to admins staging, then labs, compare memory (depends on 3) — DoD: labs RSS not higher than baseline.

## Tests
- [ ] T1. Full go test ./...
- [ ] T2. All 3 bearer auth flows smoke-tested.
- [ ] T3. MCP Inspector pass over 24 tools.

## Rollback
Revert the gitops image tag to the previous digest via ArgoCD.
