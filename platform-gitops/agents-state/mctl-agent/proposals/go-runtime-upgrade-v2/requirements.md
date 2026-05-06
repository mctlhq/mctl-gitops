# Upgrade Go Runtime from 1.24 to 1.26.2

## Context
mctl-agent is built with Go 1.24. Three CVEs have been published against Go
stdlib that are patched only in Go 1.25.9+ or Go 1.26.2: CVE-2026-32283
(crypto/tls TLS 1.3 deadlock DoS), CVE-2026-32280 (crypto/x509
chain-building DoS), and CVE-2026-32289 (html/template XSS). Go 1.24 will
NOT receive backport patches for any of these. mctl-agent establishes
outbound TLS connections to the Anthropic API (diagnose phase) and GitHub App
endpoints (PR creation, token rotation) on every alert cycle, placing
crypto/tls and crypto/x509 in active production use. This makes the two DoS
CVEs immediately exploitable by any party that can influence a TLS response
seen by the agent.

Upgrading to Go 1.26.2 — the current supported release — eliminates all three
CVEs, keeps mctl-agent on a release train that receives future security
patches, and allows a zero-breaking-change bump of chi from v5.2.1 to v5.2.5
as a bundled improvement. The go-github dependency (currently v68) is
intentionally excluded from this change because upgrading it requires
addressing breaking API changes and is tracked as a separate proposal.

## User stories
- AS a platform operator I WANT mctl-agent compiled with Go 1.26.2 SO THAT
  the three active stdlib CVEs are eliminated from the production binary.
- AS an SRE I WANT the TLS connections to the Anthropic API and GitHub App
  to use the patched crypto/tls implementation SO THAT a malicious upstream
  response cannot deadlock the agent process.
- AS a security auditor I WANT a dependency scan to report zero known Go
  runtime CVEs SO THAT compliance checks pass without exceptions.
- AS a developer I WANT the upgrade validated by the existing full test suite
  SO THAT I can be confident no behavioural regression was introduced.

## Acceptance criteria (EARS notation)
- WHEN the CI pipeline builds mctl-agent THE SYSTEM SHALL use the Go 1.26.2
  toolchain as declared in `go.mod` and in the Dockerfile base image.
- WHEN `govulncheck` is run against the built binary THE SYSTEM SHALL report
  zero findings for CVE-2026-32283, CVE-2026-32280, and CVE-2026-32289.
- WHEN an outbound TLS 1.3 connection is established to the Anthropic API or
  GitHub App endpoint THE SYSTEM SHALL use the patched crypto/tls
  implementation, eliminating the CVE-2026-32283 deadlock vector.
- WHEN certificate chain validation is performed for any outbound HTTPS call
  THE SYSTEM SHALL use the patched crypto/x509 implementation, eliminating
  the CVE-2026-32280 DoS vector.
- WHEN any HTML template is evaluated inside the service THE SYSTEM SHALL
  use the patched html/template package, eliminating the CVE-2026-32289 XSS
  vector.
- WHEN the CI pipeline executes after the upgrade THE SYSTEM SHALL pass
  `go vet ./...` with zero reported issues.
- WHEN the CI pipeline executes after the upgrade THE SYSTEM SHALL pass the
  full unit and integration test suite with zero failures.
- WHILE the service is running on Go 1.26.2 THE SYSTEM SHALL expose the same
  REST and MCP API surface as under Go 1.24 with no endpoint removals or
  contract changes.
- IF chi is bumped to v5.2.5 as part of this change THEN THE SYSTEM SHALL
  continue to route all existing endpoints without regression, given that
  chi v5.2.5 introduces no breaking API changes relative to v5.2.1.
- WHEN the upgraded image is deployed via ArgoCD to the `admins` tenant
  THE SYSTEM SHALL pass its /healthz and /readyz probes within the existing
  probe timeout window.

## Out of scope
- Upgrading google/go-github beyond v68 (breaking API changes; tracked as a
  separate proposal).
- Changes to chi router middleware configuration or API usage patterns beyond
  the version bump.
- Upgrading modernc.org/sqlite or any other non-stdlib dependency.
- Changes to Kubernetes manifests, resource limits, or ArgoCD Application
  spec.
- Adopting new Go 1.26 language features or rewriting existing code to use
  them.
- Introducing new skills or service features as part of this change.
