# Public mode: open signup, owner-only household, an SSRF-guarded Seerr address, and rate and model budgets

## Context

seerrsense already resolves each signed-in person to their own Overseerr or
Jellyseerr: `PUT /api/v1/account/connection` (`src/api/account.ts:64-125`)
proves the credentials with `describeSelf()`, seals the API key, and
`TenantResolver` (`src/providers/seerr/tenants.ts:44-81`) returns
`source: "own"` for every later call. What is missing is not multi-tenancy but
everything that makes it safe to let strangers in. Today the only gate is
`SEERRSENSE_ALLOWED_EMAILS` (`src/auth/config.ts:92-97`,
`src/auth/routes.ts:364-368`), a gitops change per address, capped in practice
by Google's 100 hand-listed test users.

Opening that gate as the code stands would hand every newcomer the operator's
own Seerr — `householdTenant()` (`src/providers/seerr/tenants.ts:88-102`)
returns the shared client built from `SEERR_URL` / `SEERR_API_KEY`
(`src/providers/seerr/client.ts:208-222`, wired at `src/api/server.ts:121-125`)
to any subject without a `user_connections` row — and would give them an
anonymous server-side request forger: `seerrUrl` is validated only as
`z.string().url().max(2048)` (`src/api/account.ts:11`) and dialled immediately
(`src/api/account.ts:85-102`) by a client that follows redirects and relays the
upstream status text back to the caller (`src/providers/seerr/client.ts:41-69`).
There is no rate limiting anywhere (`@fastify/rate-limit` is not a dependency),
and every `resolve_media` that falls through to step 3 of `MediaResolver`
(`src/api/resolver/index.ts:96-113`) is an unbudgeted paid Nebius call
(`src/api/resolver/intent.ts:96-123`). This proposal closes those four gaps,
plus two diagnosis defects the issue raises in the same pass: a wrong error
message when the target is behind Cloudflare Access, and a server that emits no
logs at all in production.

## User stories

- AS a person with a Google account I WANT to sign in to the hosted seerrsense
  without an operator adding my address to gitops SO THAT I can attach my own
  Seerr and use it from my assistant.
- AS the operator I WANT open signup to be an explicit opt-in flag SO THAT a
  missing or misspelled environment variable can never silently open the server.
- AS the household owner I WANT the shared `SEERR_URL` instance offered only to
  a named list of addresses SO THAT a stranger who has just signed in cannot
  search or file requests on my Overseerr with my API key.
- AS the platform operator I WANT the Seerr address people submit to be checked
  before and at dial time SO THAT the service cannot be used to probe
  `10.0.0.0/8`, `169.254.169.254` or `shared-pg-rw.platform-db` from inside the
  cluster.
- AS the operator I WANT per-IP and per-subject rate limits and a per-subject
  daily model budget SO THAT my Nebius bill and my pod are not a function of
  other people's curiosity.
- AS a person whose Seerr sits behind Cloudflare Access I WANT to be told that
  the Zero Trust fields are what is missing SO THAT I do not re-check an address
  and key that were always correct.
- AS whoever is on call I WANT refused sign-ins, rejected addresses, rate-limit
  hits and budget exhaustion in the pod's stdout SO THAT a diagnosis does not
  require reproducing the failure from outside the cluster.

## Acceptance criteria (EARS)

### Open signup

- WHILE `SEERRSENSE_OPEN_SIGNUP` is exactly the string `true` THE SYSTEM SHALL
  admit any Google account that passes the existing `id_token` and
  `email_verified` checks (`src/auth/google.ts:96-106`) without consulting
  `allowedEmails`.
- WHILE `SEERRSENSE_OPEN_SIGNUP` is unset, empty, or any value other than
  `true` THE SYSTEM SHALL behave exactly as it does today: only addresses in
  `SEERRSENSE_ALLOWED_EMAILS` are admitted.
- IF `SEERRSENSE_OPEN_SIGNUP` is not `true` AND `allowedEmails` is empty THEN
  THE SYSTEM SHALL admit nobody.
- WHEN a sign-in is refused because the address is outside the allowlist THE
  SYSTEM SHALL log a warn-level line naming the address and redirect with
  `error=access_denied`, unchanged from today.

### Household only for its owners

