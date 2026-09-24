# Design: issue-74-auth-dcr-fallback-restricted-to-the-clou

## Current state

### Client registration

`src/auth/clients.ts` holds the whole client story. `ResolvedClient` is
`{ clientId, clientName, redirectUris, source: "cimd" | "pre-registered" }`.
`ClientResolver.resolve()` is two steps:

1. `this.preRegistered.find((c) => c.clientId === clientId)` — an exact match
   on the operator-configured list wins with no network call.
2. Otherwise the `client_id` must start with `https://`, and
   `fetchMetadata()` fetches it as a Client ID Metadata Document, validates it
   against `ClientMetadataSchema` (`client_id`, `client_name`, `redirect_uris`),
   requires a path component, requires the document's own `client_id` to equal
   the URL it came from, caps the body at 64 KiB, forbids redirects, and caches
   the result for 10 minutes.

There is no third step. The class doc says it outright: "Dynamic Client
Registration is deprecated there and is not implemented."

`preRegisteredClients` is assembled in `src/auth/config.ts`: the account page
(`<issuer>/account`) plus whatever `parsePreRegisteredClients()` parses out of
`SEERRSENSE_OAUTH_CLIENTS` (`client_id=redirect_uri[,uri...];...`).

`isAllowedRedirectUri(client, redirectUri)` in the same file is the redirect
check: exact string match, with an RFC 8252 loopback exception that ignores the
port for `localhost`, `127.0.0.1` and `[::1]`; `parseRedirectUri()` refuses any
URI carrying userinfo before any comparison happens.

### Metadata and the authorize endpoint

`registerOAuthRoutes()` in `src/auth/routes.ts` builds
`authorizationServerMetadata` as a plain object literal and serves it, with
`cache-control: public, max-age=3600`, at `/.well-known/oauth-authorization-server`
and `/.well-known/oauth-authorization-server/mcp`. A comment above it says
`registration_endpoint` is "deliberately absent". `token_endpoint_auth_methods_supported`
is `["none"]`; `client_id_metadata_document_supported` is `true`.

`GET /oauth/authorize` validates `AuthorizeQuerySchema`, resolves the client,
checks the redirect URI, checks `resource`, and then computes the grant:

```ts
const requested = (params.scope ?? SCOPE_READ).split(/\s+/).filter(Boolean);
```

That single `?? SCOPE_READ` is the read-only default that caused
mctlhq/seerrsense#73. Unknown scopes are refused with `invalid_scope` through
the client's redirect. The resolved scope string is stored on the pending auth
row, carried through the Google leg, rendered on the consent page
(`consentPage({ scopes: pending.scope.split(/\s+/) })` with `SCOPE_LABELS`),
copied onto the auth code, and finally minted into the access token's `scope`
claim by `issueTokens()`. `request_media` in `src/mcp/server.ts` reads that
claim: `if (scopes && !scopes.includes(SCOPE_REQUEST))` it refuses.

`ipRateLimited(rateLimit, routeName)` in `routes.ts` returns the
`{ config: { rateLimit: {...} } }` route option, keyed on `req.ip`, logging on
`onExceeded`. It is applied to `/oauth/authorize`, `/oauth/google/callback`,
`/oauth/consent` and `/oauth/token`. The budget comes from
`rateLimitSettings().oauth` in `src/api/server.ts`
(`SEERRSENSE_RATE_LIMIT_OAUTH_MAX`, default 10, over
`SEERRSENSE_RATE_LIMIT_OAUTH_WINDOW_MS`, default 5 min) and is passed as
`registerOAuthRoutes(fastify, oauth, authStore, { fetchImpl, rateLimit: limits.oauth })`.

### The auth gate

`src/api/server.ts` has two layers in front of every route:

- an `onRequest` hook implementing a hand-rolled per-IP pre-auth gate, skipped
  only `if (isPublic(request.url))`;
- a `preHandler` bearer gate, skipped `if (isPublic(request.url) || isSessionRoute(request.url))`.

