# Patch chi to v5.2.5 to Fix Open Redirect CVE

## Context

GO-2026-4316 / GHSA-vrw8-fxc6-2r93 is a Moderate-severity open redirect vulnerability in the `go-chi/chi` HTTP router, published 2026-01-14. The flaw resides in the `RedirectSlashes` middleware: when an attacker supplies a crafted `Host:` header, chi constructs an absolute redirect URL using that header value rather than the canonical server hostname, thereby redirecting the user's browser to an arbitrary attacker-controlled domain (Host Header Injection).

mctl-api is currently on chi v5.2.1 and serves an OAuth 2.0 PKCE flow at `https://api.mctl.ai/mcp` for the Claude.ai MCP connector. An exploitable open redirect in this flow allows an attacker to intercept the OAuth callback and steal authorization codes, enabling account takeover or unauthorized MCP tool invocation. chi v5.2.5 is a pure patch release that hardens `RedirectSlashes` against Host Header Injection and carries no API-breaking changes; upgrading is the lowest-risk remediation available.

## User stories

- AS a platform operator I WANT chi upgraded to v5.2.5 SO THAT the open redirect vulnerability is eliminated before it can be exploited against our OAuth PKCE flow.
- AS a developer using the Claude.ai MCP connector I WANT the OAuth callback to always redirect to the legitimate mctl-api domain SO THAT my authorization code cannot be stolen by a phishing redirect.
- AS a security auditor I WANT the dependency manifest to reference only versions free of known CVEs SO THAT the service passes continuous compliance scans without exceptions.

## Acceptance criteria (EARS notation)

- WHEN a client sends an HTTP request with a malformed or attacker-controlled `Host:` header and the `RedirectSlashes` middleware is active, THE SYSTEM SHALL redirect only to the canonical server origin and SHALL NOT use the value of the `Host:` header to construct the redirect target URL.
- WHEN the OAuth 2.0 PKCE callback flow is invoked, THE SYSTEM SHALL return an HTTP redirect whose `Location` header is restricted to pre-registered redirect URIs and SHALL NOT incorporate unvalidated request headers.
- WHILE mctl-api is running in any environment (local, staging, production), THE SYSTEM SHALL route all HTTP traffic through chi v5.2.5 or later.
- IF the `go.mod` file lists `github.com/go-chi/chi/v5`, THEN THE SYSTEM SHALL specify a version of at least `v5.2.5`.
- WHEN the CI pipeline runs, THE SYSTEM SHALL execute `govulncheck ./...` and SHALL produce zero findings for GO-2026-4316.
- IF a future chi release introduces a regression, THE SYSTEM SHALL detect it via the automated vulnerability scan step in CI and SHALL block the merge.

## Out of scope

- Migrating away from chi to another HTTP router (gin, echo, etc.).
- Hardening other middleware beyond the `RedirectSlashes` change delivered in v5.2.5.
- Changes to the OAuth 2.0 PKCE logic itself (redirect-URI allowlist enforcement is a separate concern tracked elsewhere).
- Updating any dependency other than `github.com/go-chi/chi/v5` and the transitive entries affected by `go mod tidy`.
- Changes to the `labs` tenant workloads or any service other than `mctl-api`.
