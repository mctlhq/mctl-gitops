# Tasks: issue-66-turnstile-on-contact-submit-forms-harden

- [x] 1. **DONE by the operator, 2026-08-31 — do NOT create another
      widget.** Turnstile widget `mctl-ai-forms` exists in Cloudflare
      account `6a09f637d20e1f66a8e9d45ebe778058`: hostname `mctl.ai`,
      mode **Managed**, pre-clearance off.
      **Sitekey: `0x4AAAAAAEjFjEMuTRSzlzQc`** (public by design — it ships
      in the page and belongs in the repo).
      `localhost` / `127.0.0.1` were deliberately NOT added to the
      production widget's hostname list: for local development use
      Cloudflare's documented always-passes test keys
      (sitekey `1x00000000000000000000AA`, secret
      `1x0000000000000000000000000000000AA`) rather than widening where
      the production sitekey is valid.

- [x] 2. **DONE by the operator, 2026-08-31.** `TURNSTILE_SECRET_KEY` is
      set as a Worker secret on `mctl-landing-form`
      (`wrangler secret put`, upload confirmed). The fail-closed path in
      task 5/6 therefore cannot fire in production for a missing secret.
      The secret value is not in this repo, not in Vault, and not in
      gitops — Worker secrets live only in Cloudflare. Do not attempt to
      read it back; `wrangler secret list` shows names only.

- [ ] 3. Add `NUXT_PUBLIC_TURNSTILE_SITE_KEY` to `.env.example` and
      `runtimeConfig.public.turnstileSiteKey` in `nuxt.config.ts` (depends
      on 1) — DoD: `nuxt.config.ts` exposes the sitekey the same way
      `baseUrlFront` is exposed today, with the real value
      `0x4AAAAAAEjFjEMuTRSzlzQc` as the default; `.env.example` documents
      the new var under a new "Turnstile" section alongside existing
      sections. **Do not put the sitekey in `wrangler.toml [vars]`** —
      Wrangler vars reach the Worker, never the Nuxt bundle, so the widget
      would silently fail to render and both fail-closed forms would
      reject every submission.

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

- [ ] 8. Gate `handleCheckTeam` on the existing HMAC identity, and move
      the endpoint from `GET` to `POST` to do it. Today the route is
      `GET /api/github/check-team?name=…` (`cloudflare-worker/index.js:124`,
      handler at `:740`, reading `url.searchParams`). Change it to
      `POST /api/github/check-team` with a JSON body
      `{ name, github_auth: { login, sig } }` and verify with
      `hmacVerify(github_auth.login, github_auth.sig,
      env.GITHUB_OAUTH_HMAC_KEY)`, exactly as `handleFormSubmit` does at
      `cloudflare-worker/index.js:785-789`. `handleCheckTeam`'s signature
      changes from `(url, env, origin)` to `(request, env, origin)`.
      **The credentials MUST NOT travel in the query string, in any form
      — not `?sig=`, not a header-substitute crammed into the URL.** `sig`
      is an unbounded bearer — `hmacSign` signs the bare login with no
      expiry, and the 8h `AUTH_TTL` only governs the browser's own copy —
      so in a URL it lands in Cloudflare access
      logs, browser history, and outbound `Referer` headers. Today no
      credential appears in that URL at all, so a query-param design would
      *introduce* an exposure this issue is supposed to reduce. Moving the
      name into the body is a bonus: the queried tenant name stops being
      logged too. (An `Authorization` header would also satisfy the rule,
      but POST-with-body is chosen because it reuses the `github_auth`
      shape `handleFormSubmit` already validates.)
      — DoD:
      * verified caller → today's truthful answer, unchanged
        (`{available:false}` for an existing tenant, `{available:true}`
        for a free name);
      * missing or invalid signature → **401**, one fixed body, identical
        for an existing and a non-existing name.
        **This is a deliberate divergence from `handleFormSubmit`, which
        answers 401 for a missing `github_auth` and 403 for a bad `sig`
        — do not "align" check-team to that split.** Collapsing both into
        one 401 here is safe for the same reason the split is safe there
        (neither reveals anything about the queried *name*), and it is
        preferable because check-team is the endpoint an enumerator
        actually probes: one response means one thing to measure. On
        `/api/submit` the 401/403 split stays as it is today — that
        endpoint is not touched by this task, and changing its status
        codes would be an unrelated API break;
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
      contract. **The `onSubmit` error path must call the composable's
      `reset()` whenever the request reached the backend and failed
      (any non-2xx, and any thrown network error after send).** Turnstile
      tokens are single-use: without a reset, one Telegram-side 500 leaves
      the user holding a spent token, and every retry comes back 400
      "Verification failed" until they manually reload the page — a
      transient backend blip turns into a dead form.

