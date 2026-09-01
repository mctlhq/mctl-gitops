# Tasks: issue-199-go-1-26-6-toolchain-bump-dockerfile-dige

- [ ] 1. Bump `go.mod` Go version from `go 1.26.0` to `go 1.26.6` (`go.mod:3`)
      and run `go mod tidy`. — DoD: `go.mod` declares `go 1.26.6`; `go mod
      tidy` runs clean with no diff churn beyond expected stdlib-adjacent
      metadata; `git diff go.sum` reviewed for sanity (no unexpected
      unrelated dependency drops).

- [ ] 2. **DROPPED at approval — do not do this here.** The
      `k8s.io/client-go` ↔ `k8s.io/apimachinery` alignment moves to its own
      issue and its own PR. Leave `k8s.io/client-go v0.36.1`,
      `k8s.io/api v0.36.1` and `k8s.io/apimachinery v0.36.3` exactly as they
      are; `go mod tidy` in task 1 must not be used as cover for bumping
      them. If tidy tries to move a `k8s.io/*` line on its own, stop and say
      so in the PR rather than letting it through.
      — DoD: `git diff go.mod` shows a changed `go` directive and nothing
      else in the `k8s.io/*` block.

- [ ] 3. Build and test against the updated toolchain/deps (depends on 2) —
      run `go build ./...` and `go test -p 1 ./...` (matching the `-p 1`
      flag `validate.yml`'s `test` job uses for the Postgres-backed
      `internal/alerts`/`internal/api` packages) locally or in a scratch CI
      run. — DoD: both commands exit 0. With task 2 dropped there is no
      dependency change to break a call site, so a failure here means the
      toolchain bump itself broke something and must be investigated, not
      worked around.

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

- [ ] 6a. **Pin govulncheck itself** in the same job — change
      `go install golang.org/x/vuln/cmd/govulncheck@latest` to a pinned
      release (`@v1.7.0`, the version whose 2026-08-27 DB produced this
      issue's findings), with a comment giving the version and why it is
      pinned. — DoD: no `@latest` remains in the job.
      **Why this is not optional once task 6 lands.** While the job was
      `continue-on-error`, a surprise from `@latest` cost nothing. Fail-closed,
      `@latest` means an upstream govulncheck release can turn every PR in
      this repo red with no change on our side, and it makes the gate's
      behaviour unreproducible between two runs of the same commit.
      Note the distinction and do not "fix" it the other way: the
      **vulnerability database** must keep floating — new CVEs failing the
      build is the entire point of task 6 — it is the **tool binary** that
      gets pinned. govulncheck fetches the DB at run time, so pinning the
      binary does not freeze the data.

- [ ] 6b. State plainly in the PR description that removing
      `continue-on-error` makes the **job** fail, which is not the same as
      making the **merge** fail. Whether `govulncheck` blocks a merge depends
      on it being configured as a required status check in the repo ruleset,
      which is a settings change outside this repo's files and outside this
      issue. — DoD: the PR says which of the two this change delivers, so no
      reviewer reads "fail-closed" as "cannot be merged past". If it is not
      currently required, file a follow-up rather than implying it is.

- [ ] 7. Full CI verification (depends on 1-6) — open the PR and confirm
      `validate.yml` (lint + test), `security.yml` (govulncheck + trivy),
      and any image-build step all pass end to end. — DoD: all required
      checks green on the PR; no `continue-on-error` remaining on the
      govulncheck job in the merged workflow file.

## Tests
- [ ] T1. `go build ./...` succeeds against the Go 1.26.6 toolchain with
      the `k8s.io/*` dependency set **unchanged**.
- [ ] T2. `go test -p 1 ./...` passes (full existing suite, unchanged
      assertions — this is a dependency/toolchain bump, not a behavior
      change, so no test logic should need editing).
- [ ] T3. `govulncheck ./...` reports 0 reachable vulnerabilities against
      the updated toolchain and dependency set.
- [ ] T4. `docker build .` succeeds using the digest-pinned
      `golang:1.26.6-alpine@sha256:...` builder stage, and the resulting
      image runs (`docker run --rm <image> mctl-api --help` or equivalent
      smoke invocation) without a missing-binary or exec-format error.
- [ ] T5. **Prove the gate by mutation, not by a green run.** On a scratch
      branch, set `go.mod` back to `go 1.26.0`, push, and confirm the
      `govulncheck` job **fails**; then restore 1.26.6 and confirm it
      passes. Record both run URLs in the PR description. A green run on a
      clean tree proves only that the job ran — it cannot distinguish a
      working gate from one that would pass on anything, which is exactly
      the failure this issue exists to correct. (Drop the `act` suggestion:
      it neither reproduces `setup-go`'s `go-version-file` resolution nor
      the network fetch of the vulnerability DB, so a green `act` run would
      prove less than the push does.)

## Rollback
This change is fully reversible via `git revert` of the single PR:
- Revert `go.mod`/`go.sum` to restore `go 1.26.0`; run `go mod tidy` to
  confirm the reverted graph still resolves. No `k8s.io/*` version moves in
  this PR, so there is nothing else in the module graph to unwind — which is
  the point of splitting that work out: reverting a CVE fix should never be
  entangled with reverting a dependency alignment.
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
