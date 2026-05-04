# Upgrade Go toolchain from 1.24 to 1.26.x

## Context

mctl-api v4.14.0 is built with Go 1.24, which falls outside the active-support window now that Go 1.26 has been released. On 7 April 2026, five stdlib CVEs were published that directly affect the service: two crypto/x509 denial-of-service vulnerabilities (CVE-2026-32280, CVE-2026-32281) sit in the certificate chain-building code that go-oidc/v3 traverses on every OIDC JWT verification; one crypto/tls TLS 1.3 deadlock (CVE-2026-32283) can halt the entire API server under load because every inbound HTTPS connection and every outbound TLS call to Vault, ArgoCD, Backstage, and Argo Workflows passes through that code path; a cmd/compile memory-corruption bug (CVE-2026-27143) affects every binary compiled with the vulnerable toolchain; and an html/template XSS issue (CVE-2026-32289) carries minimal but non-zero exposure.

All five vulnerabilities are fixed in Go 1.26.x. The upgrade closes the CVE surface, restores the service to an actively supported toolchain, and carries no Go-level API break because Go's compatibility guarantee is maintained across 1.24 to 1.26.

## User stories

- AS a platform engineer I WANT mctl-api to be compiled with a Go toolchain that has no known critical CVEs SO THAT the API server does not expose a crypto/tls deadlock vector under production load.
- AS a security officer I WANT every binary deployed to the `admins` tenant to be compiled with a non-memory-corrupting toolchain SO THAT I can attest to the integrity of compiled artifacts.
- AS an on-call engineer I WANT OIDC JWT verification to be immune to the crypto/x509 chain-building DoS SO THAT a malformed certificate presented during authentication cannot take the service down.
- AS a platform engineer I WANT the Go runtime to remain within the active-support window SO THAT future CVE patches are available without an emergency upgrade cycle.

## Acceptance criteria (EARS notation)

- WHEN mctl-api is built, THE SYSTEM SHALL use Go 1.26.2 or a later 1.26.x patch release as the declared toolchain in `go.mod`.
- WHEN the container image is assembled, THE SYSTEM SHALL produce a binary whose `go version` output reports `go1.26.x`.
- WHEN a valid OIDC JWT is presented to any authenticated endpoint, THE SYSTEM SHALL complete JWT verification without entering an unbounded certificate chain-building loop (CVE-2026-32280 / CVE-2026-32281 mitigated).
- WHEN the API server handles concurrent HTTPS requests, THE SYSTEM SHALL not deadlock inside crypto/tls (CVE-2026-32283 mitigated).
- WHILE the service is running under the `admins` tenant, THE SYSTEM SHALL serve all existing REST and MCP Streamable HTTP endpoints with no regression in response contract or HTTP status codes.
- WHILE the service is running under the `admins` tenant, THE SYSTEM SHALL maintain all existing authentication flows (GitHub PAT, Dex JWT, OAuth JWT) without behavioral change.
- IF `govulncheck` is executed against the compiled binary, THEN THE SYSTEM SHALL report zero vulnerabilities for CVE-2026-32280, CVE-2026-32281, CVE-2026-32283, CVE-2026-27143, and CVE-2026-32289.
- IF the CI pipeline builds the service, THEN THE SYSTEM SHALL fail the build if the Go toolchain version in `go.mod` is below 1.26.0.

## Out of scope

- Upgrading any application-level dependency (chi, pgx, go-oidc, mcp-go, client-go, etc.) beyond what is strictly required to compile cleanly under Go 1.26.2.
- Changing any REST or MCP API contract, request/response schema, or authentication logic.
- Migrating the deployment infrastructure (Kubernetes manifests, ArgoCD applications, Helm chart values) beyond the container image tag change.
- Addressing CVE-2026-32289 (html/template XSS) with application-level mitigations — the toolchain upgrade alone closes it.
- Upgrading Go past the 1.26.x minor line.
