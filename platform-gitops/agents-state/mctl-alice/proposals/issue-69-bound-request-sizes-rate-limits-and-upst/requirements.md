# Bound request sizes, rate limits and upstream timeouts (S5a)

## Context

Issue mctlhq/mctl-alice#69 is slice (a) of security finding S5 in
`docs/plans/public-launch-readiness.md`. The plan asks for "request size limits,
endpoint-specific rate limits, upstream timeouts". The hosted service
(`alice.mctl.ai`, tenant `labs`, one replica) has four related gaps today:

- It reads request bodies with no byte cap. This covers `parseRequestBody` in
  `src/server/http-server.ts`, the inline `req.on("data")` readers for `/mcp`,
  `/auth/save-token` and `/auth/save-cookie`, the SDK-read body on `/messages`,
  and the local `/save-token` helper in `src/auth/oauth-helper.ts`.
- No endpoint enforces any rate limit, but the `/terms` page
  (`src/server/pages.ts`) promises one.
- Most outbound calls to Yandex have no deadline. These are the Quasar CSRF and
  API calls, the OAuth token exchange and refresh, the profile lookup and the QR
  login. Because of this, account deletion and Quasar disconnect can hang on an
  unresponsive upstream.
- Quasar and QR error messages copy raw upstream response bodies into errors
  that reach clients.

An unauthenticated client can tie up memory and connections, and can brute-force
or flood the OAuth endpoints. Also, one stalled Yandex call blocks a user's
account deletion indefinitely. All of this has to be fixed before the public
launch.

## User stories

- AS the operator of the hosted service I WANT request bodies capped and abusive
  clients throttled SO THAT one client cannot exhaust memory, connections or the
  OAuth/login flows for everyone else.
- AS a user deleting my account or disconnecting Quasar I WANT the request to
  finish even when Yandex does not answer SO THAT my data is removed and I am
  told which proxy scenarios might be left behind.
- AS an MCP client author I WANT clear 413 and 429 responses (with
  `Retry-After`) SO THAT my client can back off correctly.
- AS a security reviewer I WANT upstream error text reduced to a status and a
  short sanitized message SO THAT upstream bodies, which may contain cookies,
  tokens or personal data, never reach responses or logs.

## Acceptance criteria (EARS)

Body size

- WHEN any HTTP handler reads a request body THE SYSTEM SHALL read it through
  the single helper `readBody` / `parseRequestBody` in
  `src/server/request-limits.ts`, with an explicit byte limit.
- IF a request's `Content-Length` exceeds the limit for its route THEN THE
  SYSTEM SHALL answer 413 without reading the body.
- IF the bytes actually received exceed the limit (chunked, or `Content-Length`
  absent or false) THEN THE SYSTEM SHALL stop buffering, answer 413, and close
  the connection.
- WHILE handling OAuth (`/oauth/register`, `/oauth/token`, `/oauth/revoke`,
  `POST /oauth/authorize`), account forms (`/account/*`), `/auth/save-token`,
  `/auth/save-cookie` and the REST `/api/*` endpoints THE SYSTEM SHALL apply the
  small-body limit of 16 KiB.
- WHILE handling MCP JSON-RPC bodies (`POST /mcp`, `/`, `/sse`, `/mcp/sse`,
  `/messages`, `/mcp/messages`) THE SYSTEM SHALL apply the MCP body limit of
  1 MiB.
- WHEN a body is accepted THE SYSTEM SHALL parse JSON and
  `application/x-www-form-urlencoded` exactly as `parseRequestBody` does today.

Rate limiting

- WHEN a client exceeds the per-client budget for one of these buckets THE
  SYSTEM SHALL answer 429 with a `Retry-After` header in whole seconds and a
  JSON error body, and SHALL NOT run the handler:
  - `oauth-register` (`POST /oauth/register`)
  - `oauth-token` (`POST /oauth/token`)
  - `oauth-authorize` (`GET`/`POST /oauth/authorize`)
  - `login` (`/auth/login`, `/auth/callback`, `/auth/qr-code`,
    `/auth/qr-status`, `/auth/save-cookie`, `/auth/save-token`)
  - `mcp` (MCP POST/SSE entry points, `/messages`, `/api/*`)
