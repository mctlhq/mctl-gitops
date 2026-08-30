# Stop returning the GitHub access token to the browser in session payload

## Context

The Cloudflare Worker's GitHub OAuth "fragment-redirect" flows (`for=docs`,
`for=mcp`, `for=tg-mcp`, handled in `handleGitHubCallback`,
`cloudflare-worker/index.js:576-603`) exchange the OAuth `code` for a GitHub
access token, then store a session payload that includes `token: accessToken`
(`cloudflare-worker/index.js:588`). That payload is persisted server-side (the
Cache API via `putOAuthSession`) and also packed into an encrypted, HttpOnly
`__gh_session` cookie (`encryptSessionPayload`). When the consuming page
(`docs.mctl.ai/mcp/connecting` or `labs-mctl-telegram.mctl.ai/telegram/connect`)
later calls `POST /api/github/session` to redeem the one-time session id or
cookie, `handleGitHubSession` (`cloudflare-worker/index.js:655-701`) only
strips `sessionId` and `exp` before returning the rest of the payload as JSON
(`cloudflare-worker/index.js:699-700`). The GitHub access token therefore
reaches the browser's JS context on those consuming pages in plain JSON,
where an XSS bug or a malicious/compromised browser extension on that origin
could read and exfiltrate it, giving an attacker the scope of that token
(currently `read:user user:email`, granted in `handleGitHubLogin`,
`cloudflare-worker/index.js:483`) against the user's GitHub account.

This matters because it defeats the whole point of doing the OAuth token
exchange server-side: the worker already goes out of its way (see the
comments at `cloudflare-worker/index.js:572-575` and `605-608`) to keep
`access_token` out of URLs; it should not then hand the same token to the
browser in a fetch response body. The normal (non-fragment) landing flow
already gets this right — its `userData` object
(`cloudflare-worker/index.js:609-616`) never includes the token.

**Correction applied at approval (2026-08-30):** the paragraphs above are
the issue's framing, and it is only partly right. Two of the three
fragment flows cannot be brought to the landing flow's standard, because
for them the token is the deliverable, not a leak:
`docs.mctl.ai/mcp/connecting` gives the user that token to paste into their
MCP client as the `api.mctl.ai/mcp` bearer. Only `tg-mcp` — which never
calls this endpoint — can lose it. What this proposal actually fixes is
therefore narrower than the issue's title: drop the token for `tg-mcp`, and
replace the blocklist response construction with an allowlist so future
payload fields cannot leak by default. The genuinely larger problem the
issue is circling — a GitHub credential doubling as our API bearer, with
mctl-api's blast radius and no revocation — is mctlhq/mctl-api#218.

## User stories

- AS a security-conscious operator of mctl.ai I WANT the GitHub OAuth access
  token to reach only the one flow that actually needs it SO THAT the
  Telegram connect flow, which never reads it, stops carrying a live
  credential through a cache entry, a cookie, and a JSON response for no
  reason.
- AS a developer integrating with the `/api/github/session` endpoint I WANT
  a clearly-defined response shape SO THAT I know exactly what is available
  client-side — and, for the docs MCP page, that the `token` I depend on is
  there deliberately rather than by accident.
- AS a future contributor to this worker I WANT the session response to be
  built from an explicit allowlist of fields SO THAT adding a new field to
  the internal session payload cannot silently leak it to the browser.

## Acceptance criteria (EARS)

- WHEN `POST /api/github/session` successfully redeems a live session
  (via one-time `code` or the `__gh_session` cookie) THE SYSTEM SHALL build
  the JSON body from an explicit allowlist of `login`, `name`,
  `avatar_url`, `html_url`, `sig`, and `token`, and SHALL NOT include any
  field outside that list — in particular no `sessionId`, no `exp`, and no
  field a future change adds to the internal payload.
- WHEN the redeemed session originated from the `docs` or `mcp` flow THE
  SYSTEM SHALL include `token`, because `docs.mctl.ai/mcp/connecting`
  requires it as the `api.mctl.ai/mcp` bearer it hands the user.
- WHEN the redeemed session originated from the `tg-mcp` flow THE SYSTEM
  SHALL NOT include `token`, and the token SHALL NOT have been written to
  the Cache API entry or the `__gh_session` cookie for that flow at all.
- WHEN `POST /api/github/session` is called with an expired, missing, or
  already-consumed session THE SYSTEM SHALL continue to return
  `401 { error: 'Session expired or missing' }` exactly as today.
- WHILE the GitHub OAuth fragment-redirect flow (`for=docs|mcp|tg-mcp`) is
  exchanging a code for an access token THE SYSTEM SHALL continue to use
  that token server-side only (to call the GitHub `/user` and `/user/emails`
  APIs) and SHALL NOT place it in any URL, query string, or fragment.
- IF a new field is later added to the internal session payload THEN THE
  SYSTEM SHALL require it to be explicitly added to the response allowlist
  before it is exposed via `/api/github/session` (i.e. the response is built
  by picking allowed fields, not by blocklisting sensitive ones).
- WHEN the normal (non-fragment) landing OAuth flow completes THE SYSTEM
  SHALL keep delivering identity data via the URL fragment exactly as today
  (`landingSuccessLocation`, no `token` field) — this flow is unaffected by
  this change.
- WHEN `GET /api/github/login` and `GET /api/github/callback` are exercised
  end-to-end for the normal landing flow, and when `check-team`
  (`handleCheckTeam`) is called THE SYSTEM SHALL keep working exactly as
  before this change (neither uses or is affected by the session-payload
  shape).

## Out of scope

- Turnstile / check-team hardening (companion issue, cross-linked from
  issue #65).
- Changes to the GitHub OAuth scope (`read:user user:email`) requested in
  `handleGitHubLogin`.
- Any change in the `mctl-docs` or `mctl-telegram` repos. Those repos own
  the pages at `docs.mctl.ai/mcp/connecting` and
  `labs-mctl-telegram.mctl.ai/telegram/connect` that call
  `/api/github/session`; this proposal only changes what `mctl-web`'s
  worker returns to them.
- Revoking or rotating already-issued GitHub tokens that may have already
  been exposed by the current behavior — that is an incident-response
  action, not a code change.

## Open questions

**Resolved by the operator before approval (2026-08-30).** Both original
questions are answered; see the Operator decisions section in `tasks.md`
for the full reasoning and the verified references.

- *Does any consumer read `data.token`?* **Yes.**
  `mctl-docs/docs/.vitepress/theme/components/McpSetup.vue:168-170` reads it
  and renders it into every MCP client config snippet as the
  `api.mctl.ai/mcp` bearer. The `tg-mcp` target does not — it never calls
  this endpoint. Hence the flow-conditional behaviour above.
- *Should the token also be removed from the server-side payload, not just
  filtered from the response?* **For `tg-mcp`, yes** — it is omitted at
  construction, so it never reaches the Cache API entry or the cookie. **For
  `docs`/`mcp`, no** — the consumer needs it.
