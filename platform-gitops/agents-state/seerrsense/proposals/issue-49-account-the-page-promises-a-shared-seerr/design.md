# Design: issue-49-account-the-page-promises-a-shared-seerr

## Current state

**Who reaches the household Seerr.** `TenantResolver`
(`src/providers/seerr/tenants.ts:38-133`) is built once in
`src/api/server.ts:310-317` from the auth store, the encryption key,
`createDefaultSeerrClient()` (which returns `undefined` when `SEERR_API_KEY` is
unset, `src/providers/seerr/client.ts:435-444`) and
`authSettings.oauth?.householdEmails` — a lowercased `Set` parsed once in
`src/auth/config.ts:115-120`. `resolve()` returns the person's own instance if a
`user_connections` row exists, otherwise calls `householdTenant(email, subject,
true)`, which refuses at `tenants.ts:116-119`:

```ts
if (!this.household) return { email, source: "none", subject };
if (ownerOnly && !this.householdEmails.has(email.toLowerCase())) {
  return { email, source: "none", subject };
}
```

`ownerOnly` is false only for the legacy shared token and stdio mode
(`tenants.ts:58-59`), which keep the old behaviour. When the result is
`source: "none"`, every HTTP route and MCP tool answers with
`notConnectedMessage` (`tenants.ts:136-139`, used at `server.ts:530`, `545`,
`561`, `605`).

**What the account page is told.** `GET /api/v1/account/connection`
(`src/api/account.ts:72-85`) returns `email`, `connected` (a row exists or not),
`seerrUrl`, `cfAccessConfigured`, `updatedAt`. It knows nothing about the
household rule. `public/account.html:145-152` branches on `connected` alone and,
in the `else` arm, prints "Using the shared Seerr until you attach your own." The
disconnect handler (`account.html:180-185`) repeats the same untruth with
"Disconnected. Using the shared Seerr again." Existing tests pin the response
shape: `tests/account.test.ts` asserts
`Object.keys(body).sort()` equals
`["cfAccessConfigured", "connected", "email", "seerrUrl", "updatedAt"]`.

**The session.** `issueSession` (`src/auth/session.ts:20-34`) signs an HS256 JWT
with audience `${issuer}/account` and an 8-hour expiry; `POST /account/session`
sets it as `seerrsense_session` with `path:"/"`, `httpOnly:true`,
`sameSite:"lax"`, `secure` iff the issuer is https (`server.ts:511-518`).
`readSession` (`session.ts:36-53`) verifies it statelessly. `@fastify/cookie` is
registered at `server.ts:374`, in the same nested plugin scope where
`registerAccountRoutes` is called (`server.ts:464`), so `reply.clearCookie` is
available to those routes. Nothing clears the cookie: `logout`, `signout` and
`clearCookie` appear nowhere under `src/`.

**Route gating.** `PUBLIC_PREFIXES` (`server.ts:35-57`) skips the bearer gate for
the page and its sign-in leg; `SESSION_PREFIXES = ["/api/v1/account/"]`
(`server.ts:65`) marks routes that authenticate themselves with the cookie and
deliberately refuse an MCP token (`server.ts:328-329`). Any new route under
`/api/v1/account/` inherits that treatment with no change to either list.

**Storage.** `AuthStore` (`src/auth/store.ts:71-98`) has `MemoryAuthStore` and
`PostgresAuthStore` implementations; `PostgresAuthStore.init` creates its tables
with `CREATE TABLE IF NOT EXISTS` (`store-pg.ts:16-72`) and `purgeExpired`
(`store-pg.ts:226-229`) deletes expired OAuth rows. The server runs
`purgeExpired` at boot and hourly (`server.ts:383-394`).

## Proposed solution

Three changes, in dependency order.

### 1. One predicate, two callers (`src/providers/seerr/tenants.ts`)

Extract the household admission rule into a public, synchronous, side-effect-free
method on `TenantResolver`, and have `householdTenant` call it:

