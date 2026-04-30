# Tasks: go-upgrade-stdlib-cves-v2

- [ ] 1. Update `go.mod` toolchain directive — change the `go` line to
  `go 1.26` and add/update `toolchain go1.26.2`. Run `go mod tidy` and commit
  resulting `go.mod` and `go.sum` changes.
  DoD: `go mod tidy` exits 0; `go.mod` declares `go 1.26` and
  `toolchain go1.26.2`; `go.sum` is consistent; no unrelated module version
  changes are introduced.

- [ ] 2. Update Dockerfile build stage (depends on 1) — replace
  `FROM golang:1.24-alpine AS builder` with
  `FROM golang:1.26.2-alpine AS builder`. Verify the runtime stage requires
  no changes.
  DoD: `docker build` completes successfully; `go version` inside the built
  container reports `go1.26.2`; image size delta is within ±5 MB of the
  previous image.

- [ ] 3. Update CI workflow Go version pins (depends on 1) — change all
  `go-version: '1.24.x'` (or equivalent) entries in CI configuration files
  to `go-version: '1.26.2'`.
  DoD: CI pipeline passes on the feature branch; every `go version` step in
  CI logs reports `go1.26.2`; no jobs are skipped.

- [ ] 4. Run full test suite under Go 1.26.2 and resolve any failures
  (depends on 3) — execute `go test -race ./...`. No test logic may be
  deleted or skipped to force a pass.
  DoD: `go test -race ./...` exits 0 with zero failures and zero data-race
  reports; no test cases removed or marked as skipped relative to the
  Go 1.24 baseline.

- [ ] 5. Add CVE regression tests (depends on 4) — write three targeted
  regression tests:
  (a) TLS 1.3 key-update stress test asserting mctl-api `/healthz` remains
      responsive under repeated `KeyUpdate` messages (CVE-2026-32283).
  (b) OIDC wildcard certificate validation test asserting the OIDC verifier
      rejects a spoofed wildcard cert that would have bypassed validation
      before the fix (CVE-2026-33810).
  (c) `html/template` XSS fuzz case confirming a `<script>` payload injected
      into a template variable is HTML-escaped in rendered output
      (CVE-2026-32289).
  DoD: All three tests are committed under `*_test.go` files; all pass on
  Go 1.26.2; tests (a) and (b) are confirmed to fail or produce measurable
  degradation when run against the Go 1.24 binary, documenting the regression
  baseline.

- [ ] 6. Bump image tag in ArgoCD Helm values and open pull request (depends
  on 2, 5) — update `image.tag` (or equivalent) in the GitOps repository to
  the new go1.26.2-based image digest. Confirm `PodDisruptionBudget`
  (`minAvailable: 1`) is present in the `admins` tenant manifests.
  DoD: PR is open; ArgoCD diff shows only the image tag change; at least one
  reviewer has approved; no changes to `labs` tenant manifests.

- [ ] 7. Staged rollout and observation (depends on 6) — merge the PR and
  monitor the rolling update. Observe CPU, memory, error rate, and p99
  latency for 30 minutes post-deployment.
  DoD: All pods running the new image; `/healthz` returns HTTP 200; p99
  latency is within 10% of the pre-upgrade baseline; no increase in
  error-rate alerts; Prometheus dashboard screenshot attached to the PR.

## Tests

- [ ] T1. Unit — `go test -race ./...` passes on Go 1.26.2 with zero failures
  and zero data-race reports.
- [ ] T2. Integration — existing auth-flow integration tests (GitHub PAT,
  Dex JWT, OAuth JWT paths) pass against the upgraded binary.
- [ ] T3. CVE-2026-32283 regression — TLS 1.3 key-update stress test confirms
  the DoS is not reproducible on Go 1.26.2.
- [ ] T4. CVE-2026-33810 regression — wildcard certificate spoofing test
  confirms the bypass is not possible on Go 1.26.2.
- [ ] T5. CVE-2026-32289 regression — `html/template` XSS fuzz case confirms
  payloads are escaped correctly.
- [ ] T6. Container smoke test — `docker run --rm <image> go version` reports
  `go1.26.2`; `/healthz` returns HTTP 200 within 5 s of startup.
- [ ] T7. Image provenance — CI-generated SBOM (or `go version -m` output) is
  attached to the GitHub release and confirms no Go 1.24.x artefacts remain.

## Rollback

If the upgraded deployment causes elevated error rates, failed liveness probes,
or any on-call alert within the observation window:

1. In the GitOps repository, revert the `image.tag` commit (or open a revert
   PR) to restore the previous Go 1.24-based image digest.
2. ArgoCD detects the drift and syncs automatically (or trigger manually with
   `argocd app sync mctl-api`), rolling the `admins` tenant back to the
   previous image within one rolling-update cycle.
3. The PodDisruptionBudget (`minAvailable: 1`) ensures at least one healthy
   replica serves traffic throughout the rollback.
4. After rollback, open a post-mortem issue capturing the failure mode before
   re-attempting the upgrade. Reference both this proposal and the original
   `go-upgrade-stdlib-cves` proposal for context.

No database migrations, Vault policy changes, or CRD updates are introduced
by this proposal, so rollback is a pure image-tag revert.
