# Tasks: issue-74-auth-dcr-fallback-restricted-to-the-clou

- [ ] 1. Add the allowlist to the OAuth config — `src/auth/config.ts`: add
  `SEERRSENSE_DCR_REDIRECT_URIS: z.string().optional()` to `OAuthEnvSchema`,
  add `dcrRedirectUris: string[]` to `OAuthConfig`, and parse it: unset means
  `["https://mcp.mctl.ai/servers-callback"]`, set means comma-split/trim/filter,
  set-and-empty means `[]`. Validate each entry is a parseable URL with no
  userinfo and throw on a bad entry, matching how `parsePreRegisteredClients`
  throws. Comment why the polarity is opposite to `allowedEmails`.
  — DoD: `loadAuthSettings` returns the default entry when the variable is
  absent, the parsed list when set, `[]` when set to `""`, and throws on
  `"not a url"`. `npm run typecheck` passes.

- [ ] 2. Persist registered clients in the store (depends on 1) —
  `src/auth/store.ts`: add the `RegisteredClient` interface
  (`clientId`, `clientName`, `redirectUris`, optional `scope`, `createdAt`) and
  `putRegisteredClient` / `getRegisteredClient` to `AuthStore`; implement both
  on `MemoryAuthStore` with a `Map` that `close()` clears and `purgeExpired()`
  deliberately does not sweep (comment the reason, as `user_connections` does).
  `src/auth/store-pg.ts`: append `CREATE TABLE IF NOT EXISTS
  oauth_registered_clients (client_id TEXT PRIMARY KEY, client_name TEXT NOT
  NULL, redirect_uris TEXT NOT NULL, scope TEXT, created_at BIGINT NOT NULL)`
  to `SCHEMA_SQL` and implement the two methods, storing `redirect_uris` as a
  JSON array string. Leave `deleteSubject` untouched.
  — DoD: both implementations round-trip a client with and without `scope`;
  `init()` stays idempotent; `purgeExpired` leaves the row alone.

- [ ] 3. Resolve DCR clients between pre-registered and CIMD (depends on 2) —
  `src/auth/clients.ts`: extend `ResolvedClient.source` with `"dcr"`, add
  optional `defaultScope?: string`, add a fourth constructor parameter to
  `ClientResolver` typed as the narrow structural
  `{ getRegisteredClient(clientId: string): Promise<RegisteredClient | undefined> }`,
  and insert the lookup in `resolve()` after the `preRegistered` hit and before
  the `https://` check. Set `defaultScope` to the registration's `scope` if
  present, else `` `${SCOPE_READ} ${SCOPE_REQUEST}` ``. Do not put DCR clients in
  `this.cache`. Import the scope constants from `./config.js` (or re-declare the
  default string in `config.ts` and import it, whichever avoids an import
  cycle — `config.ts` already imports from `clients.ts`, so prefer a
  `DCR_DEFAULT_SCOPE` constant declared in `clients.ts` and used by both).
  — DoD: a DCR `client_id` resolves with `source: "dcr"` and the right
  `defaultScope` and makes zero `fetchImpl` calls; a pre-registered id still
  wins over a DCR row with the same id; an unknown non-https id still throws
  `ClientResolutionError`. No import cycle (`npm run typecheck` passes).

- [ ] 4. Wire the resolver to the store (depends on 3) — `src/auth/routes.ts`:
  pass `store` as the fourth argument at the existing `new ClientResolver(...)`
  site, keeping `maxBodyBytes` at its default.
  — DoD: existing OAuth tests still pass unchanged.

- [ ] 5. Client-derived scope default at `/oauth/authorize` (depends on 3) —
  `src/auth/routes.ts`: change
  `const requested = (params.scope ?? SCOPE_READ)` to
  `const requested = (params.scope ?? client.defaultScope ?? SCOPE_READ)`.
  Nothing downstream changes: the pending row, consent page, auth code and
  token `scope` claim already carry the one resolved string.
  — DoD: a DCR client with no `scope` reaches the consent screen with
  `seerr:read seerr:request`; a CIMD client with no `scope` still gets
  `seerr:read`; an explicit `scope` still wins for both.

