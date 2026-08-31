# Design: issue-66-turnstile-on-contact-submit-forms-harden

## Current state

- `cloudflare-worker/index.js` is a single Cloudflare Worker (`name =
  "mctl-landing-form"` in `cloudflare-worker/wrangler.toml`) that routes
  `mctl.ai/api/*`. It is the sole backend for OAuth, check-team, submit,
  and contact — there is no separate API service for these forms.
- Routing happens in the top-level `fetch` handler (lines 56-140): a fixed
  `RATE_LIMITS` map keyed by pathname (lines 41-46) is checked at line
  94-106 for every request whose path matches, via `checkRateLimit`
  (Cache API-backed, lines 147-165) before any handler runs.
- `handleCheckTeam` (lines 740-775): validates `name` against
  `/^[a-z0-9][a-z0-9-]{0,62}$/`, mints a short-lived Backstage JWT
  (`createLandingJwt`), and calls
  `GET {BACKSTAGE_APP_URL}/api/tenant-management/tenants/{name}`. Backstage
  404 -> `{available: true}` (200); Backstage 2xx -> `{available: false,
  message: ...}` (200); anything else -> 500. This is called from
  `app/composables/useTeamValidation.ts` on a 600ms debounce as the user
  types a team name in `RequestAccessForm.vue`, with no auth requirement on
  either side.
- `handleFormSubmit` (lines 779-919): requires `github_auth.login` +
  `github_auth.sig`, HMAC-verifies `sig` against `login` using
  `GITHUB_OAUTH_HMAC_KEY` (`hmacVerify`, lines 468-479), re-checks tenant
  existence via Backstage (skipped for `getUnlimitedUsers(env)`), then POSTs
  to Backstage's tenant-provisioning endpoint, sends a Telegram message, and
  optionally a Resend welcome email. The `github_auth` blob is exactly what
  `useAuth.ts`'s `authData` computed property sends — the OAuth-callback
  payload (`login`, `name`, `email`, `avatar_url`, `html_url`, `sig`)
  persisted client-side in `localStorage` under `mctl_auth` for 8 hours
  (`AUTH_TTL`), independent of whether the user's actual GitHub session or
  browser tab is still open.
- `handleContactForm` (lines 923-980): validates `name`/`email`/`message`
  presence and trivial shape, then sends straight to Telegram. No auth, no
  CAPTCHA, no bot signal beyond the blanket rate limit (3 req / 5 min / IP,
  `RATE_LIMITS['/api/contact']`) and the `BOT_UA_FRAGMENTS` check — which
  only runs for `REDIRECT_SUFFIXES` hosts (`.mctl.me`/`.mctl.ru`), not for
  `mctl.ai` API traffic (see `isRedirectDomain` gate, lines 65-75).
- CORS is enforced per-endpoint via `corsHeaders`/`sessionCorsHeaders`
  against `ALLOWED_ORIGINS` / `SESSION_ORIGINS` (lines 26-32, 169-196) —
  contact/submit/check-team use the plain `corsHeaders` (`ALLOWED_ORIGINS`
  = `https://mctl.ai` + `http://localhost:3000`).
- Frontend: `app/composables/useApi.ts` posts JSON bodies directly to
  `https://mctl.ai/api/submit` and `/api/contact` with
  `Content-Type: application/json`; `ContactForm.vue` and
  `RequestAccessForm.vue` build those bodies via `vee-validate` +
  `yup` schemas, no CAPTCHA field today. `nuxt.config.ts` exposes a public
  runtime config block (`runtimeConfig.public`) already used for
  `baseUrlFront` — the natural place to add a public Turnstile sitekey.
- The repo ships `.claude/skills/turnstile-spin/SKILL.md`, a general
  Turnstile-setup skill whose default recipe deploys a *separate* managed
  siteverify Worker that a frontend calls directly, keeping the caller's
  own backend out of the loop entirely (`browser -> spin worker ->
  siteverify`, per its "hard scope boundary"). That recipe assumes the
  caller doesn't already own a backend Worker terminating the form POSTs.
  This repo does — `handleContactForm` and `handleFormSubmit` already are
  the backend — so this proposal deviates from Spin's default topology (see
  Alternatives).
- No existing worker tests exercise `handleFormSubmit`, `handleContactForm`,
  `handleCheckTeam`, or `checkRateLimit`. The only worker test file,
  `cloudflare-worker/oauth.test.mjs`, covers OAuth/session helpers exported
  from `index.js` (HMAC, session redeem, location builders) via Node's
  built-in `node:test` + `node:assert/strict` — no framework, no network
  mocking library. Coverage is achieved by testing the exported pure
  helper functions directly, not by driving the `fetch` handler end-to-end.

## Proposed solution