- WHILE `SEERRSENSE_HOUSEHOLD_EMAILS` lists a caller's address THE SYSTEM SHALL
  offer that caller the operator-configured household client when they have no
  `user_connections` row, with `source: "household"` and the existing
  `findUserIdByEmail` attribution.
- IF a caller has no `user_connections` row and their address is not listed in
  `SEERRSENSE_HOUSEHOLD_EMAILS` THEN THE SYSTEM SHALL resolve them to
  `source: "none"` with no client, and every tool and REST route SHALL answer
  with `notConnectedMessage()` (`src/providers/seerr/tenants.ts:106-109`).
- WHILE the caller is the legacy shared token (`subject === "static-token"`) or
  stdio mode (no subject) THE SYSTEM SHALL keep today's path and receive the
  household client.
- IF `SEERRSENSE_HOUSEHOLD_EMAILS` is unset or empty THEN THE SYSTEM SHALL offer
  the household client to no signed-in subject (fail closed), while leaving the
  static-token and stdio paths untouched.

### SSRF guard on the Seerr address

- WHEN `PUT /api/v1/account/connection` receives a `seerrUrl` THE SYSTEM SHALL
  validate it before any network call is made.
- IF a submitted `seerrUrl` has a scheme other than `https:` THEN THE SYSTEM
  SHALL answer 400 and SHALL NOT dial the address.
- IF a submitted `seerrUrl` carries userinfo, a non-empty query or fragment, or
  resolves — by literal IP or by DNS — to a loopback, RFC 1918, link-local
  (including `169.254.169.254`), CGNAT `100.64.0.0/10`, IPv4 broadcast, "this
  network" `0.0.0.0/8`, reserved `240.0.0.0/4`, IPv6 loopback `::1`, IPv6 ULA
  `fc00::/7`, IPv6 link-local `fe80::/10`, IPv4-mapped IPv6 `::ffff:0:0/96`, or
  IPv4-compatible IPv6 address THEN THE SYSTEM SHALL answer 400 with a generic
  message and SHALL NOT dial the address.
- WHILE a stored connection is being dialled THE SYSTEM SHALL re-run the same
  address check inside `SeerrClient` before each request, so a hostname that
  changed meaning between validation and use is refused.
- WHEN `SeerrClient` issues a request for a per-user connection THE SYSTEM SHALL
  pin the connection to the address the guard approved, so a second DNS answer
  between check and connect cannot reach a different host.
- IF an upstream answers with a 3xx THEN THE SYSTEM SHALL NOT follow it and
  SHALL treat the response as a failure.
- WHEN a dial to a per-user Seerr fails for any reason THE SYSTEM SHALL return a
  generic message to the caller and SHALL NOT include the upstream status code,
  status text, body, or resolved IP address in anything the caller can see.
- WHILE the client in use is the operator-configured household client built from
  `SEERR_URL` THE SYSTEM SHALL exempt it from the address guard and from
  pinning.

### Cloudflare Access diagnosis

- IF a dial to a per-user Seerr is answered with a redirect to a
  `*.cloudflareaccess.com` host, or with Cloudflare Access response headers,
  THEN THE SYSTEM SHALL answer the person with a message naming Cloudflare
  Access and the Zero Trust fields rather than the generic "did not accept the
  address and key".

### Rate limits

- WHEN more than the configured number of requests per window arrive from one IP
  address on `/oauth/*`, `/account/session`, or
  `PUT /api/v1/account/connection` THE SYSTEM SHALL answer 429.
- WHEN more than the configured number of requests per window arrive for one
  authenticated subject on `/mcp` or `/api/v1/*` THE SYSTEM SHALL answer 429.
- WHILE a request carries no authenticated subject on a subject-limited route
  THE SYSTEM SHALL fall back to limiting by IP address.
- WHEN a request is refused by a rate limit THE SYSTEM SHALL log a warn-level
  line naming the route and the key class (subject or IP), never the token.

### Model budget

- WHEN a `resolve_media` tool call or `GET /api/v1/resolve` would invoke the
  Nebius model for a subject that has already reached
  `SEERRSENSE_RESOLVE_DAILY_LIMIT` model calls in the current UTC day THE SYSTEM
  SHALL NOT call `generateObject` and SHALL answer with a plain "daily limit
  reached, try again tomorrow" message (`isError: true` for MCP, HTTP 429 for
  REST).
