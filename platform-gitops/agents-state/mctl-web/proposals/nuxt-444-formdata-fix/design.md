# Design — nuxt-444-formdata-fix

## Current state

mctl-web runs Nuxt 4.3.1 (see `context/architecture.md`). The tenant sign-up
flow works as follows:

1. The user fills in the form validated by vee-validate + yup.
2. `useFetch('/api/submit', { method: 'POST', body: formData })` sends the
   FormData payload to the Cloudflare Worker.
3. The Worker calls the Backstage API, dispatches a Telegram message, and
   triggers a Resend email.

In Nuxt 4.3.x the deduplication layer in `useFetch` computes a cache key from
the request options including the body. The hashing routine does not handle
`FormData` objects correctly: it serialises them to `[object FormData]` instead
of their actual field content. As a result:

- On the first call, any key derived from `[object FormData]` is stored.
- On a retry (network hiccup, HMR, StrictMode double-invocation), a second
  call with an identical `FormData` instance is computed to the same broken
  key and may be treated as already in-flight (dropped) or as a new request
  (duplicate), depending on timing.

The practical risk is silent duplicate tenant creation in Backstage or a silently
dropped provisioning request that leaves the user with no email and no tenant.

Additionally, Nuxt 4.3.x manifest fetch has no automatic retry; a transient
CDN hiccup during hydration of a prerendered page causes the hydration to fail
or fall back to a full client-side render, resulting in a flash-of-unhydrated-
content for `/`, `/docs`, and `/privacy`.

## Proposed solution

Bump `nuxt` from `4.3.1` to `4.4.4` in `package.json`. This is a patch-level
upgrade with no breaking changes per the Nuxt release notes for 4.4.x.

The two fixes included in 4.4.4 that are directly relevant:

1. **FormData body hashing fix** — the deduplication layer now serialises
   `FormData` entries to a stable content-derived key, eliminating the
   duplicate/dropped request hazard on `/api/submit`.
2. **Manifest fetch retry logic** — the prerender manifest loader retries on
   transient fetch failures before falling back to a full reload, improving
   hydration reliability for all three prerendered routes.

No changes to `nuxt.config.ts`, the Cloudflare Worker, or any other dependency
are required. The change is limited to one version string in `package.json` and
the resulting `package-lock.json` update.

Steps:

1. Edit `package.json`: change `"nuxt": "^4.3.1"` (or equivalent) to
   `"nuxt": "^4.4.4"`.
2. Run `npm ci` to regenerate `package-lock.json`.
3. Run `nuxt build` and verify the `dist/` output is produced without errors.
4. Run existing unit tests and Playwright/Cypress end-to-end suite against the
   build.
5. Deploy to staging (admins tenant), smoke-test the sign-up form end-to-end.

## Alternatives considered

**Option A — Custom deduplication key in every `useFetch` call**
Manually pass a stable `key` option to every `useFetch` that uses a `FormData`
body, so the broken hashing is bypassed. This would fix the symptom on the
current call-sites but is fragile: any future `useFetch` call with FormData
would silently reintroduce the bug; it also requires auditing every fetch
call-site and adds maintenance burden. Dropped in favour of the upstream fix.

**Option B — Pin at 4.3.1 and wait for 4.5.x**
Continue on the current version until the next minor release. This leaves the
deduplication bug in production, accumulates technical debt, and means every
new tenant sign-up is at risk of duplication or loss. Unacceptable given that
this is the core user journey.

**Option C — Replace `useFetch` with a raw `$fetch` / `fetch` call for the
submit route**
Bypass Nuxt's composable entirely for the FormData POST. This removes the
deduplication layer and the bug along with it, but also loses caching,
SSR-awareness, and the consistent error-handling pattern used across the
application. Over-engineered for what is a one-line version bump in 4.4.4.

## Platform impact

- **Tenant**: admins. No other tenant is affected.
- **Memory**: patch upgrade; no new transitive dependencies of significant
  size are expected. Memory footprint of the Nuxt runtime in the Worker
  bundle is unchanged.
- **labs tenant**: no impact. mctl-web is deployed in admins; labs is not
  involved.
- **SSG prerender**: `nuxt build` prerender output for `/`, `/docs`,
  `/privacy` is structurally unchanged. The manifest retry logic is
  client-side only and does not alter the static output.
- **Cloudflare Worker**: no changes to `cloudflare-worker/`. Wrangler
  deployment workflow (`deploy.yml`) is unaffected.
- **Backward compatibility**: patch upgrade; Nuxt 4.4.4 is backward-
  compatible with 4.3.x configuration and page/component APIs.
- **Rollback**: revert `package.json` and `package-lock.json` to 4.3.1 and
  redeploy. The Worker is stateless; no data migration is involved.
- **Risk**: low. The only risk is an undocumented regression in 4.4.4 caught
  by the CI suite before merge.
