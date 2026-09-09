# Design: issue-39-consent-cloudflare-email-obfuscation-rep

## Current state

**Where the consent HTML is built.** `consentPage()` in `src/auth/routes.ts:95-145`
returns a single template literal. The relevant line is 124:

```ts
  <p class="who">Signed in as ${escapeHtml(params.email)}.
    <span class="target">You will be returned to ${escapeHtml(params.redirectHost)}</span>
  </p>
```

`escapeHtml()` (`src/auth/routes.ts:67-74`) replaces `&`, `<`, `>`, `"` and `'`.
Every interpolation in the template goes through it.

**Where it is served.** Not from `/oauth/authorize`. That route
(`src/auth/routes.ts:264-325`) validates the request against
`AuthorizeQuerySchema`, resolves the client, parks a pending login via
`store.putPendingAuth`, and 302s to Google. The HTML is sent from
`GET /oauth/google/callback` (`src/auth/routes.ts:381-400`) after the ID token is
verified and `config.allowedEmails` admits the address, with `email:
identity.email` passed straight into `consentPage()`.

**The response headers.** `src/auth/routes.ts:386-389` sets:

```
default-src 'none'; style-src 'self'; img-src 'self';
form-action 'self' https: http://localhost:* http://127.0.0.1:*; base-uri 'none'
```

There is no `script-src`, so `default-src 'none'` governs scripts and blocks all
of them. This is the missing half of the issue's account of the bug: Cloudflare
rewrites the address to `[email protected]` and injects
`/cdn-cgi/scripts/.../email-decode.min.js` to put it back, and this page's own
CSP refuses to run that script. The rewrite lands; the repair does not. On the
static pages (`/privacy`, `/terms`, served by `reply.sendFile` in
`src/api/server.ts:196-201` with no CSP header) the decode script does run,
which is why only this page shows the placeholder.

**The precedent in the file.** `src/auth/routes.ts:115-117` and the header
comment in `public/assets/consent.css:1-10` both record the earlier incident: an
inline `<style>` block dropped silently under `style-src 'self'`, invisible to
the server, discovered only by looking at the rendered page. The repository's
convention is to leave the reason in the code at the point where a future
refactor would undo it.

**What the tests already assert.** `tests/oauth.test.ts:551-584` renders the
consent page through `app.inject` and asserts
`expect(consent.payload).toContain(ALLOWED_EMAIL)`. That assertion passes today
against the origin's own output — the defect is introduced downstream of the
origin, so no existing test can see it. `tests/oauth.test.ts:586-631` is the
closest model for what is needed here: it asserts the *absence* of a shape
(`<style`, ` style=`) and compares CSP directives whole rather than as
substrings, precisely because the failure mode is silent.

**The `/account` page.** It never renders an address into served HTML.
`src/api/server.ts:190-194` sends the static `public/account.html`; the address
arrives later from `GET /api/v1/account/connection`
(`src/api/account.ts:49-62`), which replies `application/json`, and the browser
writes it with `status.textContent = message` (`public/account.html:95-98`,
called at lines 146 and 150). Cloudflare's obfuscator rewrites HTML response
bodies; a JSON body is not rewritten, and a string assembled in the DOM after
load never passes the edge as markup. So `/account` is not affected by this
mechanism — but only as long as those two properties hold, and neither is
currently asserted anywhere.

## Proposed solution

Three changes, all inside `seerrsense`, none touching the zone.

**1. Wrap the address in Cloudflare's documented origin-side opt-out.**
In `consentPage()`, line 124 becomes:

```ts
  <p class="who">Signed in as <!--email_off-->${escapeHtml(params.email)}<!--/email_off-->.
```

`<!--email_off-->...<!--/email_off-->` tells the obfuscator to leave the enclosed
region alone. It needs no zone change, no DNS coordination and no Cloudflare
credential, it lives in the template that owns the text, and it is inert when
obfuscation is off — so local runs, the test suite, self-hosted deployments and
any future Configuration Rule all behave identically.

The wrapper is placed *inside* the sentence and *outside* nothing else: the
period stays outside the region so the rendered text is byte-identical to today
for a reader, and HTML comments are not rendered, so `.who` in
`public/assets/consent.css:17-20` is unaffected.

Ordering with escaping matters and is safe as written. `escapeHtml()` escapes
`>` to `&gt;`, so no value of `params.email` can emit `-->` and terminate the
comment early — the untrusted string cannot escape the region it is wrapped in,
and cannot turn the rest of the page into comment text either. The wrapper must
therefore stay *outside* the `escapeHtml()` call; wrapping before escaping would
render the literal markers as visible text.

**2. Leave a comment at the site, matching the file's existing convention.**
Directly above the `who` paragraph, in the same voice as
`src/auth/routes.ts:115-117`:

> The address is wrapped in Cloudflare's `email_off` markers because Email
> Address Obfuscation is on zone-wide for the host this runs on, and rewrites
> any address in an HTML response to `[email protected]`. Its own decode script
> would normally restore the text, but this response is `default-src 'none'`
> with no `script-src`, so that script never runs and the placeholder is what
> the user sees. Do not remove the markers; do not add `script-src` to make the
> decoder work instead.

