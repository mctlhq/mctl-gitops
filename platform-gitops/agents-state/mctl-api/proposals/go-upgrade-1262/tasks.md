# Tasks: go-upgrade-1262

- [ ] 1. Update `go.mod` — change the `go` directive from `go 1.24` to `go 1.26.2` and run `go mod tidy` to reconcile the module graph. — DoD: `go.mod` and `go.sum` are committed, `go mod verify` passes, and `go build ./...` succeeds locally with Go 1.26.2.

- [ ] 2. Update the Dockerfile (depends on 1) — replace `FROM golang:1.24` (or equivalent Alpine variant) with `FROM golang:1.26.2` in every stage that compiles the service. — DoD: `docker build` produces an image where `go version` inside the builder layer reports `go1.26.2`; the final image passes a smoke-start (`/mctl-api --version` or equivalent).

- [ ] 3. Update CI pipeline toolchain pin (depends on 1) — change the `go-version` input (GitHub Actions `setup-go` step or equivalent) to `1.26.2`. — DoD: CI configuration is committed and a triggered CI run completes the build stage successfully on Go 1.26.2.

- [ ] 4. Add `govulncheck` step to CI (depends on 3) — install `golang.org/x/vuln/cmd/govulncheck` at a pinned version and run `govulncheck ./...` as a required CI check. Configure it to fail on any finding with severity >= HIGH. — DoD: The CI step runs, reports zero findings for the ten CVEs listed in this proposal, and the step is marked required (blocks merge).

- [ ] 5. Emit runtime version at startup (depends on 1) — add a single `log.Info("runtime", "go_version", runtime.Version())` call (or equivalent structured-log statement) in `main.go` at service initialization. — DoD: A local run of the binary produces a log line containing `go1.26.2` at INFO level; unit test or log-output assertion confirms the line is present.

- [ ] 6. Deploy to `admins` staging/preview environment (depends on 2, 3) — trigger an ArgoCD sync against the staging Application pointing at the new image tag. — DoD: The pod comes up healthy, readiness probe passes, startup log shows `go1.26.2`, no error-level log lines from `crypto/tls` or `crypto/x509`.

- [ ] 7. Deploy to `admins` production (depends on 6) — promote the image tag in the ArgoCD production Application manifest and sync. — DoD: All production pods are running the new image, health checks pass for at least 15 minutes post-sync, and no elevated error rate is observed in Prometheus metrics.

## Tests

- [ ] T1. Unit tests — `go test ./...` passes with zero failures and zero new `go vet` warnings on Go 1.26.2.
- [ ] T2. OIDC JWT validation path — integration test authenticates against the Dex endpoint using a valid JWT over TLS; the request completes within the normal SLA with no TLS errors.
- [ ] T3. Vault mTLS authentication — integration test triggers a Vault `auth/kubernetes` login; a token is returned successfully and no `crypto/tls` errors appear in logs.
- [ ] T4. Concurrent TLS load — send 200 concurrent HTTPS requests to `/healthz` or a read MCP tool endpoint; verify zero connection resets or deadlock-related errors (specifically targeting CVE-2026-32283 regression).
- [ ] T5. govulncheck clean — `govulncheck ./...` on the compiled binary reports zero findings for CVE-2026-32280, CVE-2026-32281, CVE-2026-32283, CVE-2026-32289, CVE-2026-27140, CVE-2026-27143, CVE-2026-27144, CVE-2026-32282, CVE-2026-32288, CVE-2026-33810.
- [ ] T6. Startup log assertion — confirm the production pod logs contain a line with `go1.26.2` within 30 seconds of pod start.
- [ ] T7. Prometheus metrics endpoint — `/metrics` responds with HTTP 200 and a non-empty body after upgrade, confirming no metrics regression.

## Rollback
If the upgrade causes a regression at any stage:

1. **CI / build failure (tasks 1-4):** Revert the `go.mod`, `go.sum`, Dockerfile, and CI config changes via a revert commit. The previous Go 1.24 image remains in the container registry and is unaffected.

2. **Staging failure (task 6):** Point the ArgoCD staging Application manifest back to the previous image tag and sync. No database or secret changes were made, so no state rollback is needed.

3. **Production failure (task 7):** Update the ArgoCD production Application manifest image tag to the last known-good tag and trigger a sync. ArgoCD will perform a rolling replacement of pods back to the Go 1.24-based image. The rollback should complete within one standard Kubernetes rolling-update window (typically under 3 minutes given the service's replica count). After rollback, open a new incident, capture logs from the failed pods, and file a follow-up task before re-attempting the upgrade.

Note: because this proposal makes no schema, secret, or manifest changes beyond the image reference, rollback carries no data-loss risk.
