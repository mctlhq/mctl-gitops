# Design: issue-65-stop-returning-the-github-access-token-t

## Current state

The GitHub OAuth flow lives entirely in `cloudflare-worker/index.js`:

- `handleGitHubLogin` (`index.js:465-502`) starts the flow, requesting scope
  `read:user user:email` (`index.js:483`), and records a `for=` flow marker
  (`mcp`, `docs`, `tg-mcp`, or none) in the `__gh_flow` cookie.
- `handleGitHubCallback` (`index.js:506-627`) exchanges the `code` for an
  access token (`index.js:530-547`), fetches `/user` and `/user/emails` with
  it (`index.js:552-555`), then branches:
  - **Fragment-redirect flows** (`docs`/`mcp`/`tg-mcp`,
    `index.js:576-603`): builds `mcpPayload` which includes
    `token: accessToken` (`index.js:583-592`), stores it server-side via
    `putOAuthSession` (Cache API, `index.js:239-247`), and also packs the
    *entire* payload — token included — into an AES-GCM encrypted, HttpOnly
    `__gh_session` cookie via `encryptSessionPayload` (`index.js:299-311`,
    `594`, `601`). The redirect to the consuming origin
    (`docs.mctl.ai/mcp/connecting` or
    `labs-mctl-telegram.mctl.ai/telegram/connect`) carries only an opaque
    `#session=<id>` fragment (`fragmentSuccessLocation`, `index.js:227-229`).
  - **Normal landing flow** (`index.js:605-627`): builds `userData` with
    only `login`, `name`, `email`, `avatar_url`, `html_url`, `sig` — no
    token — and delivers it base64-encoded in the URL fragment
    (`landingSuccessLocation`).
- `handleGitHubSession` (`index.js:655-701`) backs `POST /api/github/session`,
  called by the consuming page's JS to redeem either the one-time `code`
  (session id) or the `__gh_session` cookie:
  - Redeems via `takeOAuthSession` (Cache API, one-time consume,
    `index.js:262-274`) and/or `redeemFromCookie` (`index.js:257-260`,
    requires **both** a live decrypted cookie **and** a live cache hit).
  - **The bug**: at `index.js:699-700`, the response body is built by
    destructuring out only `sessionId` and `exp`:
    ```js
    const { sessionId: _sessionId, exp: _exp, ...clientPayload } = payload;
    return new Response(JSON.stringify(clientPayload), { status: 200, headers });
    ```
    Every other field of `payload` — including `token` — is spread into
    `clientPayload` and shipped to the browser as JSON. This is a
    **blocklist**: any field added to `mcpPayload` in the future is exposed
    by default unless someone remembers to also update this destructure.
- `oauth.test.mjs` currently unit-tests fragment-URL shape, encryption
  round-trips, HMAC verification, and `redeemFromCookie`'s liveness
  semantics, but has no test asserting what `handleGitHubSession`'s HTTP
  response body actually contains — `handleGitHubSession` itself is not
  exported from `index.js`, so there is no way to unit-test the response
  shape today without spinning up the full `fetch` handler.

## Proposed solution

1. **Stop putting the token in the session payload at the source.**
   In `handleGitHubCallback`, remove `token: accessToken` from `mcpPayload`
   (`index.js:583-592`). `accessToken` is already fully consumed by the two
   `githubAPI()` calls that happen before `mcpPayload` is built
   (`index.js:552-555`); nothing else in the worker reads `payload.token`
   after that point. This means the token is never written to the Cache API
   entry and never encrypted into the `__gh_session` cookie in the first
   place — the smallest possible blast radius, and it makes the "expected
   fix" bullet ("strip the token from the session payload") literally true
   at its origin rather than only at the response boundary.

2. **Make the HTTP response an explicit allowlist, not a blocklist.**
   Replace the destructuring at `index.js:699-700` with a small exported
   pure function, e.g.:
   ```js
   const SESSION_RESPONSE_FIELDS = ['login', 'name', 'avatar_url', 'html_url', 'sig'];

   export function buildSessionResponsePayload(payload) {
     const out = {};
     for (const key of SESSION_RESPONSE_FIELDS) {
       if (key in payload) out[key] = payload[key];
     }
     return out;
   }
   ```
   and call it from `handleGitHubSession`:
   ```js
   return new Response(JSON.stringify(buildSessionResponsePayload(payload)), { status: 200, headers });
   ```
   This is defense in depth on top of (1): even if a future change
   reintroduces a sensitive field into the internal payload (token,
   internal ids, etc.), it does not reach the browser unless someone
   deliberately adds it to `SESSION_RESPONSE_FIELDS`. It also makes the
   response shape independently unit-testable (see Tasks/Tests) without
   needing to drive the full `fetch` handler or Cache API.