- [ ] 6. `POST /register` (depends on 2, 4) — `src/auth/routes.ts`: add
  `RegisterBodySchema` (bounded `redirect_uris` array min 1 max 8, optional
  `client_name`, `token_endpoint_auth_method`, `grant_types`, `response_types`,
  `scope`), compute `const dcrEnabled = config.dcrRedirectUris.length > 0`, and
  register the route only when `dcrEnabled`, with
  `ipRateLimited(deps.rateLimit, "/register")`. Refuse in order: unparseable
  body or missing/empty `redirect_uris` → 400 `invalid_redirect_uri`; any entry
  failing `isAllowedRedirectUri` against a synthetic `ResolvedClient` built from
  `config.dcrRedirectUris` → 400 `invalid_redirect_uri`;
  `token_endpoint_auth_method` other than `"none"`, `grant_types` outside
  `{authorization_code, refresh_token}`, `response_types` outside `{code}`, or a
  `scope` token outside `SUPPORTED_SCOPES` → 400 `invalid_client_metadata`.
  On success mint `dcr_${randomToken()}`, `putRegisteredClient`, and answer 201
  with `cache-control: no-store` and the RFC 7591 fields (no `client_secret`).
  — DoD: a portal-callback registration returns 201 with a `client_id`; every
  refusal path returns the documented code; nothing is persisted on a refusal.

- [ ] 7. Advertise `registration_endpoint` conditionally (depends on 6) —
  `src/auth/routes.ts`: conditionally spread
  `registration_endpoint: \`${config.issuer}/register\`` into
  `authorizationServerMetadata` when `dcrEnabled`, and replace the "deliberately
  absent" comment above the literal with one that states the new rule (narrow
  DCR fallback for a portal that cannot present a CIMD, off when the allowlist
  is empty). Both `.well-known` paths share the object, so both follow.
  — DoD: with the allowlist non-empty, both
  `/.well-known/oauth-authorization-server` and
  `/.well-known/oauth-authorization-server/mcp` carry the key; with it empty,
  neither does and `POST /register` answers 404.

- [ ] 8. Exempt `/register` from the bearer gate (depends on 6) —
  `src/api/server.ts`: add `"/register"` (no trailing slash, so `isPublic`
  matches it exactly) to `PUBLIC_PREFIXES`, with a comment: a client
  registering has no token by definition, and the route's own `ipRateLimited`
  limiter is its meter.
  — DoD: `POST /register` without an `Authorization` header reaches the handler
  rather than answering 401; `POST /register/anything` still answers 401.

- [ ] 9. README (depends on 1, 6, 7) — add `SEERRSENSE_DCR_REDIRECT_URIS` to the
  `## Configuration` table; rewrite the `## MCP` "Dynamic Client Registration is
  deprecated … and is not implemented" paragraph and the matching
  `## Security Model` bullet to describe the endpoint, the allowlist, its
  default, and the empty-means-off rule; extend the `## Security Model` scopes
  bullet with the per-registration-type defaults (`seerr:read` for CIMD and
  pre-registered, `seerr:read seerr:request` for DCR unless the registration or
  the authorization request names a scope); note that registrations live in the
  store, so a deployment without `DATABASE_URL` loses them on restart.
  — DoD: no sentence anywhere in the README still says DCR is not implemented;
  `grep -n "not implemented" README.md` returns nothing about registration.

## Tests

All new tests go in the existing suites, matching their established style
(`tests/oauth.test.ts` builds a server with a `stubFetch` standing in for Google
and the client document; `tests/store.test.ts` runs one contract suite over both
stores via `describe.each`).

- [ ] T1. `tests/oauth.test.ts` — a registration whose single `redirect_uris`
  entry is the portal callback answers 201 and returns a `client_id`; the
  response carries `token_endpoint_auth_method: "none"` and no
  `client_secret`.
- [ ] T2. `tests/oauth.test.ts` — a registration naming any other redirect
  (`https://evil.test/cb`, and the near-miss
  `https://mcp.mctl.ai/servers-callback.evil.test`) answers 400
  `invalid_redirect_uri`, and no client is persisted (a following
  `/oauth/authorize` with a guessed id still fails `invalid_client`).
- [ ] T3. `tests/oauth.test.ts` — a registration mixing one allowlisted and one
  non-allowlisted entry is refused: the check is over every entry, not any.
- [ ] T4. `tests/oauth.test.ts` — with `SEERRSENSE_DCR_REDIRECT_URIS=""`,
  `POST /register` answers 404 and `registration_endpoint` is absent from both
  `.well-known/oauth-authorization-server` documents. With it non-empty, the key
  is present in both and equals `<issuer>/register`.
- [ ] T5. `tests/oauth.test.ts` — **the regression test for
  mctlhq/seerrsense#73**: register a DCR client with no `scope`, run the full
  authorize → Google → consent → token flow with no `scope` parameter, assert
  the token response and the access token's `scope` claim are
  `seerr:read seerr:request`, and assert a `request_media` call over `/mcp` with
  that token succeeds rather than answering "this token is not granted the
  seerr:request scope". Must fail on current `main` at the registration step:
  there is no `/register` there.