- WHEN the total number of model calls across all subjects in the current UTC
  day reaches `SEERRSENSE_RESOLVE_GLOBAL_DAILY_LIMIT` THE SYSTEM SHALL refuse
  further model calls with the same plain message.
- WHILE `DATABASE_URL` is configured THE SYSTEM SHALL keep the counters in
  PostgreSQL so that a pod restart or a second replica does not reset them.
- WHEN the same normalised query is resolved again within the cache window THE
  SYSTEM SHALL serve the cached intent, SHALL NOT call the model, and SHALL NOT
  consume budget.
- WHILE a query is answered by the native Seerr search alone (steps 1 and 2 of
  `MediaResolver.resolveMedia`) THE SYSTEM SHALL NOT consume budget, because no
  model call was made.
- IF `SEERRSENSE_RESOLVE_DAILY_LIMIT` is unset THEN THE SYSTEM SHALL apply a
  documented non-zero default rather than an unlimited budget.

### Logging

- WHILE the HTTP server is running THE SYSTEM SHALL emit structured logs to
  stdout at `LOG_LEVEL` (default `info`), so that `kubectl logs` shows the
  warn-level events above.
- WHILE any log line is written THE SYSTEM SHALL NOT include a Seerr API key, a
  Cloudflare Access service token, an access or refresh token, a session cookie,
  or an `Authorization` header value.

## Out of scope

- Publishing the Google OAuth client from Testing to Production. It is an
  operator action in the Google console, recorded in the checklist in
  `tasks.md`, not code.
- Setting the new variables in `mctl-gitops`. Also an operator action, with the
  ordering constraint recorded in `tasks.md` and `design.md`.
- Any change to the OAuth protocol surface: client registration, PKCE, consent,
  scopes, token TTLs and refresh rotation are untouched.
- Per-user quotas on `search_media`, `get_media` or `request_media` beyond the
  route rate limits, and any billing, plan or payment concept.
- An admin UI, a user list, or a way to ban an individual subject after the fact.
- Replacing the in-process rate-limit store with Redis; a shared limiter across
  replicas is noted as a limitation, not built here.
- Egress network policy on the pod. Defence in depth at the cluster level is
  worth doing and is a `mctl-gitops` change, not a change in this repo.

## Open questions

- **Default limits.** The issue names the variables but no numbers. Proceeding
  with: 10 requests / 5 min per IP on `/oauth/*` and `/account/session`, 5 / 5
  min per IP on `PUT /api/v1/account/connection`, 120 / min per subject on
  `/mcp` and `/api/v1/*`, `SEERRSENSE_RESOLVE_DAILY_LIMIT=50`,
  `SEERRSENSE_RESOLVE_GLOBAL_DAILY_LIMIT=2000`, intent cache 10 minutes / 500
  entries. All are environment variables, so an operator can retune without a
  release.
- **`redirect: "error"` versus detecting Cloudflare Access.** The issue asks for
  both, and they conflict: `redirect: "error"` makes the response unreadable, so
  the `302` to `*.cloudflareaccess.com` that identifies an Access challenge can
  no longer be seen. Proceeding with `redirect: "manual"` plus an explicit
  refusal of every 3xx inside `SeerrClient` — never following, which is the
  security property being asked for, while still being able to read the
  `location` header and name Cloudflare Access. Recorded here because it is a
  deliberate deviation from the issue's literal wording.
- **Existing stored connections with an `http://` address.** No such row is
  known on the hosted instance. Proceeding with: the guard applies at dial time
  to stored rows as well, so such a row stops working and its owner is told to
  re-enter an `https` address. No data is deleted.
- **Whether an address should be re-checked in the background.** A hostname that
  becomes private after a connection is stored is caught at the next dial, not
  proactively. No sweeper is proposed.
- **Whether open signup should also require the encryption key.** With
  `SEERRSENSE_ENCRYPTION_KEY` unset nobody can attach a Seerr, so open signup
  would admit people to a server they cannot use. Proceeding with a startup
  warn-level log rather than a hard failure, so a self-hoster is not blocked.
