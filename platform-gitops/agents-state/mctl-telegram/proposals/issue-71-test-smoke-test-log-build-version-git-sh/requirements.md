# Startup build-version log line

## Context
Operators running `mctl-telegram` in Kubernetes have no easy way to confirm
which exact build a pod is executing without exec-ing into the container. A
single structured log line emitted at startup that includes the semantic
version and git commit SHA would let operators correlate pod logs with the
release tag and source revision in seconds.

The change is intentionally minimal: no new endpoints, no runtime behaviour
change, no additional dependencies. It extends the existing `slog.Info`
startup call that already logs configuration fields (auth mode, address, etc.)
in `cmd/server/main.go`.

## User stories
- AS an operator I WANT to see the running build version and git SHA in the
  first lines of a pod's log SO THAT I can confirm which release is deployed
  without exec-ing into the container.
- AS a developer I WANT local `go run ./cmd/server` to emit a recognisable
  "dev" version string SO THAT startup logs remain meaningful even without
  build-time injection.

## Acceptance criteria (EARS)
- WHEN the server process starts THE SYSTEM SHALL emit exactly one structured
  JSON log line at level INFO containing fields `version` and `commit` before
  the `listening` log line.
- WHEN the binary is built with `-X main.version=<semver>` and
  `-X main.commit=<sha>` ldflags THE SYSTEM SHALL log the injected values in
  the `version` and `commit` fields respectively.
- WHEN the binary is built without version or commit ldflags THE SYSTEM SHALL
  log `version=dev` and `commit=none` as sentinel defaults.
- WHILE the server is starting THE SYSTEM SHALL include the `version` and
  `commit` fields in the same log line that already reports `auth_mode`,
  `allow_send`, `addr`, and related configuration fields (the existing
  `slog.Info("starting", ...)` call in `cmd/server/main.go`).
- IF the `version` ldflag variable is set to an empty string THE SYSTEM SHALL
  log `version=dev` (the declared default).

## Out of scope
- Changes to `cmd/login/main.go` or `cmd/local/main.go`.
- New HTTP endpoints exposing build metadata.
- Reading version/SHA from environment variables at runtime.
- Changes to the `mctl-gitops` deploy pipeline (tracked separately).

## Open questions
- The `mctl-gitops/release-deploy.yaml` workflow must pass `--build-arg
  APP_COMMIT=<sha>` to `docker buildx build` for the `commit` field to show
  a real SHA in production. That workflow lives in a separate repository
  (`mctlhq/mctl-gitops`) and is out of scope for this proposal. The
  implementer should note this dependency in the PR description.
- The PR build job in `.github/workflows/build.yml` does not pass
  `APP_VERSION` to the Docker job either. Whether to add `APP_VERSION` and
  `APP_COMMIT` args there as well (pointing to the branch HEAD SHA) is left
  to the implementer's discretion; the functional requirement is satisfied as
  long as release builds carry real values.
