# Turnstile on contact/submit forms; harden unauthenticated check-team

## Context
The public Cloudflare Worker (`cloudflare-worker/index.js`, service `mctl-landing-form`)
exposes three POST/GET endpoints with no bot protection beyond a coarse
per-IP Cache API rate limiter (`RATE_LIMITS` / `checkRateLimit`, lines 41-46
and 147-165): `GET /api/github/check-team`, `POST /api/contact`, and
`POST /api/submit`. `check-team` (`handleCheckTeam`, lines 740-775) proxies
Backstage's tenant lookup and returns a distinguishable response for
"tenant exists" (200, `available: false`) vs "tenant does not exist" (404
from Backstage, mapped to `available: true`) to any anonymous caller — this
lets anyone enumerate provisioned tenant/team names. `handleContactForm`
(lines 923-980) and `handleFormSubmit` (lines 779-919) accept POST bodies
and forward them to Telegram (and, for submit, to Backstage's tenant
provisioning API) with only shape/length validation — no CAPTCHA, no proof
of human origin. `submit` does require a GitHub-derived HMAC signature
(`github_auth.sig`, verified in `handleFormSubmit` via `hmacVerify`), but
that signature is minted once at OAuth callback time and cached client-side
in `localStorage` for 8 hours (`useAuth.ts`, `AUTH_TTL = 8 * 60 * 60 * 1000`,
`restore()`) without re-checking that the underlying GitHub session is
still valid — a stolen or replayed `mctl_auth` localStorage blob remains a
usable credential against `/api/submit` for up to 8 hours after the user's
actual GitHub session may have ended.

The repo already ships a `turnstile-spin` skill
(`.claude/skills/turnstile-spin/SKILL.md`) for wiring up Cloudflare
Turnstile end-to-end, but no Turnstile widget, sitekey, or siteverify call
exists anywhere in `app/` or `cloudflare-worker/index.js` today. This
proposal closes both abuse surfaces named in the issue: add Turnstile to
the two public forms, and stop `check-team` from leaking tenant existence
to anonymous callers. Fixing the 8h-HMAC/session-revalidation weakness in
`useAuth.ts` is flagged but the GitHub-token-in-session redesign is
explicitly out of scope (companion issue per the issue body); this proposal
narrows the localStorage-HMAC problem down to what's addressable without
that redesign (see Acceptance criteria and Out of scope).

## User stories
- AS an anonymous site visitor I WANT the contact and request-access forms
  to reject automated/bot submissions SO THAT the team's Telegram channel
  and Backstage provisioning workflow are not spammed.
- AS a platform operator I WANT `check-team` to stop revealing which team
  names are already provisioned SO THAT attackers cannot enumerate tenant
  names via anonymous 200/404 probing.
- AS a platform operator I WANT worker tests covering submit/contact/rate-limit
  paths SO THAT this hardening does not silently regress in future changes.
- AS a returning user with a stale browser session I WANT `/api/submit` to
  not accept a locally-cached credential indefinitely SO THAT a leaked
  `mctl_auth` localStorage value has a bounded blast radius consistent with
  the documented 8h TTL and cannot be replayed after that TTL.

## Acceptance criteria (EARS)
- WHEN a client POSTs to `/api/contact` without a valid Turnstile token
  THE SYSTEM SHALL reject the request with 4xx and SHALL NOT forward the
  message to Telegram.
- WHEN a client POSTs to `/api/submit` without a valid Turnstile token
  THE SYSTEM SHALL reject the request with 4xx and SHALL NOT call the
  Backstage tenant-provisioning API or notify Telegram.
- WHEN a client POSTs to `/api/contact` or `/api/submit` with a Turnstile
  token that fails Cloudflare siteverify (invalid, expired, reused, or
  wrong sitekey) THE SYSTEM SHALL reject the request with 4xx and SHALL
  return a generic error message that does not reveal siteverify's
  internal error codes.
- WHEN a client POSTs to `/api/contact` or `/api/submit` with a valid,
  unexpired Turnstile token THE SYSTEM SHALL proceed with existing
  validation and downstream behavior (Telegram notification / Backstage
  submission) unchanged from today.
- WHEN an anonymous (unauthenticated) client calls
  `GET /api/github/check-team` for an existing tenant THE SYSTEM SHALL
  return the same response shape and status family as for a non-existing
  tenant, so anonymous 200-vs-404 (or field-content) enumeration is no
  longer possible.
- WHEN a request to `/api/github/check-team` is rejected for rate-limit or
  auth reasons THE SYSTEM SHALL return a response that does not itself leak
  whether the queried name exists.