```ts
/**
 * What a signed-in caller with no connection of their own reaches. This is the
 * resolver's own decision, exposed so the account page can state the truth
 * instead of keeping a second copy of the rule that drifts from this one.
 */
householdFallback(email: string): "household" | "none" {
  if (!this.household) return "none";
  if (!this.householdEmails.has(email.toLowerCase())) return "none";
  return "household";
}
```

`householdTenant(email, subject, ownerOnly)` then refuses when
`ownerOnly ? this.householdFallback(email) === "none" : !this.household`, and is
otherwise unchanged — the `findUserIdByEmail` attribution at `tenants.ts:123-130`
stays on the resolve path only, so the account API costs no network call.

This is what makes the two answers unable to diverge: deleting the membership
check inside `householdFallback` changes both the resolver's behaviour and the
page's statement at once, which is precisely the mutation the issue asks the
tests to catch. It also folds in the `!this.household` case, which a second copy
of `SEERRSENSE_HOUSEHOLD_EMAILS` read from config in `account.ts` would have
missed: with `SEERR_API_KEY` unset there is no shared instance for anyone,
listed or not.

### 2. The connection endpoint reports the effective answer (`src/api/account.ts`)

`registerAccountRoutes` already receives the live `TenantResolver`
(`account.ts:32`, wired at `server.ts:464`), so no new dependency is needed. The
GET handler adds one field:

```ts
const fallback = tenants.householdFallback(session.email);
return reply.header("cache-control", "no-store").send({
  email: session.email,
  connected: connection !== undefined,
  // What this caller reaches with no connection of their own — the resolver's
  // own answer, not a second reading of SEERRSENSE_HOUSEHOLD_EMAILS.
  fallback,
  seerrUrl: connection?.seerrUrl,
  cfAccessConfigured: connection?.cfAccessClientIdSealed !== undefined,
  updatedAt: connection?.updatedAt,
});
```

`fallback` is always present, including while `connected` is true, where it
answers "and what would I have if I disconnected". `DELETE
/api/v1/account/connection` (`account.ts:184-190`) returns it alongside
`connected: false` for the same reason, so the page can state the truth after a
disconnect without a second round trip. `PUT` is untouched: a successful save
always means `source: "own"`.

The existing key-set assertion in `tests/account.test.ts` must gain `"fallback"`;
that assertion exists to prove no secret leaks into the payload, and the new
field is a two-value enum derived from configuration the caller already
influences, so it is safe to add there.

### 3. Sign out: `DELETE /api/v1/account/session` plus session revocation

**Route.** Registered in `registerAccountRoutes`, so it sits under
`SESSION_PREFIXES` and therefore skips the bearer gate, refuses an MCP access
token by audience, and needs no edit to `PUBLIC_PREFIXES`. `DELETE` rather than
`GET` means no prefetch or prerender can trigger it, and it is not a CORS-simple
method, so a cross-origin attempt needs a preflight that this server does not
answer; the `SameSite=Lax` cookie would not be attached to a cross-site request
in any case. `DELETE` also matches the existing `DELETE
/api/v1/account/connection` shape rather than inventing a verb-in-path route.

```ts
fastify.delete("/api/v1/account/session", async (request, reply) => {
  const session = await sessionOf(request);          // undefined is fine
  if (session?.id && session.expiresAt) {
    await store.revokeSession(session.id, session.expiresAt);
  }
  return reply
    .header("cache-control", "no-store")
    .clearCookie(SESSION_COOKIE, {
      path: "/",
      httpOnly: true,
      sameSite: "lax",
      secure: config.issuer.startsWith("https://"),
    })
    .send({ signedOut: true });
});
```

The attributes mirror `server.ts:512-518` exactly — a `clearCookie` whose `path`
or `secure` differs sets a *second* cookie and leaves the original in place. The
route is idempotent: a missing, expired or forged cookie still clears and still
answers 200, so a stale session is always clearable. It touches neither
`oauth_refresh_tokens` nor `user_connections`.

