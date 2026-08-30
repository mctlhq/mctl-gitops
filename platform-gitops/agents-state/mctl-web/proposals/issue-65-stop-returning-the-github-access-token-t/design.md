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

1. **Put the token in the session payload only for the flows that consume
   it.** In `handleGitHubCallback`, `mcpPayload` (`index.js:536-545`) is
   built inside `if (fragmentTargets[ghFlow])`, so the flow is already in
   scope. Include `token: accessToken` when `ghFlow` is `docs` or `mcp`;
   omit it entirely when `ghFlow` is `tg-mcp`.

   The operator verified against the sibling repositories (see "Operator
   decisions" in tasks.md) that `docs.mctl.ai/mcp/connecting` **requires**
   the token — `mctl-docs/docs/.vitepress/theme/components/McpSetup.vue`
   reads `data.token` and renders it into the user's MCP client config as
   the `api.mctl.ai/mcp` bearer — while the `tg-mcp` target never calls
   `/api/github/session` at all (`mctl-telegram/internal/web/connect.go`
   runs its own local-jwt OAuth). So removing the token unconditionally,
   as this design originally proposed, would break MCP onboarding; removing
   it for `tg-mcp` costs nothing.

   Doing this at the source rather than at the response boundary means that
   for `tg-mcp` the token is never written to the Cache API entry and never
   encrypted into the `__gh_session` cookie either. No flow marker needs to
   be added to the payload: a `tg-mcp` session simply has no `token` key,
   and the response allowlist in step 2 copies `token` only when present.

2. **Make the HTTP response an explicit allowlist, not a blocklist.**
   Replace the destructuring at `index.js:699-700` with a small exported
   pure function, e.g.:
   ```js
   // `token` is on this list deliberately: it is the credential
   // docs.mctl.ai/mcp/connecting hands the user for api.mctl.ai/mcp, not an
   // incidental leak. It is absent from tg-mcp payloads (step 1), so those
   // responses carry no token. Removing it from here entirely requires
   // mctl-api to issue its own scoped token first — see mctlhq/mctl-api#218.
   const SESSION_RESPONSE_FIELDS = ['login', 'name', 'avatar_url', 'html_url', 'sig', 'token'];

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
   This is the core of the fix, and it stands on its own regardless of (1):
   the current destructure is a **blocklist**, so any field a future change
   adds to the internal payload reaches the browser by default. With an
   allowlist, a new field is invisible until someone deliberately adds it to
   `SESSION_RESPONSE_FIELDS`. It also makes the
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
   assert `buildSessionResponsePayload` passes `token` through when present
   (the docs/mcp case) and produces no `token` key when absent (the tg-mcp
   case), assert it includes the expected identity fields when present, and
   assert an unrecognized field added to the input payload does **not**
   appear in the output — that last one is the regression guard the
   allowlist exists for.

## Alternatives

1. **Remove the token unconditionally, for every fragment flow** (this
   design's original step 1). Rejected on evidence: it breaks
   `docs.mctl.ai/mcp/connecting`, whose entire purpose is to hand the user
   that token for their MCP client config. Landing it would have replaced a
   security finding with an outage. This is the single most important
   correction the operator made to this proposal.

2. **Add a worker endpoint that proxies GitHub-API-on-behalf-of-user calls
   so consumers never need the raw token**, per the issue's second
   "expected fix" bullet. Rejected: it solves a problem nobody has. The
   docs page does not call the GitHub API with this token — it hands the
   token to the *user*, who pastes it into an MCP client that authenticates
   to `api.mctl.ai`. A GitHub proxy would not remove the need for the
   token.

3. **Replace the GitHub token with a scoped, revocable mctl-issued token**
   and return that instead. This is the correct end state, and the real
   defect underneath this issue: a credential minted for GitHub
   `read:user user:email` currently grants full mctl-api access as that
   user at our boundary, and we cannot revoke it. Out of scope here because
   it requires mctl-api to issue and accept its own tokens. Filed as
   mctlhq/mctl-api#218.

## Platform impact

- **Backward compatibility**: None broken, by construction. The one
  consumer that reads `data.token` — `docs.mctl.ai/mcp/connecting` via
  `McpSetup.vue` — keeps receiving it, because the `docs` and `mcp` flows
  are unchanged in that respect. The `tg-mcp` flow loses a field it never
  read (`mctl-telegram/internal/web/connect.go` does not call this
  endpoint). Both facts were checked in the sibling repositories rather
  than inferred; the PR description should say so, since this repository
  alone cannot demonstrate either.
- **Migrations**: None. No data store schema changes; the Cache API entry
  and cookie are ephemeral (TTL `SESSION_TTL_SEC = 300`s) and self-expire.
- **Resource impact**: Negligible — the payload shrinks slightly (one fewer
  string field), no new external calls.
- **Risks**:
  - *A future field leaking by default*: this is the risk the allowlist
    closes, and the unit test for an unrecognized input field is what keeps
    it closed.
  - *Someone later reading this code and assuming `token` in the allowlist
    is the original bug, and "fixing" it*: mitigated by the comment beside
    `SESSION_RESPONSE_FIELDS` and by mctlhq/mctl-api#218 naming the
    prerequisite for actually removing it.
- **Security improvement**: honest accounting — this removes the token from
  the `tg-mcp` flow entirely (cache entry, cookie, and response), and stops
  the response from leaking whatever fields the payload grows in future. It
  does **not** stop a live GitHub token from reaching browser JS on
  `docs.mctl.ai`, because that is what that page is for. The issue's
  acceptance criterion ("no `token`/`access_token` field in any response
  reaching the browser") is therefore deliberately not met for `docs`/`mcp`
  — say this plainly in the PR description rather than letting a reviewer
  discover it. The two changes that would actually close it are
  mctlhq/mctl-docs#93 (stop persisting the token in `localStorage`) and
  mctlhq/mctl-api#218 (scoped mctl-issued tokens).
