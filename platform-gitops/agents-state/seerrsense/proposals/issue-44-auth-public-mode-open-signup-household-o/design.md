# Design: issue-44-auth-public-mode-open-signup-household-o

## Current state

### The gate

`loadAuthSettings` (`src/auth/config.ts:61-130`) parses the environment with
`OAuthEnvSchema` and builds `allowedEmails` from `SEERRSENSE_ALLOWED_EMAILS`
(`:92-97`), lowercased and trimmed. `OAuthConfig` (`:33-47`) is the object every
auth route receives. The only consumer of `allowedEmails` is the Google callback
(`src/auth/routes.ts:364-368`), which redirects with `access_denied` for any
address not in the set. Identity itself is already sound: `GoogleOidc.exchangeCode`
(`src/auth/google.ts:69-108`) verifies issuer, audience and nonce and refuses an
`id_token` whose `email_verified` is not `true` (`:105`), and lowercases the
address. Scopes requested from Google are `openid email profile` (`:61`), which
are non-sensitive.

### Which Seerr a caller reaches

`TenantResolver.resolve` (`src/providers/seerr/tenants.ts:44-81`) reads
`auth.extra.subject` and `auth.extra.email` — set by `authenticate`
(`src/auth/verifier.ts:36-53` for OAuth, `:59-69` for the legacy token, where the
subject is the literal `"static-token"`). With a `user_connections` row it builds
a per-user `SeerrClient` from the sealed key and returns `source: "own"`;
otherwise it falls through to `householdTenant` (`:88-102`), which returns the
shared client with `source: "household"` and an `attributedUserId` looked up by
email. `Tenant` (`:14-19`) carries `client`, `email`, `attributedUserId` and
`source` — but not the subject. Resolutions are cached per subject for 60 s so
`/mcp` stays off the database on the hot path, and `forget()` (`:84-86`) is
called from the account routes on write and delete.

The household client is `createDefaultSeerrClient()`
(`src/providers/seerr/client.ts:208-217`), built from `SEERR_URL`,
`SEERR_API_KEY`, `SEERRSENSE_LOCALE` and the pod's `CF_ACCESS_*` credentials
(`src/core/config.ts:8-24`), and passed into the resolver at
`src/api/server.ts:121-125`. It is `undefined` when `SEERR_API_KEY` is unset,
which is the only situation today in which a signed-in person can get
`source: "none"` (`tests/tenants.test.ts:112-118`).

### The Seerr address

`ConnectionSchema` (`src/api/account.ts:10-17`) validates `seerrUrl` as
`z.string().url().max(2048)` and nothing more. The `PUT` handler
(`:64-125`) builds a `SeerrClient` from the submitted address and immediately
calls `describeSelf()` (`:96`), whose failure is turned into the fixed string
"That Seerr did not accept the address and key." (`:100`). `SeerrClient.fetch`
(`src/providers/seerr/client.ts:41-69`) concatenates `${this.baseUrl}${path}`,
passes no `redirect` option — so Node's undici follows up to 20 hops — sets a
10 s abort timeout, and on a non-2xx throws
`Seerr API error: ${response.status} ${response.statusText}`. That message
reaches the MCP caller verbatim through every tool's catch block
(`src/mcp/server.ts:53-58, 74-79, 98-103, 132-137`). There is no scheme, host or
address check anywhere in `src/`.

### The model path

`MediaResolver.resolveMedia` (`src/api/resolver/index.ts:50-113`) tries native
Seerr search (step 1), a normalised variant (step 2), and only then calls
`this.intentExtractor.extract(query)` (`:96`). `NebiusIntentExtractor.extract`
(`src/api/resolver/intent.ts:96-122`) is one `generateObject` call, temperature
0, `maxOutputTokens: 400`, `maxRetries: 1`, 20 s abort. It is constructed once
per process at `src/api/server.ts:344` for the REST route and once per MCP server
instance at `src/mcp/server.ts:35-39` — that is, per request, since
`createMcpHandler` runs its factory per request (`src/api/server.ts:335-337`).
`MediaResolver` has a per-call `searched` map (`:52-60`) that dedupes Seerr
searches within one resolution, but nothing survives the request. There is no
counter and no cache of intents.