1. **Turnstile verification helper in the existing worker.**
   Add a small exported helper in `cloudflare-worker/index.js`, following
   the file's existing helper-function style (see `hmacVerify`,
   `createLandingJwt`):

   ```js
   const TURNSTILE_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify';

   export async function verifyTurnstileToken(token, secret, remoteip) {
     if (!secret) return { success: false, reason: 'not_configured' };
     if (typeof token !== 'string' || !token) return { success: false, reason: 'missing_token' };
     const body = new URLSearchParams({ secret, response: token });
     if (remoteip) body.set('remoteip', remoteip);
     try {
       const res = await fetch(TURNSTILE_VERIFY_URL, { method: 'POST', body });
       const data = await res.json();
       return { success: !!data.success, reason: data.success ? null : (data['error-codes']?.[0] || 'failed') };
     } catch (e) {
       return { success: false, reason: 'network_error' };
     }
   }
   ```

   This mirrors the existing pattern of small testable exported helpers
   (`hmacVerify`, `sessionIsLive`, etc.) that `oauth.test.mjs` already
   imports and unit-tests, and keeps the network call mockable in tests via
   dependency injection (pass a `fetchImpl` param defaulting to global
   `fetch`, matching how the file already isolates side effects — see
   Tests below for how this is exercised without hitting Cloudflare's real
   API).

2. **Wire into `/api/contact` and `/api/submit`.**
   In `handleContactForm` and `handleFormSubmit`, read `turnstile_token`
   from the JSON body (new field, additive — does not remove existing
   fields) and call `verifyTurnstileToken(turnstile_token,
   env.TURNSTILE_SECRET_KEY, request.headers.get('CF-Connecting-IP'))`
   before doing any Telegram/Backstage side effect. On failure, return the
   same `{ success: false, message: ... }` 400 shape both handlers already
   use elsewhere (e.g. line 930 `'All fields are required'`), with a
   generic message ("Verification failed, please try again.") — never
   surface Turnstile's `error-codes` to the client, per the acceptance
   criteria. On `env.TURNSTILE_SECRET_KEY` unset, fail closed with 500
   `Server misconfiguration`, mirroring the existing
   `BACKSTAGE_LANDING_TOKEN`-missing branch in `handleCheckTeam`
   (lines 751-754).

3. **check-team hardening.**
   - Apply the existing `RATE_LIMITS` mechanism but tighten
     `/api/github/check-team`'s entry (currently absent from `RATE_LIMITS`
     entirely — it has no rate limit today) to something like `{ max: 20,
     windowSec: 60 }` per IP.
   - Add Turnstile verification to `check-team` as well, but sourced from a
     query param (`?turnstile_token=`) since it's a GET request driven by
     debounced keystrokes rather than a form submit. To avoid a Turnstile
     challenge firing on every keystroke pause (UX concern raised in Open
     Questions), the frontend obtains one Turnstile token per form-render
     (invisible/managed mode executes once, silently, on page load in the
     common case) and reuses it for the debounced check-team calls during
     that session, then re-verifies+consumes a fresh token at final
     `/api/submit` time. Token reuse across check-team calls within its
     ~5 minute Turnstile validity window is acceptable since check-team is
     read-only.
   - Change the response shape so `handleCheckTeam` returns
     `{ available: true }` (200) uniformly for both "tenant exists" and
     "tenant does not exist" once the request passes format validation,
     Turnstile, and rate-limit checks — i.e. stop branching on Backstage's
     200-vs-404 for the response the anonymous caller sees. The real
     duplicate-tenant guard remains authoritative server-side at
     `/api/submit` (lines 806-822, unauthenticated-caller-proof since it
     runs after HMAC verification), so removing check-team's
     existence-leak does not reopen duplicate provisioning. `500` is still
     returned on genuine Backstage/config errors (distinguish "we could not
     tell" from "it doesn't exist", which is fine — a 500 leaks nothing
     about a specific name existing).
   - Frontend impact: `useTeamValidation.ts`'s `teamAvailable`/`teamError`
     UX degrades gracefully — every syntactically valid name will now read
     as "available" from check-team's perspective; actual collision is
     still caught at submit time via `handleFormSubmit`'s 409 response
     (`Team "${team}" is already provisioned...`, line 814-818), which
     already exists and is unaffected. `RequestAccessForm.vue`'s
     success-modal flow already handles a submit-time error via
     `formStatus`, so no new frontend error path is needed — this is
     recorded in tasks.md as a UX note for the reviewer, not a blocking
     change.

4. **Config plumbing.**
   - New Worker secret `TURNSTILE_SECRET_KEY` (via `wrangler secret put`,
     following the existing convention documented in the file header
     comment, lines 8-20, and `.env.example`'s "Secrets" section).
   - New public sitekey exposed to the frontend via
     `nuxt.config.ts`'s existing `runtimeConfig.public` block (alongside
     `baseUrlFront`), e.g. `public.turnstileSiteKey`, sourced from a new
     `NUXT_PUBLIC_TURNSTILE_SITE_KEY` env var, added to `.env.example`.
     Sitekeys are not secret (Cloudflare's own docs: safe to ship
     client-side), consistent with `baseUrlFront` already living in
     `public`.

