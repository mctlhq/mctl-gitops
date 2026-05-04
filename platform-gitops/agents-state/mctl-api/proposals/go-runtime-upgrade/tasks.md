# Tasks: go-runtime-upgrade

- [ ] 1. Update `go.mod` toolchain directive to Go 1.26.2 — DoD: `go.mod` contains `go 1.26.2`; `go mod tidy` completes without error and produces a clean `go.sum`; no `replace` directives pointing at stdlib packages are present.

- [ ] 2. Update CI Dockerfile builder stage to `golang:1.26.2-alpine` (depends on 1) — DoD: The Dockerfile `FROM` line in the builder stage references `golang:1.26.2-alpine` (or the equivalent distroless/chainguard image pinned by digest); the image builds successfully in CI.

- [ ] 3. Verify full compilation and unit-test suite under Go 1.26.2 (depends on 1, 2) — DoD: `go build ./...` exits 0; `go test ./...` exits 0 with no test failures or race-detector errors (`-race` flag enabled); no new `go vet` warnings introduced.

- [ ] 4. Add `govulncheck` step to CI pipeline (depends on 2) — DoD: The CI workflow runs `govulncheck ./...` after the build step; the step is configured to fail the pipeline on any finding; the step passes (zero findings for CVE-2026-32280, 32281, 32283, 27143, 32289).

- [ ] 5. Add a CI toolchain-version guard (depends on 1) — DoD: The CI pipeline includes a step that parses `go.mod` and fails if the declared Go version is below `1.26.0`; this prevents accidental downgrade via a revert or merge conflict resolution.

- [ ] 6. Build and push the new container image (depends on 3, 4) — DoD: A container image tagged `mctl-api:4.14.1-go1.26.2` (or the next patch tag per versioning policy) is pushed to the registry; `docker run --rm <image> /mctl-api --version` confirms the binary reports Go 1.26.2 in its build info.

- [ ] 7. Open mctl-gitops PR to update the admins tenant image tag (depends on 6) — DoD: The gitops PR updates the `image.tag` value for the `admins/mctl-api` deployment to the new image; the PR description references this proposal and lists the five CVEs closed.

- [ ] 8. Observe ArgoCD rollout and confirm service health (depends on 7) — DoD: ArgoCD reports `Synced / Healthy` for the `admins/mctl-api` application after the rolling update completes; `/healthz` returns HTTP 200; at least one authenticated REST request and one MCP tool call succeed in the post-deploy smoke test.

## Tests

- [ ] T1. Unit tests pass under Go 1.26.2 with `-race` flag — run `go test -race ./...` in CI; zero failures and zero race conditions reported.
- [ ] T2. `govulncheck ./...` reports zero findings for the five target CVEs — verified as part of task 4; output captured as a CI artifact.
- [ ] T3. Binary build-info check — `go version -m <binary>` output contains `go go1.26.` prefix; verified in the image-build CI step (task 6).
- [ ] T4. OIDC JWT verification smoke test — a synthetic JWT signed by the Dex test issuer is verified successfully via the `/api/v1/whoami` endpoint in the staging environment; no timeout or error attributed to crypto/x509 chain building.
- [ ] T5. Concurrent TLS load test — a 60-second `hey` or `k6` run at 50 concurrent connections against `https://api.mctl.ai/healthz` (staging) completes with zero connection resets or hung goroutines; confirms CVE-2026-32283 deadlock is not reproducible.
- [ ] T6. Outbound TLS dial regression test — mctl-api in staging successfully dials Vault, ArgoCD, and Backstage (verified via `GET /api/v1/services` which exercises the Backstage catalog path and Vault secret resolution); all return expected data.
- [ ] T7. govulncheck gate enforcement test — introduce a synthetic `go.mod` entry with a known-vulnerable module version in a branch; confirm the CI pipeline fails at the govulncheck step (validates the gate works, then revert).

## Rollback

If the rollout introduces a production regression after ArgoCD sync:

1. In mctl-gitops, revert the image tag commit to the previous value (`mctl-api:4.14.0` or whatever was deployed before) and merge immediately. ArgoCD will detect the drift and re-sync within its configured poll interval (typically 3 minutes), or trigger a manual sync via the ArgoCD UI.
2. The previous Go 1.24-based image remains in the container registry and is immediately available; no rebuild is required.
3. If the gitops revert itself is blocked, use `kubectl set image deployment/mctl-api mctl-api=<registry>/mctl-api:4.14.0 -n admins` as a break-glass measure to restore the previous image directly, then follow up with the gitops revert to restore desired-state consistency.
4. After rollback, open a post-mortem issue documenting the regression before re-attempting the upgrade. The five CVEs remain open until the upgrade is re-applied; treat the service as elevated-risk and apply compensating controls (rate limiting, WAF inspection of OIDC paths) in the interim.
