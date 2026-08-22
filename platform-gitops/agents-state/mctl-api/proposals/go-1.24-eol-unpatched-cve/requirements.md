# Escalate Go 1.24 EOL — CVE-2026-42507 has no backport path

## Context
Go 1.24 reached end-of-life on 2026-02-10, the date Go 1.26.0 shipped, because the Go project only
patches the two most recently released major versions. mctl-api is still built with Go 1.24 (per
`context/architecture.md`) and has therefore received zero stdlib/crypto/runtime security patches
for over six months. CVE-2026-42507 (GO-2026-5039, `net/textproto` error-injection — unescaped
input in `Error.Error`, `ReadCodeLine`, `ReadMIMEHeader`, `ReadResponse` can inject misleading
content into logged/printed errors) is fixed only in 1.25.11 and 1.26.4; it will never be
backported to 1.24. Go 1.27.0 has now shipped (2026-08-19), meaning mctl-api's runtime is three
major versions behind and permanently exposed to this and any future stdlib CVE until upgraded.

This is not a new finding — it is an overdue escalation. At least six prior proposals have
attempted this upgrade (`go-runtime-upgrade`, `go-runtime-upgrade-v2`, `go-runtime-cve-dos`,
`go-runtime-cve-upgrade`, `go-upgrade`, `go-upgrade-1262`, `go-upgrade-stdlib-cves`,
`go-upgrade-stdlib-cves-v2`, `go-toolchain-ace-cve-27140`) and none show a merged status. The
purpose of this proposal is to state plainly that the underlying condition (unpatchable EOL
runtime) has now worsened to a permanent, structural gap rather than a single outstanding CVE, and
to consolidate the ask into one proposal that must land.

## User stories
- AS a platform security engineer I WANT the Go toolchain upgraded off the EOL 1.24 line SO THAT
  mctl-api again receives stdlib/crypto/runtime CVE patches as a matter of course.
- AS a security auditor I WANT CVE-2026-42507 closed SO THAT error strings surfaced from
  `net/textproto`-based paths (HTTP client usage, MCP transport) cannot be used to inject
  misleading content into logs.
- AS an engineering lead I WANT this treated as an escalation of the existing unmerged
  `go-runtime-upgrade*` line of proposals, not a new parallel draft, SO THAT review effort
  consolidates on a single change instead of fragmenting across nine open proposals.

## Acceptance criteria (EARS)
- WHEN mctl-api is built THE SYSTEM SHALL use a Go toolchain version that is within the two most
  recently released majors (at minimum 1.26.4, which fixes CVE-2026-42507; 1.27.x is acceptable
  and preferred as headroom against the next EOL cycle).
- WHEN the CI pipeline runs `govulncheck ./...` THE SYSTEM SHALL report zero findings for
  CVE-2026-42507.
- WHEN the CI pipeline builds mctl-api THE SYSTEM SHALL pass all existing unit and integration
  tests without required source-code changes.
- WHILE mctl-api runs on the upgraded toolchain THE SYSTEM SHALL exhibit no regression in request
  throughput or error rate versus the Go 1.24 baseline, as observed via existing Prometheus
  metrics at `/metrics`.
- IF any direct or transitive dependency declares a minimum Go version incompatible with the
  target toolchain THEN THE SYSTEM SHALL fail the build with a clear error, and the conflict SHALL
  be resolved (dependency bump or toolchain adjustment) before merge.
- IF this proposal is approved THEN the prior unmerged `go-runtime-upgrade*` family of proposals
  SHALL be marked superseded rather than continuing to accumulate as separate open drafts.

## Out of scope
- Enabling new Go 1.26/1.27 opt-in experimental language or runtime features.
- Any application-level fix for CVE-2026-39823/CVE-2026-39825 (`net/http/httputil` ReverseProxy) —
  tracked separately in `go-runtime-upgrade-v2`'s acceptance criteria; not duplicated here.
- Changes to the Dockerfile base image beyond the Go version tag.
- Migrating to a different build system or toolchain manager.
