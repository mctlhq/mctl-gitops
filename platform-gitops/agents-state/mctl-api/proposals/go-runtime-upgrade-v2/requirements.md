# go-runtime-upgrade-v2: Upgrade Go toolchain from 1.24 to 1.26.3

## Context
mctl-api is built with Go 1.24. Go 1.26.3 (released May 7, 2026) is the current stable toolchain.
An earlier proposal (`proposals/go-runtime-upgrade/`) targeted Go 1.26.x generally; this v2
proposal is raised because two additional patch releases (1.26.2 and 1.26.3) have landed since
then, adding 14+ CVEs — notably CVE-2026-27140 (CVSS 8.8, HIGH) enabling arbitrary code execution
at build time via a malicious cgo/SWIG file, and CVE-2026-33814 enabling HTTP/2 DoS via
SETTINGS_MAX_FRAME_SIZE=0 on the MCP streaming transport.

This v2 supersedes the prior proposal and pins the target to the current patch (1.26.3) rather
than a floating minor.

## User stories
- AS a platform security engineer I WANT the Go toolchain pinned to 1.26.3 SO THAT all 14+
  CVEs closed in the 1.26.2 and 1.26.3 patch cycles are remediated in mctl-api binaries.
- AS a platform engineer I WANT CVE-2026-27140 closed SO THAT a malicious cgo/SWIG file in
  any dependency cannot achieve arbitrary code execution in our CI pipeline.
- AS an SRE I WANT CVE-2026-33814 closed SO THAT an HTTP/2 client cannot put the MCP streaming
  endpoint into an infinite CONTINUATION frame loop and deny service.
- AS an SRE I WANT the Go 1.26 "Green Tea" GC SO THAT MCP streaming p99 latency improves by
  the documented 10–40% reduction in GC pause overhead.
- AS a developer I WANT go.mod pinned to `toolchain go1.26.3` SO THAT CI and local builds
  use exactly the patched release.

## Acceptance criteria (EARS)
- WHEN mctl-api is built, THE SYSTEM SHALL use Go toolchain version 1.26.3 or higher as verified
  by `go version` in the CI build log.
- WHEN the CI pipeline builds any cgo-linked code, THE SYSTEM SHALL not be susceptible to the
  trust-boundary bypass described in CVE-2026-27140.
- WHEN a TLS client sends multiple TLS 1.3 key-update messages in a single post-handshake record,
  THE SYSTEM SHALL close the connection with an error and not deadlock (CVE-2026-32283).
- WHEN an HTTP/2 peer sends SETTINGS_MAX_FRAME_SIZE=0, THE SYSTEM SHALL terminate the connection
  cleanly and not enter an infinite CONTINUATION frame loop (CVE-2026-33814).
- WHEN net/http/httputil ReverseProxy handles a request, THE SYSTEM SHALL enforce the
  GODEBUG urlmaxqueryparams limit and not forward invisible query parameters (CVE-2026-39825).
- WHEN the CI pipeline runs, THE SYSTEM SHALL pass all existing unit and integration tests
  without source-code changes to mctl-api.
- WHILE mctl-api is running on the upgraded runtime, THE SYSTEM SHALL exhibit no regressions in
  request throughput or error rate versus the Go 1.24 baseline (Prometheus metrics).
- IF any transitive dependency declares a minimum Go version above 1.26.3, THEN THE SYSTEM SHALL
  fail the build with a clear error and the PR owner SHALL resolve the conflict before merging.

## Out of scope
- Enabling any new Go 1.26 opt-in experimental features.
- Upgrading to Go 1.27 or any release candidate.
- Changes to Dockerfile base image beyond updating the Go version tag.
- Migrating to a different build system.
