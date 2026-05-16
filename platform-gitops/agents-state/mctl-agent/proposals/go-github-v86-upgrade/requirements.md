# Migrate google/go-github to v86.0.0 (context-via-Request API)

## Context

mctl-agent pins `github.com/google/go-github/v68` for GitHub PR creation (the
`fix → PR → notify` pipeline leg). The library has since released v86.0.0 (2026-05-08),
18 major versions ahead. A key breaking change in v86.0.0 is that all client methods now
receive their `context.Context` via the HTTP `Request` itself rather than as a standalone
first argument. Additional improvements include OIDC auth support for private registries
and cross-host redirect rejection.

Multiple earlier proposals (`go-github-v85-upgrade`, `go-github-v85-migration`,
`go-github-v85-authz-fix`) targeted v85 and are not yet landed. This proposal targets v86
directly, making the intermediate v85 upgrade unnecessary. At v68 the service accumulates
compounding migration debt with each passing major release; the PR-creation path is the
only consumer of this library, keeping the blast radius well-contained.

## User stories

- AS a platform engineer I WANT to run google/go-github v86.0.0 SO THAT the service stays
  on a supported library version with upstream security fixes and is not forced through a
  multi-step migration later.
- AS a developer I WANT the GitHub client call sites to follow the v86 context-via-Request
  convention SO THAT the codebase compiles with the current API and IDE tooling works
  correctly.
- AS a platform operator I WANT the PR-creation path to benefit from cross-host redirect
  rejection SO THAT a misconfigured GitHub App token cannot be silently leaked via open
  redirects.

## Acceptance criteria (EARS)

- WHEN mctl-agent compiles, THE SYSTEM SHALL link against `github.com/google/go-github/v86`
  with no remaining references to `/v68` or any intermediate version.
- WHEN a fix PR is created via the GitHub API, THE SYSTEM SHALL pass the request context
  through the HTTP Request (v86 convention) rather than as a standalone argument.
- WHEN the GitHub client follows a redirect to a different host, THE SYSTEM SHALL reject
  the redirect and return an error (cross-host redirect rejection inherited from v86).
- IF any existing unit tests for the PR-creation path fail after migration, THE SYSTEM
  SHALL NOT be released until all tests pass.
- WHILE mctl-agent creates a GitHub PR, THE SYSTEM SHALL produce the same PR content
  (title, body, branch, base) as before the migration.

## Out of scope

- Changes to the skill registry, SQLite schema, or AlertManager webhook path.
- Upgrading other dependencies alongside this change (chi, sqlite, anthropic-sdk-go).
- Enabling OIDC auth for private registries (new v86 feature — separate proposal if
  needed).
- Go toolchain upgrade — covered by `go-toolchain-1263-patch`.
