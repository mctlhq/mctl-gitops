# Backstage v1.50.4 Security Upgrade

## Context
mctl-portal runs Backstage and was last updated to version 1.0.1 (root package.json, last updated 2026-04-27). Backstage released v1.50.4 on 2026-04-29 as a dedicated security patch resolving four CVEs:

- **CVE-2026-24046 (High):** Symlink-based path traversal in `@backstage/plugin-scaffolder-backend` and `@backstage/backend-defaults` allows any user with template access to read, write, or delete files outside the scaffolder workspace.
- **CVE-2026-24048 (High):** SSRF in `FetchUrlReader` (`@backstage/backend-defaults`) — HTTP redirects from an allowlisted host bypass `backend.reading.allow`, exposing internal/sensitive URLs.
- **CVE-2026-44374 (Medium, CVSS 4.3):** Missing authorization on unprocessed-entity endpoints in `@backstage/plugin-catalog-backend-module-unprocessed` allows any authenticated user to read entities across ownership boundaries.
- **CVE-2026-29185 (Low, CVSS 2.7):** Encoded path-traversal in `@backstage/integration` SCM URLs redirects API calls using server-side integration credentials.

The Scaffolder is mctl-portal's primary onboarding mechanism (tied to mctl-gitops via Argo Workflows). CVE-2026-24046 poses a critical risk: a malicious or compromised template can escape the workspace and access mctl-gitops repository contents or other pod-mounted secrets.

## User stories
- AS a platform engineer I WANT mctl-portal to run Backstage v1.50.4 SO THAT all four patched CVEs are remediated in production.
- AS a security operator I WANT the Scaffolder to reject symlink escape attempts SO THAT no template can read or write files outside its workspace.
- AS an ops engineer I WANT `FetchUrlReader` to block redirect-based SSRF SO THAT internal Kubernetes endpoints cannot be reached via a redirecting allowlisted host.
- AS a catalog user I WANT unprocessed-entity endpoints to require authorization SO THAT entities are only visible to users with appropriate permissions.

## Acceptance criteria (EARS)
- WHEN a Scaffolder template action attempts to follow a symlink pointing outside the workspace boundary THE SYSTEM SHALL reject the operation and return an error to the template executor.
- WHEN `FetchUrlReader` receives an HTTP redirect from an allowlisted host to a URL not on the allowlist THE SYSTEM SHALL refuse to follow the redirect and return an error.
- WHEN an authenticated user without ownership rights calls the unprocessed-entity read endpoint THE SYSTEM SHALL return HTTP 403.
- WHEN `@backstage/integration` receives an SCM URL with encoded path-traversal sequences THE SYSTEM SHALL normalise and validate the URL before forwarding integration credentials.
- WHILE the Backstage backend is running post-upgrade THE SYSTEM SHALL pass all existing integration tests and health checks.
- IF the upgrade introduces a breaking change in the scaffolder template DSL THEN THE SYSTEM SHALL document the migration in a runbook before the change is deployed to production.

## Out of scope
- Upgrading to the unstable v1.51.0-next.* pre-releases.
- Changes to custom plugins or scaffolder template YAML files (unless a breaking change forces it).
- Enabling new features introduced between v1.50.2 and v1.50.4.
