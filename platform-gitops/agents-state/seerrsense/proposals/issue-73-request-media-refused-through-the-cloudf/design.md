# Design: issue-73-request-media-refused-through-the-cloudf

## Current state

The authorization server lives in `src/auth/`, mounted by
`src/api/server.ts` through `registerOAuthRoutes` (`src/auth/routes.ts:225`).

Scopes are declared once, in `src/auth/config.ts:14-17`:

```ts
export const SCOPE_READ = "seerr:read";
export const SCOPE_REQUEST = "seerr:request";
export const SCOPE_OFFLINE = "offline_access";
export const SUPPORTED_SCOPES = [SCOPE_READ, SCOPE_REQUEST, SCOPE_OFFLINE] as const;
```

`SUPPORTED_SCOPES` is what both `.well-known` documents advertise
(`src/auth/routes.ts:266` for RFC 8414, `:276` for RFC 9728).

The authorize handler (`src/auth/routes.ts:299`) validates the query with
`AuthorizeQuerySchema` (`:23`, where `scope` is `z.string().max(1024).optional()`),
resolves the client, checks the redirect URI and the `resource`, and then
computes the granted set at `:330`:

```ts
const requested = (params.scope ?? SCOPE_READ).split(/\s+/).filter(Boolean);
const unknown = requested.filter((scope) => !SUPPORTED_SCOPES.includes(scope as never));
```

That single `?? SCOPE_READ` is the defect. The resulting string is persisted on
the pending authorization (`store.putPendingAuth({ ..., scope: requested.join(" ") })`,
`:340-351`) and carried unchanged through the whole flow:

- the Google callback re-parks it under a consent handle (`:409-416`) and
  renders the consent page from it (`scopes: pending.scope.split(/\s+/)`, `:441`),
  labelled by `SCOPE_LABELS` (`:78`);
- `POST /oauth/consent` copies it onto the authorization code (`:464-475`);
- `redeemAuthorizationCode` (`:171`) returns it, and `issueTokens` (`:556`)
  both signs it into the access token's `scope` claim and stores it on the
  refresh token row;
- a refresh grant re-issues `record.scope` verbatim (`:533-540`), which is why
  a narrow grant never widens by itself.

Enforcement reads that claim back. `authenticate` (`src/auth/verifier.ts:42`)
splits the `scope` claim into `AuthInfo.scopes`; the `/mcp` pre-handler refuses
anything without `seerr:read` (`src/api/server.ts:396`); and `request_media`
checks `SCOPE_REQUEST` itself (`src/mcp/server.ts:346`), producing the exact
message in the issue.

Clients divide into two kinds. The account page names its scope explicitly —
`url.searchParams.set("scope", "seerr:read")` in `public/account.html:207` —
and must stay read-only: a page session must not be able to file requests. The
test helper in `tests/oauth.test.ts:126` also always sends a scope, which is
why no existing test covers the no-scope path. The Cloudflare MCP portal sends
no `scope` at all, lands on the `?? SCOPE_READ` branch, and ends up with a
token that passes the `/mcp` read gate and fails the `request_media` check.

Storage needs no attention: `scope` is a plain `TEXT NOT NULL` column on all
three tables in `src/auth/store-pg.ts:22,36,46`, and a bare string on the
in-memory store's records (`src/auth/store.ts:14,32,48`).

## Proposed solution

Move the default out of the handler and into the place the scope vocabulary is
already declared, then apply it only when the request named nothing.

1. **`src/auth/config.ts`** — add, next to `SUPPORTED_SCOPES`, an exported
   constant and the comment explaining it:

   ```ts
   /**
    * RFC 6749 §3.3 requires a server that receives no `scope` to either fail
    * the request or use a documented default. This is that default: everything
    * an interactive client is expected to use. offline_access is deliberately
    * absent — a refresh token is issued regardless, and returning a scope the
    * client never asked for makes both ChatGPT and Claude warn the user.
    */
   export const DEFAULT_SCOPES = [SCOPE_READ, SCOPE_REQUEST] as const;
   ```

   Keeping it beside `SUPPORTED_SCOPES` is the point: the advertised set and
   the default set cannot drift into different files.

2. **`src/auth/routes.ts:330`** — replace the `??` with an explicit
   "named nothing" test, so a present-but-empty `scope` takes the same branch
   as an absent one rather than collapsing to a zero-scope grant:

   ```ts
   const named = (params.scope ?? "").split(/\s+/).filter(Boolean);
   const requested = named.length > 0 ? named : [...DEFAULT_SCOPES];
   ```

   Everything downstream is unchanged: `requested.join(" ")` is persisted, the
   `invalid_scope` check at `:331` still runs against the named set, and the
   consent page therefore lists both grants for a portal login without any
   change to `consentPage`. Import `DEFAULT_SCOPES` from `./config.js`; while
   in that import line, drop `SCOPE_OFFLINE`, which `routes.ts` imports at `:6`
   and never uses, and `SCOPE_READ` if the edit leaves it unreferenced.

