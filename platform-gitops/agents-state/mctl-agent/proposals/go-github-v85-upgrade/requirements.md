# go-github-v85-upgrade: Upgrade google/go-github v68 → v85

## Context

`mctl-agent` uses `google/go-github` as its sole client library for GitHub operations — specifically to open fix PRs against the `mctlhq/mctl-gitops` repository. The current pinned version is **v68**, released in mid-2024. The library is now at **v85.0.0** (released 2025-04-20), which ships a direct security fix: the client now rejects HTTP responses that redirect across hosts, preventing the outbound `Authorization` header (a short-lived GitHub App installation token) from being forwarded to an unintended third-party host.

Although the installation token is rotated every 30 minutes by `cwft-rotate-github-token`, a leak window still exists within each rotation period. The v85 upgrade closes that window unconditionally. Three breaking API signature changes in v85 must be addressed during the migration.

## User stories

- AS the `mctl-agent` service I WANT the GitHub client to refuse cross-host redirects SO THAT the `Authorization` header is never forwarded to a host other than `api.github.com`.
- AS a platform engineer I WANT all GitHub API calls from `mctl-agent` to be made against the canonical host SO THAT the GitHub App installation token remains confidential.
- AS a developer I WANT the codebase to compile cleanly against go-github v85 SO THAT I can pull future security patches without an accumulated migration debt.

## Acceptance criteria (EARS)

- WHEN `mctl-agent` sends a GitHub API request and the response is an HTTP redirect to a different hostname THEN THE SYSTEM SHALL return an error and SHALL NOT follow the redirect.
- WHEN `mctl-agent` sends a GitHub API request and the URL path includes a `..` segment THEN THE SYSTEM SHALL return an error and SHALL NOT execute the request.
- WHILE `mctl-agent` is creating or retrieving a pull request THE SYSTEM SHALL use the `google/go-github` v85 client exclusively.
- WHEN the `go.mod` file is updated to `google/go-github/v68` → `v85` THE SYSTEM SHALL compile without errors and all existing unit tests SHALL pass.
- IF a breaking-API call site (`GetOrgRole`, `CreateCustomOrgRole`, `UpdateCustomOrgRole`, `MarkThreadDone`) is present in the codebase THEN THE SYSTEM SHALL use the updated v85 function signatures.

## Out of scope

- Upgrading other GitHub-related dependencies (e.g., `golang.org/x/oauth2`).
- Adding new GitHub API calls or expanding the set of PR operations.
- Changing the token rotation frequency or the Vault secret structure for `secret/platform/github-app`.
- Migrating from GitHub App authentication to a different auth mechanism.
