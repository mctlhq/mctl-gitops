# Tasks: issue-71-test-smoke-test-log-build-version-git-sh

- [ ] 1. Declare `version` and `commit` package-level variables in
  `cmd/server/main.go` — DoD: `var version = "dev"` and `var commit = "none"`
  appear as package-level vars (not consts) immediately after the `package main`
  line; `go build ./cmd/server` compiles without error; the ldflag
  `-X main.version=x` and `-X main.commit=y` overwrite the defaults when
  supplied.

- [ ] 2. Extend the `slog.Info("starting", ...)` call in `cmd/server/main.go`
  to include `version` and `commit` fields (depends on 1) — DoD: the two
  new fields appear first in the argument list of the existing call at
  approximately line 48 of `cmd/server/main.go`; `go vet ./...` passes;
  `go run ./cmd/server` (with a minimal env) prints a JSON line containing
  `"version":"dev"` and `"commit":"none"`.

- [ ] 3. Add `APP_COMMIT` build-arg and extend ldflags in `Dockerfile`
  (depends on 1) — DoD: the builder stage reads `ARG APP_COMMIT=none` and
  passes `-X main.commit=${APP_COMMIT}` alongside the existing
  `-X main.version=${APP_VERSION}` in the `go build` invocation for
  `./cmd/server`; `docker build .` succeeds with default arg values;
  `docker build --build-arg APP_VERSION=1.0.0 --build-arg APP_COMMIT=abc1234 .`
  produces a binary that logs `version=1.0.0 commit=abc1234` on startup.

## Tests

- [ ] T1. Add a unit test in `cmd/server/` (or a new `cmd/server/main_test.go`)
  that confirms the default values: `version == "dev"` and `commit == "none"`.
  This guards against accidental conversion to constants (which cannot be
  overridden by ldflags). DoD: `go test ./cmd/server/...` passes.

- [ ] T2. Verify the Dockerfile smoke-test in CI: the existing
  `.github/workflows/build.yml` `docker` job builds without `APP_COMMIT`
  and succeeds (proving the default arg keeps the build green). No code change
  required for this test — it passes automatically once task 3 is done.

## Rollback
The entire change lives in three locations: two lines added to
`cmd/server/main.go` (var declaration + log fields) and two lines changed in
`Dockerfile` (new ARG + extended ldflags). To roll back:

1. Revert the commit: `git revert <sha>`.
2. The startup log line loses the `version` and `commit` fields.
3. The Dockerfile reverts to its prior single-arg form; no image rebuild side
   effects because the build-arg defaults are "dev" / "none" — no production
   value was ever baked into the Dockerfile itself.
4. No database migrations, no config changes, no infrastructure changes are
   required.
