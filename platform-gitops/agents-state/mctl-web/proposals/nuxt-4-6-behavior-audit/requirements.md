# Audit app and Worker against Nuxt 4.6 behaviour changes

## Context
The Nuxt 4.6.4 security release changes defaults: `x-forwarded-proto` is trusted only on opt-in, error details are limited to `createError`, and cached route rules apply only to GET/HEAD. SSR behind the Kubernetes ingress, and the Cloudflare Worker (OAuth callback, rate limiting), may build redirect or callback URLs from forwarded-proto. Silent default changes could break OAuth redirects or leak/hide error info.

This must ship with, or immediately after, `nuxt-security-upgrade`. It is code and config review; it adds no runtime components.

## User stories
- AS a platform operator I WANT forwarded-proto, error and cache behaviours verified SO THAT the upgrade does not break login or redirects.
- AS a security owner I WANT explicit opt-ins only where required SO THAT trust in proxy headers stays minimal.

## Acceptance criteria (EARS)
- WHEN the audit runs THE SYSTEM SHALL list every use of `x-forwarded-proto`, `createError`, and `routeRules` cache in `app/`, `server/` and `cloudflare-worker/`.
- WHEN a path builds an absolute URL from forwarded-proto THE SYSTEM SHALL produce `https` URLs behind the ingress after the upgrade.
- IF a path requires forwarded-proto trust THEN THE SYSTEM SHALL enable the opt-in explicitly in config and only for the trusted proxy.
- WHEN an error is thrown outside `createError` THE SYSTEM SHALL NOT expose internal details to clients.
- WHEN a non-GET/HEAD request hits a route with cache rules THE SYSTEM SHALL NOT serve it from cache.
- WHILE the Worker handles `/api/github/callback` THE SYSTEM SHALL keep a working OAuth round trip on `mctl.ai`.

## Out of scope
- The version bump itself (`nuxt-security-upgrade`).
- Worker rate-limit redesign.
- Changes to wrangler/workerd versions.
