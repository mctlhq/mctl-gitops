# Bump coreos/go-oidc to v3.18.0 (oauth2 + go-jose freshness)

## Context
mctl-api uses `coreos/go-oidc/v3` for all three bearer-token verification paths: Dex JWT verification via JWKS, GitHub OAuth token validation, and OAuth JWT verification with HMAC-SHA256 (see `context/architecture.md`, Auth flow). The version currently in use pulls in `go-jose/go-jose/v4 4.1.3` and `golang.org/x/oauth2 0.28.0`.

`coreos/go-oidc v3.18.0` was released on 2026-04-08 and bumps `go-jose/go-jose/v4` to 4.1.4 and `golang.org/x/oauth2` to 0.36.0. There are no API surface changes — this is a transitive dependency freshness update. Keeping `go-jose` current reduces the window between the discovery of a JWT library vulnerability and the point at which mctl-api is exposed to it, as the library handles cryptographic operations on all inbound bearer tokens.

## User stories
- AS a security engineer I WANT `coreos/go-oidc` and its transitive JWT dependencies to be at their latest stable versions SO THAT the risk of unpatched JWT cryptographic vulnerabilities is minimised
- AS a developer I WANT the dependency bump to have zero API surface changes SO THAT it can be merged and deployed without any code modifications

## Acceptance criteria (EARS)

- WHEN `go.mod` is updated THE SYSTEM SHALL specify `github.com/coreos/go-oidc/v3 v3.18.0` or later
- WHEN `go.mod` is updated THE SYSTEM SHALL transitively include `github.com/go-jose/go-jose/v4 v4.1.4` or later and `golang.org/x/oauth2 v0.36.0` or later
- WHEN the updated dependencies are compiled THE SYSTEM SHALL produce a passing build with zero changes to non-`go.mod`/`go.sum` source files
- WHEN the full test suite runs after the bump THE SYSTEM SHALL pass all existing authentication tests for the Dex JWT, GitHub PAT, and OAuth JWT verification paths without modification
- IF a `go.sum` entry for the new versions is absent THEN THE SYSTEM SHALL fail the build until `go mod tidy` is run and the updated `go.sum` is committed

## Out of scope
- Changes to the authentication logic or verification code paths
- Upgrading any other dependency not transitively required by `go-oidc v3.18.0`
- Adding new authentication capabilities
- Upgrading Go itself (tracked separately)
