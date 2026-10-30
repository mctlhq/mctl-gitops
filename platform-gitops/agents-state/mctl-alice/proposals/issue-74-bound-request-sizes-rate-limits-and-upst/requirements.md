# Bound request sizes, rate limits and upstream timeouts (S5a)

## Context
Issue mctlhq/mctl-alice#74 is slice (a) of the request-bounding work in the
public-launch plan (`docs/plans/public-launch-readiness.md`; the plan's own
finding numbering differs, and the relevant text is under S4 "Request bodies,
registration volume and QR creation lack application-level bounds" and the
"request size limits, endpoint-specific rate limits, upstream timeouts" item).
Today the hosted server (`alice.mctl.ai`, tenant `labs`, one replica) reads
every request body without a cap. It enforces no rate limit, although `/terms`
promises one. Most outbound calls to Yandex have no deadline. Quasar errors
also copy raw upstream response bodies into messages that reach clients and
logs.

This matters because one client can exhaust memory with one large body, or
flood dynamic client registration, token, login and QR endpoints. A slow
Yandex upstream can also stall account deletion and Quasar disconnection,
which are privacy operations users must be able to finish.

## User stories
- AS the service operator I WANT every request body capped SO THAT one client cannot exhaust the pod's 256Mi memory limit.
- AS the service operator I WANT per-client rate limits on OAuth, login and MCP entry points SO THAT abuse is throttled and `/terms` is accurate.
- AS a user deleting my account or disconnecting Quasar I WANT the action to finish even if Yandex is unresponsive SO THAT my data is removed and I am told when scenarios were left behind.
- AS an MCP client developer I WANT upstream failures reported as a status plus a short message SO THAT I get actionable errors without leaked upstream content.

## Acceptance criteria (EARS)
Body limits
- WHEN any HTTP handler in `src/server/http-server.ts` or `src/auth/oauth-helper.ts` reads a request body THE SYSTEM SHALL read it through the single shared helper in `src/server/request-body.ts`, which takes a byte limit.
- IF a request declares a `Content-Length` above the limit for its endpoint THEN THE SYSTEM SHALL respond `413 Payload Too Large` without reading the body.
- IF a streamed body (chunked or without a length) grows past the limit THEN THE SYSTEM SHALL stop buffering, respond `413` with `Connection: close`, and not invoke the handler's business logic.
- WHEN an SSE message is posted to `/messages`, `/mcp/messages` or `/mcp?sessionId=` THE SYSTEM SHALL read the body with the shared helper and pass the parsed body to `SSEServerTransport.handlePostMessage`.
- WHILE a body is within its limit THE SYSTEM SHALL parse JSON and `application/x-www-form-urlencoded` bodies exactly as `parseRequestBody` does today.

Rate limits
- WHEN a client exceeds the per-window budget for `/oauth/register`, `/oauth/token`, `/oauth/authorize` (GET and POST), the login group (`/auth/login`, `/auth/callback`, `/auth/qr-code`, `/auth/qr-status`, `/auth/save-cookie`, `/auth/save-token`) or the MCP group (`/mcp`, `/`, `/sse`, `/mcp/sse`, `/messages`, `/mcp/messages`, `/api/*` tool routes) THE SYSTEM SHALL respond `429 Too Many Requests` with a `Retry-After` header in whole seconds and must not run the handler.
- WHILE a client is within its budget THE SYSTEM SHALL handle the request unchanged.
- THE SYSTEM SHALL keep limiter state in process memory with a bounded number of keys, and SHALL evict expired entries.
- WHEN rate limiting the MCP group on a request that carries a bearer token THE SYSTEM SHALL key the budget on the token fingerprint. Otherwise it SHALL key on the client address.
- WHERE `TRUST_PROXY_HOPS` is set to N > 0 THE SYSTEM SHALL take the client address from the N-th entry from the right of `X-Forwarded-For`. Otherwise it SHALL use `req.socket.remoteAddress`.
- `/healthz` and `/readyz` SHALL never be rate limited.

Upstream timeouts
- WHEN the system calls any Yandex endpoint (Quasar `yandex.ru/quasar`, `iot.quasar.yandex.ru`, `yandex.ru/iot`, `oauth.yandex.ru/token`, `login.yandex.ru/info`, `api.iot.yandex.net`, `passport.yandex.ru` QR login) THE SYSTEM SHALL attach an `AbortSignal` timeout. The default is 10 s; the existing 15 s in `yandex-api.ts` is kept.
- IF an upstream call times out THEN THE SYSTEM SHALL throw `UpstreamTimeoutError`, whose message names the upstream (for example "Yandex Quasar did not respond within 10s"), and HTTP handlers SHALL map it to 504 (JSON) or to the existing error page or JSON-RPC error.
- WHEN a user posts `/account/delete`, `/account/delete-all` or `/account/disconnect-quasar` and the Quasar cleanup times out or fails THE SYSTEM SHALL still finish the deletion or disconnection and redirect with `scenarios_left=true`, within one overall cleanup deadline (default 20 s).

Error sanitization
- IF a Yandex call returns a non-2xx status or an unexpected payload THEN THE SYSTEM SHALL produce an error message containing only the HTTP status and a short sanitized message: at most 120 characters, with control characters, HTML/markup and quotes stripped, taken from a known JSON field (`message`, `code`, `error`, `error_description`) or a fixed fallback. The raw response body SHALL NOT appear.

Tests
- THE SYSTEM SHALL have regression tests for each item above that fail when the corresponding fix is reverted.

## Out of scope
- CSP, CORS, HTML escaping and shell (`exec`) calls, which have a separate issue.
- Distributed or shared rate-limit state (Redis or Postgres). The service runs one replica.
- Session expiry, cookie flags, log redaction, and the remaining items of the launch plan.
- Changing the deployed `values.yaml` in mctl-gitops. A separate gitops PR is needed to set `TRUST_PROXY_HOPS` (see Open questions).

## Open questions
- Client address behind the ingress: the deployed ingress (`alice.mctl.ai`, cert-manager annotations only) has not been checked for whether it sets or appends `X-Forwarded-For`. Proposal: default `TRUST_PROXY_HOPS=0`, and set it to `1` through a mctl-gitops PR once the header is confirmed. Until then all unauthenticated traffic shares one address bucket. This is why the default budgets below are generous and why the MCP group keys on the token fingerprint.
- Exact budgets are not in the issue. Proposed defaults (per key, sliding 60 s window): register 10, token 30, authorize 30, login group 30 (with qr-code limited to 10), MCP group 300. Each can be overridden through `RATE_LIMIT_*` env vars.
- Body limits are not in the issue. Proposed: 64 KiB for OAuth, account and auth forms; 1 MiB for MCP and REST JSON (`MAX_MCP_BODY_BYTES`).
- Whether `/api/*` REST tool routes count as "MCP entry points". This proposal includes them in the MCP group because they dispatch the same tools.
- The local CLI helper (`src/auth/oauth-helper.ts` `/save-token`) is loopback only. It gets the body cap but no rate limit.
