# DCR fallback restricted to the Cloudflare portal callback, with the full scope set for DCR clients

## Context

The Cloudflare MCP portal can only obtain an upstream `client_id` by Dynamic
Client Registration (automatic mode) or by an operator pasting one in (manual
mode). It cannot present a Client ID Metadata Document URL. SeerrSense
implements CIMD and operator pre-registration only — `src/auth/clients.ts`
states plainly that "Dynamic Client Registration is deprecated there and is not
implemented", and `src/auth/routes.ts` omits `registration_endpoint` from the
RFC 8414 document for that reason. The portal therefore holds `seerrsense` in
manual mode, which freezes the tool catalogue at the first login and, because
the hand-entered registration carried no `scope`, left the portal read-only:
`/oauth/authorize` defaults a missing `scope` to `SCOPE_READ` alone, so
`request_media` refuses every portal call with "this token is not granted the
seerr:request scope" (`src/mcp/server.ts`). That is mctlhq/seerrsense#73.

This proposal implements the org rule from mctlhq/.github#137 for SeerrSense: a
narrow RFC 7591 registration endpoint whose `redirect_uris` must all sit on an
operator allowlist defaulting to the single portal callback
`https://mcp.mctl.ai/servers-callback`, and a wider default scope
(`seerr:read seerr:request`) for clients that registered that way. DCR is not
reopened generally: with the allowlist variable empty the endpoint is neither
advertised nor served, and the wider default never reaches a CIMD or
pre-registered client. The consent screen already enumerates every granted
scope, so the wider default stays visible to the person before any token is
issued.

## User stories

- AS the operator of the Cloudflare MCP portal I WANT SeerrSense to accept a
  Dynamic Client Registration for the portal callback SO THAT the `seerrsense`
  upstream can run in automatic mode and re-sync its tool catalogue without the
  server being removed and re-added.
- AS a household member using SeerrSense through the shared portal I WANT the
  portal's token to carry `seerr:request` SO THAT `request_media` files a
  request instead of refusing it.
- AS the SeerrSense operator I WANT registration restricted to an explicit
  redirect-URI allowlist that is empty-by-default-off SO THAT opening DCR for
  one known portal does not turn the server into an open client registry.
- AS a person authorizing a client I WANT the consent screen to keep listing
  every scope being granted SO THAT a wider default is something I see rather
  than something I discover later.
- AS a self-hoster I WANT nothing to change unless I set the new variable SO
  THAT my CIMD and pre-registered clients keep their current `seerr:read`
  default and my deployment keeps answering 404 on `/register`.

## Acceptance criteria (EARS)

### Registration endpoint

- WHEN `SEERRSENSE_DCR_REDIRECT_URIS` is unset THE SYSTEM SHALL treat the
  allowlist as the single entry `https://mcp.mctl.ai/servers-callback`.
- WHEN `SEERRSENSE_DCR_REDIRECT_URIS` is set to a non-empty comma-separated
  list THE SYSTEM SHALL treat exactly those entries as the allowlist.
- WHILE the allowlist is non-empty THE SYSTEM SHALL serve `POST /register` and
  SHALL include `registration_endpoint: "<issuer>/register"` in both
  `/.well-known/oauth-authorization-server` and
  `/.well-known/oauth-authorization-server/mcp`.
- WHILE the allowlist is empty (`SEERRSENSE_DCR_REDIRECT_URIS` set to the empty
  string or to only separators) THE SYSTEM SHALL omit `registration_endpoint`
  from both authorization-server metadata documents and SHALL answer
  `POST /register` with 404.
- WHILE OAuth is not configured (no `oauth` block from `loadAuthSettings`) THE
  SYSTEM SHALL not serve `POST /register` at all, exactly as it serves no other
  OAuth route.
- WHEN `POST /register` receives a body whose every `redirect_uris` entry is on
  the allowlist, compared by the same exact-match rule
  `isAllowedRedirectUri` uses for authorization (no prefix or wildcard
  matching, userinfo refused) THE SYSTEM SHALL persist the client and answer
  201 with `client_id`, `client_id_issued_at`, `redirect_uris`,
  `token_endpoint_auth_method: "none"`, `grant_types`, `response_types`,
  `client_name` and the client's effective `scope`.
- IF any `redirect_uris` entry is absent from the allowlist THEN THE SYSTEM
  SHALL answer 400 with `error: "invalid_redirect_uri"` and SHALL persist
  nothing.
- IF `redirect_uris` is missing or empty THEN THE SYSTEM SHALL answer 400 with
  `error: "invalid_redirect_uri"`.
- IF the body names `token_endpoint_auth_method` as anything other than
  `"none"` THEN THE SYSTEM SHALL answer 400 with
  `error: "invalid_client_metadata"`.
- IF the body names `grant_types` or `response_types` containing anything
  outside `{authorization_code, refresh_token}` and `{code}` respectively THEN
  THE SYSTEM SHALL answer 400 with `error: "invalid_client_metadata"`.
- IF the body names a `scope` containing a token outside `SUPPORTED_SCOPES`
  THEN THE SYSTEM SHALL answer 400 with `error: "invalid_client_metadata"`.
- WHILE registering a client THE SYSTEM SHALL issue no `client_secret` and
  SHALL keep PKCE S256 mandatory for that client on both legs, unchanged.
- WHEN a client is registered THE SYSTEM SHALL mint a `client_id` that is not
  an `https:` URL, so it can never be mistaken for a Client ID Metadata
  Document URL.