**Revocation.** Clearing a cookie only tells the browser to forget it; the JWT
stays valid for up to 8 hours if the value was ever captured, so sign-out without
a server-side record cannot actually end a session. A minimal denylist keyed on
the session's `jti`:

- `src/auth/session.ts`: `issueSession` adds `.setJti(randomUUID())`;
  `readSession` returns `id` (the `jti`) and `expiresAt` (the `exp`) on the
  `Session`, and accepts an optional `isRevoked?: (id: string) => Promise<boolean>`
  dependency, returning `undefined` when the token carries a revoked `jti`.
- `src/auth/store.ts` / `store-pg.ts`: `revokeSession(id, expiresAt)` and
  `isSessionRevoked(id)`. Memory: a `Map<string, number>`. Postgres: `CREATE
  TABLE IF NOT EXISTS revoked_sessions (jti TEXT PRIMARY KEY, expires_at BIGINT
  NOT NULL)` in `init`, plus one more `DELETE ... WHERE expires_at < $1` line in
  `purgeExpired`, which the server already runs at boot and hourly.
- `src/api/account.ts`: `sessionOf` passes `isRevoked: (id) =>
  store.isSessionRevoked(id)`, so every `/api/v1/account/*` route refuses a
  revoked cookie with the 401 it already returns for an unreadable one.

Cost is one indexed primary-key lookup per account-API request, on a path that
already reads `user_connections`. The `/mcp` hot path never calls `readSession`
and is unaffected. The table holds one row per sign-out for at most 8 hours.

Cookies issued before this deploy carry no `jti`: `readSession` accepts them as
today (nothing to look up), and sign out still clears them. They age out within
`SESSION_TTL_SECONDS`.

### 4. The page states one of three true things (`public/account.html`)

Replace the two-arm branch at `account.html:145-152` with a single renderer used
by `load()`, by the disconnect handler, and by the save handler:

```js
function renderStatus(body) {
  var who = "Signed in as " + body.email + ". ";
  if (body.connected) return show(who + "Connected to " + body.seerrUrl + ".", "ok");
  if (body.fallback === "household") {
    return show(who + "Using the shared Seerr until you attach your own.");
  }
  // Unknown or absent fallback lands here on purpose: never promise an
  // instance this account may not be allowed to reach.
  return show(who + "No Seerr is connected yet — attach yours below to start.");
}
```

The third state uses the neutral `.status` style, not `.is-bad`, so a normal
starting state does not look like a failure, and echoes the tone of
`notConnectedMessage` so the assistant's answer reads as a continuation of the
page rather than a fault. The disconnect handler at `account.html:180-185` calls
`renderStatus` with the `DELETE` response instead of its hardcoded sentence.

A `Sign out` control (`<button class="btn btn-secondary" id="sign-out">`) is
added inside `#signed-in`, above the status line and away from the form's
`Disconnect` button, so the "end my browser session" and "detach my Seerr"
actions are never adjacent. It is visible whenever `#signed-in` is shown; it is
never hidden. Its handler issues `fetch("/api/v1/account/session", { method:
"DELETE", credentials: "same-origin" })` and then `location.reload()`, which
re-runs `load()`, meets a 401, and renders the signed-out block with no residual
values left in the form — the right outcome on a borrowed computer.

No address is ever rendered into the served HTML, so the existing assertions at
`tests/account.test.ts` that `/account`'s payload contains no email address stay
true: every value still arrives as JSON and is written with `textContent`.

## Alternatives

**Read `SEERRSENSE_HOUSEHOLD_EMAILS` in `account.ts` from `OAuthConfig`.** The
`config` argument already carries `householdEmails` (`src/auth/config.ts:147`),
so the endpoint could test membership itself in two lines and touch no other
file. Dropped: it is a second copy of the rule, which is the bug the issue is
about, and it silently gets the `SEERR_API_KEY`-unset case wrong — a listed
address would be told it has a shared instance that `createDefaultSeerrClient()`
never built.