- WHILE the server runs as a single replica THE SYSTEM SHALL keep rate-limit
  state in process memory, with a bounded number of tracked clients.
- WHEN the server runs in hosted mode (`AUTH_REQUIRED=true`) THE SYSTEM SHALL
  identify the client by the address that the trusted reverse proxy appends to
  `X-Forwarded-For`. In any other case it SHALL use the socket's remote address.
- THE SYSTEM SHALL NOT rate-limit `/healthz`, `/readyz` or static assets.

Upstream timeouts

- WHEN the service makes any outbound call to Yandex THE SYSTEM SHALL pass an
  `AbortSignal` timeout. This covers Quasar (`yandex.ru/quasar`,
  `iot.quasar.yandex.ru`, `yandex.ru/iot`), the OAuth token exchange and refresh
  (`oauth.yandex.ru/token`), the profile lookups (`login.yandex.ru/info`,
  `api.iot.yandex.net/v1.0/user/info`), QR login (`passport.yandex.ru`) and the
  IoT API.
- IF an outbound Yandex call times out THEN THE SYSTEM SHALL raise an
  `UpstreamTimeoutError` whose message names the upstream and says it timed
  out. HTTP handlers SHALL map it to 504, or to the existing error status of
  their flow.
- WHEN a user deletes their account or disconnects Quasar and proxy-scenario
  cleanup fails or exceeds its overall deadline THE SYSTEM SHALL still finish
  the request. Account deletion SHALL remove telemetry, the user and their
  sessions; Quasar disconnect SHALL clear the cookie. Both SHALL redirect with
  `scenarios_left=true`.

Upstream error text

- IF a Yandex call returns a non-success status THEN THE SYSTEM SHALL raise an
  error that contains only the HTTP status and a short sanitized message. The
  message SHALL have at most 200 characters, no control characters and no
  cookie- or token-like values, and SHALL NOT include the raw response body.
- WHEN a Quasar scenario create or update returns an unexpected payload THE
  SYSTEM SHALL NOT `JSON.stringify` the upstream response into the error
  message.

Tests

- Each of the four areas above SHALL have regression tests that fail when the
  fix is reverted.

## Out of scope

- CSP, CORS, HTML escaping and shell interpolation. These belong to the
  separate S5 slice named in the issue.
- Distributed or shared rate limiting across replicas. The deployment runs
  `replicaCount: 1`.
- Per-account quotas, billing-tier limits, and changes to the `/terms` text
  beyond making the existing promise true.
- Ingress-level (nginx) body or rate limits. These can be added later as
  defence in depth.
- The client-metadata fetch in `src/auth/oauth-controller.ts`
  (`fetchMetadataDocument`), which is already size-capped and has a 4 s timeout.

## Open questions

- Exact budgets. The proposal uses these defaults:
  - `oauth-register`: 10 per minute
  - `oauth-token`: 60 per minute
  - `oauth-authorize`: 30 per minute
  - `login`: 60 per minute (QR status polling is included)
  - `mcp`: 300 per minute

  All are per client IP. They are constants in one table, so the reviewer can
  tune them.
- Client identity behind the ingress. The proposal trusts only the rightmost
  `X-Forwarded-For` entry in hosted mode. Whether the `labs` ingress controller
  appends to or overwrites that header was not observed. The `TRUST_PROXY_HOPS`
  override exists for this case.
- Whether `mcp` should also be keyed per access token in addition to per IP, so
  that many users behind one NAT, such as ChatGPT or Claude connector egress
  IPs, do not share one budget. The proposal keys `mcp` by token fingerprint
  when a bearer token is present and by IP otherwise. Confirm this is wanted.
- Upstream timeout values. The proposal uses 10 s per call (the IoT API keeps
  its existing 15 s) and a 20 s overall deadline for proxy-scenario cleanup.
