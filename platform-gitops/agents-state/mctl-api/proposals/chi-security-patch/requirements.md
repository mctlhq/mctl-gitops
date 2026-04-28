# Upgrade chi/v5 to v5.2.5 (RedirectSlashes security fix)

## Context
chi/v5 v5.2.5 (released 2025-02-05) contains a security fix in the `RedirectSlashes` middleware as well as a fix for double handler invocation in `RouteHeaders`. mctl-api uses chi/v5 5.2.1 as the HTTP router for all REST and MCP endpoints, including the public `https://api.mctl.ai`. The lag is 4 patch versions while an explicit security fix exists.

The vulnerability in the `RedirectSlashes` middleware potentially allows manipulation of request paths via an incorrect redirect, which under certain configurations may be used to bypass routing or auth middleware. The upgrade is a patch bump without breaking changes in the chi/v5 API, minimal effort with a direct security effect.

## User stories
- AS a platform security engineer I WANT chi/v5 upgraded to v5.2.5 SO THAT the known security vulnerability in RedirectSlashes middleware is remediated on the public API endpoint.
- AS a developer I WANT the router library to be on the latest patch version SO THAT the RouteHeaders double-handler bug does not cause unexpected behaviour in API routing.

## Acceptance criteria (EARS)
- WHEN mctl-api handles any HTTP request with a trailing slash THE SYSTEM SHALL apply the patched RedirectSlashes behaviour from chi v5.2.5 without path manipulation vulnerability.
- WHEN the application starts THE SYSTEM SHALL load chi/v5 v5.2.5 or later (verified via `go.mod` and `go.sum`).
- WHILE the service is running THE SYSTEM SHALL route all existing REST endpoints and the `/mcp` endpoint correctly without regression.
- IF a RouteHeaders middleware is configured and a matching request arrives THE SYSTEM SHALL invoke the handler exactly once (no double-call regression).
- WHEN the updated binary is deployed to the `admins` tenant THE SYSTEM SHALL return correct HTTP status codes for all routes covered by existing integration tests.

## Out of scope
- Changing chi middleware configuration (adding or removing `RedirectSlashes` — a separate decision).
- Updating chi-related dependencies (httprate etc.) beyond the transitive requirements of v5.2.5.
- Evaluating a replacement of chi with another router.
- Changing routing or auth-middleware logic.
