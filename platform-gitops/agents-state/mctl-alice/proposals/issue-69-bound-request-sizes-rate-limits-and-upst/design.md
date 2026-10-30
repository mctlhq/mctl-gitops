# Design: issue-69-bound-request-sizes-rate-limits-and-upst

## Current state

**HTTP server** (`src/server/http-server.ts`, a single `http.createServer`
handler that routes by `url.pathname`)

- `parseRequestBody(req)` (around line 123) concatenates every `data` chunk into
  a string with no limit. It then parses the string as form-urlencoded or JSON,
  falling back to form. `parseJsonBody` is an alias for it.
- The following handlers call `parseRequestBody` / `parseJsonBody`:
  - `/oauth/register` (764). Any error becomes 400.
  - `POST /oauth/authorize` (904)
  - `/oauth/token` (981)
  - `/oauth/revoke` (1007)
  - `/api/say`, `/api/command`, `/api/volume`, `/api/media`,
    `/api/scenarios/trigger` (1238 to 1336)
  - `/account/revoke-grant` (1501)
- Three handlers read the body inline, also with no limit:
  - MCP POST (`isMcpPost`, around 1047): `let body = ""; req.on("data", ...)`,
    then `JSON.parse`.
  - `/auth/save-token` (1700)
  - `/auth/save-cookie` (1919)
- The SSE `/messages` route (1161 to 1189) passes the raw request to
  `transport.handlePostMessage(req, res)` of `@modelcontextprotocol/sdk`
  (lockfile: 1.30.0). The SDK reads the body itself, with its own 4 MB default.
- The local CLI auth server in `src/auth/oauth-helper.ts` (`/save-token`,
  around line 232) also reads its body inline.
- The only existing size cap is `readCapped` in `src/auth/oauth-controller.ts`
  (line 133), which is used for outbound client-metadata documents.
- There is no rate limiting anywhere in `src/`. `src/server/pages.ts:123` (the
  terms page) states that per-minute request limits apply.
- The only per-client value derived today is `fingerprint(req)` (line 535), a
  SHA-256 of the bearer token used for SSE ownership. Nothing reads
  `X-Forwarded-For` or `socket.remoteAddress`.

**Outbound calls**

- `src/client/quasar-client.ts`:
  - `getAccountUid` has `AbortSignal.timeout(10000)`.
  - `getCsrfToken` (`yandex.ru/quasar`) and `request()` (both fetches, including
    the 403 retry) have no signal.
  - `request()` throws `Quasar API error (${status}): ${text}` with the full
    upstream body (line 312).
  - `createProxyScenario` and the TTS and command update paths embed
    `JSON.stringify(res)` of upstream payloads (lines 393, 425, 460).
  - `cleanupAllProxyScenarios` loops `DELETE` calls with no overall deadline.
- `src/client/yandex-api.ts` already uses an `AbortController` with a 15 s
  timeout and maps `AbortError` to `YandexApiError(408)`.
- `src/auth/token-storage.ts`: `exchangeCodeForToken` and `refreshAccessToken`
  (`oauth.yandex.ru/token`) have no signal.
- `src/auth/oauth-helper.ts`: `fetchYandexProfile` (`login.yandex.ru/info`,
  `api.iot.yandex.net/v1.0/user/info`) and `validateTokenAndGetSpeakers` have
  no signal.
- `src/auth/yandex-qr-auth.ts`: `initQrAuth` and `checkQrAuthStatus` make five
  `passport.yandex.ru` fetches with no signal. Line 158 embeds `errBody`, and
  `/auth/qr-code` returns `err.message` to the browser.

**Account flows** (`http-server.ts` 1434 to 1497)

- `removeProxyScenarios(userId)` builds a `QuasarClient` and awaits
  `cleanupAllProxyScenarios()`. Any non-storage error makes it return `false`,
  and `/account/delete` and `/account/disconnect-quasar` then redirect with
  `scenarios_left=true`.
- The failure path is therefore correct. The hang is the problem: with no
  deadline, a stalled upstream never produces the error.

**Tests**

