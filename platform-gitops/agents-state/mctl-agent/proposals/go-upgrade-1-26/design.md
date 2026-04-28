# Design: go-upgrade-1-26

## Current state

According to `context/architecture.md` and `context/current-version.md`, mctl-agent v1.5.0
is built with **Go 1.24**. In `go.mod` the directive `go 1.24` is set, the Dockerfile uses
the base image `golang:1.24`. Go is a single-binary application without CGO (pure-Go
SQLite via modernc.org). The current stable release is **Go 1.26.2** (2026-04-07).

## Proposed solution

Minimal changes in three places:

1. **`go.mod`**: change the directive `go 1.24` → `go 1.26.2`.
2. **`Dockerfile`** (build stage): replace `FROM golang:1.24` → `FROM golang:1.26.2-alpine`
   (or `-bookworm` if Debian is used).
3. **CI workflow** (if the Go version is pinned explicitly, e.g. in `.github/workflows/*.yml`
   or in an ArgoCD ApplicationSet): update the `go-version` field.

Run `go mod tidy` — confirm there are no incompatibilities with dependencies.
Run a full `go test ./...`.

Go guarantees backward compatibility for code, so no application-logic changes are expected.
Green Tea GC is enabled automatically — no env variables needed.

## Alternatives

| Option | Why dropped |
|---|---|
| Stay on the Go 1.24 patch series | Go does not provide LTS patches for retired minor versions; security fixes are backported only to the current minor. 1.24.x no longer receives security updates. |
| Upgrade to Go 1.25 | Skipped because 1.25 is no longer current. 1.26.2 is the current stable. There is no point in an extra hop. |
| Update only CI, not the Dockerfile | The build image in production stays vulnerable; a single version is needed everywhere. |

## Platform impact

- **Migration**: only build configuration files (go.mod, Dockerfile, CI YAML).
  Application code is unchanged.
- **Backward compatibility**: the Go 1 compatibility promise guarantees full compatibility.
- **Resource impact**: Green Tea GC reduces GC overhead by 10–40% — memory consumption
  does not grow. Neutral for the `labs` tenant (close to its memory limit).
- **Risks and mitigations**: minimal. Risk — a rare toolchain change breaks the build.
  Mitigation — `go test ./...` in CI before merge. Rollback — revert go.mod + Dockerfile.
