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
(`cloudflare-worker/index.js:609-616`) never includes the token. This
proposal brings the MCP/docs/tg-mcp session-redeem path to the same
standard.

## User stories

- AS a security-conscious operator of mctl.ai I WANT the GitHub OAuth access
  token to never leave the Cloudflare Worker's server-side storage SO THAT an
  XSS or malicious extension on a consuming origin cannot steal a user's
  GitHub credentials.
- AS a developer integrating with the `/api/github/session` endpoint (from
  docs.mctl.ai or the Telegram MCP connector) I WANT a clearly-defined,
  minimal response shape (login, name, avatar_url, html_url, sig) SO THAT I
  know exactly what identity data is available client-side and am not
  tempted to rely on a token that should not be there.
- AS a future contributor to this worker I WANT the session response to be
  built from an explicit allowlist of fields SO THAT adding a new field to
  the internal session payload cannot silently leak it to the browser.

## Acceptance criteria (EARS)

- WHEN `POST /api/github/session` successfully redeems a live session
  (via one-time `code` or the `__gh_session` cookie) THE SYSTEM SHALL return
  a JSON body containing only `login`, `name`, `avatar_url`, `html_url`, and
  `sig` — no `token`, `access_token`, `sessionId`, or `exp` field.
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

- Does the JS on `docs.mctl.ai/mcp/connecting` or
  `labs-mctl-telegram.mctl.ai/telegram/connect` currently read `data.token`
  from the `/api/github/session` response and use it for anything (e.g. to
  call the GitHub API directly from the browser, or to hand the token to an
  MCP client config)? This clone contains only `mctl-web`, so those pages'
  source is not visible here. Most reasonable interpretation, given (a) the
  token's scope is only `read:user user:email` (no repo/API-acting
  capability worth exposing), and (b) the sibling "normal landing flow"
  never sends a token and only exposes identity fields, is that consumers
  only need identity (`login`, `name`, `avatar_url`, `html_url`) and `sig`
  for HMAC-verified identity linking, same as the landing flow. This
  proposal proceeds on that assumption. If it turns out a consumer does
  need server-side GitHub API access on behalf of the user, the correct
  follow-up (per the issue's own guidance) is a dedicated
  service-to-service endpoint on the worker — not exposing the raw token to
  browser JS — coordinated as a separate cross-repo change with
  `mctl-docs`/`mctl-telegram` maintainers.
- Should the access token also be removed from the server-side session
  payload entirely (i.e. never stored in the Cache API entry or the
  encrypted `__gh_session` cookie), rather than merely filtered out of the
  HTTP response? This proposal's design section recommends removing it at
  the source (not just filtering on the way out) since nothing else in the
  worker reads `payload.token` after it is fetched from GitHub — see
  `design.md` for the reasoning.