Vitest, in `tests/*.test.ts`. `tests/http-server.test.ts` starts
`createHttpServer(PORT, {...})` on a fixed port and uses `fetch`.
`tests/hosted-access.test.ts` and `tests/qr-auth.test.ts` stub `globalThis.fetch`.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/labs/mctl-alice/values.yaml`: tenant `labs`,
  image `2.2.4`, `replicaCount: 1`, `AUTH_REQUIRED: "true"`,
  `PUBLIC_BASE_URL: https://alice.mctl.ai`, ingress host `alice.mctl.ai` (no
  ingress annotations for body or rate limits), memory limit 256Mi, CPU limit
  250m. This shows that in-process limiting is valid (one replica) and that
  unbounded bodies are a real memory risk at 256Mi.
- `mctl_get_service_status(labs, mctl-alice)`: ArgoCD Healthy and Synced, image
  tag `2.2.4`, host `alice.mctl.ai`.
- Not observed: the ingress controller's `X-Forwarded-For` behaviour (append or
  overwrite, number of hops). This is recorded under Open questions.

## Proposed solution

### 1. `src/server/request-limits.ts` (new): one body reader

- `class PayloadTooLargeError extends Error { status = 413 }`
- `readBody(req, limit): Promise<string>`:
  - Reject immediately with `PayloadTooLargeError` if `Content-Length` is
    greater than `limit`.
  - Otherwise accumulate `Buffer` chunks and count bytes. On overflow, remove
    the listeners, `req.resume()` the rest away (or destroy it if it keeps
    flowing), and reject.
  - Generalize and reuse the logic of `readCapped` from `oauth-controller.ts`.
    `readCapped` can then delegate to a shared `collectCapped(stream, limit)`.
- `parseRequestBody(req, limit = BODY_LIMIT_SMALL)`: the same parsing semantics
  as today's function, moved here, with `readBody` in front.
- `parseJsonRpcBody(req, limit = BODY_LIMIT_MCP)`: returns the parsed JSON, or
  `undefined` for an empty body.
- Constants: `BODY_LIMIT_SMALL = 16 * 1024` and `BODY_LIMIT_MCP = 1024 * 1024`.
- `sendPayloadTooLarge(res)`: writes 413 with
  `{"error":"payload_too_large"}` and `Connection: close`.

Changes in `http-server.ts`:

- Delete the local `parseRequestBody` and `parseJsonBody` and import the new
  helpers.
- Replace the three inline readers (MCP POST, `/auth/save-token`,
  `/auth/save-cookie`) with `await parseJsonRpcBody` / `await readBody`. This
  also flattens the `req.on("end", async ...)` callbacks into ordinary awaited
  code inside the existing `try`.
- `/messages`: read the body with `parseJsonRpcBody` after the owner check and
  call `transport.handlePostMessage(req, res, parsed)`. The SDK's
  `parsedBody` third argument skips its own `raw-body` read.
- In the top-level `catch` of the request handler, and in each handler `catch`
  that already maps errors (`/oauth/register` returns 400 for everything), check
  `err instanceof PayloadTooLargeError` first and answer 413.
- `src/auth/oauth-helper.ts` `/save-token` (local CLI): use `readBody` with the
  small limit.

### 2. `src/server/rate-limit.ts` (new): in-process limiter

- `class RateLimiter`:
  - A fixed-window counter per `(bucket, key)` in a `Map`.
  - Each bucket has `{ limit, windowMs }`.
  - `check(bucket, key, now = Date.now())` returns
    `{ allowed: true }` or `{ allowed: false, retryAfterSec }`.
  - Expired entries are swept lazily on access, plus a `setInterval(...).unref()`
    sweep every minute.
  - A hard cap of 50,000 tracked keys. Above it, expired entries are evicted
    first. If none are expired, the request fails open for new keys and the
    event is logged once, rather than letting memory grow without bound.
  - Fixed windows are chosen for simplicity. The burst at a window edge (up to
    2x) is acceptable for this threat model.
- Default bucket table, exported so tests and reviewers see one source:

  | Bucket | Limit | Routes |
  |---|---|---|
  | `oauth-register` | 10 per 60 s | `POST /oauth/register` |
  | `oauth-token` | 60 per 60 s | `POST /oauth/token` |
  | `oauth-authorize` | 30 per 60 s | `GET`/`POST /oauth/authorize` |
  | `login` | 60 per 60 s | `/auth/login`, `/auth/callback`, `/auth/qr-code`, `/auth/qr-status`, `/auth/save-cookie`, `/auth/save-token` |
  | `mcp` | 300 per 60 s | MCP POST/SSE paths, `/messages`, `/mcp/messages`, `GET /mcp`, `/api/*` |

