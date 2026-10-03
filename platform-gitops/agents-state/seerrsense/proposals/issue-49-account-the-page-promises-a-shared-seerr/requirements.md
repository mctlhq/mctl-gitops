# Tell the account page the truth about the shared Seerr, and let people sign out

## Context

Signed in at `/account`, a person with no Seerr of their own is told
"Using the shared Seerr until you attach your own." The page decides that from
a single boolean, `connected`, returned by `GET /api/v1/account/connection`
(`src/api/account.ts:72-85`, branched on in `public/account.html:145-152`). The
server's actual rule is stricter: `TenantResolver.householdTenant`
(`src/providers/seerr/tenants.ts:111-132`) hands the household instance only to
a signed-in subject whose address is in `SEERRSENSE_HOUSEHOLD_EMAILS`, and only
when a household client exists at all (`createDefaultSeerrClient()` returns
`undefined` without `SEERR_API_KEY`, `src/providers/seerr/client.ts:435-444`).
The page and the resolver therefore disagree, and the page is the one talking to
the human. With `SEERRSENSE_OPEN_SIGNUP` on, the misleading branch is now the
default arrival experience: every new person is outside the household, so every
new person is promised something they do not have, and later meets
`notConnectedMessage` (`src/providers/seerr/tenants.ts:136-139`) inside an
assistant, where it reads as a malfunction.

The same page offers no way to sign out. The session is an `httpOnly` cookie set
at `src/api/server.ts:511-518` and lives 8 hours
(`SESSION_TTL_SECONDS`, `src/auth/session.ts:4`). No route anywhere in `src/`
clears it — `logout`, `signout` and `clearCookie` appear nowhere in the tree. On
a shared or borrowed computer the only way to end the session is to clear site
data by hand. Both defects went unnoticed because, before open signup, the only
person who ever signed in was the owner, for whom the sentence was true and who
had no reason to sign out.

## User stories

- AS a person who has just signed up and attached nothing I WANT the account
  page to tell me what my account can actually reach SO THAT the assistant's
  "No Seerr is connected to this account yet" is the expected next step rather
  than a fault.
- AS a household member listed in `SEERRSENSE_HOUSEHOLD_EMAILS` I WANT the page
  to keep telling me I am on the shared Seerr SO THAT I know I need not attach
  anything before searching.
- AS someone signing in on a shared or borrowed computer I WANT a visible sign
  out control SO THAT I can end the browser session without clearing site data.
- AS someone who signs out I WANT my MCP clients (Claude, ChatGPT) to keep
  working SO THAT ending a browser session does not silently unauthorise every
  assistant I have connected.
- AS a maintainer I WANT the page's statement and the resolver's decision to come
  from one place SO THAT they cannot drift apart again.

## Acceptance criteria (EARS)

Reporting what the caller actually gets:

- WHEN `GET /api/v1/account/connection` is called with a valid session cookie
  THE SYSTEM SHALL include a `fallback` field whose value is `"household"` or
  `"none"`, meaning what this caller reaches when they have no connection of
  their own.
- WHILE serving that field THE SYSTEM SHALL derive it from the same predicate
  `TenantResolver` itself uses to admit a subject to the household instance, and
  SHALL NOT read a second copy of `SEERRSENSE_HOUSEHOLD_EMAILS`.
- IF the signed-in address is in `SEERRSENSE_HOUSEHOLD_EMAILS` AND a household
  client is configured THEN THE SYSTEM SHALL report `fallback: "household"`.
- IF the signed-in address is not in `SEERRSENSE_HOUSEHOLD_EMAILS` THEN THE
  SYSTEM SHALL report `fallback: "none"`, whether or not `SEERR_API_KEY` is set.
- IF no household client is configured (`SEERR_API_KEY` unset) THEN THE SYSTEM
  SHALL report `fallback: "none"` for every caller, including listed addresses.
- WHEN computing `fallback` THE SYSTEM SHALL make no network call to the
  household Seerr and SHALL NOT mutate the resolver's per-subject cache.
- WHEN `DELETE /api/v1/account/connection` succeeds THE SYSTEM SHALL return the
  same `fallback` value alongside `connected: false`, so the page can state the
  post-disconnect situation without a second request.

What the page says:

- WHILE a connection of the person's own exists THE SYSTEM SHALL state that the
  account is connected to that address.