### Everything else that is missing

`package.json` has no `@fastify/rate-limit` and no `undici`. The Fastify instance
comes from `createMcpFastifyApp({ host: "0.0.0.0" })` (`src/api/server.ts:91`)
with no logger option, so Fastify's default `logger: false` applies and the
`request.log.warn` calls at `src/auth/routes.ts:357,365,490`,
`src/api/account.ts:98` and `src/api/server.ts:264` go nowhere — which matches
the issue's observation that `kubectl logs` shows only `> node dist/index.js`.
`PostgresAuthStore` (`src/auth/store-pg.ts:15-64`) creates its schema on start
under an advisory lock; adding a *new table* to `SCHEMA_SQL` is safe, and the
note at `:66-70` warns only that a new *column* on an existing table needs a real
migration.

Tests reshape `process.env`, dynamically `import` `buildServer`, and inject a
stub through `buildServer({ fetchImpl })` while also `vi.stubGlobal("fetch", ...)`
because `SeerrClient` uses the global (`tests/account.test.ts:83-104, 225-252`).

## Proposed solution

Six changes, each fail-closed, each independently testable.

### 1. `SEERRSENSE_OPEN_SIGNUP` — a third field on `OAuthConfig`

Add `SEERRSENSE_OPEN_SIGNUP: z.string().optional()` to `OAuthEnvSchema` and
`openSignup: boolean` to `OAuthConfig`, computed as
`parsed.SEERRSENSE_OPEN_SIGNUP === "true"` — strict equality, so `"TRUE"`,
`"1"`, `"yes"` and a typo all mean "closed". The single consumer changes from

```ts
if (!config.allowedEmails.has(identity.email)) { ... }
```

to

```ts
if (!config.openSignup && !config.allowedEmails.has(identity.email)) { ... }
```

at `src/auth/routes.ts:364`. Nothing else in the flow moves: consent, PKCE,
scopes, token issuance and the fail-closed empty-list behaviour are untouched,
and the `request.log.warn` on refusal stays. Open signup deliberately does not
consult `allowedEmails` at all when on, so an operator does not have to empty
one variable to use the other.

At startup, if `openSignup` is on and `encryptionKey` is undefined, log a
warn-level line: people would be admitted to a server on which they cannot
attach a Seerr (`src/api/account.ts:39-47` already answers 503 for that case).

### 2. `SEERRSENSE_HOUSEHOLD_EMAILS` — a second set, consulted in `TenantResolver`

Parse it exactly like `allowedEmails` into `householdEmails: Set<string>` on
`OAuthConfig`. `TenantResolver` gains it as a constructor argument (defaulting
to an empty set, so the existing three-argument call sites and
`tests/tenants.test.ts` keep compiling), and `householdTenant` becomes:

```ts
private async householdTenant(email: string, ownerOnly: boolean): Promise<Tenant> {
  if (!this.household) return { email, source: "none" };
  if (ownerOnly && !this.householdEmails.has(email.toLowerCase())) {
    return { email, source: "none" };
  }
  ...
}
```

`ownerOnly` is `true` on the signed-in path (`:76`) and `false` on the
no-identity path (`:50-52`), which keeps the legacy shared token and stdio on the
household client exactly as today — they have no address to check and
`tests/tenants.test.ts:88-110` pins that behaviour. `source: "none"` already
flows correctly through every caller: `src/api/server.ts:291,303,315,353` answer
409 with `notConnectedMessage()`, and `src/mcp/server.ts:26-29` returns
`notConnected()`.

Fail-closed follows for free: an unset variable is an empty set, so no signed-in
subject is offered the household. That is why the gitops value must land before
the release — see **Platform impact**.

`Tenant` also gains `subject?: string`, set from the value `resolve()` already
computes. It costs nothing and is what the model budget keys on.

### 3. `src/providers/seerr/guard.ts` — one address guard, used at both ends

A new module with no Fastify or Seerr knowledge:

