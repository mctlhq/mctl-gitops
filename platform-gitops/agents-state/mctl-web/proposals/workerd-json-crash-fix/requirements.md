# workerd v1.20260505.1 JSON Module Crash Fix

## Context
On May 5, 2026 Cloudflare released workerd v1.20260505.1, which contains an explicit fix for
a potential crash when the Worker runtime handles JSON modules. The mctl-web Cloudflare Worker
processes JSON payloads across multiple endpoints (`/api/submit`, `/api/contact`,
`/api/github/callback`). A crash in the underlying runtime translates directly to 5xx errors
for end-users with no graceful fallback, since the Worker is the only entry point for all
dynamic traffic.

workerd is a transitive dependency pulled in by wrangler. The existing `wrangler-cve-2026-0933`
proposal already recommends upgrading wrangler to 4.87.0 (which carried workerd v1.20260504.1).
Today's release shows the runtime is patched daily; this proposal ensures the crash fix in
v1.20260505.1 is explicitly verified as included in the deployed wrangler version.

## User stories
- AS a platform engineer I WANT the Cloudflare Worker to run on a workerd runtime free of
  known crash paths SO THAT JSON-heavy endpoints remain stable under load.
- AS an end-user I WANT tenant onboarding form submissions to succeed without 5xx errors
  SO THAT I can register without retrying or contacting support.

## Acceptance criteria (EARS)
- WHEN wrangler is upgraded or pinned, THE SYSTEM SHALL confirm via `wrangler --version`
  and its lockfile that the resolved workerd version is ≥ v1.20260505.1.
- WHEN the Worker is deployed with the updated wrangler, THE SYSTEM SHALL pass the existing
  integration test suite (submit + contact + GitHub OAuth flows) without 5xx responses.
- WHILE the Worker processes a JSON module import at runtime, THE SYSTEM SHALL not crash or
  return an unhandled exception to the caller.
- IF wrangler's resolved workerd version is older than v1.20260505.1 after an upgrade,
  THEN THE SYSTEM SHALL fail the CI build with a version-check step before deployment.

## Out of scope
- Upgrading workerd independently of wrangler (it is a transitive dependency only).
- Changes to Worker application logic or endpoint behaviour.
- Pinning workerd to a specific version in `wrangler.toml` (not a supported pattern).