`isPublic()` matches `PUBLIC_REDIRECTS` exactly, then `PUBLIC_PREFIXES` where an
entry ending in `/` is a prefix and everything else is an exact match — with
`"/"` deliberately exact so it is the landing page, not a wildcard. So
`/oauth/*` and `/.well-known/*` are public by prefix, and **`/register` is not
public today**.

### Store

`AuthStore` in `src/auth/store.ts` is a flat interface over pending auths, auth
codes, refresh tokens, user connections, revoked sessions/subjects and resolve
usage, implemented twice: `MemoryAuthStore` (Maps) and `PostgresAuthStore` in
`src/auth/store-pg.ts`. The Postgres schema is one `SCHEMA_SQL` string of
`CREATE TABLE IF NOT EXISTS` statements applied in `init()` under
`pg_advisory_lock(SCHEMA_LOCK_ID)`, because a rollout runs two pods. Its own
comment notes that `IF NOT EXISTS` never alters an existing table, so a new
*column* needs a real migration — a brand-new *table* does not.
`purgeExpired()` deliberately leaves `user_connections` alone.
`tests/store.test.ts` runs one contract suite over both stores via
`describe.each`, adding `PostgresAuthStore` only when `TEST_DATABASE_URL` is
set.

## Proposed solution

Five touch points. The shape of each is dictated by what already exists.

### 1. Config: the allowlist (`src/auth/config.ts`)

Add `SEERRSENSE_DCR_REDIRECT_URIS: z.string().optional()` to `OAuthEnvSchema`
and a `dcrRedirectUris: string[]` field to `OAuthConfig`. Parsing mirrors
`allowedEmails`/`householdEmails` — split on `,`, trim, drop empties — with one
deliberate difference in the *unset* case:

```ts
const DEFAULT_DCR_REDIRECT_URIS = ["https://mcp.mctl.ai/servers-callback"];

const dcrRedirectUris =
  parsed.SEERRSENSE_DCR_REDIRECT_URIS === undefined
    ? DEFAULT_DCR_REDIRECT_URIS
    : parsed.SEERRSENSE_DCR_REDIRECT_URIS.split(",").map((u) => u.trim()).filter(Boolean);
```

Unset means the portal callback; set-and-empty means off. This is the opposite
polarity from `allowedEmails`, which fails closed, and that is intentional and
worth a comment in the code: the allowlist does not decide *who may sign in*,
it decides *which callback may be registered*, and a registration for that one
callback grants nothing on its own — the person still passes Google, the email
allowlist and the consent screen. Each entry is validated at load time with the
same rules `parseRedirectUri` applies (parseable URL, no userinfo) and a bad
entry throws, consistent with how `parsePreRegisteredClients` throws on a
malformed entry rather than silently dropping it.

### 2. Store: persist registered clients

Add to `src/auth/store.ts`:

```ts
export interface RegisteredClient {
  clientId: string;
  clientName: string;
  redirectUris: string[];
  /** RFC 7591 `scope` from the registration, if the client named one. */
  scope?: string;
  createdAt: number;
}
```

and to `AuthStore`:

```ts
putRegisteredClient(client: RegisteredClient): Promise<void>;
getRegisteredClient(clientId: string): Promise<RegisteredClient | undefined>;
```

`MemoryAuthStore` gets a `private registeredClients = new Map<string, RegisteredClient>()`,
cleared in `close()` and **not** touched by `purgeExpired()` — registrations do
not expire, the same reasoning that exempts `user_connections`.

`PostgresAuthStore` gets a new table appended to `SCHEMA_SQL`:

```sql
CREATE TABLE IF NOT EXISTS oauth_registered_clients (
  client_id     TEXT   PRIMARY KEY,
  client_name   TEXT   NOT NULL,
  redirect_uris TEXT   NOT NULL,   -- JSON array, same as the app's shape
  scope         TEXT,
  created_at    BIGINT NOT NULL
);
```

A new table under `CREATE TABLE IF NOT EXISTS` in the existing advisory-locked
`init()` needs no migration tool and no extra deploy step, which is exactly the
case the file's own comment carves out. `redirect_uris` is stored as a JSON
array in a `TEXT` column rather than `TEXT[]`: the store already round-trips
only scalars through `pg`, and a JSON string keeps the two implementations
byte-comparable in `tests/store.test.ts`.

