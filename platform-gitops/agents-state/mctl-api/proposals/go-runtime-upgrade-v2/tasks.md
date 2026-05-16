# Tasks: go-runtime-upgrade-v2

- [ ] 1. Update go.mod and go.sum — change `go 1.24` to `go 1.26.3` and `toolchain go1.26.3`;
  run `go mod tidy` to refresh go.sum and surface any dependency minimum-version conflicts.
  DoD: `go version` in CI prints `go1.26.3`; `go mod tidy` exits 0 with no new dependency
  errors; `go.sum` committed.

- [ ] 2. Resolve any dependency minimum-version conflicts (depends on 1) — for each dependency
  that declares `go 1.25+` or higher, run `go get <dep>@latest` and confirm the newer version
  is backward-compatible with mctl-api. DoD: `go build ./...` exits 0 with no `toolchain`
  mismatch warnings.

- [ ] 3. Update Dockerfile build-stage base image (depends on 1) — change `FROM golang:1.24-alpine`
  (or equivalent) to `FROM golang:1.26.3-alpine`. DoD: CI Docker build uses the 1.26.3 image
  and `go version` inside the container prints `go1.26.3`.

- [ ] 4. Fix any new `go vet` / `staticcheck` warnings (depends on 2, 3) — run `go vet ./...`
  and `staticcheck ./...` with the new toolchain; address any newly surfaced issues. DoD: both
  tools exit 0 on the mctl-api codebase with no suppressions added.

- [ ] 5. Run full unit and integration test suite (depends on 4) — execute `go test ./...`
  including DB integration tests. DoD: zero new test failures attributable to the toolchain bump.

- [ ] 6. Load test in staging — 10-minute sustained load at 1 000 RPS on REST + MCP endpoints;
  compare Prometheus p50/p99 latency and GC metrics against Go 1.24 baseline (depends on 5).
  DoD: p99 latency ≤ baseline; no error-rate regression; GC pause reduction visible in
  `go_gc_pauses_seconds` histogram.

- [ ] 7. Observe staging for 24 hours (depends on 6) — leave the upgraded image running;
  confirm no memory leaks, connection-pool anomalies, or TLS handshake errors. DoD: all
  Prometheus alert rules silent; no anomalies in logs.

- [ ] 8. Promote to production (depends on 7) — merge PR, let ArgoCD apply the image.
  DoD: production pod reports Go 1.26.3 in the `/metrics` build-info label; health check green.

## Tests

- [ ] T1. **CVE-2026-27140 CI guard** — add a CI step that checks `go env GOVERSION` equals
  `go1.26.3` (or higher) and fails the build if not, preventing accidental downgrade.

- [ ] T2. **TLS deadlock regression (CVE-2026-32283)** — confirm the existing TLS integration
  tests pass; optionally add a test sending a crafted post-handshake record with multiple
  key-update messages and asserting the connection is closed with an error (not a hang).

- [ ] T3. **HTTP/2 DoS regression (CVE-2026-33814)** — confirm the MCP streaming integration
  tests pass; optionally add a test sending SETTINGS_MAX_FRAME_SIZE=0 and asserting the
  connection is terminated cleanly.

- [ ] T4. **GC baseline comparison** — record `go_gc_pauses_seconds_bucket` before and after
  upgrade in staging; assert p99 pause time does not regress.

## Rollback
1. Revert the `go.mod`, `go.sum`, and Dockerfile changes: `git revert <commit-sha>`.
2. Rebuild the image with the reverted toolchain.
3. ArgoCD will detect the new image digest and redeploy automatically if the previous image
   is still cached; otherwise trigger a manual sync from the previous known-good image tag.
4. If already in production: `argocd app rollback mctl-api` to the previous revision.