- IF the caller of `check-team` is not authenticated (no valid session)
  THEN THE SYSTEM SHALL still allow the request to proceed (per the issue's
  "at minimum Turnstile + per-IP rate limit" fallback) but SHALL apply
  Turnstile verification and a tightened per-IP rate limit before querying
  Backstage.
- WHILE the `TURNSTILE_SECRET_KEY` (or equivalent) environment secret is
  unset or empty THE SYSTEM SHALL fail closed on `/api/contact` and
  `/api/submit` (reject with 5xx "server misconfiguration", matching the
  existing `BACKSTAGE_LANDING_TOKEN`-missing pattern in `handleCheckTeam`,
  lines 751-754) rather than silently skipping verification.
- WHEN the Cloudflare siteverify API call itself fails or times out
  (network error, 5xx from Cloudflare) THE SYSTEM SHALL treat the request
  as failed verification (fail closed) and return 4xx/5xx rather than
  allowing the submission through.
- WHEN worker tests are run (`node --test cloudflare-worker/*.test.mjs`)
  THE SYSTEM SHALL exercise: missing-token rejection, invalid-token
  rejection, valid-token pass-through, and rate-limit-exceeded rejection
  for both `/api/submit` and `/api/contact`, plus the check-team
  uniform-response behavior.
- IF the stored `mctl_auth` localStorage entry (`useAuth.ts`) is older than
  its `exp` (8h TTL) THEN `restore()` SHALL continue to discard it (already
  true today) — no regression permitted here.

## Out of scope
- Removing the GitHub access token from the session payload
  (`mcpPayload.token` / OAuth session redesign) — explicit companion issue
  per the issue body, requires mctl-api changes (see `mctlhq/mctl-api#218`
  referenced in `cloudflare-worker/index.js` comments).
- Replacing the 8h localStorage HMAC credential with server-side session
  re-validation against a live GitHub session on every `/api/submit` call.
  That requires either a GitHub API round-trip per submit or a server-side
  session store, both bigger changes than "add Turnstile + fix check-team
  enumeration." Recorded as a follow-up.
- Adding Turnstile to `/api/github/login`, `/api/github/callback`, or
  `/api/github/session` — these are OAuth-flow endpoints, not free-form
  forms, and already carry state-cookie CSRF protection.
- Any change to the Backstage tenant-management API itself.
- Migrating the rate limiter off the Cache API to KV/D1 (issue does not
  ask for this; current limiter is "reasonable abuse protection" per its
  own comment, lines 143-145).
- Building a brand-new siteverify proxy Worker (as the `turnstile-spin`
  skill's default recipe does) — see design.md Alternatives for why
  siteverify is called in-process instead.

## Open questions
- The issue says check-team should "require the authenticated session (or
  at minimum Turnstile + per-IP rate limit)". Requiring the session cookie
  would break the current UX, where `useTeamValidation.ts` calls
  `check-team` live as the user types a team name *before* they have
  necessarily completed GitHub OAuth (it's used for inline debounced
  availability feedback in `RequestAccessForm.vue`, not gated behind auth
  in the UI). Full session-gating would need a frontend flow change. This
  proposal takes the "at minimum" fallback explicitly offered by the issue:
  Turnstile + tightened per-IP rate limit + uniform response shape, without
  requiring a session. Flagged for reviewer sign-off; full session-gating
  is a reasonable follow-up if product wants to hide check-team from
  logged-out visitors entirely.
- Whether the Turnstile widget should be "managed" (visible, adaptive
  challenge) or "invisible" mode. Given these are low-friction
  contact/request forms, this proposal assumes **managed (non-intrusive)**
  mode, consistent with the `turnstile-spin` skill's default
  recommendation. Reviewer can override.
- Exact uniform response body for check-team is not specified by the
  issue beyond "does not distinguish". This proposal specifies
  `{ available: true }` unconditionally for any syntactically valid,
  Turnstile-verified, rate-limit-passing request (see design.md) — i.e.
  the endpoint becomes advisory-only for anonymous callers and stops being
  a reliable existence oracle. The Backstage-side authoritative check
  still happens at `/api/submit` time (lines 806-822), so this does not
  weaken duplicate-tenant prevention.
- Whether Turnstile should also gate `check-team`'s frequent debounced
  calls (fired on every valid keystroke pause) — a per-request Turnstile
  challenge on every keystroke-driven call is poor UX. This proposal
  instead applies Turnstile only where the issue explicitly requires it
  (contact, submit) and relies on a tightened rate limit + response
  uniformity for check-team, per the issue's own "at minimum" phrasing.
