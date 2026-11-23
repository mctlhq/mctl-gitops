# Move toolchain to Go 1.27.4 / 1.26.11 for the net/http MaxBytesReader crash fix

## Context
Go 1.27.4 and 1.26.11 (released 2026-11-10) fix CVE-2026-97054 / GO-2026-6859, an HTTP/1 server crash caused by a header race in `net/http` `MaxBytesReader`. mctl-agent exposes public webhook endpoints (`/api/v1/alerts`, `/api/v1/telegram`, `/mcp`) on chi, so the crash is remotely triggerable. Sources conflict on whether 1.26.11 fully fixes it, so the exact patched release must be verified, not assumed.

The same release carries eleven cgo/toolchain CVEs (CVE-2026-97033 to 97043). They are low risk here because modernc sqlite is pure Go (no CGO). This proposal covers only the delta over earlier toolchain proposals: `go-toolchain-bump`, `bump-go-toolchain`, `go-toolchain-security-upgrade`, `go-runtime-patch`, `go-toolchain-1263-patch`. None of them targets 1.27.4/1.26.11 or CVE-2026-97054. `context/architecture.md` still says Go 1.24, so the real baseline in `go.mod` must be checked first.

## User stories
- AS the service owner I WANT the build toolchain on a release that fixes CVE-2026-97054 SO THAT a remote caller cannot crash the webhook server.
- AS a reviewer I WANT a `govulncheck` gate in CI SO THAT known-vulnerable stdlib builds cannot ship.

## Acceptance criteria (EARS)
- WHEN the baseline is checked THE SYSTEM SHALL record the current `go` and `toolchain` directives from `go.mod` and the CI image tag.
- WHEN the fixed version is selected THE SYSTEM SHALL pin the patch release that the Go vulnerability database (GO-2026-6859) lists as fixed, and SHALL NOT pin an unverified one.
- WHEN CI builds the binary THE SYSTEM SHALL use the same pinned toolchain in `go.mod`, the Dockerfile and the CI image.
- WHEN `govulncheck` runs in CI THE SYSTEM SHALL fail the build if GO-2026-6859 or any other reachable stdlib vulnerability is reported.
- WHEN a request with an oversized body or racing headers hits a webhook endpoint THE SYSTEM SHALL respond with an error and keep serving.
- WHILE the deployment runs in `admins` THE SYSTEM SHALL keep memory usage within current limits (no runtime memory growth expected).
- IF the 1.26.11 fix is shown to be incomplete THEN THE SYSTEM SHALL use 1.27.4 or a later verified release.

## Out of scope
- Dependency upgrades (chi, sqlite): see `chi-suppressnotfound-redirectslashes-audit` and `modernc-sqlite-v1620-wal-hardening`.
- Enabling CGO or changing the build approach.
- Changes to webhook handler logic or body-size limits.
