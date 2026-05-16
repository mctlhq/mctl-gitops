# Tasks: go-toolchain-1263-patch

- [ ] 1. Update `go.mod` — change `go` directive to `1.26.3` and `toolchain` directive to
  `go1.26.3`. — DoD: `go version` inside the module resolves to go1.26.3; `go mod tidy`
  produces no diff.

- [ ] 2. Update CI/CD base image (depends on 1) — change `FROM golang:...` in `Dockerfile`
  and any CI workflow files to `golang:1.26.3-alpine` (or equivalent). — DoD: CI build
  log shows `go version go1.26.3`; image digest pinned in Dockerfile comment.

- [ ] 3. Run full test suite (depends on 2) — execute `go test ./...` with the new
  toolchain in CI. — DoD: all tests green; no new `go vet` warnings introduced.

- [ ] 4. Smoke-test webhook path (depends on 3) — fire a synthetic AlertManager alert at
  `/api/v1/alerts` in staging and verify ticket creation and Telegram notification.
  — DoD: end-to-end alert flow completes without error or latency regression.

- [ ] 5. Update GitOps manifest toolchain annotation (depends on 4) — bump any
  `mctl-agent` ArgoCD Application annotations or ConfigMap values that reference the Go
  version. — DoD: ArgoCD shows the application Synced with new manifest version.

- [ ] 6. Tag and release (depends on 5) — create `v1.5.1` git tag. — DoD: release artifact
  built from go1.26.3; changelog entry references CVE-2026-33814, -39826, -39823,
  -42499/-39820, -42501.

## Tests

- [ ] T1. `go test ./...` passes on go1.26.3 — verifies no stdlib behavior regressions.
- [ ] T2. `govulncheck ./...` reports no known vulnerabilities — confirms CVEs are fixed.
- [ ] T3. HTTP/2 regression test: connect to `/api/v1/alerts` over h2c, send a crafted
  SETTINGS frame with MAX_FRAME_SIZE=0, assert the server returns an error and does not
  hang (CVE-2026-33814 specific test).
- [ ] T4. `go mod verify` succeeds against the module proxy — confirms CVE-2026-42501
  checksum bypass is not exploitable in CI.

## Rollback

Revert the `go.mod` and Dockerfile changes to the previous toolchain version and redeploy.
No database migrations, no API changes, no state to unwind. The rollback is a standard
ArgoCD sync to the previous commit.
