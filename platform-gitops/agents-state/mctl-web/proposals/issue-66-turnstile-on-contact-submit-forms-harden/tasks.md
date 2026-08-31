# Tasks: issue-66-turnstile-on-contact-submit-forms-harden

- [ ] 1. Create the Turnstile widget (managed mode) via Cloudflare
      dashboard or `turnstile-spin` skill's `widget-create.sh`, scoped to
      `mctl.ai` + `localhost` + `127.0.0.1`. Record the sitekey and secret.
      — DoD: sitekey obtained; secret never committed to the repo.

- [ ] 2. Provision `TURNSTILE_SECRET_KEY` as a Cloudflare Worker secret for
      `mctl-landing-form` via `wrangler secret put TURNSTILE_SECRET_KEY`
      (depends on 1). — DoD: secret set in the Worker's production
      environment, verifiable via `wrangler secret list` (name present,
      value not shown); done *before* task 4 deploys, so the fail-closed
      path never fires in production for a missing secret.

- [ ] 3. Add `NUXT_PUBLIC_TURNSTILE_SITE_KEY` to `.env.example` and
      `runtimeConfig.public.turnstileSiteKey` in `nuxt.config.ts` (depends
      on 1) — DoD: `nuxt.config.ts` exposes the sitekey the same way
      `baseUrlFront` is exposed today; `.env.example` documents the new
      var under a new "Turnstile" section alongside existing sections.

- [ ] 4. Add `verifyTurnstileToken(token, secret, remoteip, fetchImpl)` to
      `cloudflare-worker/index.js`, exported like `hmacVerify` /
      `sessionIsLive`, calling
      `https://challenges.cloudflare.com/turnstile/v0/siteverify` with a
      injectable `fetchImpl` param (default `fetch`) for testability — DoD:
      function exported, handles missing-secret (`not_configured`),
      missing/empty token (`missing_token`), non-2xx/network error
      (`network_error`), and Cloudflare `success: false`
      (`error-codes[0]`) as distinct `reason` values without ever
      throwing.

- [ ] 5. Wire `verifyTurnstileToken` into `handleContactForm` — read
      `turnstile_token` from the JSON body, verify before the Telegram
      call, return 400 `{success: false, message: 'Verification failed,
      please try again.'}` on failure, 500 `{success: false, message:
      'Server misconfiguration'}` if `env.TURNSTILE_SECRET_KEY` is unset
      (depends on 4) — DoD: no Telegram POST occurs when verification
      fails; existing 400 branches (missing fields, invalid email, short
      message) still run in their current order relative to the new check
      (Turnstile check happens after basic shape validation, so malformed
      requests still get their existing specific error messages, not a
      generic Turnstile rejection).