```ts
export interface GuardOptions { lookup?: (host: string) => Promise<string[]> }
export class BlockedAddressError extends Error {}
export async function assertPublicSeerrUrl(raw: string, opts?: GuardOptions): Promise<{
  url: URL; addresses: string[];
}>
export function isBlockedAddress(ip: string): boolean
```

`assertPublicSeerrUrl` parses the URL and rejects, in order: any scheme other
than `https:`; userinfo; a non-empty query or fragment; a hostname that is
already an IP literal and is blocked; and otherwise resolves the hostname with
the injected `lookup` (default `dns.promises.lookup(host, { all: true, verbatim: true })`)
and rejects if *any* returned address is blocked. Rejecting on any, not all,
means a DNS answer that mixes a public and a private address cannot be used to
win the race.

`isBlockedAddress` works on the parsed form, not on strings, so
`0x7f.1`, `2130706433`, `[::ffff:10.0.0.1]` and `[::ffff:a00:1]` all reduce to
the same decision. Blocked: `0.0.0.0/8`, `10/8`, `127/8`, `169.254/16`
(including `169.254.169.254`), `172.16/12`, `192.168/16`, `100.64/10`,
`192.0.0/24`, `198.18/15`, `224/4`, `240/4`, `255.255.255.255`; `::`, `::1`,
`fc00::/7`, `fe80::/10`, `ff00::/8`, and any IPv4-mapped (`::ffff:0:0/96`) or
IPv4-compatible IPv6 address, which is unwrapped and re-tested as IPv4.

It is called in two places:

- **`src/api/account.ts`**, immediately after `ConnectionSchema.safeParse` and
  *before* the `SeerrClient` is constructed. A `BlockedAddressError` becomes
  400 with a generic message and a warn log naming the host (not the key). This
  is what makes the issue's test assertion — `stubFetch` must not have been
  called — hold.
- **`src/providers/seerr/client.ts`**, inside `fetch()`, for any client marked
  as untrusted.

### 4. `SeerrClient`: untrusted mode, pinning, no redirects, typed failures

`SeerrCredentials` gains `untrusted?: boolean` (set wherever a *user-supplied*
address is used: the `PUT` candidate in `src/api/account.ts:85-90` and the
per-user client in `src/providers/seerr/tenants.ts:61-71`) and an optional
injected `lookup` for tests. `createDefaultSeerrClient()` does not set it, so the
operator's household client is exempt, as the issue requires.

Inside `fetch()`, when `untrusted`:

1. `const { addresses } = await assertPublicSeerrUrl(this.baseUrl, { lookup })`
   — re-run per request, so a name that changed meaning since the `PUT` is
   caught. The result is memoised for a few seconds per client instance to keep
   a burst of tool calls from issuing a resolution each.
2. Pass `dispatcher: new Agent({ connect: { lookup: pinnedLookup(addresses) } })`
   (undici, added as an explicit dependency — it is Node's internal fetch
   implementation but is not importable without it). `pinnedLookup` answers only
   with an address the guard approved and re-checks it with `isBlockedAddress`
   before handing it back, so the TCP connection goes to a vetted address while
   SNI and certificate validation still use the real hostname. This is the
   check-then-connect race the issue asks to close; a stubbed global `fetch` in
   tests simply ignores the dispatcher, which is fine because the guard has
   already run.
3. `redirect: "manual"`, and then an explicit refusal of any 3xx.

Failures become typed rather than stringly:

```ts
export class SeerrUnreachableError extends Error {}      // transport, timeout, 3xx, non-2xx
export class SeerrAccessChallengeError extends Error {}  // Cloudflare Access
```

A 3xx whose `location` host ends in `.cloudflareaccess.com`, or a response
carrying `cf-access-*` / `cf-mitigated: challenge` headers, raises
`SeerrAccessChallengeError`. Everything else raises `SeerrUnreachableError`
carrying the upstream status *internally* — logged, never rendered. The
`PUT` handler maps the two to:

- Access: "That address is behind Cloudflare Access — fill in the Zero Trust
  fields (CF-Access-Client-Id and CF-Access-Client-Secret)."
- otherwise: "Could not reach that Seerr. Check the address and key and try
  again."

