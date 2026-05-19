# Design: issue-71-test-smoke-test-log-build-version-git-sh

## Current state

### Server entry point
`cmd/server/main.go` is the only binary addressed by this issue. Its `main()`
function already emits a structured startup log line (lines 48-55):

```go
slog.Info("starting",
    "auth_mode", cfg.AuthMode,
    "auth_required", cfg.AuthRequired,
    "allow_send", cfg.AllowSend,
    "mcp_path", cfg.MCPPath,
    "addr", cfg.Addr,
    "telegram_configured", cfg.TGAPIID != 0 && cfg.TGAPIHash != "",
)
```

There is no `version` or `commit` field in this call, and no package-level
variables declared to hold build-time values.

### Dockerfile ldflag wiring
`Dockerfile` already threads a build-arg through to the linker for the server
binary (lines 10-13):

```dockerfile
ARG APP_VERSION=dev
RUN CGO_ENABLED=0 GOOS=linux \
    go build -ldflags="-s -w -X main.version=${APP_VERSION}" \
    -o /mctl-telegram ./cmd/server && \
```

The flag `-X main.version=${APP_VERSION}` targets a package-level symbol
`main.version`, but that symbol does not exist anywhere in `cmd/server/main.go`
today. The linker silently discards an `-X` flag that names an undefined symbol,
so the flag is a no-op until the variable is declared.

No `-X main.commit` flag is present anywhere in the repository.

### Local daemon (out of scope)
`cmd/local/main.go` uses `const version = "0.6.0"` — a hardcoded constant that
is not injected via ldflags. This binary is out of scope for the issue.

### CI pipeline
`.github/workflows/build.yml` runs `go build ./...` and `docker build` for
every PR but does not pass `APP_VERSION` or any commit arg to either step.
The release workflow (`.github/workflows/release-please.yml`) dispatches to
`mctlhq/mctl-gitops` where the release-deploy job presumably passes the image
tag as the version; the SHA wiring is TBD in that repo.

## Proposed solution

### 1. Declare ldflag variables in `cmd/server/main.go`
Add two package-level variables immediately after the `package main` declaration:

```go
// version and commit are set at build time via -ldflags.
// Defaults keep local `go run` output recognisable.
var (
    version = "dev"
    commit  = "none"
)
```

The declared defaults ("dev" / "none") are used whenever the binary is built
without ldflags — `go run`, `go test ./...`, or a plain `go build`.

### 2. Extend the existing startup log call
Append `version` and `commit` fields to the existing `slog.Info("starting", ...)`
call so the change is a minimal diff to a single call site:

```go
slog.Info("starting",
    "version", version,
    "commit", commit,
    "auth_mode", cfg.AuthMode,
    ...
)
```

Placing them first in the argument list makes them the leftmost fields in the
rendered JSON object, matching operator expectations (most important fields
first).

### 3. Wire commit SHA into the Dockerfile
Extend the Dockerfile to accept and forward an `APP_COMMIT` build-arg
alongside the existing `APP_VERSION`:

```dockerfile
ARG APP_VERSION=dev
ARG APP_COMMIT=none
RUN CGO_ENABLED=0 GOOS=linux \
    go build -ldflags="-s -w -X main.version=${APP_VERSION} -X main.commit=${APP_COMMIT}" \
    -o /mctl-telegram ./cmd/server && \
```

The `APP_COMMIT` default of `"none"` ensures that builds that do not supply
the arg (e.g., the current PR Docker job) continue to produce a valid binary.

### Resulting log line (production build)
```json
{"time":"2026-05-19T08:00:00Z","level":"INFO","msg":"starting",
 "version":"1.4.2","commit":"a3f9c12",
 "auth_mode":"local-jwt","auth_required":true,...}
```

### Resulting log line (local dev / CI without args)
```json
{"time":"...","level":"INFO","msg":"starting",
 "version":"dev","commit":"none",
 "auth_mode":"local-dev",...}
```

## Alternatives

### A. Use `runtime/debug.ReadBuildInfo()` for the SHA
Go 1.18+ embeds `vcs.revision` and `vcs.time` into binaries when the build
runs inside a VCS checkout. The SHA could be read at startup via
`debug.ReadBuildInfo()` without any ldflag.

Dropped because: the Docker build uses `COPY . .` with no `.dockerignore`
today, so `.git` is included in the build context — but that is fragile. Any
future `.dockerignore` addition, a shallow clone, or a source-only tarball
export silently reverts the SHA to an empty string. The explicit ldflag
approach matches the pattern already established for `APP_VERSION` and keeps
the wiring visible in the Dockerfile.

### B. Expose version via a dedicated `/version` endpoint
A JSON endpoint `GET /version` returning `{"version":"...","commit":"..."}` is
common in services. The issue explicitly excludes new endpoints ("No new
endpoints, no behaviour change"), so this option is out of scope.

### C. Add a separate `buildinfo` internal package
A standalone `internal/buildinfo` package with exported `Version` and `Commit`
variables would make the values accessible to any package (e.g., future
`/version` endpoint). The overhead of a new package is not justified for a
single log call. If a `/version` endpoint is added later, extracting the
variables into a `buildinfo` package is a natural follow-up.

## Platform impact

- **Migrations**: none. This is a pure logging change.
- **Backward compatibility**: the existing `slog.Info("starting", ...)` log
  line gains two new fields. Any log parser that already captures this line
  will see additional structured fields. Strict schema parsers that reject
  unknown fields would break, but the project emits free-form JSON slog output
  and no such parser is in use.
- **Resource impact**: negligible — two string variables added to the data
  segment of the binary.
- **Risk**: low. The only failure mode is a build-arg name collision if
  `APP_COMMIT` is already used for another purpose in `mctl-gitops`; the
  implementer should verify before merging.
- **Rollback**: revert the single commit. The log line loses the two fields;
  no data is lost and no migration is required.