- `clientKey(req, trustProxyHops)`:
  - When `trustProxyHops > 0`, take the entry `trustProxyHops` from the right of
    `X-Forwarded-For`, so that client-supplied left-hand entries cannot spoof
    it.
  - Otherwise use `req.socket.remoteAddress`.
  - `trustProxyHops` defaults to 1 when `authRequired` and 0 otherwise, and can
    be overridden with the `TRUST_PROXY_HOPS` env var or a
    `createHttpServer` option.
- For the `mcp` bucket, the key is `fingerprint(req)` (the existing token hash)
  when a bearer token is present, and the client IP otherwise. NAT-shared
  connector egress then does not collapse all users into one budget, while
  unauthenticated floods are still limited per IP.
- Wiring in `http-server.ts`: one `routeBucket(pathname, method)` function, and
  one check placed after the Origin check and before the
  `/healthz`/`/readyz`/static branches are skipped. When the check fails, answer
  429 with `Retry-After: <sec>`, `Cache-Control: no-store` and
  `{"error":"rate_limited"}`.
  - Health, readiness, static assets, public pages, `.well-known` and OpenAPI
    get no bucket.
  - `createHttpServer` accepts a `rateLimits` option (bucket overrides, or
    `false` to disable) so existing tests that loop many requests stay
    unaffected and new tests can use tiny budgets.

### 3. `src/client/upstream.ts` (new): timeouts and sanitized errors

- Defaults: `UPSTREAM_TIMEOUT_MS = 10_000`, overridable through an exported
  `setUpstreamTimeoutMs(ms)` (tests only) or the `UPSTREAM_TIMEOUT_MS` env var.
- `upstreamSignal(ms?)`: returns `AbortSignal.timeout(ms)`.
- `class UpstreamTimeoutError extends Error`. The message is
  `"<Upstream name> did not respond within <n> s"`, and `status = 504`.
- `upstreamFetch(name, url, init)`: wraps `fetch` with `upstreamSignal()`,
  combined through `AbortSignal.any` with `init.signal` if a caller passes one.
  It maps a `TimeoutError` or `AbortError` caused by the timeout to
  `UpstreamTimeoutError(name)`.
- `class UpstreamHttpError extends Error { status }` and
  `upstreamError(name, status, body?)`:
  - Build `"<name> error (HTTP <status>)"`, optionally followed by
    `": <msg>"`.
  - `msg` comes only from a parsed JSON `message`, `error_description`, `error`
    or `code` string field, run through `sanitizeUpstreamText`. Raw HTML or
    text bodies are never included.
- `sanitizeUpstreamText(s, max = 200)`:
  - Strip control characters and collapse whitespace.
  - Redact values that match cookie, token or `Session_id`-like patterns
    (`/(Session_id|sessionid2|yandexuid|access_token|refresh_token|OAuth|Bearer)[=: ]+\S+/gi`
    becomes `$1=[redacted]`).
  - Truncate to `max` with an ellipsis.

Call sites:

- `quasar-client.ts`:
  - `getCsrfToken` and both fetches in `request()` use `upstreamFetch("Yandex Quasar", ...)`.
  - The non-OK path calls `upstreamError("Quasar API", res.status, await safeJson(res))`.
  - The three `JSON.stringify(res)` messages become fixed text plus a sanitized
    `status`/`code` field if present.
  - `getAccountUid` switches to the helper.
- `token-storage.ts`: `exchangeCodeForToken` and `refreshAccessToken` use
  `upstreamFetch("Yandex OAuth", ...)`. A non-JSON error body no longer throws
  an opaque `SyntaxError`; it goes through `upstreamError`.
- `oauth-helper.ts`: `fetchYandexProfile` (both endpoints) and
  `validateTokenAndGetSpeakers`. The existing fallback behaviour is unchanged.
  With `requireVerifiedIdentity`, a timeout still ends in the existing "Yandex
  profile verification failed; reconnect" error.
