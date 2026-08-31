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
      (e.g. `{ max: 20, windowSec: 60 }`). **No Turnstile on this
      endpoint** — see operator decisions 1-2: it is identity-gated
      instead, and a challenge on every debounced keystroke is bad UX.
      — DoD: rate limit entry present and exercised by a test.

- [ ] 8. Gate `handleCheckTeam` on the existing HMAC identity: require
      `login` and `sig` (query params, or the same `github_auth` shape the
      submit endpoint uses) and verify with
      `hmacVerify(login, sig, env.GITHUB_OAUTH_HMAC_KEY)`, exactly as
      `handleFormSubmit` does at `cloudflare-worker/index.js:785-789`.
      — DoD:
      * verified caller → today's truthful answer, unchanged
        (`{available:false}` for an existing tenant, `{available:true}`
        for a free name);
      * missing or invalid signature → **401**, one fixed body, identical
        for an existing and a non-existing name;
      * the 401 body must not vary with the queried name in any way —
        no echo of the name, no length-dependent content;
      * within each other failure class the response is likewise
        name-independent: rate limit stays **429 + Retry-After**, genuine
        Backstage/config failures stay **500**. Do NOT collapse these
        classes into one another — a caller still has to be able to tell
        "reauthenticate" from "back off" from "operator outage", and none
        of those distinctions reveals whether the name exists.

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
      (depends on 9) — DoD: same as 10, for the request-access form.
      `useTeamValidation.ts` does **not** send a Turnstile token; instead
      it sends the signed identity (`login` + `sig` from `useAuth`) and
      skips the call entirely when the user is not signed in, showing
      "sign in with GitHub to check availability" in the field rather than
      failing silently.

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

- [ ] T4. `handleCheckTeam` identity-gate and non-disclosure tests:
      * verified `login`+`sig`: stub Backstage 200 for name A and 404 for
        name B, assert the truthful `{available:false}` / `{available:true}`
        answers — the feature still works for signed-in users;
      * missing signature, and invalid signature: assert 401 with a body
        byte-identical for an existing and a non-existing name;
      * stub a Backstage 500 and assert 500 still surfaces (errors are not
        swallowed into a false "available");
      * assert none of the failure responses echo or vary with the queried
        name.

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

## Operator decisions (approve, 2026-08-31)

Open questions, resolved. The first two are linked and the proposal's
answers to them are inconsistent with each other, so read them together.

1. **`check-team`: gate it on the identity the codebase already has —
   reject both the always-`available: true` response and a new session
   mechanism.**

   The proposal keeps `check-team` anonymous "to preserve the UX of live
   availability feedback", and then, to stop enumeration, has it return
   `{ available: true }` unconditionally. Those two decisions cancel out.
   An endpoint that always says "available" does not preserve the feature;
   it makes it lie to every user, including authenticated ones, who then
   discover the collision at submit. A check that always says yes is worse
   than no check, because it looks like a check.

   Use the credential that already exists instead. `handleFormSubmit`
   (`cloudflare-worker/index.js:785-789`) already requires
   `github_auth.login` + `github_auth.sig` and verifies it with
   `hmacVerify(login, sig, GITHUB_OAUTH_HMAC_KEY)`; the signature is minted
   at OAuth callback (`index.js:588`). So:
   - `check-team` requires the same `login` + `sig` pair and verifies it the
     same way. Verified callers get the truthful answer they get today.
   - Unverified callers get a single uniform 401 that reveals nothing —
     byte-identical for existing and non-existing names.
   - Uniformity is required *within* each failure class, not across them.
     Rate limiting keeps its 429 + Retry-After and genuine server errors
     keep their 500: a caller still has to be able to tell "reauthenticate"
     from "back off" from "operator outage", and none of those distinctions
     says anything about whether the queried name exists. (An earlier draft
     of this decision asked for one response across all classes; that was
     wrong and would have made the endpoint undebuggable for no privacy
     gain.)
   - Anonymous enumeration is then closed completely rather than traded for
     a broken feature.

   This deliberately does **not** invent a stronger gate than the one on
   `/api/submit`. It leans on the 8h localStorage HMAC the proposal itself
   flags as weak — accepted, because `check-team` is strictly less
   sensitive than `submit`, which already accepts exactly this credential.
   Hardening that credential is one problem, in one place, and it is filed
   separately rather than solved twice.

   Frontend change, in scope: `app/composables/useTeamValidation.ts` must
   not call `check-team` without auth, and should say so in the field
   ("sign in with GitHub to check availability") rather than silently
   showing nothing. Checked before deciding: `RequestAccessSection.vue`
   renders `GithubAuth` directly above `RequestAccessForm` and always
   mounts the form, and `RequestAccessForm.vue`'s submit already refuses
   with `js.submit.github_required` when `authData` is absent — so the only
   behaviour lost is live feedback for someone typing a team name *before*
   signing in, and signing in is already required to get any further.

2. **No Turnstile on `check-team`.** Agreed with the proposal's reasoning —
   a challenge on every debounced keystroke is bad UX — and decision 1
   makes it moot.

3. **Turnstile in managed (non-intrusive) mode.** Accepted as proposed.

4. **Fail-closed behaviour accepted as written**, and it is the part most
   worth not softening later: missing `TURNSTILE_SECRET_KEY` → reject;
   siteverify network error or 5xx → reject. Do not add an "allow on
   verification-service outage" path.

Sequencing — this one can take the public site down if ignored:

5. **`TURNSTILE_SECRET_KEY` must exist in the worker environment before
   this merges.** Worker secrets are not in git and not in
   `.github/workflows/deploy.yml`; `cloudflare-worker/wrangler.toml` says
   they are set via the Cloudflare dashboard or `wrangler secret put`. With
   decision 4, deploying the code before the secret exists means
   `/api/contact` and `/api/submit` both reject every request — a total
   outage of both public forms, not a degraded mode. The Turnstile widget
   also has to be created for the `mctl.ai` zone first to get a sitekey for
   the frontend. Operator prerequisite, ahead of the PR: create the widget,
   put the secret, then merge.

6. **The sitekey is public and belongs to the frontend build, not the
   Worker.** Follow the proposal's task 3 as written:
   `NUXT_PUBLIC_TURNSTILE_SITE_KEY` in `.env.example` and exposed through
   `nuxt.config.ts`'s `runtimeConfig.public`. An earlier draft of this
   decision also offered `[vars]` in `wrangler.toml` as an alternative —
   that is wrong: Wrangler vars reach only the `mctl-landing-form` Worker,
   and the Worker consumes only the *secret*. The sitekey put there would
   never reach the prerendered browser bundle, the widget would never
   render, no token would be issued, and the fail-closed endpoints would
   reject every submission. Commit it; do not treat it as sensitive.

Out of scope, confirmed, with the follow-up filed rather than implied:

7. Replacing the 8h `localStorage` HMAC with server-side session
   re-validation stays out of scope here — see mctlhq/mctl-web#70.
