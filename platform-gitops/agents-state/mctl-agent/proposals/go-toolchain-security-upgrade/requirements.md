# Bump Go toolchain from 1.24 to 1.27.0

## Context
mctl-agent is built and shipped on Go 1.24. The 2026 Go stdlib CVE batch
(Red Hat advisories) includes several issues that directly affect this
service: crypto/tls DoS via repeated TLS 1.3 key updates
(CVE-2026-32283) and crypto/x509 DoS in certificate-chain building
(CVE-2026-32280) hit every outbound TLS connection mctl-agent makes
(Anthropic API, GitHub API, AlertManager/Telegram webhook callers);
html/template XSS via URL escaping (CVE-2026-39823) is relevant to any
templated output; and cmd/go supply-chain issues (CVE-2026-42501
checksum-validation bypass via malicious module proxy, CVE-2026-39819
arbitrary file overwrite via symlink, CVE-2026-27140 RCE via malicious
SWIG filenames) affect our build pipeline's trust boundary.

Go 1.27.0 was released 2026-08-19 and is now the latest stable release.
A toolchain bump is self-contained — it changes no application API
surface — and is the highest-leverage security fix available this
cycle for the lowest effort.

## User stories
- AS the mctl-agent maintainer I WANT the Go toolchain upgraded to the
  latest patched stable release SO THAT outbound TLS connections,
  certificate validation, and the build pipeline are not exposed to
  known, fixed stdlib CVEs.
- AS a platform operator I WANT the CI/build pipeline to build with a
  toolchain that has cmd/go's checksum-validation and symlink-handling
  fixes SO THAT a compromised module proxy or malicious dependency
  cannot tamper with the build.

## Acceptance criteria (EARS)
- WHEN the mctl-agent module is built THE SYSTEM SHALL use Go 1.27.0 (or
  the latest patched 1.27.x release available at build time) as
  declared in `go.mod`'s `go` and `toolchain` directives.
- WHEN the full test suite is run against the upgraded toolchain THE
  SYSTEM SHALL pass with no test failures or new vet/lint warnings
  introduced solely by the toolchain change.
- WHEN a TLS connection is established to the Anthropic API, GitHub
  API, or an inbound webhook client THE SYSTEM SHALL use the Go 1.27.0
  crypto/tls and crypto/x509 implementations (i.e. no vendored/forked
  copies of these packages remain in use).
- IF the CI build environment pins a Go version via `GOTOOLCHAIN` or a
  container base image THEN THE SYSTEM SHALL have that pin updated to
  match `go.mod` so CI and local/dev builds cannot silently diverge.
- WHILE the upgrade PR is open THE SYSTEM SHALL keep the binary's
  external behavior (API contract, skill pipeline output, ticket
  schema) unchanged — this is a toolchain bump only, not a feature
  change.
- IF any first-party or vendored code fails to compile or triggers a
  new `go vet` finding under Go 1.27.0 THEN THE SYSTEM SHALL have that
  code fixed as part of this proposal before merge, scoped strictly to
  what the toolchain bump requires.

## Out of scope
- Any application-level API or behavior change.
- Upgrading other dependencies (chi, modernc.org/sqlite, google/go-github)
  — tracked separately in `go-chi-v5.3.2-router-upgrade` and
  `sqlite-stack-dependency-update`.
- Adopting new Go 1.27 language features or stdlib APIs beyond what is
  needed to fix compile/vet breaks.
- Changing the container base image's OS/distro, only its Go version.
