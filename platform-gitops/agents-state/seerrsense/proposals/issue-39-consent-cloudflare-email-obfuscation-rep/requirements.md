# Keep the signed-in address readable on the consent screen under Cloudflare email obfuscation

## Context

The OAuth consent screen is the only screen SeerrSense renders for a person, and
its job is to let them confirm *which* identity a client is about to be
authorized against before pressing Allow. The paragraph that does this is built
in `consentPage()` at `src/auth/routes.ts:124`
(`<p class="who">Signed in as ${escapeHtml(params.email)}.`). In production on
`seerrsense.mctl.ai` the line reads `Signed in as [email protected].`, because
Cloudflare Email Address Obfuscation is enabled zone-wide on `mctl.ai` and
rewrites any address it finds in an HTML response into that placeholder plus a
`/cdn-cgi/l/email-protection#...` link, expecting its own
`/cdn-cgi/scripts/.../email-decode.min.js` to restore the text in the browser.

On this page that restoration never happens, and the repository can see why: the
response carries `default-src 'none'; style-src 'self'; img-src 'self';
form-action ...; base-uri 'none'` (`src/auth/routes.ts:386-389`) and declares no
`script-src`, so `default-src 'none'` blocks the decode script the edge injected.
The origin's own hardening and the edge's rewrite combine into a page that names
nobody. The flow still completes and the refresh token is still issued, so the
mechanism is cosmetic; the consequence is not, because a person with more than
one Google account cannot tell which one Google silently returned under
`prompt=none`. This is the second time an edge or policy layer has quietly
rewritten this specific page — the comment at `src/auth/routes.ts:115-117` and
the header of `public/assets/consent.css` record the first, an inline `<style>`
dropped silently by `style-src 'self'`.

## User stories

- AS a person authorizing an MCP client I WANT the consent screen to show the
  address I am actually signed in as SO THAT I can confirm the right Google
  account before granting access.
- AS a person with several Google accounts I WANT to see which account
  `prompt=none` returned SO THAT I can cancel and re-run the flow instead of
  authorizing a client against the wrong identity.
- AS a maintainer of `seerrsense` I WANT the fix to live in the template that
  owns the text SO THAT it needs no zone change, no DNS coordination, and
  survives a future edge configuration I do not control.
- AS a reviewer I WANT a test that fails when the protection is removed SO THAT
  the next refactor of `consentPage()` cannot silently reintroduce the defect.

## Acceptance criteria (EARS)

- WHEN `GET /oauth/google/callback` renders the consent page for a verified,
  allowlisted identity THE SYSTEM SHALL emit the signed-in address inside a
  region delimited by `<!--email_off-->` and `<!--/email_off-->`.
- WHILE the consent page is rendered THE SYSTEM SHALL contain no occurrence of
  the signed-in address outside an `email_off` region.
- WHEN the consent page is rendered THE SYSTEM SHALL keep the visible sentence
  unchanged for a reader — `Signed in as <address>.` — with no added whitespace,
  markup or element inside the `who` paragraph beyond the existing
  `<span class="target">`.
- WHILE rendering the address THE SYSTEM SHALL continue to pass it through
  `escapeHtml()` (`src/auth/routes.ts:67-74`), so that `>` cannot appear raw and
  no value can terminate the surrounding HTML comment early.
- WHEN the consent response is sent THE SYSTEM SHALL keep its existing
  Content-Security-Policy unchanged, including the absence of `script-src`, so
  no edge-injected script becomes executable on this page.
- IF the `email_off` wrapper is removed from `consentPage()` THEN THE SYSTEM
  SHALL fail the test suite, not merely the manual check in production.
- WHEN the account settings page (`GET /account`, `public/account.html`) and its
  JSON backend (`GET /api/v1/account/connection`,
  `src/api/account.ts:49-62`) are audited for the same shape THE SYSTEM SHALL
  either be shown not to render an address into served HTML, or be given the
  same protection.
- WHILE this change is deployed THE SYSTEM SHALL keep every existing consent
  behaviour intact: the single-use consent handle, the `deny` path, client-name
  escaping, and the stylesheet links asserted in `tests/oauth.test.ts:551-640`.

## Out of scope

- Turning Email Address Obfuscation off for the `mctl.ai` zone, or adding a
  Cloudflare Configuration Rule scoped to `seerrsense.mctl.ai`. Both are
  operator decisions outside this repository and must not be the first move.
- Relaxing the consent page CSP to let `/cdn-cgi/scripts/.../email-decode.min.js`
  run. Permitting an edge-injected script in order to repair edge-injected
  markup trades a cosmetic defect for a real weakening of the one screen that
  guards authorization.
- The `mailto:` addresses in `public/privacy.html:109` and
  `public/terms.html:80`. Those are published contact addresses on pages served
  without a restrictive CSP; obfuscation there is harmless and arguably wanted.
- Any change to the Google OIDC exchange, the allowlist check
  (`src/auth/routes.ts:355-359`), token issuance, or the consent state machine.
- Redesigning the consent screen or its copy.

## Open questions

- The issue states the consent screen is served by `GET /oauth/authorize`. In
  the clone `/oauth/authorize` only parks a pending login and redirects to
  Google (`src/auth/routes.ts:264-325`); the HTML is rendered by
  `GET /oauth/google/callback` (`src/auth/routes.ts:381-400`). Proceeding
  against the actual render site; no behavioural ambiguity results.
- Whether the operator will *also* scope a Cloudflare Configuration Rule to
  `seerrsense.mctl.ai` later. The origin-side wrapper is correct either way and
  is inert when obfuscation is off, so this proposal does not wait on it.
- Whether any future page should render an address server-side at all. Recorded
  as a convention question; this proposal only fixes the one page that does.
