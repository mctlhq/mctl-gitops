# Design: nuxt-4-6-behavior-audit

## Current state
Nuxt SSR with prerendered routes behind a Kubernetes ingress; a separate Cloudflare Worker serves `/api/*` (GitHub OAuth, submit, contact) with rate limits. See `context/architecture.md`. The Worker is not a Nuxt app, so Nuxt default changes mostly affect the SSR server; the Worker is reviewed only for its own forwarded-proto assumptions.

## Proposed solution
Perform a targeted code and config audit against the three behaviour changes:
1. Grep for `x-forwarded-proto`, `useRequestURL`, `getRequestProtocol` and absolute-URL construction in Nuxt server code and the Worker. Test the ingress path in `admins`. Where trust is needed, set the Nitro opt-in explicitly (config option name taken from the 4.6.4 release notes) in `nuxt.config.ts`.
2. Review error handling: ensure server routes use `createError` for intended client-visible messages.
3. Review `routeRules` for cache/swr/isr and confirm no reliance on caching of non-GET/HEAD.
Document findings in the PR; fix only what is broken. Findings are verified on a preview build before promotion.

## Alternatives
- Enable the forwarded-proto opt-in globally without audit: widens trust unnecessarily. Dropped.
- Skip the audit and rely on smoke tests: OAuth callback is hard to cover with smoke tests. Dropped.
- Merge into `nuxt-security-upgrade`: makes that PR larger and harder to roll back separately. Dropped.

## Platform impact
- Migrations: none.
- Backward compatibility: config-only changes; explicit opt-in preserves old behaviour where needed.
- Resource impact: none; `labs` memory is unaffected by config changes (the memory gate sits in `nuxt-security-upgrade`).
- Risks and mitigations: an overly broad opt-in weakens header trust (restrict to ingress); a missed OAuth redirect issue (manual end-to-end login test on preview before production).
