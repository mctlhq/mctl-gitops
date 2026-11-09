# Tasks: nuxt-4-6-behavior-audit

- [ ] 1. Inventory uses of `x-forwarded-proto`, absolute URL construction, `createError` and `routeRules` caching in `app/`, `server/`, `cloudflare-worker/` — DoD: inventory table in the PR.
- [ ] 2. Test redirect/callback URL generation on a 4.6.4 preview behind the ingress (depends on 1; needs `nuxt-security-upgrade` task 2) — DoD: all generated URLs use `https` and the correct host.
- [ ] 3. Add explicit forwarded-proto opt-in in `nuxt.config.ts` only if task 2 shows it is needed (depends on 2) — DoD: config merged, restricted to ingress; or a note that none is needed.
- [ ] 4. Review error handling and cache rules (depends on 1) — DoD: server routes use `createError` for client messages; no non-GET/HEAD cache dependency.
- [ ] 5. Run a manual end-to-end GitHub OAuth login on preview (depends on 3, 4) — DoD: login completes and returns to `mctl.ai`.

## Tests
- [ ] T1. Preview request behind ingress yields `https` absolute URLs.
- [ ] T2. OAuth login round trip succeeds.
- [ ] T3. A server error outside `createError` returns no stack or internal detail to the client.
- [ ] T4. POST to a route with cache rules is not cached.

## Rollback
Revert the config opt-in commit; if the upgrade itself must be reverted, follow the rollback in `nuxt-security-upgrade`. No data or infrastructure changes are involved.
