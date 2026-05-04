# Upgrade Go 1.24 to 1.26.2

## Context
mctl-agent is built with Go 1.24 and makes continuous outbound TLS connections to the GitHub API
(`api.github.com`) and the Anthropic API on every remediation cycle. Two denial-of-service
vulnerabilities published on 2026-04-07 affect `crypto/x509` chain-building in all Go versions
prior to 1.26.2 (and 1.25.9):

- **CVE-2026-32280** — excessive work when building certificate chains with large intermediate
  certificate sets.
- **CVE-2026-32281** — inefficient policy-mapping validation that can be triggered by a crafted
  TLS certificate.

A compromised or malicious intermediate CA presenting a crafted certificate during the TLS handshake
could exploit either vulnerability to exhaust CPU and halt the agent entirely. Because the agent
runs continuously and its liveness is critical for automated remediation, a CPU-exhausting DoS
is an availability-class incident.

Upgrading the Go toolchain to 1.26.2 is a self-contained build change: no API surface is altered,
no runtime configuration changes are required, and the upgrade also bundles fixes in `crypto/tls`,
`archive/tar`, `html/template`, and `net/http`.

## User stories
- AS a platform engineer I WANT the agent to be built with a Go toolchain that includes fixes for
  CVE-2026-32280 and CVE-2026-32281 SO THAT a crafted TLS certificate cannot exhaust agent CPU and
  cause a remediation outage.
- AS a security reviewer I WANT the Go version in the Dockerfile and `go.mod` to be pinned to
  1.26.2 SO THAT dependency scanners report no outstanding toolchain CVEs.
- AS an on-call engineer I WANT the build CI to enforce a minimum Go version SO THAT future
  regressions to an older toolchain are caught before deployment.

## Acceptance criteria (EARS)
- WHEN the agent binary is built THEN THE SYSTEM SHALL use Go 1.26.2 or later as the compiler
  toolchain.
- WHEN `go.mod` is inspected THEN THE SYSTEM SHALL declare `go 1.26.2` (or higher) in the module
  directive.
- WHEN the agent establishes a TLS connection to an external endpoint THEN THE SYSTEM SHALL use the
  `crypto/x509` chain-builder that includes the CVE-2026-32280 and CVE-2026-32281 mitigations.
- WHILE the agent is handling an outbound TLS handshake with a crafted certificate chain THEN THE
  SYSTEM SHALL bound certificate chain-building work and not enter unbounded CPU consumption.
- IF the Dockerfile base image specifies a Go version earlier than 1.26 THEN THE SYSTEM SHALL fail
  CI with a linting or image-scan error.

## Out of scope
- Adopting any Go 1.26 language features or new standard-library APIs in application code.
- Upgrading third-party dependencies beyond what `go mod tidy` requires for Go 1.26 compatibility
  (those are handled in separate proposals).
- Modifying runtime configuration, environment variables, or Kubernetes manifests beyond the
  Dockerfile base image.
