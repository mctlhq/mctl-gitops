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
in `localStorage` (`useAuth.ts`, `AUTH_TTL = 8 * 60 * 60 * 1000`,
`restore()`) without re-checking that the underlying GitHub session is
still valid.

**Correction, 2026-08-31 (found by the codex reviewer on this proposal's
own decisions PR; an earlier revision of this document said "8 hours"
here and was wrong).** The signature does **not** expire. `hmacSign` signs
the bare `login` string and nothing else — no timestamp, no nonce — and
`hmacVerify(login, sig, secret)` recomputes over that same bare login. The
Worker never sees `exp`. `AUTH_TTL` governs only when the *browser*
discards its own `localStorage` copy, which an attacker who has already
copied the value is not bound by. A leaked `sig` is therefore an
**unbounded** bearer for that login, replayable by any HTTP client for as
long as `GITHUB_OAUTH_HMAC_KEY` keeps its value; the only revocation is a
key rotation, which invalidates every user's signature at once.

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
  names are already provisioned **to unauthenticated callers** SO THAT
  attackers cannot enumerate tenant names by anonymous probing. It must
  keep revealing them to a caller with a valid signature — that is the
  endpoint's purpose, and behind the identity gate it is not an oracle.
- AS a platform operator I WANT worker tests covering submit/contact/rate-limit
  paths SO THAT this hardening does not silently regress in future changes.
- AS a returning user with a stale browser session I WANT `/api/submit` to
  stop accepting a locally-cached credential forever SO THAT a leaked
  `mctl_auth` value has a bounded blast radius. **Today it does not**: the
  signature carries no expiry, so this is a statement of intent tracked in
  mctlhq/mctl-web#70, not something this proposal delivers. Nothing here
  may be written as if the 8h `AUTH_TTL` already bounds server-side
  replay — it does not.

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
- WHILE `/api/github/check-team` exists THE SYSTEM SHALL accept it as
  `POST` with a JSON body `{ name, github_auth: { login, sig } }` and
  SHALL NOT accept the caller's identity (`login`, `sig`) via the query
  string or any other part of the URL, because `sig` is an unbounded
  bearer (no expiry is signed or verified) and a URL propagates it into
  access logs, browser history, and `Referer` headers.
- WHEN `/api/github/check-team` changes from `GET` to `POST` THE SYSTEM
  SHALL be rolled out so that no window exists in which the deployed Nuxt
  frontend and the deployed Worker disagree about the method. There is no
  safe one-sided state: a new frontend POSTing at an old GET-only Worker
  fails, and an old frontend GETting at a new POST-only Worker fails. The
  method change SHALL therefore either ship atomically with the frontend,
  or go out in two steps — first a Worker that accepts **both** methods,
  then, once the new frontend is live, a follow-up that removes `GET`.
- WHILE a transitional `GET /api/github/check-team` exists during such a
  two-step rollout THE SYSTEM SHALL answer `{available: true}` (200)
  unconditionally for any syntactically valid name, SHALL NOT query
  Backstage, and SHALL NOT accept `login`/`sig` from the query string.
  The transitional path SHALL NOT preserve today's truthful anonymous
  answer: that answer is the enumeration oracle this proposal exists to
  close, and leaving it live for the length of a migration window — even
  a rate-limited one — would defer the fix rather than deliver it. The
  authoritative duplicate-tenant check at `/api/submit` is unaffected, so
  the degraded answer cannot cause a duplicate provision.
- WHILE a rollback of the Worker is possible THE SYSTEM SHALL NOT leave a
  POST-only frontend deployed against a Worker version that does not
  accept `POST`. The rollback procedure SHALL revert the frontend
  together with the Worker unless the specific Worker version being
  restored also accepts `POST`. The existence of a two-step rollout does
  NOT satisfy this: a restored `GET`-only Worker serves old frontends,
  and the live frontend after migration is not one.
- WHEN a client calls `/api/github/check-team` without a `github_auth`
  block, or with one whose signature fails
  `hmacVerify(login, sig, GITHUB_OAUTH_HMAC_KEY)`, THE SYSTEM SHALL
  return **401** with a single fixed body that is byte-identical for an
  existing and a non-existing name, so anonymous enumeration is no longer
  possible.
