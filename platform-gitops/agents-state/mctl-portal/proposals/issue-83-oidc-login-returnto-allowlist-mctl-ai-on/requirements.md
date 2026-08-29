# OIDC /login returnTo allowlist (*.mctl.ai only)

## Context
The `oidc-provider-backend` plugin exposes `GET /login?returnTo=<url>` (used by
Traefik ForwardAuth flows) and `GET /tenant-login`, both of which eventually
redirect the browser to a `returnTo` value. In `router.ts`, the `/login`
handler (lines 256-268) reads `req.query.returnTo`, only checks that it is
non-empty, and then either redirects directly to it (already-authenticated
session) or persists it via `store.savePendingAuth` and redirects back to it
once GitHub OAuth completes (`/github/callback`, `res.redirect(pending.returnTo)`
around line 445). No host allowlist is applied, so `/login` is an open
redirect on the identity flow of `app.mctl.ai` — an attacker can send a
victim a link like `https://app.mctl.ai/api/oidc-provider/login?returnTo=https://evil.example/`
that looks like a trusted login link but ends up on an attacker-controlled
page after a real GitHub login, which is a strong phishing primitive
(credential harvesting, OAuth-token relay, etc.). This matters because
`/login` is the externally reachable, unauthenticated entry point of the
platform's SSO flow.

## User stories
- AS a platform user clicking a login link AS a I WANT the post-login
  redirect to only ever land on an mctl.ai-owned page SO THAT a malicious
  `returnTo` link cannot silently forward me to a phishing site after I
  authenticate.
- AS the platform security team I WANT the OIDC `/login` endpoint to reject
  off-platform `returnTo` targets SO THAT the SSO flow cannot be used as an
  open-redirect primitive in phishing campaigns.
- AS a developer integrating a new mctl-owned frontend I WANT relative paths
  and `https://*.mctl.ai` absolute URLs to keep working exactly as before
  SO THAT this fix does not break existing login round-trips.

## Acceptance criteria (EARS)
- WHEN `GET /login` is called with a `returnTo` value that is a relative
  path (e.g. `/catalog`) THE SYSTEM SHALL treat it as valid and use it for
  the post-login redirect.
- WHEN `GET /login` is called with a `returnTo` value that is an absolute
  `https://` URL whose hostname is exactly `mctl.ai` or ends with
  `.mctl.ai` (dot-boundary suffix match) THE SYSTEM SHALL treat it as valid
  and use it for the post-login redirect.
- WHEN `GET /login` is called with a `returnTo` value whose scheme is not
  `https` (e.g. `http://`, or a protocol-relative value such as
  `//evil.example`) THE SYSTEM SHALL reject it and fall back to the default
  post-login page.
- WHEN `GET /login` is called with a `returnTo` value whose hostname is not
  `mctl.ai` and does not end with `.mctl.ai` on a dot boundary (e.g.
  `evil.example`, or `mctl.ai.evil.example`, which merely contains
  `mctl.ai` as a substring) THE SYSTEM SHALL reject it and fall back to the
  default post-login page.
- WHEN a `returnTo` value is rejected THE SYSTEM SHALL NOT persist the
  original attacker-supplied value via `store.savePendingAuth`; it SHALL
  substitute the default post-login page before continuing the flow (both
  the already-authenticated redirect and the GitHub OAuth round-trip).
- IF the already-authenticated branch of `/login` is taken (valid session
  cookie) THEN THE SYSTEM SHALL apply the same allowlist check before
  calling `buildSessionCookie`/`res.redirect`.
- WHILE the GitHub OAuth round-trip is in flight (`/login` -> GitHub ->
  `/github/callback`) THE SYSTEM SHALL preserve a validated `returnTo`
  unchanged end to end, so normal logins keep redirecting to the page the
  user originally requested.

## Out of scope
- `/tenant-login` already only ever builds `returnTo` from
  `buildTenantServiceUrl(tenant, service)` (a server-constructed
  `https://<tenant>-<service>.<baseDomain>/` URL), not from a raw
  user-supplied URL, and `/authorize`'s use of `req.originalUrl` as
  `returnTo` is an internal relative path, not user-controlled host. Adding
  the allowlist there is not required by this issue; only `/login` accepts
  an arbitrary absolute `returnTo`. No behavioral change is made to either
  endpoint here, though the design notes them for reviewer awareness.
- The existing `decodeOpenAICodexReturnTo` allowlist (which also permits
  `localhost` and `*.mctl.me`) is a separate, already-validated code path
  for a different flow and is not modified by this proposal.
- Allowing `mctl.me` or `localhost` for `/login` is not requested by the
  issue and is left out; only `mctl.ai` / `*.mctl.ai` over `https` is in
  scope, matching the issue's expected fix verbatim.
- Changing the shape/content of the default post-login page itself (this
  proposal only decides what happens when `returnTo` is rejected: fall back
  to a safe default target such as the issuer root).

## Open questions
- The issue does not specify what the "default post-login page" URL should
  be. This proposal uses the OIDC issuer's own root path (e.g.
  `<issuer>/`) as the fallback, since it is always same-origin and requires
  no new configuration. If a product-facing default (e.g. the Backstage
  catalog home) is preferred, that can be swapped in later without changing
  the validation logic. Proceeding with the issuer-root fallback as the
  most reasonable interpretation.
- The issue does not say whether local dev (`http://localhost:7007/...`,
  see `app-config.yaml`'s `oidcProvider.issuer`) needs an allowance so that
  `/login` keeps working against a local Backstage instance. This proposal
  keeps the allowlist strictly `https://mctl.ai` / `https://*.mctl.ai` plus
  relative paths, matching the issue's explicit test list; relative paths
  cover the common local-dev `/login?returnTo=/catalog` case, so no local
  dev regression is expected. Proceeding without a localhost carve-out.
