# Tasks: go-toolchain-security-upgrade

- [ ] 1. Update `go.mod` `go` and `toolchain` directives from 1.24 to
      1.27.0 and run `go mod tidy` — DoD: `go.mod`/`go.sum` reflect the
      new toolchain, `go.sum` unchanged in module-version content (only
      toolchain metadata changes, if any).
- [ ] 2. Update the container build image and any CI workflow pin to
      Go 1.27.0 (depends on 1) — DoD: Dockerfile build stage and CI
      config both reference Go 1.27.0; a grep for the old "1.24"
      version string in build-related files returns no hits.
- [ ] 3. Build the full module and fix any compile/`go vet ./...`
      breaks surfaced by the new toolchain (depends on 1) — DoD: `go
      build ./...` and `go vet ./...` both succeed with zero errors and
      zero new warnings versus the 1.24 baseline.
- [ ] 4. Run the full existing test suite against the upgraded
      toolchain (depends on 3) — DoD: all existing tests, including the
      table-driven tests for the 9 builtin Go skills, pass unmodified.
- [ ] 5. Rebuild and smoke-test the container image locally (exercise
      `/healthz`, `/readyz`, and one skill diagnose path) (depends on
      2, 4) — DoD: image builds, health endpoints return 200, at least
      one end-to-end ticket→skill-match→diagnose flow completes as
      before.
- [ ] 6. Deploy via the normal ArgoCD sync path for
      `admins-mctl-agent` and confirm health/sync status post-deploy
      (depends on 5) — DoD: ArgoCD Application shows health=Healthy,
      syncStatus=Synced on the new revision; `mctl_list_incidents` for
      admins/mctl-agent still returns 0 in the 24h following rollout.
- [ ] 7. Update `context/current-version.md` bump note (owner: agent
      maintainer, outside `context/` write-lock for spec-writer — flag
      for manual update, not performed by this proposal's tasks)
      (depends on 6) — DoD: noted as a follow-up, not a spec-writer
      deliverable.

## Tests
- [ ] T1. `go build ./...` succeeds under Go 1.27.0.
- [ ] T2. `go vet ./...` reports no new findings versus the Go 1.24
      baseline.
- [ ] T3. Full existing unit/table-driven test suite passes unchanged
      (`go test ./...`).
- [ ] T4. Manual/CI smoke test: outbound TLS calls to the Anthropic API
      and GitHub API succeed (or, in a sandboxed test, TLS handshake
      against a local test server using TLS 1.3 succeeds without
      regression).
- [ ] T5. Container image builds successfully with the updated base
      image and starts up cleanly (`/healthz` returns 200 within
      normal startup time).

## Rollback
Revert the `go.mod` `go`/`toolchain` directive change and the
Dockerfile/CI Go-version pin back to 1.24 in a single revert commit;
redeploy the previous known-good image tag through ArgoCD (sync to the
prior revision). No data migration was performed, so no data-level
rollback is needed — this is purely a build/toolchain revert.
