# Go Runtime Upgrade: 1.24 → 1.26.2

## Context
mctl-agent is built with Go 1.24. Three CVEs — CVE-2026-32283, CVE-2026-32280, and CVE-2026-32281 — were fixed in Go 1.26.2 (released 2026-04-07). All three affect the `crypto/tls` and `crypto/x509` standard-library packages and enable denial-of-service attacks by exhausting CPU or deadlocking TLS connections. mctl-agent receives HTTPS webhooks from AlertManager and Telegram, and makes outbound HTTPS calls to the GitHub API and Anthropic API, placing it squarely in the blast radius of all three vulnerabilities.

In addition to the security fixes, Go 1.26 introduces the Green Tea GC (10–40 % reduction in GC overhead) and a revamped `go fix` tooling, both beneficial for a long-running service under variable alert load.

## User stories
- AS a platform engineer I WANT mctl-agent compiled with Go 1.26.2 SO THAT the three TLS/x509 DoS vulnerabilities are eliminated from production.
- AS an SRE I WANT lower GC pause overhead in mctl-agent SO THAT alert processing latency remains stable under burst load.
- AS a security auditor I WANT the dependency scan to show no known Go-runtime CVEs SO THAT compliance checks pass.

## Acceptance criteria (EARS)
- WHEN the CI pipeline builds mctl-agent, THE SYSTEM SHALL use `go 1.26.2` as declared in `go.mod`.
- WHEN `govulncheck` is run against the built binary, THE SYSTEM SHALL report zero findings for CVE-2026-32283, CVE-2026-32280, and CVE-2026-32281.
- WHEN mctl-agent starts in the `admins` tenant, THE SYSTEM SHALL pass `/healthz` and `/readyz` within 10 seconds.
- WHILE mctl-agent handles an AlertManager webhook, THE SYSTEM SHALL complete the TLS handshake without deadlocking.
- IF the Go 1.26 toolchain introduces a compilation error in existing code, THE SYSTEM SHALL have that error resolved before the PR is merged.
- WHEN the new binary is deployed, THE SYSTEM SHALL retain all existing API endpoint behaviour with no regression in the test suite.

## Out of scope
- Upgrading any third-party Go dependencies beyond what is strictly required for Go 1.26 compatibility.
- Switching the base container image (only the Go toolchain version changes).
- Adopting new Go 1.26 language features or rewriting existing code to use them.
