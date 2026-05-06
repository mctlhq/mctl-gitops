# Tasks: mcp-go-v052-upgrade

- [ ] 1. Bump dependency — run `go get github.com/mark3labs/mcp-go@v0.52.0 && go mod tidy` in the mctl-api module root — DoD: `go.mod` records `mark3labs/mcp-go v0.52.0`, `go.sum` is updated, `go mod tidy` reports no unused dependencies, and the module graph is committed.

- [ ] 2. Fix compile errors (depends on 1) — address any breaking API changes surfaced by `go build ./...` — DoD: `go build ./...` exits 0 with no errors or warnings; every changed call site has a code comment explaining the adaptation.

- [ ] 3. Adopt transport-agnostic `Handle` entry point (depends on 2) — replace the manual `router.Post("/mcp", ...)` / `router.Get("/mcp", ...)` pair with a single `mcpServer.Handle(r)` call on the chi sub-router mounted at `/mcp` — DoD: both POST and GET routes at `/mcp` are registered exclusively via `Handle`; no direct route registrations for `/mcp` remain in the chi setup; `go build ./...` still exits 0.

- [ ] 4. Verify fd stability under retry load (depends on 3) — run a local load script that sends 100 requests with deliberate 404-triggering paths against the dev server and checks `/proc/<pid>/fd` count before and after — DoD: fd count after the run is within ±5 of the count before; the result is recorded in the PR description.

- [ ] 5. Update architecture.md reference version (depends on 3) — change `mark3labs/mcp-go 0.31` to `mark3labs/mcp-go 0.52.0` in `context/architecture.md` under Tech stack — DoD: the file reflects the new version; no other lines changed.

## Tests

- [ ] T1. Unit tests — `go test ./...` passes with zero failures and zero skips related to MCP tool handlers — covers all 24 tool definitions remaining intact after the upgrade.
- [ ] T2. Integration test — start the full mctl-api binary in `AUTH_REQUIRED=false` mode and issue a `POST /mcp` initialize + `POST /mcp` tools/list request sequence; assert the response lists exactly 24 tools with the expected names.
- [ ] T3. Fd-leak regression test — replicate the scenario from Task 4 in CI using a short-lived test binary; assert that open fds do not grow over 50 sequential 404-triggering retry cycles.
- [ ] T4. Smoke test on `labs` tenant — deploy to `labs` canary pod, run T2 against it, observe memory usage in Prometheus over 10 minutes; assert memory does not increase relative to pre-upgrade baseline.

## Rollback

1. Revert the `go.mod` / `go.sum` change to `mark3labs/mcp-go v0.51.x` (the
   previously shipped version) using `git revert` on the upgrade commit.
2. Revert the `Handle` call-site change to the previous `router.Post` /
   `router.Get` pair in the same revert commit.
3. Run `go build ./...` and `go test ./...` to confirm the reverted state
   compiles and passes.
4. Re-deploy the previous image tag via ArgoCD (`argocd app set mctl-api
   --revision <previous-sha>`); ArgoCD will roll the pod back within one sync
   cycle.
5. Confirm `/mcp` availability with a `POST /mcp` initialize call; verify fd
   count returns to the pre-upgrade observed baseline.

The rollback does not require any database migration or Kubernetes manifest
change, making it fast and low-risk.
