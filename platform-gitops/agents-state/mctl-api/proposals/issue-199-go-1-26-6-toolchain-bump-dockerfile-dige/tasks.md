# Tasks: issue-199-go-1-26-6-toolchain-bump-dockerfile-dige

- [ ] 1. Bump `go.mod` Go version from `go 1.26.0` to `go 1.26.6` (`go.mod:3`)
      and run `go mod tidy`. — DoD: `go.mod` declares `go 1.26.6`; `go mod
      tidy` runs clean with no diff churn beyond expected stdlib-adjacent
      metadata; `git diff go.sum` reviewed for sanity (no unexpected
      unrelated dependency drops).

- [ ] 2. Align `k8s.io/client-go` with `k8s.io/apimachinery` (depends on 1)
      — bump the `k8s.io/client-go v0.36.1` require line in `go.mod` to a
      version compatible with `k8s.io/apimachinery v0.36.3` (or bump both to
      the latest mutually-compatible pair), then `go mod tidy` again to
      reconcile `k8s.io/api` and indirect `k8s.io/*`/`sigs.k8s.io/*` lines.
      — DoD: `go.mod`'s `k8s.io/client-go` and `k8s.io/apimachinery` versions
      are from the same aligned release line; `go mod tidy` produces a
      clean `go.sum`.

- [ ] 3. Build and test against the updated toolchain/deps (depends on 2) —
      run `go build ./...` and `go test -p 1 ./...` (matching the `-p 1`
      flag `validate.yml`'s `test` job uses for the Postgres-backed
      `internal/alerts`/`internal/api` packages) locally or in a scratch CI
      run. — DoD: both commands exit 0; any `k8s.io/client-go` API breakage
      surfaced by the bump in step 2 is fixed in this same task, not
      deferred.

- [ ] 4. Run `govulncheck ./...` against the updated toolchain/deps (depends
      on 3) — DoD: output reports 0 reachable vulnerabilities. If any of the
      25 previously-reported findings remain, identify the minimal
      additional dependency bump needed and apply it, then re-run until
      clean.

- [ ] 5. Resolve and pin the Dockerfile builder image digest — resolve the
      current manifest digest for `golang:1.26.6-alpine` (e.g. `docker
      pull golang:1.26.6-alpine && docker inspect --format='{{index
      .RepoDigests 0}}' golang:1.26.6-alpine`, or `crane digest
      golang:1.26.6-alpine`) and update `Dockerfile:1` from
      `FROM golang:1.26-alpine AS builder` to
      `FROM golang:1.26.6-alpine@sha256:<resolved-digest> AS builder`, with
      a comment recording the resolution date. — DoD: `Dockerfile:1`
      contains a `@sha256:` pinned reference to `golang:1.26.6-alpine`;
      `docker build .` succeeds from the pinned digest.

- [ ] 6. Flip `security.yml` govulncheck job to fail-closed (depends on 4) —
      remove the `continue-on-error: true` line and its preceding stopgap
      comment from the `govulncheck` job in
      `.github/workflows/security.yml` (lines 22-25 currently). — DoD: the
      job has no `continue-on-error`; a manual/CI run of the workflow on the
      updated branch completes green without the flag.

- [ ] 7. Full CI verification (depends on 1-6) — open the PR and confirm
      `validate.yml` (lint + test), `security.yml` (govulncheck + trivy),
      and any image-build step all pass end to end. — DoD: all required
      checks green on the PR; no `continue-on-error` remaining on the
      govulncheck job in the merged workflow file.

## Tests
- [ ] T1. `go build ./...` succeeds against the Go 1.26.6 / aligned
      `k8s.io/client-go` + `k8s.io/apimachinery` module graph.
- [ ] T2. `go test -p 1 ./...` passes (full existing suite, unchanged
      assertions — this is a dependency/toolchain bump, not a behavior
      change, so no test logic should need editing).
- [ ] T3. `govulncheck ./...` reports 0 reachable vulnerabilities against
      the updated toolchain and dependency set.
- [ ] T4. `docker build .` succeeds using the digest-pinned
      `golang:1.26.6-alpine@sha256:...` builder stage, and the resulting
      image runs (`docker run --rm <image> mctl-api --help` or equivalent
      smoke invocation) without a missing-binary or exec-format error.
- [ ] T5. A dry run of `.github/workflows/security.yml`'s `govulncheck` job
      (e.g. via `act` or a scratch branch push) confirms the job now fails
      the workflow if a reachable vulnerability is (re-)introduced, and
      passes cleanly on the current tree.

## Rollback
This change is fully reversible via `git revert` of the single PR:
- Revert `go.mod`/`go.sum` to restore `go 1.26.0` and the prior
  `k8s.io/client-go`/`k8s.io/apimachinery` versions; run `go mod tidy` to
  confirm the reverted graph still resolves.
- Revert `Dockerfile:1` to `FROM golang:1.26-alpine AS builder`.
- Revert `.github/workflows/security.yml` to restore the
  `continue-on-error: true` line and its comment on the `govulncheck` job.
No data migrations, no running-service state, and no external API contracts
are touched by this change, so rollback carries no data-loss or downtime
risk — worst case is CI going back to informational-only govulncheck and the
image build going back to a floating base tag, i.e. exactly today's state.
If CI fail-closed on govulncheck proves too disruptive immediately after
merge (e.g. a new CVE lands the same week with no available fix), the
narrowest rollback is re-adding `continue-on-error: true` to just that job
(reverting task 6 only) while keeping the toolchain/digest bumps in place.