- WHEN a client calls `/api/github/check-team` with a valid signature THE
  SYSTEM SHALL return today's truthful answer — `{available:false}` for
  an existing tenant, `{available:true}` for a free name — because behind
  the identity gate that distinction is the feature, not an oracle.
- WHEN a request to `/api/github/check-team` is rejected for rate-limit or
  configuration reasons THE SYSTEM SHALL return a response that does not
  vary with the queried name, and SHALL keep those classes distinct from
  each other and from the 401 (429 with `Retry-After` for rate limit, 500
  for genuine Backstage/config failure).
- WHILE `/api/github/check-team` is identity-gated THE SYSTEM SHALL NOT
  require a Turnstile token on that endpoint — the issue's "at minimum
  Turnstile + per-IP rate limit" fallback applies only where no identity
  is available, and a challenge fired on every debounced keystroke is
  both worse UX and a weaker gate than a signature.
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
  for both `/api/submit` and `/api/contact`; and, for `check-team`, the
  **identity-gate and non-disclosure** behaviour — truthful answers for a
  verified caller, a fixed 401 for missing/invalid/malformed credentials,
  a 401 (not a 500) for every malformed body shape, and a rejected
  query-string identity. **Not** "uniform-response behaviour": that was
  the rejected design, and a test suite written to it would assert the
  opposite of what is being built.
- IF the stored `mctl_auth` localStorage entry (`useAuth.ts`) is older than
  its `exp` THEN `restore()` SHALL continue to discard it (already true
  today) — no regression permitted here. Note this is a browser-side
  convenience only and bounds nothing server-side; see the correction in
  Context above.

## Out of scope
- Removing the GitHub access token from the session payload
  (`mcpPayload.token` / OAuth session redesign) — explicit companion issue
  per the issue body, requires mctl-api changes (see `mctlhq/mctl-api#218`
  referenced in `cloudflare-worker/index.js` comments).
- Replacing the non-expiring localStorage HMAC credential with server-side session
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
- ~~The issue says check-team should "require the authenticated session (or
  at minimum Turnstile + per-IP rate limit)". Requiring the session cookie
  would break the current UX, where `useTeamValidation.ts` calls
  `check-team` live as the user types a team name *before* they have
  necessarily completed GitHub OAuth. This proposal takes the "at minimum"
  fallback: Turnstile + tightened per-IP rate limit + uniform response
  shape, without requiring a session.~~
  **REJECTED at approval (2026-08-31). Do not implement any of the
  struck-through text above.** The identity gate is required, not
  optional; there is no Turnstile on `check-team`; the response is not
  uniform for verified callers. The UX objection does not survive
  contact with the actual fix: the composable simply skips the call while
  the user is signed out and says so in the field, which needs no flow
  redesign. See the acceptance criteria above — they are the authority —
  and Operator decisions 1-2 in `tasks.md`.
- Whether the Turnstile widget should be "managed" (visible, adaptive
  challenge) or "invisible" mode. **Resolved: managed**, and the widget
  has already been created that way (Operator decision 3).
**Both resolved by the operator at approval (2026-08-31);** the acceptance
criteria above are the authority, these entries record what changed.

- *What should check-team's response body be?* The proposal answered
  "`{available:true}` unconditionally, for everyone" — **rejected.** That
  makes the endpoint advisory-only, i.e. it stops doing the one thing it
  exists for (telling the user their chosen name is free), while still
  serving unauthenticated traffic. Resolved instead by gating on identity:
  verified callers get the truthful answer, everyone else gets a fixed
  401. Uniformity is required *within* each failure class, not across the
  success path. The Backstage-side authoritative check at `/api/submit`
  (lines 806-822) remains the duplicate-tenant guard either way.
- *Should Turnstile also gate check-team's debounced calls?* **No** — and
  not merely for the UX reason the proposal gave. With an identity gate a
  challenge would be redundant: a signature is the stronger check and
  costs the user nothing per keystroke. Turnstile stays only where the
  issue requires it, on `/api/contact` and `/api/submit`.
- *How do the identity credentials travel?* Added at approval, after the
  agy reviewer caught it: **body only, never the URL.** The endpoint moves
  `GET` → `POST`. `sig` is an unbounded bearer, and today's URL carries no
  credential at all, so a `?sig=` design would have created a log/history/
  `Referer` exposure this issue is meant to reduce.