3. **`tests/oauth.test.ts`** — teach `getAuthorizationCode`/`runFlow` to omit
   the `scope` query parameter (e.g. `scope: null` meaning "send none"), then
   add the regression cases described in tasks.md. The helper currently hard
   codes `scope: options.scope ?? "seerr:read seerr:request"` (`:126`), so
   today no test can even express the failing request.

4. **`README.md`** — extend the scopes bullet in Security Model (`:405-408`)
   with the documented default and the consequence for existing grants: a
   grant already issued keeps its scope across refreshes, so a client that was
   connected before this change must re-authorize once to widen.

Why this shape rather than patching the symptom: the grant string is computed
in exactly one place and flows unchanged through pending auth, code, access
token and refresh token. Fixing it at that one place fixes the portal, any
future silent client, and the consent screen's own rendering simultaneously,
and leaves every enforcement point (`src/api/server.ts:396`,
`src/mcp/server.ts:346`) untouched, so the least-privilege model is preserved
rather than weakened.

The security argument for the wider default: the scope set is not what makes a
grant safe here. Approval is. Nothing is issued until a signed-in, allowlisted
person clicks Allow on a page that names the client, the redirect host and
every capability being handed over (`src/auth/routes.ts:437-445`). A default
that silently omits `seerr:request` does not protect that person — it produces
a token that fails halfway through the only workflow the product exists for,
while the consent screen already told them requests were included.

## Alternatives

1. **Teach the Cloudflare portal to name its scopes** — change the upstream
   OAuth registration in `mctl-gitops` (`infrastructure/cloudflare/portal`,
   applied through the portal-server-auth apply job) so it requests
   `seerr:read seerr:request`. Dropped as the primary fix: it repairs one
   client while every other RFC-conformant client that omits `scope` stays
   half-broken, it puts the fix in a different repository from the defect, and
   the issue's acceptance criteria are written against the server's default.
   It remains available as an optional belt-and-braces follow-up.

2. **Stop checking `seerr:request` in `request_media`, or grant every supported
   scope at the token gate** — dropped. It would give the account page's
   deliberately read-only grant (`public/account.html:207`) the power to file
   requests, and it would delete the distinction the consent screen advertises.
   `tests/oauth.test.ts:1125` exists precisely to keep that distinction.

3. **Widen narrow grants at refresh time** — have the refresh branch
   (`src/auth/routes.ts:533`) upgrade a `seerr:read`-only grant to the new
   default, so the portal heals without re-authorizing. Dropped: it escalates a
   grant beyond what the person consented to, on a code path with no user
   present, and it breaks the invariant that a refresh returns the grant's own
   scope. Re-authorizing the portal once is the honest cost.

4. **Make the default configurable (`SEERRSENSE_DEFAULT_SCOPES`)** — dropped.
   RFC 6749 §3.3 asks for a *documented* default, not a tunable one; a knob
   here adds validation surface, another way for a deployment to be subtly
   wrong, and a second source of truth beside `SUPPORTED_SCOPES`.

## Platform impact

- **Migrations:** none. `scope` is already `TEXT NOT NULL` in all three tables
  (`src/auth/store-pg.ts:22,36,46`); only the value written changes.
- **Backward compatibility:** existing access and refresh tokens are untouched,
  and refreshes keep returning the grant's stored scope. Clients that name
  their scopes — the account page, the direct Claude connector, every existing
  test except the new ones — see no behaviour change. The one visible change is
  that a fresh authorization with no `scope` now yields a token whose `scope`
  response field is `seerr:read seerr:request`.
- **Operational follow-up:** the portal's `seerrsense` upstream must be signed
  out and signed back in once after deploy for its token to pick up the new
  default; the Ratatouille repro (TMDB 2062) is the acceptance check.
- **Risk: a client that omitted `scope` intending read-only now receives write
  capability.** Mitigated by the consent page, which lists "Request new films
  and series on your behalf" before anything is granted, and by the fact that
  read-only remains expressible with an explicit `scope=seerr:read` — a
  property pinned by a test. `request_media` still performs its own check, so
  no enforcement path is loosened; only the grant a person is asked to approve
  changes.
- **Risk: the default and the advertised set drift apart.** Mitigated by
  declaring `DEFAULT_SCOPES` in `src/auth/config.ts` beside `SUPPORTED_SCOPES`,
  and by a test asserting every default scope is a supported one.
- **Resource impact:** none. No new requests, storage or model calls; the grant
  string grows by fourteen characters.
- **Rollout:** ordinary container deploy of `seerrsense`; no coordination with
  the database or the portal beyond the one re-authorization above. Reverting
  the two source lines restores the old behaviour exactly.
