# Tasks: issue-39-consent-cloudflare-email-obfuscation-rep

- [ ] 1. Wrap the signed-in address in Cloudflare's `email_off` markers in
      `consentPage()`, `src/auth/routes.ts:124`. The line becomes
      `<p class="who">Signed in as <!--email_off-->${escapeHtml(params.email)}<!--/email_off-->.`
      — markers outside the `escapeHtml()` call, period outside the region, no
      other change to the paragraph or to `<span class="target">`.
      DoD: `npm run typecheck` passes; the rendered payload contains
      `<!--email_off-->owner@example.com<!--/email_off-->` when the suite runs;
      the visible sentence is byte-identical to today apart from the two
      comments.

- [ ] 2. Leave the reason at the site (depends on 1). Add a comment directly
      above the `who` paragraph in the voice of the existing note at
      `src/auth/routes.ts:115-117`: obfuscation is on zone-wide for this host,
      it rewrites addresses in HTML responses to `[email protected]`, its own
      `/cdn-cgi/scripts/.../email-decode.min.js` would restore the text but this
      response is `default-src 'none'` with no `script-src` so that script never
      runs — do not remove the markers, and do not add `script-src` to make the
      decoder work instead.
      DoD: a reader of `src/auth/routes.ts` who has never seen this issue can
      tell why the markers are there and what not to do about them.

- [ ] 3. Confirm the CSP is untouched (depends on 1). Verify
      `src/auth/routes.ts:386-389` still reads exactly as before, in particular
      that no `script-src` was added while working in the file.
      DoD: `git diff` for this change touches no header string;
      `tests/oauth.test.ts:616-619` (whole-directive `style-src 'self'` check)
      still passes.

- [ ] 4. Audit `/account` for the same shape, as the issue asks. Read
      `public/account.html:95-98,133-153` and `src/api/account.ts:49-62` and
      confirm the address is delivered as JSON and written with `textContent`
      after load, so it never passes the edge as HTML. Change nothing there
      unless the audit contradicts this.
      DoD: written finding in the PR description, plus test T3 below; no
      production code change in `public/account.html` or `src/api/account.ts`
      if the audit holds.

- [ ] 5. Leave `public/privacy.html:109` and `public/terms.html:80` alone
      (depends on 4). Those `mailto:` addresses are published contact details on
      pages served without a CSP, where the decode script runs normally;
      obfuscation there is harmless. State the decision in the PR description so
      the omission reads as considered rather than missed.
      DoD: no diff to either file; one sentence in the PR explaining why.

- [ ] 6. Open the PR against `mctlhq/seerrsense` referencing issue #39, with a
      Conventional Commit subject (`fix(consent): ...`) so `release-please`
      picks it up.
      DoD: CI green — `npm run check:tokens`, `npm run typecheck`, `npm test`
      with `TEST_DATABASE_URL` set, and the Docker build, per
      `.github/workflows/ci.yml`.

## Tests

- [ ] T1. New case in the `consent` describe block of `tests/oauth.test.ts`
      (alongside the style case at line 586): drive `/oauth/authorize` →
      `/oauth/google/callback` the way the existing cases do, extract every
      `<!--email_off-->([\s\S]*?)<!--\/email_off-->` region from
      `consent.payload`, and assert `ALLOWED_EMAIL` appears inside one of them.
      DoD: passes on the fixed code; fails if the opening or closing marker is
      misspelled.

- [ ] T2. Mutation half of T1, in the same case: strip every `email_off` region
      from the payload and assert the remainder does **not** contain
      `ALLOWED_EMAIL`. Comment why, in the file's existing voice: the assertion
      at line 580 (`toContain(ALLOWED_EMAIL)`) passes with or without the
      wrapper, because the defect is introduced downstream of the origin and is
      invisible to any test that only checks the address is present.
      DoD: reverting task 1 alone turns this case red; it also fails if a future
      edit renders the address a second time outside a region.

- [ ] T3. `/account` guard, in `tests/account.test.ts`: assert
      `GET /api/v1/account/connection` answers with a `content-type` containing
      `application/json`, and that the HTML from `GET /account` contains no
      address-shaped string. This makes the reason `/account` is unaffected an
      executable claim rather than a note.
      DoD: passes today; fails if someone starts rendering the address into
      `public/account.html` server-side or changes the endpoint's content type.

- [ ] T4. Extend the existing escaping case (`tests/oauth.test.ts:634-660`) or
      add an assertion beside it: the payload contains exactly one
      `<!--email_off-->` and one `<!--/email_off-->`. Guards the one way the
      untrusted value could interact with the new markup, even though
      `escapeHtml()` escaping `>` already makes an early comment close
      unreachable.
      DoD: passes; fails if a nested or duplicated region is introduced.

- [ ] T5. Manual verification against production, after deploy. Run the
      claude.ai connector flow against `https://seerrsense.mctl.ai/mcp` and read
      the `Signed in as` line on the consent screen. This is the only place the
      defect is observable, because it is introduced after the origin responds;
      no test in this repository can replace it.
      DoD: the screen names the real address; a view-source shows the
      `email_off` markers survived the edge and no `/cdn-cgi/l/email-protection`
      link is present in the `who` paragraph. Record the result on issue #39.

## Rollback

Revert the single commit and redeploy. The change is additive markup in one HTML
response with no schema, stored state, config or header change, so a revert is
complete and instant — the consent screen returns to showing
`[email protected]`, which is the current production behaviour, and the OAuth
flow itself is unaffected either way (it completes and issues tokens with or
without this fix). If the markers turn out to be correct but ineffective at the
edge, leave them in place — they are inert — and escalate the zone-level options
(disable Email Address Obfuscation for `mctl.ai`, or a Configuration Rule scoped
to `seerrsense.mctl.ai`) to whoever owns the zone as a separate change.
