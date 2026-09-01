# Tasks: issue-101-go-1-25-13-bump-dockerfile-go-mod-toolch

**Version target decided at approval: `1.26.6`, not the `1.25.13` in the
directory slug.** The slug is the loop's identifier and is not renamed. See
requirements.md Open questions for the reasoning; do not re-litigate it
during implementation.

- [ ] 1. Bump `go.mod`'s `go` directive from `1.25.0` to `1.26.6`
      (`go.mod:3`); run `go mod tidy` to regenerate `go.sum` if any
      transitive checksum lines change. — DoD: `go.mod` reads `go 1.26.6`;
      `go build ./...`, `go vet ./...`, and `go test ./...` all pass.
      **This is the step that can surface real work.** CI currently runs
      vet/lint on the 1.25 line, so 1.26's analyzer set is new to this
      repo even though the release image already builds on 1.26. If vet or
      the linter reports something new, fix it in this PR and say so in the
      description — do not add a nolint/suppression to keep the diff small,
      and do not fall back to 1.25.13 to make the finding go away. If the
      finding is large enough to deserve its own review, stop and report
      rather than bundling it.

- [ ] 2. Resolve the digest for `golang:1.26.6-alpine` and update
      `Dockerfile:1` from `FROM golang:1.26-alpine AS builder` to `FROM
      golang:1.26.6-alpine@sha256:<resolved-digest> AS builder` (depends on
      1, so the pinned version matches the go.mod line). Record the
      resolution date in a comment. — DoD: `Dockerfile` line 1 has an
      explicit `golang` version matching go.mod's `go` directive and is
      pinned with `@sha256:...`; `docker build .` succeeds and produces a
      working `/usr/local/bin/mctl-agent` binary.

- [ ] 3. Update README.md's Tech Stack table (`README.md:37-38`) and
      Prerequisites bullet (`README.md:79`) to state `Go 1.26.6` (table) /
      `Go 1.26+` (prerequisites) and `go-chi/chi v5.3.1`, matching go.mod
      (depends on 1). — DoD: `grep` for `Go 1.24` and `chi v5.2.1` in
      README.md returns no matches; the stated versions equal go.mod's `go`
      directive and the `github.com/go-chi/chi/v5` require line.

- [ ] 4. Run `govulncheck ./...` locally (or via a scratch CI run) against
      the bumped module and confirm 0 reachable vulnerabilities (depends on
      1, 2). — DoD: govulncheck output shows no reachable findings for the
      27 stdlib vulnerabilities cited in the issue. Record the govulncheck
      version and DB date alongside the output, so the evidence is
      reproducible rather than a bare "it was green".

- [ ] 5. Remove `continue-on-error: true` from the `govulncheck` step in
      `.github/workflows/security.yml:33`, and replace the stale comment at
      lines 30-32 ("current Go 1.24 patch line...") with a short note that
      the job is fail-closed as of the 1.26.6 bump (depends on 4 passing
      clean). — DoD: the govulncheck step in `security.yml` has no
      `continue-on-error` field; a PR run of the `security` workflow's
      `govulncheck` job completes green (exit 0) against the bumped module.

- [ ] 5a. **Pin the govulncheck binary** in the same job — change `go
      install golang.org/x/vuln/cmd/govulncheck@latest` to a pinned release
      (`@v1.7.0`, the version whose 2026-08-27 DB produced this issue's
      findings), with a comment giving the version and why it is pinned. —
      DoD: no `@latest` remains in the job.
      **Why this is not optional once task 5 lands.** While the job was
      `continue-on-error`, a surprise from `@latest` cost nothing.
      Fail-closed, `@latest` means an upstream govulncheck release can turn
      every PR in this repo red with no change on our side, and it makes the
      gate's behaviour unreproducible between two runs of the same commit.
      Note the distinction and do not "fix" it the other way: the
      **vulnerability database** must keep floating — new CVEs failing the
      build is the entire point of task 5 — it is the **tool binary** that
      gets pinned. govulncheck fetches the DB at run time, so pinning the
      binary does not freeze the data.
      (Same decision as mctl-api#199 task 6a in this wave; keep the two
      repos on the same pinned version so a finding in one is reproducible
      in the other.)

- [ ] 5b. State plainly in the PR description that removing
      `continue-on-error` makes the **job** fail, which is not the same as
      making the **merge** fail. Whether `govulncheck` blocks a merge depends
      on it being configured as a required status check in the repo ruleset,
      which is a settings change outside this repo's files and outside this
      issue. — DoD: the PR says which of the two this change delivers, so no
      reviewer reads "fail-closed" as "cannot be merged past". If it is not
      currently required, file a follow-up rather than implying it is.

## Tests
- [ ] T1. `go build ./...` and `go vet ./...` succeed against `go.mod`'s new
      `go 1.26.6` directive. Any new vet finding is reported, not
      suppressed (task 1).
- [ ] T2. `go test ./...` passes unchanged (no test relies on
      Go-version-specific behavior between 1.25.0 and 1.26.6).
- [ ] T3. `govulncheck ./...` reports 0 reachable vulnerabilities after
      tasks 1-2.
- [ ] T4. `docker build .` against the updated Dockerfile succeeds, and the
      builder stage's `go version` (via `docker run --entrypoint go
      <builder-stage-tag> version`) reports `1.26.6` — i.e. assert the
      digest pin actually resolves to the intended toolchain, rather than
      trusting the tag text next to it.
- [ ] T5. `grep -Rn "Go 1.24\|chi v5.2.1" README.md` returns no matches
      after task 3.
- [ ] T6. **Prove the gate by mutation, not by a green run.** On a scratch
      branch, set `go.mod` back to `go 1.25.0`, push, and confirm the
      `govulncheck` job **fails**; then restore 1.26.6 and confirm it
      passes. Record both run URLs in the PR description. A green run on a
      clean tree proves only that the job ran — it cannot distinguish a
      working gate from one that would pass on anything, which is exactly
      the failure this issue exists to correct.

## Rollback

- All changes are confined to `go.mod`/`go.sum`, `Dockerfile`, `README.md`,
  and `.github/workflows/security.yml` — no database migration, no runtime
  config, no API contract change.
- If the bump breaks the build or test suite, or if the digest-pinned base
  image fails to build: `git revert` the single commit/PR that lands these
  changes. `go.mod`'s `go` directive reverts to `1.25.0`, `Dockerfile`
  reverts to the floating `golang:1.26-alpine` line, and README/CI revert to
  their prior (stale but functioning) state.
- Note what the revert restores and what it does not: reverting brings back
  the *floating* `golang:1.26-alpine` tag, so the builder toolchain stays on
  1.26 either way. The revert undoes the pin and the fail-closed gate, not
  the toolchain generation. Do not describe the rollback as "back to 1.25".
- If only the CI fail-closed flip (task 5) proves too aggressive (e.g. a new
  vuln lands upstream between merge and the next scan and blocks unrelated
  PRs), the narrower rollback is to re-add `continue-on-error: true` to the
  `govulncheck` step alone, without reverting the version bump itself, and
  file a follow-up issue for the new finding.
- No deployed-service rollback path is needed beyond the normal image
  rollback (`mctl_rollback_service` / previous GHCR tag) if a bad image
  somehow reaches production — this proposal does not change any runtime
  behavior of the built binary, only its build inputs.