**Have the endpoint call `tenants.resolve()` and report `tenant.source`.** The
most literally accurate answer. Dropped: `resolve()` populates the per-subject
cache and, on the household path, makes a `findUserIdByEmail` call to the shared
Seerr (`tenants.ts:123-130`) — a network round trip and a cache write on what is
today a cheap page load, plus it would build a per-user `SeerrClient` (and its
undici agent) purely to answer a question about a boolean.

**Per-subject session epoch instead of a `jti` denylist.** Store one
"sessions issued before T are invalid" timestamp per subject; sign-out sets it to
now. One row per person forever instead of one per sign-out, and it gives
"sign out everywhere" free. Dropped: it also signs the person out of their other
devices, which is not what a sign-out button on one browser implies, and the
issue is explicit that this "ends the browser session only".

**Cookie clearing with no revocation at all.** Smallest possible change, and it
fully addresses the stated borrowed-computer threat since the `httpOnly` cookie's
only copy lives in that browser. Dropped as the primary design because the
issue's verification requires the old cookie value to be refused afterwards, and
because a sign-out that cannot end a leaked session is a weaker promise than the
button implies. Recorded as the fallback if the reviewer wants a smaller diff.

**`POST /api/v1/account/logout`.** Equivalent on safety. Dropped for consistency:
the account API is resource-shaped (`GET`/`PUT`/`DELETE` on
`/api/v1/account/connection`), and the session is a resource this deletes.

## Platform impact

**Migrations.** One additive table, `revoked_sessions`, created by
`PostgresAuthStore.init` with `CREATE TABLE IF NOT EXISTS` — the same mechanism
every existing table uses (`store-pg.ts:16-72`). No existing table is altered,
so a rollback needs no down-migration; the table is simply left unused. Note the
warning already in `store-pg.ts:73`: `CREATE TABLE IF NOT EXISTS` never alters an
existing table, which is fine here because the table is new.

**Backward compatibility.**

- API: `fallback` is an added field. Existing clients that read `connected` keep
  working. The one place this is pinned is the key-set assertion in
  `tests/account.test.ts`, which must be updated in the same change.
- Sessions: cookies issued before the deploy have no `jti` and stay valid until
  they expire; they cannot be individually revoked, only cleared. The window is
  at most 8 hours after rollout.
- MCP: nothing on the `/mcp` path changes. `readSession` is not on it, the
  resolver's cached behaviour is unchanged, and refresh tokens are untouched, so
  Claude and ChatGPT connections survive a sign-out.
- Self-hosters running `MemoryAuthStore` lose the denylist on restart, exactly as
  they already lose refresh tokens (`src/auth/store.ts:100-104`). Worth one line
  in the README.

**Resource impact.** One primary-key lookup added per `/api/v1/account/*`
request — a page-load-frequency path that already queries `user_connections`. One
row per sign-out, retained no longer than that session's own expiry and swept by
the hourly `purgeExpired` the server already schedules. `householdFallback` is a
`Set` membership test: no I/O.

**Risks and mitigations.**

- *Mismatched `clearCookie` attributes leave the session alive.* A `path` or
  `secure` mismatch sets a second cookie instead of clearing the first. Mitigated
  by deriving both from the same expressions used at `server.ts:512-518` and by
  asserting the `Set-Cookie` attributes in a test.
- *The denylist lookup being skipped on some route.* It lives inside `sessionOf`
  in `account.ts`, the single entry point every account route already uses, so a
  new route cannot forget it.
- *Wording converging again.* Covered by a test asserting the served page carries
  all three distinct sentences and still branches on `fallback`.
- *`fallback` misread as "what I have now" while connected.* Mitigated by naming
  (`fallback`, not `source`), a comment at the field, and a README line.
- *Denylist growth if `purgeExpired` stops running.* Bounded in practice by
  sign-out frequency; the rows are tiny and the sweep is already wired at boot
  as well as hourly.
