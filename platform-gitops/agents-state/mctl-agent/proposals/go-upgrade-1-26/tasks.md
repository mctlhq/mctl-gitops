# Tasks: go-upgrade-1-26

- [ ] 1. Update the directive in `go.mod` from `go 1.24` to `go 1.26.2` —
  DoD: `go.mod` contains the line `go 1.26.2`, `go mod verify` passes without errors.

- [ ] 2. Update the base image in `Dockerfile` (depends on 1) —
  DoD: `FROM golang:1.26.2-alpine` (or equivalent) in the build stage; the image builds
  locally with `docker build .` without errors.

- [ ] 3. Update CI workflow (if the Go version is pinned explicitly) (depends on 1) —
  DoD: all references to `go-version: '1.24'` or equivalents are replaced with `'1.26.2'`;
  the pipeline runs and goes green.

- [ ] 4. Run `go mod tidy` and commit the changes (depends on 1) —
  DoD: `go.sum` is up to date, no unused dependencies, no compatibility errors.

- [ ] 5. Run the full test suite (depends on 2, 4) —
  DoD: `go test ./...` passes without failures and the race detector (`-race`) does not
  surface new races.

- [ ] 6. Build and verify the binary (depends on 5) —
  DoD: `go build ./...` succeeds; `./mctl-agent --version` prints the correct version;
  `/healthz` answers 200 in a local Docker run.

## Tests

- [ ] T1. Unit tests of Go skills: `go test ./internal/skill/... -v -race` — all pass.
- [ ] T2. HTTP layer test: `go test ./internal/... -run TestAlert` — the webhook handler
  accepts a test AlertManager payload without behavioural changes.
- [ ] T3. Smoke test in staging: deploy the image with Go 1.26.2 to the admins/staging
  slot, send a test alert, confirm a ticket is created and a PR is opened.
- [ ] T4. GC baseline: capture `runtime.MemStats` before and after — confirm `PauseTotalNs`
  has not grown compared to the Go 1.24 baseline.

## Rollback

Revert the commit with go.mod and Dockerfile changes → rebuild the image → update the
tag in the admins-tenant GitOps manifest. ArgoCD reconciles the rollback automatically.
