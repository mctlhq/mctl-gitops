# Tasks: go-1.24-eol-unpatched-cve

- [ ] 1. Decide final target version (1.26.4 floor vs. 1.27.x) and record the decision — DoD:
      short ADR note or PR description states the chosen version and rationale.
- [ ] 2. Update `go.mod`/`go.sum` — change `go 1.24` to the chosen target and pin `toolchain` to
      match; run `go mod tidy` (depends on 1) — DoD: `go version` in CI prints the target version;
      `go mod tidy` exits 0.
- [ ] 3. Resolve any dependency minimum-version conflicts (depends on 2) — DoD: `go build ./...`
      exits 0 with no toolchain mismatch warnings.
- [ ] 4. Update Dockerfile build-stage base image to match the target Go version (depends on 2) —
      DoD: CI Docker build uses the target image; `go version` inside the container matches.
- [ ] 5. Fix any new `go vet` / `staticcheck` warnings surfaced by the newer toolchain (depends on
      3, 4) — DoD: both tools exit 0 with no new suppressions.
- [ ] 6. Run full unit and integration test suite (depends on 5) — DoD: zero new failures
      attributable to the toolchain bump.
- [ ] 7. Run `govulncheck ./...` (depends on 6) — DoD: zero findings for CVE-2026-42507.
- [ ] 8. Load test in staging: sustained load on REST + MCP endpoints, compare Prometheus p50/p99
      latency and GC metrics against the 1.24 baseline (depends on 7) — DoD: p99 latency ≤
      baseline, no error-rate regression.
- [ ] 9. Soak in staging for 24 hours (depends on 8) — DoD: no anomalies in logs or alerts.
- [ ] 10. Promote to production via mctl-gitops → ArgoCD (depends on 9) — DoD: production pod
       reports the target Go version in `/metrics` build-info label; `current-version.md` updated;
       ArgoCD reports `Healthy`/`Synced`.
- [ ] 11. Close the eight superseded prior Go-upgrade proposals (`go-runtime-upgrade`,
       `go-runtime-upgrade-v2`, `go-runtime-cve-dos`, `go-runtime-cve-upgrade`, `go-upgrade`,
       `go-upgrade-1262`, `go-upgrade-stdlib-cves`, `go-upgrade-stdlib-cves-v2`,
       `go-toolchain-ace-cve-27140`) with a note pointing to this proposal (depends on 10) — DoD:
       each proposal has a cross-reference note; no further parallel drafts open for this issue.

## Tests
- [ ] T1. `govulncheck ./...` reports zero findings for CVE-2026-42507.
- [ ] T2. CI guard step fails the build if the toolchain version drops below the agreed target
      (prevents accidental downgrade).
- [ ] T3. Full existing unit + integration test suite passes unmodified.
- [ ] T4. Staging load test: p99 latency and error rate at or better than the Go 1.24 baseline.
- [ ] T5. 24-hour staging soak with no anomalies in logs, memory usage, or connection-pool
      behaviour.

## Rollback
Revert the `go.mod`, `go.sum`, and Dockerfile changes (`git revert <commit-sha>`), rebuild, and
either let ArgoCD auto-sync the reverted image or run `argocd app rollback mctl-api` to the
previous known-good revision. No data or schema changes are introduced, so rollback carries no
data-migration risk — it is a pure code/image revert.