`deleteSubject()` is not extended: a registered client is not a person's data,
it is an operator-scoped credential shared by a portal.

### 3. Resolver: a third step, in the middle

`ResolvedClient.source` gains `"dcr"`, and `ResolvedClient` gains an optional
`defaultScope?: string`. `ClientResolver` gains a constructor dependency:

```ts
constructor(
  private readonly preRegistered: ResolvedClient[] = [],
  private readonly fetchImpl: typeof fetch = fetch,
  private readonly maxBodyBytes = 64 * 1024,
  private readonly registered?: {
    getRegisteredClient(clientId: string): Promise<RegisteredClient | undefined>;
  },
) {}
```

A narrow structural type, not `AuthStore`, so `clients.ts` keeps importing only
types from `store.ts` and the resolver stays testable with a two-line stub.
`resolve()` becomes preset → registered → CIMD:

```ts
const preset = this.preRegistered.find((c) => c.clientId === clientId);
if (preset) return preset;

const dcr = await this.registered?.getRegisteredClient(clientId);
if (dcr) {
  return {
    clientId: dcr.clientId,
    clientName: dcr.clientName,
    redirectUris: dcr.redirectUris,
    source: "dcr",
    defaultScope: dcr.scope ?? `${SCOPE_READ} ${SCOPE_REQUEST}`,
  };
}

if (!clientId.startsWith("https://")) throw new ClientResolutionError(...);
```

The DCR lookup sits before the `https://` check, so a minted `client_id` is
never fetched as a document. The minted id is deliberately not an https URL —
`dcr_${randomToken()}` — which makes that ordering belt and braces rather than
load-bearing. Resolved DCR clients are not put in `this.cache`: the cache exists
to bound outbound fetches, and a store read is already local (and must stay
live, so a future revocation takes effect on the next authorize).

`registerOAuthRoutes` already has `store`, so the wiring is a fourth argument
at the existing construction site:

```ts
const clients = new ClientResolver(config.preRegisteredClients, deps.fetchImpl ?? fetch, undefined, store);
```

`isAllowedRedirectUri` is not touched. A DCR client's `redirectUris` are the
ones it registered, and they were allowlist-checked at registration time; the
per-authorize check is the same exact-match-plus-loopback rule every client
gets.

### 4. Routes: `POST /register`, and the scope default

In `registerOAuthRoutes`:

```ts
const dcrEnabled = config.dcrRedirectUris.length > 0;
const authorizationServerMetadata = {
  ...,
  ...(dcrEnabled ? { registration_endpoint: `${config.issuer}/register` } : {}),
};
```

Conditional spread on the existing literal, so when DCR is off the key is
absent rather than `undefined` — `undefined` would survive into the served JSON
shape as a missing key anyway, but an explicit spread is what a reader can
check. Both `.well-known` paths share the one object, so both follow.

The route is registered only when `dcrEnabled`:

```ts
if (dcrEnabled) {
  fastify.post("/register", ipRateLimited(deps.rateLimit, "/register"), handler);
}
```

Not registering it is what produces the 404 the issue asks for — Fastify's
not-found handler answers, and per the comment in `server.ts` that handler runs
through the root hooks, so an unauthenticated prober gets the same 404 either
way. When the allowlist is empty there is no route and nothing to rate-limit.

The handler, validating with a `RegisterBodySchema` in the same style as
`AuthorizeQuerySchema` (every client-controlled string bounded, because this is
an unauthenticated endpoint):

```ts
const RegisterBodySchema = z.object({
  redirect_uris: z.array(z.string().max(2048)).min(1).max(8),
  client_name: z.string().max(256).optional(),
  token_endpoint_auth_method: z.literal("none").optional(),
  grant_types: z.array(z.string().max(64)).max(8).optional(),
  response_types: z.array(z.string().max(64)).max(8).optional(),
  scope: z.string().max(256).optional(),
});
```

Order of refusals, each with its RFC 7591 §3.2.2 error code:

1. Unparseable body, or `redirect_uris` missing/empty → 400
   `invalid_redirect_uri` (the issue names this code for the redirect failure
   mode, and an absent list is that failure mode).