- `yandex-qr-auth.ts`: all five passport fetches. The error at line 158 drops
  `errBody`.
- `yandex-api.ts`: keep the 15 s timeout, but switch to `upstreamSignal(15000)`
  and the shared timeout error type (status 504 instead of 408, with a clear
  message). Keep the `responseData` field on `YandexApiError` for logic, but use
  only `sanitizeUpstreamText` on `responseData.message` in the message string.

Account flows:

- `removeProxyScenarios` in `http-server.ts` passes an overall deadline.
  `cleanupAllProxyScenarios({ deadlineMs: 20_000 })` checks the remaining time
  before each `DELETE` and passes `AbortSignal.any([perCall, overall])`. When
  the deadline expires it counts the remaining scenarios as failed and throws.
  The existing `catch` then returns `false`, which leads to
  `scenarios_left=true`, while deletion of telemetry, the user and the sessions
  proceeds as today.
- Routes that surface upstream errors map them:
  - `/auth/qr-code` and `/auth/qr-status`: `UpstreamTimeoutError` becomes 504
    with the sanitized message. Other upstream errors become 502.
  - `/auth/callback` token exchange: the existing error page shows the
    sanitized message.
  - The MCP tool error formatting in `src/tools/handlers.ts:527` already uses
    `err.message`, which is now safe.

## Alternatives

1. **Limit at the ingress** (nginx `proxy-body-size` and `limit-rps`
   annotations in gitops). Rejected as the primary fix:
   - It does not cover local or self-hosted mode.
   - It cannot express per-endpoint OAuth budgets or per-token MCP keys.
   - It does not satisfy "regression tests that fail with the fix reverted".
   - It is still worthwhile later as defence in depth.
2. **Third-party middleware** (`express-rate-limit`, `raw-body`). Rejected:
   - The server is a bare `node:http` handler, not Express.
   - The needed logic is about 100 lines.
   - The repo keeps dependencies minimal (5 runtime dependencies).
3. **Token-bucket or sliding-log limiter, or a Postgres-backed shared limiter.**
   Rejected for now:
   - The deployment has one replica, and the issue explicitly allows
     in-process limiting.
   - A sliding log costs memory per request.
   - A DB-backed limiter adds a storage round trip, and a new fail-closed
     dependency, on every request.
   - The `RateLimiter` interface leaves room to swap the implementation if the
     service scales out.

## Platform impact

- **Migrations:** none. No storage schema change.
- **Configuration:**
  - New optional env vars `TRUST_PROXY_HOPS` and `UPSTREAM_TIMEOUT_MS`. The
    defaults are right for the current deployment (`AUTH_REQUIRED=true` behind
    one ingress).
  - No gitops change is required.
- **Backward compatibility:**
  - Clients that send bodies over 16 KiB to OAuth or REST endpoints, or over
    1 MiB to MCP, now receive 413. Legitimate payloads are far below this:
    DCR metadata is a few hundred bytes, and tool calls carry short phrases.
  - `YandexApiError` for timeouts changes status from 408 to 504. Check the
    callers in `station-service.ts` and the tests.
  - The `/messages` path now pre-parses the body. The SDK behaviour is
    otherwise unchanged.
- **Resources:**
  - The limiter map is bounded (50k keys, roughly a few MB at most), which is
    well under the 256Mi limit.
  - Memory per request is now bounded at 1 MiB per in-flight MCP body.
- **Risks and mitigations:**
  - *Wrong client IP behind the proxy.* If the ingress overwrites
    `X-Forwarded-For`, the rightmost entry is still the real client. If there
    are extra hops, all users could share one key; `TRUST_PROXY_HOPS` fixes
    this without a code change. After rollout, verify with logs: log the bucket
    and a truncated key hash on 429, never the raw IP.
  - *Budgets too tight for legitimate connectors.* The bucket table is a single
    constant. 429 responses carry `Retry-After`, which MCP clients honour.
    Watch the 429 counts in logs after the deploy.
  - *Timeout too short for slow-but-healthy Yandex.* 10 s is generous for these
    endpoints, and the env override exists.
  - *Partial scenario cleanup.* This is already handled by `scenarios_left=true`.
    The recorded scenario ids are kept for a later retry, as today.