- [ ] T6. `tests/oauth.test.ts` — a CIMD client with no `scope` still gets
  `seerr:read` only, and its `request_media` is still refused; the same for a
  pre-registered client from `SEERRSENSE_OAUTH_CLIENTS`.
- [ ] T7. `tests/oauth.test.ts` — a DCR client sending
  `scope=seerr:read` explicitly gets exactly `seerr:read` and stays read-only.
- [ ] T8. `tests/oauth.test.ts` — a registration carrying
  `scope: "seerr:read"` makes that the client's default: a later authorize with
  no `scope` parameter grants `seerr:read` only. A registration carrying
  `scope: "seerr:write"` is refused 400 `invalid_client_metadata`.
- [ ] T9. `tests/oauth.test.ts` — `token_endpoint_auth_method:
  "client_secret_basic"`, a `grant_types` naming `implicit`, and a
  `response_types` naming `token` each answer 400 `invalid_client_metadata`;
  `redirect_uris: []` and a body with no `redirect_uris` answer 400
  `invalid_redirect_uri`.
- [ ] T10. `tests/oauth.test.ts` — the consent screen rendered for a
  no-scope DCR client contains the `seerr:request` label "Request new films and
  series on your behalf", so the wider grant is visible before issuance.
- [ ] T11. `tests/rate-limit.test.ts` — `POST /register` answers 429 on the
  (N+1)th request from one IP within the window, logging the same
  `{ route: "/register", key: "ip" }` shape the other OAuth routes log.
- [ ] T12. `tests/oauth.test.ts` — `POST /register` with no `Authorization`
  header is not answered 401 (it reaches the handler), and the minted
  `client_id` does not start with `https://`, so it is never fetched as a CIMD
  — assert `stubFetch` was never called with it.
- [ ] T13. `tests/store.test.ts` — extend the shared contract suite:
  round-trip a registered client with and without `scope`, confirm an unknown
  `client_id` returns `undefined`, confirm `purgeExpired` does not remove it,
  and confirm a second `init()` is still idempotent with the new table.
- [ ] T14. `tests/client-pinning.test.ts` (or `tests/oauth.test.ts`, whichever
  owns resolver-level assertions) — resolution order: a pre-registered entry
  wins over a DCR row with the same `client_id`; a DCR row wins over a CIMD
  fetch and triggers no fetch at all.
- [ ] T15. `tests/auth-config.test.ts` — `dcrRedirectUris` is the portal default
  when the variable is unset, the parsed list when set, `[]` when set to `""`,
  and `loadAuthSettings` throws on a malformed entry.
- [ ] T16. Confirm `tests/portal-allowlist.test.ts` and
  `tests/source-hygiene.test.ts` still pass untouched — no tool was added or
  renamed, so the allowlist drift guard must stay green by construction.

## Rollback

Every layer is independently reversible and the change is off by one variable.

1. **Fastest, no deploy.** Set `SEERRSENSE_DCR_REDIRECT_URIS=""` in the service
   values and sync. `/register` stops being registered, `registration_endpoint`
   disappears from both metadata documents, and any client already registered
   stops being able to register a new one. Note that an *existing* DCR client
   keeps resolving out of the store and keeps its wider default — emptying the
   allowlist closes the door, it does not evict who is already inside.
2. **Evict registered clients.** `DELETE FROM oauth_registered_clients;` on the
   service database. `ClientResolver` then falls through to the CIMD path and
   the portal's `client_id` fails `invalid_client` on the next authorize, which
   is the intended fail-closed outcome. Existing refresh tokens issued to that
   client still work until they expire; `POST /oauth/revoke` is the explicit way
   to end them, and `revokeFamily` handles the rest.
3. **Revert the image.** `mctl_rollback_service` to the previous tag. The new
   table is simply unread by the old image; no down-migration exists or is
   needed, and no existing table was altered. The old image restores the
   `?? SCOPE_READ` default for every client, so the portal returns to read-only
   — which is the pre-change state, i.e. #73 again.
4. **Revert the gitops flip.** If mctlhq/mctl-gitops#1363 has already moved the
   `seerrsense` portal upstream to automatic, revert that PR first so the portal
   returns to manual mode before step 2 or 3, otherwise the portal holds a
   `client_id` this server no longer recognises and the upstream has to be
   signed out and back in from the dashboard.
