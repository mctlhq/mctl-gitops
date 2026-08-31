# Tasks: issue-101-go-1-25-13-bump-dockerfile-go-mod-toolch

- [ ] 1. Bump `go.mod`'s `go` directive from `1.25.0` to `1.25.13`
      (`go.mod:3`); run `go mod tidy` to regenerate `go.sum` if any
      transitive checksum lines change. — DoD: `go.mod` reads `go
      1.25.13`; `go build ./...`, `go vet ./...`, and `go test ./...` all
      pass with no new errors or warnings attributable to the version bump.

- [ ] 2. Resolve the digest for `golang:1.25.13-alpine` and update
      `Dockerfile:1` from `FROM golang:1.26-alpine AS builder` to `FROM
      golang:1.25.13-alpine@sha256:<resolved-digest> AS builder` (depends on
      1, so the pinned version matches the go.mod line). — DoD: `Dockerfile`
      line 1 has an explicit `golang` version matching go.mod's `go`
      directive and is pinned with `@sha256:...`; `docker build .` (or the
      project's `make` build target, if one wraps it) succeeds and produces
      a working `/usr/local/bin/mctl-agent` binary.

- [ ] 3. Update README.md's Tech Stack table (`README.md:37-38`) and
      Prerequisites bullet (`README.md:79`) to state `Go 1.25.13` (table)
      / `Go 1.25+` (prerequisites) and `go-chi/chi v5.3.1`, matching go.mod
      (depends on 1). — DoD: `grep` for `Go 1.24` and `chi v5.2.1` in
      README.md returns no matches; the stated versions equal go.mod's `go`
      directive and the `github.com/go-chi/chi/v5` require line.

- [ ] 4. Run `govulncheck ./...` locally (or via a scratch CI run) against
      the bumped module and confirm 0 reachable vulnerabilities (depends on
      1, 2). — DoD: govulncheck output shows no reachable findings for the
      27 stdlib vulnerabilities cited in the issue.

- [ ] 5. Remove `continue-on-error: true` from the `govulncheck` step in
      `.github/workflows/security.yml:33`, and replace the stale comment at
      lines 30-32 ("current Go 1.24 patch line...") with a short note that
      the job is fail-closed as of the 1.25.13 bump (depends on 4 passing
      clean). — DoD: the govulncheck step in `security.yml` has no
      `continue-on-error` field; a PR run of the `security` workflow's
      `govulncheck` job completes green (exit 0) against the bumped module.

## Tests

- [ ] T1. `go build ./...` and `go vet ./...` succeed against `go.mod`'s new
      `go 1.25.13` directive with no source changes required.
- [ ] T2. `go test ./...` passes unchanged (no test relies on Go-version-
      specific behavior between 1.25.0 and 1.25.13).
- [ ] T3. `govulncheck ./...` reports 0 reachable vulnerabilities after
      tasks 1-2.
- [ ] T4. `docker build .` against the updated Dockerfile succeeds, and the
      resulting image's `go version` (inspected via a throwaway `docker run
      --entrypoint go <builder-stage-tag> version` against the builder
      stage, or `docker run <final-image> mctl-agent --version` if the
      binary reports its build toolchain) matches `1.25.13`.
- [ ] T5. `grep -Rn "Go 1.24\|chi v5.2.1" README.md` returns no matches
      after task 3.
- [ ] T6. A full `security.yml` workflow run (PR trigger) shows the
      `govulncheck` job passing without `continue-on-error` masking any
      failure.

## Rollback

- All changes are confined to `go.mod`/`go.sum`, `Dockerfile`, `README.md`,
  and `.github/workflows/security.yml` — no database migration, no runtime
  config, no API contract change.
- If the 1.25.13 bump breaks the build or test suite, or if the digest-pinned
  base image fails to build: `git revert` the single commit/PR that lands
  these changes. `go.mod`'s `go` directive reverts to `1.25.0`, `Dockerfile`
  reverts to the floating `golang:1.26-alpine` line, and README/CI revert to
  their prior (stale but functioning) state.
- If only the CI fail-closed flip (task 5) proves too aggressive (e.g. a new
  vuln lands upstream between merge and the next scan and blocks unrelated
  PRs), the narrower rollback is to re-add `continue-on-error: true` to the
  `govulncheck` step alone, without reverting the version bump itself, and
  file a follow-up incident/issue for the new finding.
- No deployed-service rollback path is needed beyond the normal image
  rollback (`mctl_rollback_service` / previous GHCR tag) if a bad image
  somehow reaches production — this proposal does not change any runtime
  behavior of the built binary, only its build inputs.