The MCP tools already stringify `error.message` (`src/mcp/server.ts:56, 77, 101,
136`); with typed errors carrying no upstream detail, that relay stops being an
oracle. Trusted (household) clients keep today's `Seerr API error: <status>`
message, which only the operator ever sees.

**Why `redirect: "manual"` and not `redirect: "error"`.** `"error"` rejects the
promise before anything about the response can be read, which makes the Access
challenge — a `302` to `*.cloudflareaccess.com` — indistinguishable from any
other failure, and the issue asks for both behaviours in the same pass.
`"manual"` never follows either; it just lets us name what happened. The
security property (no redirect is ever followed, so no second, unvetted host is
dialled) is identical.

### 5. Rate limits: `@fastify/rate-limit`, registered once, `hook: "preHandler"`

Register the plugin with `global: false` and `hook: "preHandler"`. The hook
choice matters: the bearer gate is a global `preHandler`
(`src/api/server.ts:131-164`), and Fastify runs global `preHandler` hooks before
route-level ones, so by the time the limiter's key generator runs, the subject
that gate resolved is on `request.raw.auth`. At `onRequest` — the plugin default
— it would not be.

- Per-IP, via `config.rateLimit` on the routes: `/oauth/authorize`,
  `/oauth/token`, `/oauth/consent`, `/oauth/google/callback`, `/oauth/register`,
  `/account/session`, and `PUT /api/v1/account/connection` (tighter, since each
  call dials an arbitrary host).
- Per-subject on `/mcp` and the `/api/v1/*` routes, with
  `keyGenerator: (req) => subjectOf(req) ?? req.ip`.
- `onExceeding` logs a warn line with the route and whether the key was a
  subject or an IP; the key itself is hashed in the log, never the token.

Two operational notes are part of this change, not afterthoughts. First,
`request.ip` must come from `X-Forwarded-For`, or every request appears to
originate from the ingress controller and a per-IP limit becomes a single global
one — so the Fastify instance is created with `trustProxy: true` (verified
against `createMcpFastifyApp`'s option pass-through; if it does not forward
Fastify options, `fastify.setTrustProxy`-equivalent configuration is applied at
construction instead). Second, the default store is per-process, so during a
rollout two pods each enforce the limit independently. That is accepted: the
limits are a floodgate, not an accounting system.

Health probes (`/health`, `/healthz`, `/ready`, `/readyz`) and `/assets/*` are
left unlimited so kubelet cannot lock itself out.

### 6. The model budget

Three cooperating pieces, all in front of `NebiusIntentExtractor` rather than
inside it, so the LLM class stays a plain adapter.

**Counter.** A new table, added to `SCHEMA_SQL` in `src/auth/store-pg.ts`:

```sql
CREATE TABLE IF NOT EXISTS resolve_usage (
  subject TEXT   NOT NULL,
  day     DATE   NOT NULL,
  count   INT    NOT NULL DEFAULT 0,
  PRIMARY KEY (subject, day)
);
```

New table, not a new column, so the note at `src/auth/store-pg.ts:66-70` is
respected and the on-start `CREATE TABLE IF NOT EXISTS` is enough. Two methods on
the `AuthStore` interface:

```ts
countResolve(subject: string, day: string): Promise<number>;   // INSERT ... ON CONFLICT DO UPDATE SET count = count + 1 RETURNING count
purgeResolveUsage(before: string): Promise<void>;              // called from the existing hourly purge
```

The global ceiling uses the same table under the reserved subject
`"__global__"`, which cannot collide: every real subject is `google:<sub>` or
`static-token`. `MemoryAuthStore` gets the same two methods over a `Map`,
which is correct for a self-hoster and resets on restart.

`countResolve` increments and returns atomically, so two replicas cannot both
see "one below the cap". `purgeResolveUsage` is added to the existing
`purgeExpired` sweep (`src/api/server.ts:107-114`) with a 7-day retention, so the
table does not grow without bound.

**Cache.** A bounded LRU (500 entries, 10 min) keyed on the same `normalise()`
already used in `src/api/resolver/index.ts:41`, holding the extracted
`MediaIntent`. Process-local; a hit costs no budget and no model call. Caching an
intent is safe to share across subjects because the key *is* the query the
caller supplied — a hit returns only what that caller already asked for.