3. **No change to the normal landing flow, `check-team`, or the OAuth
   login/callback state machine.** `userData` (`index.js:609-616`) already
   excludes the token and is untouched. `handleCheckTeam` doesn't touch
   session payloads at all. The `code`/state-cookie CSRF check, the
   one-time cache consume semantics (`sessionIsLive`, `redeemFromCookie`,
   `takeOAuthSession`), and the cookie encryption mechanism are unchanged —
   only the *contents* of what gets encrypted/cached and what gets
   returned are reduced.

4. **Update `oauth.test.mjs`** to cover the new behavior (see tasks.md):
   assert `buildSessionResponsePayload` never includes `token`/`access_token`
   even when given a payload that has one (guards against regression if
   someone re-adds `token` to `mcpPayload` later), and assert it does
   include the expected identity fields when present.

## Alternatives

1. **Keep storing the token server-side (cache + cookie) and only filter
   it out of the HTTP response (i.e. just fix `index.js:699-700`, skip step
   1 above).** Rejected as the sole fix: it satisfies the acceptance
   criteria ("no token in any response reaching the browser") but leaves the
   token sitting in two extra places (Cache API entry, encrypted cookie)
   for no functional benefit, since nothing in this codebase ever reads it
   back out. Doing both (1) and (2) costs nothing extra and is strictly
   safer. Kept as a fallback: if the open question about downstream
   consumers resolves to "yes, some backend needs the token server-side",
   step 1 is the one part of this design that would need to be revisited
   (see Platform impact).

2. **Add a new worker endpoint that mediates GitHub-API-on-behalf-of-user
   calls for `docs`/`tg-mcp` consumers, so they never need the raw token at
   all**, per the issue's second "expected fix" bullet. Rejected for *this*
   proposal: there is no evidence in this repo that any consumer actually
   needs to act as the user against the GitHub API — the scope granted is
   only `read:user user:email`, and the sibling landing flow proves identity
   + HMAC `sig` is sufficient for this worker's own downstream consumer
   (`handleFormSubmit` validates `github_auth.sig` via `hmacVerify`,
   `index.js:764`). Building a speculative proxy endpoint without a known
   caller would add unverifiable surface area. If the open question
   surfaces a real need, that becomes its own follow-up proposal scoped
   with the actual consuming repo.

3. **Rotate/shorten token TTL or scope it down further as compensating
   control instead of removing it from the response.** Rejected: it doesn't
   address the actual defect (token reaching browser JS), and the issue's
   acceptance criteria are explicit that no token field should reach the
   browser at all, not that its exposure window should shrink.

## Platform impact

- **Backward compatibility**: If `docs.mctl.ai/mcp/connecting` or
  `labs-mctl-telegram.mctl.ai/telegram/connect` currently read `data.token`
  from the `/api/github/session` response and depend on it, this change
  breaks that specific behavior for those two pages (their other fields —
  `login`, `name`, `avatar_url`, `html_url`, `sig` — are unaffected). Per
  the open question in requirements.md, this is treated as unlikely given
  the token's narrow scope and the precedent set by the landing flow, but
  it is a real cross-repo risk. Mitigation: call this out explicitly in the
  PR description so reviewers with visibility into `mctl-docs`/
  `mctl-telegram` can flag it before merge; the change is a single-file,
  easily-revertible worker diff if a real dependency surfaces.
- **Migrations**: None. No data store schema changes; the Cache API entry
  and cookie are ephemeral (TTL `SESSION_TTL_SEC = 300`s) and self-expire.
- **Resource impact**: Negligible — the payload shrinks slightly (one fewer
  string field), no new external calls.
- **Risks**:
  - *Silent breakage of a downstream consumer* (see backward compatibility
    above). Mitigated by flagging in the PR and by the fact that
    `SESSION_ORIGINS` (`index.js:28-32`) is a small, known, allowlisted set
    of two extra origins, making it easy to reach out directly if needed.
  - *Regression re-introducing the leak*: mitigated by switching from a
    blocklist to an allowlist (`buildSessionResponsePayload`) plus a new
    unit test asserting the token never appears in the built response even
    when present in the input payload.
- **Security improvement**: This directly shrinks the XSS/extension blast
  radius described in the issue — a compromised script on
  `docs.mctl.ai` or `labs-mctl-telegram.mctl.ai` can no longer harvest a
  live GitHub access token via this endpoint.