- WHILE `POST /register` is reachable THE SYSTEM SHALL meter it per IP with the
  same `ipRateLimited` helper and the same `SEERRSENSE_RATE_LIMIT_OAUTH_*`
  budget that guards `/oauth/authorize`, and SHALL answer 429 past the
  ceiling.
- WHILE `POST /register` is reachable THE SYSTEM SHALL serve it without a
  bearer token, like every other route in the OAuth flow, and SHALL keep the
  pre-auth IP gate applied to it.

### Client resolution

- WHEN `/oauth/authorize` resolves a `client_id` THE SYSTEM SHALL consult
  operator pre-registered clients first, then DCR-registered clients in the
  store, then Client ID Metadata Documents.
- WHEN a DCR-registered `client_id` is resolved THE SYSTEM SHALL make no
  outbound HTTP request for it.
- IF a `client_id` is neither pre-registered, nor DCR-registered, nor an
  `https:` URL with a path THEN THE SYSTEM SHALL answer 400 `invalid_client`,
  as today.
- WHILE a DCR-registered client is authorizing THE SYSTEM SHALL apply the
  existing `isAllowedRedirectUri` check against the `redirect_uris` recorded at
  registration.

### Scope defaults

- WHEN a DCR-registered client reaches `/oauth/authorize` with no `scope`
  parameter and named no `scope` at registration THE SYSTEM SHALL grant
  `seerr:read seerr:request`.
- WHEN a DCR-registered client reaches `/oauth/authorize` with no `scope`
  parameter and named a `scope` at registration THE SYSTEM SHALL grant exactly
  the registered `scope`.
- WHEN a CIMD or pre-registered client reaches `/oauth/authorize` with no
  `scope` parameter THE SYSTEM SHALL grant `seerr:read` only, unchanged.
- WHEN any client names a `scope` at `/oauth/authorize` THE SYSTEM SHALL grant
  exactly the named scopes and no more, whatever its registration type — so an
  explicit `scope=seerr:read` from a DCR client stays read-only.
- WHILE any authorization is in flight THE SYSTEM SHALL keep refusing unknown
  scopes with `invalid_scope` through the client's `redirect_uri`, unchanged.
- WHEN the consent screen is rendered THE SYSTEM SHALL list every scope that
  will be granted, including the wider DCR default, using the existing
  `SCOPE_LABELS` text.

### Documentation

- WHEN the README security model is read THE SYSTEM SHALL describe the
  registration endpoint, `SEERRSENSE_DCR_REDIRECT_URIS` and its default, the
  empty-means-off rule, and the per-registration-type scope defaults; and the
  Configuration table SHALL list the new variable.

## Out of scope

- Any change to `docs/portal-allowlist.json` or to the tool set: no tool is
  added, removed or re-annotated, so `tests/portal-allowlist.test.ts` is
  untouched.
- The gitops change that flips the portal upstream from manual to automatic
  (mctlhq/mctl-gitops#1363) and the one-off dashboard sign-in that follows it.
- Client configuration management: no `GET/PUT/DELETE
  /register/{client_id}`, no `registration_access_token`, no
  `registration_client_uri`. RFC 7591 permits omitting the RFC 7592
  management API and this proposal omits it.
- Confidential clients: no `client_secret` is ever issued, and
  `token_endpoint_auth_methods_supported` stays `["none"]`.
- Expiry or garbage collection of registered clients, and any admin UI to list
  or revoke them. They are operator-scoped rows behind a one-entry allowlist.
- Removing CIMD support or changing the loopback redirect rule in
  `isAllowedRedirectUri`.
- Any change to `SEERRSENSE_OAUTH_CLIENTS` parsing or to the legacy shared
  token.

## Open questions

- **Mount path versus the public-route list.** The issue names `POST /register`.
  `PUBLIC_PREFIXES` in `src/api/server.ts` matches `"/"` exactly rather than as
  a prefix, so `/register` is not public today and would be caught by the
  bearer `preHandler` before the handler runs. Proceeding with `/register` as
  the issue specifies and adding it to `PUBLIC_PREFIXES` as an exact entry;
  `/oauth/register` (already public via the `"/oauth/"` prefix) is recorded as
  the rejected alternative in `design.md`.
- **Deduplication of repeat registrations.** RFC 7591 says nothing about it and
  the issue is silent. Proceeding with a fresh `client_id` per successful
  registration, and no dedup on identical metadata: the allowlist already
  bounds who can register, and re-using an id across registrations would let
  one caller's metadata edit reach another caller's grants.
- **Whether `client_name` is required.** The issue does not say.
  `ClientMetadataSchema` requires it for a CIMD, but RFC 7591 makes it
  optional. Proceeding with optional, defaulting to the string
  `"Registered client"` so the consent screen never renders an empty heading.
- **Store availability.** Registered clients are persisted in the store, so on
  `MemoryAuthStore` (no `DATABASE_URL`) they are lost on restart and the portal
  would have to register again. Accepted: the hosted deployment that needs the
  portal sets `DATABASE_URL`, and the README note says so.
- **Rate-limit budget sharing.** `ipRateLimited` is given `limits.oauth`, whose
  counters are per route in `@fastify/rate-limit`, so `/register` gets its own
  10-per-5-minutes bucket rather than sharing `/oauth/authorize`'s. Reading
  "rate-limit the endpoint like `/oauth/authorize`" as "the same helper and the
  same budget", not "the same shared counter".