**Gate.** A `BudgetedIntentExtractor implements IntentExtractor` wrapping the
Nebius one:

```ts
async extract(query) {
  const hit = this.cache.get(normalise(query));
  if (hit) return hit;
  if (!(await this.budget.consume(this.subject))) throw new ResolveBudgetError();
  const intent = await this.inner.extract(query);
  this.cache.set(normalise(query), intent);
  return intent;
}
```

`consume` checks the global ceiling and the per-subject cap and increments both.
Both call sites build it: `src/api/server.ts:346-363` (which already builds a
fresh `MediaResolver` per request and now has `tenant.subject` to key on) and
`src/mcp/server.ts:35-39`. `ResolveBudgetError` is caught and rendered as
`{ isError: true, content: [{ type: "text", text: "You have reached today's limit for resolve_media. Try again tomorrow." }] }`
for MCP and HTTP 429 with the same sentence for REST — plainly, not as a silent
degradation.

Counting at the model boundary rather than at the tool boundary means a query
answered by native Seerr search (steps 1-2 of `resolveMedia`) is free. That is
the intent of the issue — the budget exists because the model costs money — and
it is stated explicitly in `requirements.md` so the three documents agree.

### 7. Logging

Pass a logger to the Fastify instance at `src/api/server.ts:91`:

```ts
createMcpFastifyApp({
  host: "0.0.0.0",
  trustProxy: true,
  logger: {
    level: process.env.LOG_LEVEL ?? "info",
    redact: {
      paths: ["req.headers.authorization", "req.headers.cookie", "req.headers['x-api-key']",
              "*.apiKey", "*.seerrApiKeySealed", "*.cfAccessClientSecret"],
      remove: true,
    },
  },
})
```

Pino writes to stdout, which is correct for HTTP mode; stdio mode never reaches
`buildServer` (`src/index.ts:10-19`), so the JSON-RPC channel stays clean. The
warn lines the issue asks for then appear because the call sites already exist
(`src/auth/routes.ts:357,365`, `src/api/account.ts:98`) plus the three added here
(household refusal, blocked address, rate-limit hit, budget exhaustion). If
`createMcpFastifyApp` turns out not to forward Fastify options, the fallback is
to build the Fastify instance directly with the same DNS-rebinding protections
the helper applies — but the option pass-through is the expected shape and is
verified in task 11.

## Alternatives

**Make an empty `SEERRSENSE_ALLOWED_EMAILS` mean "open".** Fewer variables, and
it reads naturally. Dropped because it inverts the one property the current
design is built on: a variable that fails to reach the pod would flip the server
from "nobody" to "everybody". The issue rules it out explicitly and it is right
to.

**Drop the household fallback entirely once open signup exists.** Everyone
attaches their own Seerr; `source: "household"` disappears for signed-in people
and the code gets simpler. Dropped because the owner would lose their own
working setup on rollout with no path back short of attaching their own instance
through the account page, and because the legacy token and stdio paths still
need the shared client. A named owner list is the smaller change and keeps
`tests/tenants.test.ts` meaningful.

**Guard only in the `PUT`, not in `SeerrClient`.** One call site, no per-request
DNS cost. Dropped because it is exactly the DNS-rebinding hole the issue names:
a hostname that resolves publicly at validation time and privately at dial time
is stored once and then dialled on every tool call for as long as the connection
exists. Guarding at dial time is what makes the stored row safe, not just the
submission.

**Put the SSRF guard in an egress `NetworkPolicy` instead of code.** Genuinely
strong, and the platform supports it (`allow_internet_egress` on the workspace).
Dropped as the *only* measure: it lives in `mctl-gitops`, not this repo, so a
`npx seerrsense` self-hoster gets nothing, and a policy broad enough to permit
arbitrary user Seerr instances on the internet cannot express "not the pod's own
neighbours" precisely. Recommended as defence in depth in the operator
checklist, not as a substitute.