5. **Frontend widget.**
   - Load `https://challenges.cloudflare.com/turnstile/v0/api.js` (async
     defer) and render a `cf-turnstile` widget in `ContactForm.vue` and
     `RequestAccessForm.vue`, gated behind the existing `BaseForm`
     component's submit flow — per the `turnstile-spin` skill's own
     "gate, don't replace" contract (SKILL.md, "The frontend-edit
     contract"): the existing `onSubmit` handlers keep their current
     logic; a Turnstile token is read from the widget and added to the
     JSON body already being POSTed by `useApi.ts`'s
     `submitContactForm`/`submitAccessRequest`, no other behavior changes.
   - A small `useTurnstile` composable (new file,
     `app/composables/useTurnstile.ts`) wraps script injection + widget
     render/reset, following the existing composable style in
     `app/composables/` (small, single-purpose, `ref`-based state, no
     external state library).

## Alternatives

1. **Deploy a separate managed siteverify Worker (turnstile-spin's default
   recipe).** Dropped: that recipe exists for callers who don't already own
   a backend terminating the form. Here, `cloudflare-worker/index.js`
   already is that backend, already holds `TELEGRAM_BOT_TOKEN`,
   `BACKSTAGE_LANDING_TOKEN`, etc. as Worker secrets, and already makes
   outbound calls to third-party APIs (Telegram, Backstage, Resend) inline
   in the request handler. Adding a second Worker hop (browser -> siteverify
   Worker -> browser -> mctl-landing-form Worker) would add latency, a new
   deployable, and a new CORS surface for zero benefit — the existing
   Worker can call `siteverify` itself exactly like it already calls
   Backstage and Telegram.
2. **Require full session-gating (GitHub-authenticated) on check-team**, as
   the issue's primary suggestion. Dropped for this proposal (see Open
   Questions) because `useTeamValidation.ts` calls check-team before OAuth
   necessarily completes, as live-typing feedback; gating it behind a
   session would require a frontend redesign of the request-access flow
   order (auth-then-type vs type-then-auth) beyond what this issue's
   "at minimum" fallback requires. Recorded as a valid stronger follow-up.
3. **Move the Cache-API rate limiter to Durable Objects / KV for
   accuracy.** Dropped: out of scope per the issue (which only asks for
   "per-IP rate limit", already structurally present via `RATE_LIMITS`);
   the existing Cache API approach's known eventual-consistency limitation
   is called out in its own comment (lines 143-145) and not something this
   issue's acceptance criteria require fixing.
4. **Client-side-only Turnstile (verify token shape in the browser, skip
   server-side siteverify).** Rejected outright — Turnstile is only a
   meaningful defense when the token is verified server-side against
   Cloudflare's siteverify API using the secret key; a client-only check is
   trivially bypassable and would not satisfy "Form POSTs without a valid
   Turnstile token are rejected" (issue acceptance criteria).

## Platform impact

- **Migrations:** none (no database/schema changes; Worker is stateless
  aside from Cache API rate-limit entries).
- **Backward compatibility:** additive JSON field (`turnstile_token`) on
  two existing POST bodies. Old frontend builds without the field will
  start getting rejected at `/api/contact`/`/api/submit` once the backend
  change deploys — **this requires the frontend deploy (Turnstile widget +
  token field) to ship no later than the backend enforcement**, or a
  short soft-launch window where the backend logs-but-doesn't-reject
  missing tokens. Recommendation captured in tasks.md: land the frontend
  widget in the same PR/release as backend enforcement, or use a feature
  flag / two-step rollout (verify-but-warn, then verify-and-reject) if
  independent deploy timing is a concern given `mctl-web`'s tag-triggered
  deploy (`tag-deploy.yml`, one image contains both frontend and worker
  source per `Dockerfile`/`nginx.conf` — check whether the Cloudflare
  Worker is deployed from the same image/pipeline or separately; if
  separate, coordinate the two rollouts).
- **Resource impact:** one additional outbound fetch (`siteverify`) per
  contact/submit/check-team request — Cloudflare's own dependency, same
  trust/latency tier as the existing Backstage/Telegram calls already made
  inline.
- **Risks + mitigations:**
  - *Risk:* Turnstile/siteverify outage blocks legitimate submissions
    (fail-closed design). *Mitigation:* this is the deliberate, required
    behavior per acceptance criteria ("fail closed"); Cloudflare's
    siteverify has its own high-availability SLA as a first-party service
    colocated with the Worker runtime, and this matches how
    `BACKSTAGE_LANDING_TOKEN`-missing is already handled as fail-closed
    500 today.
  - *Risk:* check-team's uniform-response change silently changes contract
    for any other consumer of `/api/github/check-team` beyond
    `useTeamValidation.ts`. *Mitigation:* grep confirms
    `useTeamValidation.ts` is the only caller in this repo; flag in PR
    description for reviewers to check `mctl-api`/other repos for external
    consumers.
  - *Risk:* secret rollout — `TURNSTILE_SECRET_KEY` must be set via
    `wrangler secret put` before the code deploy that reads it goes live,
    or the fail-closed path will 500 every contact/submit request.
    *Mitigation:* call this out explicitly as task 1 (provisioning),
    ordered before the code-deploy task, in tasks.md.