- [ ] 11. Wire the Turnstile widget into `RequestAccessForm.vue` and
      thread the token through `useApi.ts`'s `submitAccessRequest` payload
      (depends on 9) — DoD: same as 10, for the request-access form,
      including the same `reset()`-on-failure requirement.
      `useTeamValidation.ts` does **not** send a Turnstile token; instead
      it switches to `POST` (per task 8) and sends
      `{ name, github_auth: { login, sig } }` with the signed identity
      from `useAuth` in the **body, never the query string**, and skips
      the call entirely when the user is not signed in, showing
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
      **The `GET` → `POST` change on `check-team` (task 8) is a separate,
      harder case and a soft-launch flag does not cover it.** A method
      change has no safe one-sided state: a new frontend POSTing at an old
      GET-only Worker fails, and an old frontend GETting at a new POST-only
      Worker fails — so "frontend first", which this task otherwise
      permits, breaks availability checking in one direction and
      Worker-first breaks it in the other. Pick one of:
      * ship Worker and frontend **atomically**, if the deploy pipeline
        can guarantee it; or
      * make the Worker accept **both** methods in this release — `POST`
        with the identity gate, and `GET` continuing to serve exactly
        today's unauthenticated behaviour — then remove `GET` in a
        follow-up PR once the new frontend is live. The transitional
        `GET` must **not** grow query-param credential support; it keeps
        its current anonymous semantics until it is deleted, and the
        follow-up issue to delete it is filed as part of this task, not
        left implicit.
      — DoD: the chosen option is stated in the PR description, and if the
      two-step option is taken, the follow-up issue number for removing
      `GET` is in the description too.

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
        name;
      * **assert the query-string path is not an accepted credential
        channel**: a request carrying a valid `login`/`sig` only as
        `?login=…&sig=…` (empty or absent JSON body) gets the same 401 as
        an unauthenticated caller. This is the test that keeps the
        credential out of access logs — without it, someone can
        "helpfully" restore query-param support later and every review
        after that reads green.

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
  **Exception — the check-team method change.** The sentence above is true
  only for the Turnstile field, which is additive. It is *not* true for
  task 8: a POST-only frontend left in place against a reverted GET-only
  Worker breaks availability checking outright. If the two-step
  both-methods rollout (task 13) was taken, this exception does not
  apply — the reverted Worker still answers `GET`. If the atomic rollout
  was taken, a Worker rollback **must** revert the frontend with it.
  Whichever was chosen has to be named in the PR description precisely so
  that whoever runs the rollback knows which of these two worlds they are
  in.
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
   `/api/submit`. It leans on the localStorage HMAC the proposal itself
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
   this merges — ✅ SATISFIED 2026-08-31, before implementation starts.**
   Worker secrets are not in git and not in
   `.github/workflows/deploy.yml`; `cloudflare-worker/wrangler.toml` says
   they are set via the Cloudflare dashboard or `wrangler secret put`. With
   decision 4, deploying the code before the secret exists means
   `/api/contact` and `/api/submit` both reject every request — a total
   outage of both public forms, not a degraded mode. The operator has
   therefore already created the widget (`mctl-ai-forms`, sitekey
   `0x4AAAAAAEjFjEMuTRSzlzQc`) and uploaded the secret to
   `mctl-landing-form`; tasks 1 and 2 are marked done above. **Do not
   create a second widget and do not re-put the secret** — a fresh
   `wrangler secret put` with a different value would invalidate the
   deployed one.

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

Added 2026-08-31 after the agy reviewer's P2/P3 on this decisions PR — both
findings were correct and both are defects this decision introduced, not
pre-existing ones:

7. **The identity travels in a POST body, never in the URL** — decision 1
   originally permitted "query params" as one way to pass `login`/`sig` to
   `check-team`. That was wrong. `sig` is an unbounded bearer (no expiry is signed or checked; the 8h
   `AUTH_TTL` is a browser-side convenience only), and
   `check-team` is a `GET`, so query params would have written a live
   credential into Cloudflare access logs, browser history, and outbound
   `Referer` headers. The endpoint today carries no credential in its URL
   at all, so this would have *created* an exposure while nominally
   hardening the endpoint. The endpoint therefore moves `GET` → `POST`
   with `{ name, github_auth: { login, sig } }`, reusing the shape
   `handleFormSubmit` already validates. T4 asserts that a query-string
   identity is rejected, so the door cannot be quietly reopened later.

8. **The frontend resets the Turnstile widget when a submission fails
   after reaching the backend.** Turnstile tokens are single-use, so
   without a reset a transient Telegram/Backstage 500 leaves the user
   holding a spent token: every retry returns 400 "Verification failed"
   until they reload the page by hand. A backend blip would present as a
   permanently broken form. Folded into tasks 10 and 11 rather than left
   as a UX note.

Out of scope, confirmed, with the follow-up filed rather than implied:

9. Replacing the non-expiring `localStorage` HMAC with server-side session
   re-validation stays out of scope here — see mctlhq/mctl-web#70.

   **Correction to this proposal's threat model, 2026-08-31, from the
   codex reviewer.** Earlier revisions of all three files — and my own PR
   comment — called `sig` an "8-hour bearer". That is wrong, and it
   understated the problem. `hmacSign` signs the bare `login` and nothing
   else; `hmacVerify(login, sig, secret)` recomputes over that same bare
   login. No expiry is signed and none is checked. `AUTH_TTL = 8h`
   (`useAuth.ts:6,37`) only decides when the *browser* throws away its own
   copy — an attacker holding a copied `sig` is not bound by it. A leaked
   signature is replayable by any HTTP client indefinitely, and the only
   revocation is rotating `GITHUB_OAUTH_HMAC_KEY`, which logs out every
   user at once.

   Two consequences, both of which should be carried into mctl-web#70:
   (a) decision 7 gets stronger, not weaker — putting a *permanent*
   bearer in a URL is worse than putting an 8-hour one there; (b) #70 is
   not the tidy-up it reads as. This task makes `sig` the sole gate on a
   third endpoint, so the absence of any expiry or revocation is now
   load-bearing in three places. Do not let "it expires in 8 hours"
   survive anywhere in the eventual #70 discussion.