**Keep the resolve counter in memory.** No schema change, no database call on the
resolve path. Dropped because the issue asks specifically for a counter that
survives a restart, and because a rollout restarts the pod — resetting every
budget — several times a week. The database round trip happens only on a query
that reaches the model, which already costs a 20 s-budget model call.

**Do the rate limiting in the ingress controller.** Cheaper, and outside the
process. Dropped because a per-subject limit needs the verified JWT subject,
which the ingress does not have, and because self-hosters have no ingress.

## Platform impact

**Migrations.** One new table, `resolve_usage`, created by the existing on-start
`CREATE TABLE IF NOT EXISTS` under the advisory lock at
`src/auth/store-pg.ts:99-112`. No existing table is altered and no column is
added to one, so the caveat at `:66-70` does not apply. Rolling back the release
leaves an unused table behind, which is harmless.

**New dependencies.** `@fastify/rate-limit` and `undici` (for `Agent` and the
pinned `connect.lookup`; Node 22 ships undici internally but does not expose it
as an importable module). Both are runtime dependencies and both go into the
production image (`Dockerfile`, `npm ci --omit=dev`).

**New environment variables**, all optional and all fail-closed:
`SEERRSENSE_OPEN_SIGNUP`, `SEERRSENSE_HOUSEHOLD_EMAILS`,
`SEERRSENSE_RESOLVE_DAILY_LIMIT`, `SEERRSENSE_RESOLVE_GLOBAL_DAILY_LIMIT`,
`SEERRSENSE_RATE_LIMIT_*`, `LOG_LEVEL`. Documented in the README table at
`README.md:94-119`.

**Backward compatibility and the rollout ordering.** This is the one hazard.
`SEERRSENSE_HOUSEHOLD_EMAILS` is fail-closed, so the release that reads it will,
on an unchanged `values.yaml`, take the household instance away from the owner —
their signed-in subject has no `user_connections` row today and would resolve to
`source: "none"`. The gitops change setting `SEERRSENSE_HOUSEHOLD_EMAILS` to the
owner's address **must be merged and synced before the image carrying this
change is deployed**. Setting a variable the running image ignores is a no-op, so
the ordering is safe in that direction and only in that direction. Everything
else is compatible by construction: `SEERRSENSE_OPEN_SIGNUP` unset reproduces
today's allowlist behaviour exactly, the guard exempts the operator's household
client, and the legacy token and stdio paths are untouched.

**Resource impact.** One DNS resolution per untrusted dial (memoised for a few
seconds per client), one `INSERT ... ON CONFLICT` per model call, and one
in-process counter map per rate-limited route. The intent cache is bounded at 500
entries. The MCP hot path keeps its "no database read per tool call" property:
`TenantResolver`'s 60 s cache is unchanged, and the resolve counter is touched
only on the resolve path.

**Risks and mitigations.**

- *An `undici` `Agent` per request is expensive.* Mitigated by constructing one
  dispatcher per `SeerrClient` instance and reusing it while the pinned
  addresses are still fresh; a per-user client already lives for the 60 s tenant
  cache window.
- *The guard refuses a legitimate Seerr on a private LAN.* This is intended for
  the hosted public server and is a real regression for a self-hoster whose
  Overseerr is at `http://192.168.1.5:5055`. Mitigated by applying the guard only
  to *stored, user-submitted* connections — the household client from
  `SEERR_URL` stays exempt, which is the path a self-hoster on a LAN uses.
- *`trustProxy` misconfiguration.* Trusting `X-Forwarded-For` unconditionally
  lets a caller forge their own IP and evade a per-IP limit. Mitigated by
  trusting only the hop count the ingress actually adds rather than the whole
  chain, and by the per-subject limits, which are not IP-derived.
- *Per-process rate-limit state.* Two pods during a rollout mean up to double the
  configured limit. Accepted; noted in the README.
- *Open signup plus a public `resolve_media`.* The global daily ceiling is the
  backstop if a single subject's cap is set too generously; both are environment
  variables and can be lowered without a release.
- *Enabling the logger surfaces something noisy or sensitive.* Mitigated by the
  redaction list and by starting at `info` with the ability to set `LOG_LEVEL`
  in gitops; the tests assert that no API key appears in a log line.
