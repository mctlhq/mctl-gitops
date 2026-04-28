# Tasks: go-upgrade-stdlib-cves

- [ ] 1. Update `go.mod` toolchain directive — change the `go` line to
  `go 1.26` and add or update `toolchain go1.26.2`. Run `go mod tidy` and
  commit the resulting `go.mod` and `go.sum` changes.
  DoD: `go mod tidy` exits 0; `go.mod` declares `go 1.26`; `go.sum` is
  consistent; no unrelated module version changes are introduced.

- [ ] 2. Update Dockerfile build stage (depends on 1) — replace
  `FROM golang:1.24-alpine AS builder` with `FROM golang:1.26.2-alpine AS
  builder`. Verify the runtime stage requires no changes.
  DoD: `docker build` succeeds locally; `go version` inside the built
  container reports `go1.26.2`; image size delta is within ±5 MB of the
  previous image.

- [ ] 3. Update CI workflow Go version pins (depends on 1) — change all
  `go-version: '1.24.x'` (or equivalent) entries in CI configuration to
  `go-version: '1.26.2'` so test, lint, and build jobs use the same
  toolchain as the production image.
  DoD: CI pipeline passes on the feature branch with no skipped jobs; the
  `go version` step in CI logs shows `go1.26.2`.

- [ ] 4. Run full test suite under Go 1.26.2 and fix any compilation errors
  (depends on 3) — execute `go test -race ./...` and resolve any issues
  introduced by the toolchain change. No test logic may be deleted to make
  tests pass.
  DoD: `go test -race ./...` exits 0; no test cases removed or skipped
  compared to the baseline on Go 1.24.

- [ ] 5. Add CVE-2026-32283 regression test (depends on 4) — write an
  integration test that opens a TLS 1.3 connection to mctl-api and sends
  multiple consecutive `KeyUpdate` messages. Assert that the server remains
  responsive (HTTP 200 on `/healthz`) and that no goroutine leak is detected
  by `goleak` or equivalent.
  DoD: Test is committed under `_test.go`; test passes on Go 1.26.2; test
  is confirmed to fail (or produce measurable degradation) when run against
  the Go 1.24 binary, documenting the regression baseline.

- [ ] 6. Bump image tag in ArgoCD Helm values and open pull request (depends
  on 2, 5) — update the `image.tag` (or equivalent) in the GitOps
  repository to the new Go 1.26.2-based image digest. Ensure the
  `PodDisruptionBudget` (`minAvailable: 1`) is present in the manifest.
  DoD: PR is open; ArgoCD diff shows only the image tag change; at least
  one reviewer has approved; no changes to `labs` tenant manifests.

- [ ] 7. Staged rollout and observation (depends on 6) — merge the PR and
  monitor the rolling update in the `admins` tenant. Observe CPU, memory,
  error rate, and p99 latency for 30 minutes post-deployment.
  DoD: All pods are running the new image; `/healthz` returns 200; p99
  latency is within 10% of the pre-upgrade baseline; no increase in
  error-rate alerts; Datadog/Prometheus dashboard screenshot attached to
  the PR.

## Tests

- [ ] T1. Unit — `go test -race ./...` passes on Go 1.26.2 with zero
  failures and zero data-race reports.
- [ ] T2. Integration — existing auth-flow integration tests (GitHub PAT,
  Dex JWT, OAuth JWT paths) pass against the upgraded binary.
- [ ] T3. CVE regression — TLS 1.3 key-update stress test (task 5) passes,
  confirming CVE-2026-32283 is not reproducible on Go 1.26.2.
- [ ] T4. Container smoke test — `docker run --rm <image> go version` reports
  `go1.26.2`; `/healthz` returns HTTP 200 within 5 s of startup.
- [ ] T5. Image provenance — CI-generated SBOM (or `go version -m` output)
  is attached to the GitHub release and confirms no Go 1.24.x artefacts
  remain in the final image.

## Rollback

If the upgraded deployment causes elevated error rates, failed liveness
probes, or any on-call alert within the observation window:

1. In the GitOps repository, revert the `image.tag` commit (or open a
   revert PR) to restore the previous Go 1.24-based image digest.
2. ArgoCD will detect the drift and sync automatically (or trigger a manual
   sync with `argocd app sync mctl-api`), rolling the `admins` tenant back
   to the previous image within one rolling-update cycle.
3. The `PodDisruptionBudget` (`minAvailable: 1`) ensures at least one
   healthy replica serves traffic throughout the rollback.
4. After rollback, open a post-mortem issue referencing this proposal and
   capturing the failure mode before re-attempting the upgrade.

No database migrations, Vault policy changes, or CRD updates are introduced
by this proposal, so rollback is purely an image-tag revert.
