# Tasks: go-toolchain-bump

- [ ] 1. VERIFY target version: check go.dev/dl for the latest stable patch and whether Go 1.26.10 exists/is current — DoD: verified version recorded in the PR description with the source URL.
- [ ] 2. VERIFY CVE applicability: look up CVE-2026-78661, CVE-2026-97045 and CVE-2026-111943 in the Go vuln DB/NVD and record affected and fixed versions; confirm whether Go 1.24 is affected — DoD: table of CVE, affected range, fixed-in, affected-by-1.24 yes/no (depends on 1).
- [ ] 3. Run `govulncheck ./...` and `govulncheck -mode=binary` on the current deployed binary — DoD: baseline output saved with the PR; reachable findings listed.
- [ ] 4. Capture baseline RSS/CPU of mctl-agent in `admins` — DoD: numbers recorded (read-only metrics inspection).
- [ ] 5. Bump `go.mod` directives, Dockerfile builder image and CI to the verified version (depends on 1, 2, 3) — DoD: build passes locally and in CI.
- [ ] 6. Fix any vet/compile issues from the upgrade (depends on 5) — DoD: `go vet ./...` clean.
- [ ] 7. Re-run `govulncheck` on the new binary (depends on 5) — DoD: no reachable findings for the listed CVEs.
- [ ] 8. Deploy to `admins` through ArgoCD and compare RSS/CPU (depends on 4, 7) — DoD: RSS within 10% of baseline; /healthz and /readyz green; test webhook processed.

## Tests
- [ ] T1. Full `go test ./...` on the new toolchain — all pass including table-driven skill tests.
- [ ] T2. Webhook smoke test: POST sample payload to `/api/v1/alerts` and `/api/v1/telegram` in a non-prod/staging run — 2xx and ticket created.
- [ ] T3. Outbound TLS check to GitHub, Anthropic and Telegram APIs from the new image — handshakes succeed.
- [ ] T4. `govulncheck` gate in CI — fails on reachable vulnerabilities.

## Rollback
Revert the PR (go.mod, Dockerfile, CI) and let ArgoCD sync the previous image tag. No data migration is involved, so rollback is stateless.