2. Any entry not on `config.dcrRedirectUris` → 400 `invalid_redirect_uri`. The
   comparison reuses the allowlist as a synthetic `ResolvedClient` and calls
   `isAllowedRedirectUri({ redirectUris: config.dcrRedirectUris, ... }, uri)`,
   so registration and authorization cannot drift apart on what "matches"
   means, and userinfo is refused by the same code path.
3. `token_endpoint_auth_method` present and not `"none"`, or `grant_types` /
   `response_types` outside what this server supports, or a `scope` token
   outside `SUPPORTED_SCOPES` → 400 `invalid_client_metadata`.

Then mint and persist:

```ts
const clientId = `dcr_${randomToken()}`;
await store.putRegisteredClient({
  clientId,
  clientName: body.client_name ?? "Registered client",
  redirectUris: body.redirect_uris,
  scope: body.scope,
  createdAt: Date.now(),
});
return reply.status(201).header("cache-control", "no-store").send({
  client_id: clientId,
  client_id_issued_at: Math.floor(Date.now() / 1000),
  redirect_uris: body.redirect_uris,
  client_name: ...,
  token_endpoint_auth_method: "none",
  grant_types: ["authorization_code", "refresh_token"],
  response_types: ["code"],
  scope: body.scope ?? `${SCOPE_READ} ${SCOPE_REQUEST}`,
});
```

No `client_secret`, no `client_secret_expires_at`, no
`registration_access_token`. `cache-control: no-store` matches what
`/oauth/token` already sends for a credential-bearing response.

The scope default in `/oauth/authorize` changes from a constant to a
client-derived one:

```ts
const requested = (params.scope ?? client.defaultScope ?? SCOPE_READ)
  .split(/\s+/).filter(Boolean);
```

One line, and it is the whole of change 2 in the issue. `defaultScope` is
populated only for `source: "dcr"`, so CIMD and pre-registered clients keep
`SCOPE_READ`. An explicit `scope` parameter still wins for every client, so
`scope=seerr:read` from a DCR client stays read-only. Everything downstream —
the `invalid_scope` check, the pending row, the consent page's `SCOPE_LABELS`
list, the auth code, the token's `scope` claim, `request_media`'s own check —
already reads that one string and needs no change. That is why the consent
screen keeps showing the wider grant for free (criterion 3 of the issue).

### 5. The public-route list (`src/api/server.ts`)

Add `"/register"` to `PUBLIC_PREFIXES`. It has no trailing slash, so `isPublic`
matches it exactly and `/register/anything` still meets the bearer gate. This
exempts it from the bearer `preHandler` — a client registering has no token by
definition — while leaving the `onRequest` pre-auth IP gate off it as well,
consistent with `/oauth/*`. Its own `ipRateLimited` limiter is the meter that
applies, which is what the issue asks for. Add the entry next to the OAuth ones
with a comment naming the reason, in the style of the existing entries.

### 6. README