- [ ] 6. Wire `verifyTurnstileToken` into `handleFormSubmit` — same
      pattern, verified before the tenant-existence check / Backstage
      provisioning call (depends on 4) — DoD: no Backstage POST and no
      Telegram POST occurs when verification fails; existing HMAC/team-name
      validation order preserved (Turnstile check added after the existing
      `github_auth` HMAC check, so an unauthenticated caller still gets
      401 "GitHub authentication required" rather than a Turnstile error,
      preserving today's most-specific-error-first behavior).

- [ ] 7. Add `/api/github/check-team` to `RATE_LIMITS`
      (e.g. `{ max: 20, windowSec: 60 }`) and add Turnstile verification
      via a `?turnstile_token=` query param, sourced once per form session
      on the frontend (depends on 4) — DoD: `handleCheckTeam` rejects
      missing/invalid Turnstile tokens the same way contact/submit do;
      rate limit entry present and exercised by a test.

- [ ] 8. Change `handleCheckTeam`'s response to return `{available: true}`
      uniformly (200) for both Backstage-exists and Backstage-404 cases,
      once format validation + Turnstile + rate-limit checks pass; keep
      500 for genuine Backstage/config errors — DoD: response body and
      status code are identical for a known-existing tenant name and an
      unused one, verified by a test that stubs both Backstage outcomes.

- [ ] 9. Add a `useTurnstile` composable
      (`app/composables/useTurnstile.ts`) that injects
      `https://challenges.cloudflare.com/turnstile/v0/api.js` (async
      defer) and exposes a `render`/`reset`/`token` interface, following
      the style of existing composables (`useContactForm.ts`,
      `useTeamValidation.ts`) — DoD: composable is SSR-safe (no-op on
      `import.meta.server`, matching the guard pattern already used in
      `useAuth.ts`'s `parseOAuth`/`cleanUrl`).

- [ ] 10. Wire the Turnstile widget into `ContactForm.vue`, gating the
      existing `onSubmit` handler on a present token (depends on 9) — DoD:
      existing `useForm`/`yup` validation and `submitContactForm` call are
      unchanged except for the added `turnstile_token` field in the
      payload sent by `useApi.ts`'s `submitContactForm`; a visible
      Turnstile widget renders in the form per the "gate, don't replace"
      contract.

- [ ] 11. Wire the Turnstile widget into `RequestAccessForm.vue` and
      thread the token through `useApi.ts`'s `submitAccessRequest` payload
      (depends on 9) — DoD: same as 10, for the request-access form;
      `useTeamValidation.ts`'s debounced `checkAvailability` call also
      passes the current token as `?turnstile_token=` when calling
      check-team.

- [ ] 12. Update `useApi.ts` to accept and send `turnstile_token` in both
      `submitAccessRequest` and `submitContactForm` payloads (depends on
      9) — DoD: type signatures updated, both POST bodies include the new
      field.

- [ ] 13. Coordinate rollout ordering: confirm whether the Cloudflare
      Worker (`cloudflare-worker/index.js`) deploys independently of the
      Nuxt frontend image (check `.github/workflows/` and `tag-deploy.yml`
      referenced in `CLAUDE.md`); if independent, sequence so the frontend
      (widget + token field) ships before or atomically with backend
      enforcement, or add a temporary soft-launch flag that logs-but-does-
      not-reject missing tokens for one release — DoD: rollout plan
      documented in the PR description; no production window exists where
      old frontend builds get hard-rejected by new backend enforcement
      without a deliberate decision to accept that.

## Tests

- [ ] T1. `verifyTurnstileToken` unit tests (new
      `cloudflare-worker/turnstile.test.mjs`, following
      `oauth.test.mjs`'s `node:test` + `node:assert/strict` style, with a
      stub `fetchImpl`): missing secret -> `not_configured`; missing/empty
      token -> `missing_token`; stub returns `{success: true}` ->
      `{success: true}`; stub returns `{success: false, 'error-codes':
      ['timeout-or-duplicate']}` -> `{success: false, reason:
      'timeout-or-duplicate'}`; stub throws/network error ->
      `{success: false, reason: 'network_error'}`.

- [ ] T2. `handleContactForm` integration-style tests (call the exported
      `fetch` handler or `handleContactForm` directly with a stub `env`
      and injected Turnstile fetch stub): valid fields + valid token ->
      200 success, Telegram stub called; valid fields + missing token ->
      400, Telegram stub NOT called; valid fields + failing-verify token
      -> 400, Telegram stub NOT called; missing `TURNSTILE_SECRET_KEY` ->
      500, Telegram stub NOT called.

- [ ] T3. `handleFormSubmit` integration-style tests: valid `github_auth`
      + valid team + valid token -> proceeds to Backstage stub; valid
      `github_auth` + valid team + missing/invalid token -> 400, Backstage
      stub NOT called; invalid `github_auth.sig` -> still 403 (existing
      behavior) even with a valid Turnstile token, confirming check order
      from task 6's DoD.

- [ ] T4. `handleCheckTeam` uniform-response test: stub Backstage to
      return 200 for name A and 404 for name B; assert both produce
      identical `{available: true}` 200 responses once Turnstile/rate-limit
      pass; stub a Backstage 500 and assert the endpoint still returns 500
      (errors are not silently swallowed into a false "available").

- [ ] T5. Rate-limit test for `/api/github/check-team`: drive
      `checkRateLimit` (already exported-testable pattern, or via the
      `fetch` handler with a stubbed Cache) past the new `max` within
      `windowSec` and assert a 429 with `Retry-After`.

- [ ] T6. Existing `oauth.test.mjs` suite still passes unmodified (no
      regression in OAuth/session helpers from this change).

## Rollback

- The Turnstile checks are additive branches inside existing handler
  functions and the check-team response change is a single conditional
  simplification — revert is a straight `git revert` of the feature PR's
  merge commit (per `CLAUDE.md`'s branch+PR workflow: `git checkout -b
  fix/revert-turnstile-hardening`, `git revert -m 1 <merge-sha>`, PR,
  merge).
- If only the *frontend* needs rolling back (e.g. widget causes a
  layout/UX regression) while keeping backend enforcement, temporarily
  flip backend enforcement to soft-fail (log-only) via the rollout flag
  from task 13, redeploy the Worker, then revert the frontend PR
  separately — this avoids stranding users who can no longer submit
  either form.
- If only the *backend* needs rolling back (e.g. `TURNSTILE_SECRET_KEY`
  provisioning issue causing fail-closed 500s in production), the Worker
  deploy can be rolled back independently via `mctl_rollback_service` /
  the platform's existing Worker deploy mechanism (`tag-deploy.yml` per
  `CLAUDE.md`), redeploying the previous image tag; the frontend widget
  is harmless to leave in place (it just sends an unused `turnstile_token`
  field) while the backend is rolled back.
- No data migrations occur, so rollback carries no data-loss risk; Cache
  API rate-limit entries and Turnstile widget/sitekey can remain
  provisioned even after a code rollback with no side effects.