- WHILE no connection exists AND `fallback` is `"household"` THE SYSTEM SHALL
  state that the shared Seerr is in use until the person attaches their own.
- WHILE no connection exists AND `fallback` is `"none"` THE SYSTEM SHALL state
  that nothing is connected yet and point at the form below, phrased as a normal
  starting state and not styled as an error.
- IF the response carries no `fallback` field, or an unrecognised value, THEN THE
  SYSTEM SHALL render the "nothing connected yet" wording, never the shared-Seerr
  promise.
- WHILE the page is in its signed-in state THE SYSTEM SHALL keep the three
  statements textually distinct from one another.

Signing out:

- WHEN a signed-in person activates the sign out control THE SYSTEM SHALL end the
  browser session and return the page to its signed-out state.
- WHEN sign out is requested THE SYSTEM SHALL clear `seerrsense_session` with the
  same `path`, `httpOnly`, `sameSite` and `secure` attributes it was set with at
  `src/api/server.ts:512-518`, so the browser actually drops it.
- WHEN a sign-out request carries a session cookie that identifies a session
  THE SYSTEM SHALL record that session as revoked, so replaying the same cookie
  value afterwards is refused with 401 by every `/api/v1/account/*` route.
- WHILE recording a revocation THE SYSTEM SHALL retain the record no longer than
  that session's own expiry, and SHALL delete it in the existing hourly
  `purgeExpired` sweep (`src/api/server.ts:383-394`).
- IF sign out is requested with a missing, expired or unreadable cookie THEN THE
  SYSTEM SHALL still clear the cookie and answer success, so a stale session is
  always clearable.
- WHILE handling sign out THE SYSTEM SHALL NOT delete or modify any row in
  `oauth_refresh_tokens` or `user_connections`; MCP grants are revoked only via
  `POST /oauth/revoke` (`src/auth/routes.ts:533-541`).
- THE SYSTEM SHALL NOT expose sign out as a plain `GET`, so a link prefetch or
  prerender cannot end a session.
- WHILE the sign-out route is registered THE SYSTEM SHALL authenticate it with
  the browser session cookie only and SHALL refuse an MCP access token, matching
  the rest of `/api/v1/account/*`.
- WHILE a session cookie was issued before this change (no session identifier
  inside it) THE SYSTEM SHALL still accept it until it expires and SHALL still
  clear it on sign out.

## Out of scope

- Revoking MCP refresh tokens or access tokens on sign out. `/oauth/revoke`
  already exists for that and conflating the two would sign people out of Claude
  and ChatGPT unexpectedly.
- A "sign out everywhere / all devices" control.
- Changing `SESSION_TTL_SECONDS`, the cookie's `SameSite` policy, or adding
  sliding session renewal.
- Changing who is admitted to the household instance, or the
  `SEERRSENSE_HOUSEHOLD_EMAILS` / `SEERRSENSE_OPEN_SIGNUP` semantics themselves.
- Rewording `notConnectedMessage` in the MCP tools beyond keeping it consistent
  in tone with the page's new third state.
- Introducing a DOM test harness (jsdom is not in `devDependencies`); page copy
  is asserted against the served HTML, as `tests/landing.test.ts` already does.
- Any visual redesign of `/account` beyond adding one button and rewording the
  status line.

## Open questions

- Server-side revocation is included because the issue's verification asks that
  "a follow-up `GET /api/v1/account/connection` with the old cookie returns
  401", which a stateless JWT cannot satisfy by clearing a cookie alone. If a
  reviewer prefers the smaller change, drop the denylist and weaken that
  assertion to "the response tells the browser to drop the cookie" — at the cost
  that sign-out cannot end a session whose cookie value leaked. Proceeding with
  revocation.
- `MemoryAuthStore` loses the revocation list on restart, exactly as it already
  loses refresh tokens (`src/auth/store.ts:100-104`). Accepted, and documented,
  rather than solved.
- Whether `fallback` should instead be an `effective: "own" | "household" |
  "none"` field. Proceeding with `fallback` as the issue suggested, because the
  page needs the post-disconnect answer while a connection still exists.
- Exact wording of the third state. Proceeding with "No Seerr is connected yet —
  attach yours below to start.", echoing `notConnectedMessage` in tone.
- Whether the existing "Disconnect" button should be relabelled to reduce
  confusion with "Sign out". Proceeding with keeping "Disconnect" and separating
  the two controls visually.