`## Configuration` table gains `SEERRSENSE_DCR_REDIRECT_URIS` ("Comma-separated
allowlist of `redirect_uris` a Dynamic Client Registration may claim. Unset
defaults to `https://mcp.mctl.ai/servers-callback`; set to the empty string to
turn registration off, in which case `/register` answers 404 and is absent from
metadata"). The `## MCP` paragraph and the two `## Security Model` bullets that
currently read "Dynamic Client Registration … is not implemented" are rewritten
to describe the narrow endpoint, and the scopes bullet gains the
per-registration-type defaults. The rewrite must be a rewrite, not an addition:
leaving the old "is not implemented" sentence next to the new endpoint is the
kind of contradiction this README does not have anywhere else.

## Alternatives

**Mount the endpoint at `/oauth/register`.** Free public-route handling (the
`"/oauth/"` prefix already covers it) and no edit to `server.ts`. Dropped
because the issue and the org rule in mctlhq/.github#137 both name
`POST /register`, the sibling upstreams are being aligned on one path, and the
portal reads the path out of `registration_endpoint` anyway — so the only thing
the shorter path costs is one line in `PUBLIC_PREFIXES`, and the only thing it
buys is consistency across servers. Recorded as an open question rather than
silently swapped.

**Pre-register the portal callback instead, via `SEERRSENSE_OAUTH_CLIENTS`.**
The mechanism already exists and would need no code at all. Dropped because it
does not solve the actual problem: the portal cannot be *given* a `client_id`
in automatic mode, and manual mode is what freezes the tool catalogue at the
first login. It is also what the deployment does today, and #73 is the result.

**Give every client the `seerr:read seerr:request` default.** One-line change,
no per-source branching. Dropped because it widens the default grant for every
CIMD client — Claude, ChatGPT, anything a self-hoster points at the server —
which is a security regression nobody asked for, and the issue is explicit that
CIMD and pre-registered clients keep `seerr:read`.

**Keep the wider scope out of the default and have the portal request it
explicitly.** Cleanest in principle: the client asks for what it needs.
Dropped because the portal does not send a `scope` on the authorization
request, which is precisely the mechanism of #73; a default is the only lever
this server controls.

**Store registered clients in memory only.** No schema change, no store
interface change. Dropped because a rollout or a pod restart would silently
de-register the portal, which then fails every call until an operator notices —
and the store interface exists to make exactly this kind of state survive a
rollout.

## Platform impact

**Migrations.** One new table, `oauth_registered_clients`, created by the
existing `PostgresAuthStore.init()` inside the advisory lock. No existing table
is altered, so the "`IF NOT EXISTS` never alters a table" caveat in
`store-pg.ts` does not bite. No separate migration step, no deploy ordering
constraint, and a rollback needs no down-migration — the table is simply unread
by the previous image.

**Backward compatibility.** Unset `SEERRSENSE_DCR_REDIRECT_URIS` turns
registration *on* for the portal callback on every deployment, including
self-hosters who never asked for it. That is the org rule's polarity and is
argued for above, but it is the one behavioural change a self-hoster would not
have chosen, and the README must say so plainly next to the variable. Nothing
else changes without a registration: no existing client's default scope moves,
no existing redirect check loosens, the token, refresh and revoke endpoints are
untouched, and `docs/portal-allowlist.json` and the tool set are untouched, so
`tests/portal-allowlist.test.ts` stays green by construction.

**Resource impact.** One extra store read per `/oauth/authorize` for a
`client_id` that is not pre-registered — a primary-key lookup, against a store
already read twice in the same flow. The `/register` route is metered at 10 per
5 minutes per IP and writes one small row per success; the row cap is the
allowlist, not the limiter, since every accepted registration must name an
allowlisted callback. No new outbound calls. On `MemoryAuthStore` the rows live
in a `Map` that `purgeExpired` does not sweep, bounded in practice by the same
rate limit and by process lifetime.

**Risks and mitigations.**

- *An open registration endpoint.* Mitigated by the allowlist being the first
  check, by `isAllowedRedirectUri`'s exact-match rule (no prefix matching, so
  `https://mcp.mctl.ai/servers-callback.evil.test` is refused), by the userinfo
  refusal inside `parseRedirectUri`, and by the per-IP limiter. A registration
  grants nothing by itself: the holder still needs a person to pass Google, the
  email allowlist and the consent screen.
- *Row growth from repeat registrations.* Every successful registration mints a
  new row for the same allowlisted callback. Bounded by the limiter; a cleanup
  or `GET /register` listing is deliberately out of scope, and the open
  question records that repeat registrations are not deduplicated.
- *A wider default reaching a client that should not have it.* Mitigated
  structurally: `defaultScope` is set only on `source: "dcr"`, and a DCR client
  only exists if it registered an allowlisted callback. A test asserts the CIMD
  and pre-registered defaults have not moved.
- *The wider grant being invisible to the person.* Mitigated by the consent
  page, which renders `pending.scope` and therefore the wider set, with the
  existing "Request new films and series on your behalf" label. A test asserts
  that label appears for a DCR client.
- *A minted `client_id` colliding with the CIMD path.* Mitigated twice: the
  `dcr_` prefix is not an https URL, and the store lookup runs before the
  `https://` check.
- *Registrations lost on `MemoryAuthStore`.* Accepted and documented; the
  hosted deployment sets `DATABASE_URL`.