This is the load-bearing part of the change for anyone reading the file later:
without it the markers look like dead syntax and get tidied away.

**3. Pin the invariant with mutation-sensitive tests.**
A new case in the `consent` describe block of `tests/oauth.test.ts`, alongside
the existing style case, that:

- extracts every `<!--email_off-->(...)<!--/email_off-->` region from
  `consent.payload` and asserts `ALLOWED_EMAIL` appears in one of them; and
- asserts the address occurs *nowhere else* in the payload — strip the
  `email_off` regions from the string and assert the remainder does not contain
  `ALLOWED_EMAIL`.

The second half is what makes the test mutation-sensitive: with the wrapper
removed, the address is still in the payload (so the existing line 580 assertion
still passes) but it is no longer inside any region, and both halves fail. It
also catches a future edit that renders the address a second time somewhere
unprotected.

A companion case for `/account` records the audit as an executable claim rather
than a comment: assert `GET /api/v1/account/connection` answers with a
`content-type` containing `application/json`, and that the HTML served by
`GET /account` does not contain an `@`-shaped address. That is the cheapest form
of "check `/account` for the same shape" the issue asks for, and it converts the
reason `/account` is safe into something CI defends.

No new files, no new dependency, no route or header change.

## Alternatives

**Turn Email Address Obfuscation off for the `mctl.ai` zone.** One switch, fixes
every current and future page, and removes the class of bug rather than one
instance. Dropped as the *first* move: the setting is zone-wide and affects every
service behind `mctl.ai`, not just `seerrsense`; the decision belongs to whoever
owns the zone; and it leaves this repository with no defence if the setting is
ever re-enabled or the service moves behind another edge with the same feature.
Worth raising with the operator as a separate item — the origin-side wrapper
costs nothing if it later happens.

**A Cloudflare Configuration Rule scoped to `seerrsense.mctl.ai`.** Narrower
blast radius than the zone switch and still one place to reason about. Dropped
for the same ownership reason, plus a worse one: the fix would live in a console
nobody reading `src/auth/routes.ts` can see, which is exactly the failure mode
the `consent.css` comment exists to prevent. It also does not travel with the
code to a self-hosted deployment.

**Add `script-src https://seerrsense.mctl.ai` (or a `/cdn-cgi/` source) to the
consent CSP so the decode script runs.** Repairs the symptom using the
mechanism Cloudflare intends. Dropped firmly: it makes the one screen that
guards authorization capable of executing script injected between the origin and
the browser, in exchange for cosmetics. `default-src 'none'` on this page is a
deliberate property, and the existing test at `tests/oauth.test.ts:616-619`
already treats CSP weakening as a regression.

**Render the address client-side, the way `/account` does — ship a placeholder
and fill it from a JSON endpoint.** Sidesteps the obfuscator structurally, and
there is precedent in the codebase. Dropped: it requires `script-src` on this
page for the same reason as above, turns a static confirmation screen into one
that can fail to populate, and adds an unauthenticated-ish endpoint that returns
the pending login's address keyed by the consent handle. Far more surface than
two comment markers.

## Platform impact

- **Migrations.** None. No schema, no stored state, no config, no environment
  variable. `AuthStore` (`src/auth/store.ts`, `src/auth/store-pg.ts`) is
  untouched.
- **Backward compatibility.** Full. The change is additive markup inside one
  HTML response; comments are ignored by every HTML parser. The consent form,
  its single-use handle (`src/auth/routes.ts:364-371`, `403-437`), the CSP, and
  every other route are unchanged. Rendered text is identical for a reader.
- **Resource impact.** About 30 bytes on one response that is served once per
  authorization. Nil.
- **Deployment.** Ships as an ordinary image rollout through the normal release
  path (`release-please`, `.github/workflows/release-binaries.yml`). No
  coordination with the edge, no cache purge needed — the consent response is
  `cache-control: no-store` (`src/auth/routes.ts:390`).
- **Risk: the marker syntax is wrong or the region is mis-nested.** Cloudflare
  matches `<!--email_off-->` and `<!--/email_off-->` exactly. Mitigation: the new
  test asserts the address is inside a *matched* region, so a typo in either
  marker fails CI. The residual risk — correct markers that the edge ignores for
  some other reason — is only observable in production, which is why the manual
  verification step is retained in `tasks.md`.
- **Risk: a future refactor of `consentPage()` drops the markers.** Mitigation:
  the mutation-sensitive test, plus the in-code comment explaining why they are
  there. This is the same pair of defences the earlier inline-`<style>` incident
  left behind, and that one has held.
- **Risk: the escaped address terminates the HTML comment.** Not reachable —
  `escapeHtml()` escapes `>`, so `-->` cannot be emitted. Mitigation: keep the
  markers outside the `escapeHtml()` call, and keep the existing XSS-escaping
  test (`tests/oauth.test.ts:634-660`) green; consider extending it to assert
  the payload still contains exactly one `<!--/email_off-->`.
- **Residual exposure.** Any *new* server-rendered page that prints an address
  will hit this again. This proposal fixes the one page that does and asserts
  `/account` does not; it does not add a general guard. Recorded in
  `requirements.md` under Open questions.
