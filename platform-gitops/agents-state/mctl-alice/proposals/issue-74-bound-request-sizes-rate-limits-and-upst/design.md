# Design: issue-74-bound-request-sizes-rate-limits-and-upst

## Current state

Body reading (no cap anywhere):
- `src/server/http-server.ts:132` `parseRequestBody` concatenates `req.on("data")` chunks into a string without a limit, then parses JSON or form data. It is aliased as `parseJsonBody` (line 165). Callers: `/oauth/register` (792), `/oauth/authorize` POST (932), `/oauth/token` (1009), `/oauth/revoke` (1035), `/api/say|command|volume|media|scenarios/trigger` (1266-1364) and `/account/revoke-grant` (1529).
- Separate unbounded readers in the same file: the MCP JSON-RPC POST (`isMcpPost`, around line 1075), `/auth/save-token` (1732) and `/auth/save-cookie` (1960).
- `/messages` (around line 1190) hands the raw request to `SSEServerTransport.handlePostMessage(req, res)` from `@modelcontextprotocol/sdk`, which buffers with its own internal limit (4 MB in the SDK).
- `src/auth/oauth-helper.ts:254` (local CLI helper `/save-token`) is unbounded.
- `src/auth/oauth-controller.ts:132` already has `readCapped(stream, limit)` for client-metadata documents, but its error message is metadata-specific ("Client metadata document is too large", asserted in `tests/oauth-client-binding.test.ts:151`).

Rate limiting: none. `src/server/pages.ts:123` (`/terms`) promises "automatic per-minute request limits (rate limiting)". The only request identity available today is `fingerprint(req)` (`http-server.ts:552`, a sha256 of the bearer token). No code reads `X-Forwarded-For` or `remoteAddress`.

Outbound Yandex calls:
- Has a deadline: `QuasarClient.getAccountUid` (`src/client/quasar-client.ts:232`, `AbortSignal.timeout(10000)`) and `YandexApiClient.request` (`src/client/yandex-api.ts:105`, AbortController with 15 s).
- No deadline: `QuasarClient.getCsrfToken` (252), `QuasarClient.request` (299 and the retry at 307); `exchangeCodeForToken` / `refreshAccessToken` (`src/auth/token-storage.ts:132,161`); `fetchYandexProfile` (`src/auth/oauth-helper.ts:332,354`); QR login `initQrAuth` / status (`src/auth/yandex-qr-auth.ts:88,108,136,215,257`).
- Account deletion and disconnect (`http-server.ts:1463` `removeProxyScenarios`, used at 1482 and 1506) await `QuasarClient.cleanupAllProxyScenarios()` (`quasar-client.ts:494`). That method runs `getScenarios()` and then one DELETE per scenario in sequence. Every failure except `StorageUnavailableError` already becomes `scenarios_left=true`, but a hung upstream never fails, so the request hangs.

Upstream error text:
- `quasar-client.ts:311-312`: `throw new Error(\`Quasar API error (${res.status}): ${text}\`)` includes the full raw body.
- `quasar-client.ts:393,425,460`: `JSON.stringify(res)` of the upstream payload goes into error messages.
- `token-storage.ts:141,171`: Yandex `error_description` is passed through verbatim.
- These messages reach clients through the JSON-RPC `err.message` (`http-server.ts` around line 665), REST error bodies, and `/auth/qr-code` `message: err.message` (around line 1903).

Tests use vitest with a real `createHttpServer(PORT, {...})` on a local port (`tests/http-server.test.ts`) and `vi`-mocked `fetch` (for example `tests/quasar-client.test.ts`).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-alice/values.yaml`: image `2.2.6`, `replicaCount: 1`, RollingUpdate with `maxSurge: 1` (two pods can briefly overlap during a rollout), memory limit 256Mi, `AUTH_REQUIRED=true`, `PUBLIC_BASE_URL=https://alice.mctl.ai`, ingress host `alice.mctl.ai` with only cert-manager annotations. There is no `TRUST_PROXY*` or rate-limit env.
- `mctl_get_service_config(labs, mctl-alice)`: imageTag 2.2.6, host alice.mctl.ai, port 8080, base-service, hasDatabase true. This agrees with the gitops values.
- Not observed: whether the ingress controller sets `X-Forwarded-For` for this host, and live request volumes. Both are recorded under Open questions in requirements.md.

## Proposed solution

### 1. `src/server/request-body.ts` (new): the single body reader
- `export class PayloadTooLargeError extends Error { statusCode = 413 }`.
- `export async function readBodyCapped(stream, limit): Promise<Buffer>` is the generalized form of `readCapped`. It throws `PayloadTooLargeError` on overflow and stops consuming the stream.
- `export async function readRequestBody(req, { limit }): Promise<string>` rejects early when `content-length` is greater than `limit`, then calls `readBodyCapped`.
- `export async function parseRequestBody(req, { limit = FORM_BODY_LIMIT })` keeps today's JSON-then-form logic, moved from `http-server.ts:132`.
- Constants: `FORM_BODY_LIMIT = 64 * 1024` and `MCP_BODY_LIMIT` (1 MiB, env `MAX_MCP_BODY_BYTES`).
- `export function sendPayloadTooLarge(res)` writes 413 with `Connection: close`. The connection is closed instead of drained, so the client cannot keep streaming.
- `oauth-controller.ts` `readCapped` becomes a thin wrapper that calls `readBodyCapped` and rethrows its existing metadata message, so the existing test keeps passing.
- In `http-server.ts`, every `req.on("data")` reader is replaced: MCP POST uses `readRequestBody(req, { limit: MCP_BODY_LIMIT })`, `/auth/save-*` and `/api/*` use `parseRequestBody`, and the `parseJsonBody` alias is removed. `/messages` reads with `MCP_BODY_LIMIT`, parses JSON, and calls `transport.handlePostMessage(req, res, parsed)`. The SDK's third `parsedBody` parameter skips its own reader.
- The top-level `try` in the request handler maps `PayloadTooLargeError` to `sendPayloadTooLarge`, so every route returns 413 the same way. Per-route catch blocks that currently return 400 rethrow `PayloadTooLargeError` instead. This affects `/oauth/register`, `/oauth/token` and the MCP POST parse-error path, which become 413.
- `oauth-helper.ts` `/save-token` uses `readRequestBody` with `FORM_BODY_LIMIT`.
- A grep-based test fails if `req.on("data"` reappears in `src/`.

### 2. `src/server/rate-limit.ts` (new): in-process limiter
- `class RateLimiter { constructor({ limit, windowMs, maxKeys = 10_000 }); hit(key, now = Date.now()): { allowed: true } | { allowed: false; retryAfterSec } }`.
- It is a sliding-window counter (current window plus the weighted previous window) stored in a `Map`. Entries expire after two windows. When the map exceeds `maxKeys`, an opportunistic sweep removes the oldest entries. A swept key starts again with a fresh budget, which fails open but keeps memory bounded.
- `clientAddress(req)` returns `req.socket.remoteAddress` unless `TRUST_PROXY_HOPS > 0`. In that case it uses the N-th `X-Forwarded-For` entry from the right, falling back to the socket address.
- `createHttpServer` builds one limiter per bucket: `register`, `token`, `authorize`, `login`, `qr` and `mcp`. Budgets come from `HttpServerOptions.rateLimits` (tests) or `RATE_LIMIT_<BUCKET>` env vars, with the defaults listed in requirements.md.
- A `rateLimitBucket(pathname, method)` function maps routes to buckets. It runs right after the Origin check and `setSecurityHeaders`, and before any body read or authentication. Health and static routes return null. Key: for the `mcp` bucket, `fingerprint(req)` when an `Authorization` header is present, otherwise `clientAddress(req)`. All other buckets use `clientAddress(req)`.
- When a request is over budget: respond `429`, `Retry-After: <sec>`, `Cache-Control: no-store`. OAuth paths get the JSON body `{"error":"too_many_requests"}` (on `/oauth/token` this is a standard JSON error body). The MCP POST gets a JSON-RPC error body `{code:-32029, message:"Rate limit exceeded"}`, still with HTTP 429.
- Limiter state is reset on process restart. That is acceptable for a single replica, and the brief RollingUpdate overlap only doubles the budget for a short time.

### 3. `src/client/upstream.ts` (new): bounded Yandex fetch
- `export class UpstreamTimeoutError extends Error { constructor(upstream, ms) }` and `export class UpstreamError extends Error { status; upstream }`.
- `export async function upstreamFetch(url, init, { upstream: "Yandex Quasar" | "Yandex OAuth" | ..., timeoutMs = 10_000, signal? })` combines `AbortSignal.timeout(timeoutMs)` with an optional caller signal through `AbortSignal.any` (available in Node 22, the Dockerfile base). It converts a `TimeoutError` or `AbortError` caused by the deadline into `UpstreamTimeoutError`. The signal also bounds reading the response body (`res.text()` / `res.json()`).
- `export function sanitizeUpstreamMessage(bodyText): string` parses JSON when it can and picks `message | error_description | error | code`. Otherwise it uses a fixed "unexpected response". It strips control characters, `<>"'\``, collapses whitespace and truncates to 120 characters.
- `export function upstreamError(upstream, status, bodyText)` returns `new UpstreamError(\`${upstream} error (${status}): ${sanitizeUpstreamMessage(bodyText)}\`)`.
- Call sites switched to `upstreamFetch`: `quasar-client.ts` (`getAccountUid`, `getCsrfToken`, `request` and its retry), `token-storage.ts` (both `/token` calls; `error_description` goes through `sanitizeUpstreamMessage`), `oauth-helper.ts` `fetchYandexProfile` (both calls; the existing catch keeps the fallback behaviour, and with `requireVerifiedIdentity` a timeout now fails fast), `yandex-qr-auth.ts` (all 5 calls), and `yandex-api.ts` (it replaces the hand-rolled AbortController and keeps 15 s).
- `quasar-client.ts:312` becomes `throw upstreamError("Yandex Quasar", res.status, text)`. Lines 393, 425 and 460 replace `JSON.stringify(res)` with `sanitizeUpstreamMessage(JSON.stringify(res))`, which keeps only a known field.

### 4. Account deletion and disconnect deadline
- `QuasarClient` gains an optional `signal?: AbortSignal` constructor option, which is threaded into every `upstreamFetch`.
- `cleanupAllProxyScenarios` checks `signal.aborted` between DELETEs and stops early by throwing. Because it throws, the existing `failed` / throw path is kept and `deleteQuasarScenarios` is not called, so the recorded ids survive for a later retry.
- `removeProxyScenarios` (`http-server.ts:1463`) constructs the client with `signal: AbortSignal.timeout(CLEANUP_DEADLINE_MS = 20_000)`. Its existing catch already returns `false` for anything except `StorageUnavailableError`, so `/account/delete*` and `/account/disconnect-quasar` continue and redirect with `scenarios_left=true`.
- The warning log uses the sanitized message.

### 5. HTTP mapping of upstream errors
- In the JSON/REST error helpers and `/auth/qr-code`: `UpstreamTimeoutError` maps to 504 and `UpstreamError` to 502, both with the sanitized message. The JSON-RPC tool path keeps `-32000` with the sanitized message.

## Alternatives
- Third-party middleware (`raw-body`, `express-rate-limit`, `rate-limiter-flexible`). Dropped: the server uses plain `node:http` without a framework, and each of these adds a dependency for about 60 lines of code. `raw-body` would also duplicate the `readCapped` code that already exists.
- Postgres-backed rate-limit counters, which would survive restarts and scale across replicas. Dropped for now: the service has one replica, the issue explicitly allows in-process state, and a database write per request adds latency and a dependency on storage health. This can be revisited when the replica count grows.
- Server-wide `server.requestTimeout` and `headersTimeout` only, with no body cap. Dropped: a time limit does not bound memory, because a fast client can still send a large body within it. It could be added later as a complement.
- A global `fetch` wrapper or undici dispatcher with a timeout. Dropped: it would hide which upstream failed, cannot produce the per-upstream error message the criteria require, and would also affect the client-metadata fetch, which already has its own 4 s `https.get` timeout.

## Platform impact
- No storage migration. New optional env vars (`TRUST_PROXY_HOPS`, `RATE_LIMIT_*`, `MAX_MCP_BODY_BYTES`). With defaults, behaviour is safe even without gitops changes.
- Backward compatibility:
  - Bodies over 64 KiB on forms or over 1 MiB on MCP are now rejected. Legitimate MCP tool calls (phrases, commands) are far below this.
  - OAuth and MCP clients that hit the limit get 429 with `Retry-After`, which standard clients honour.
  - Error message text changes. Callers that parsed the raw Quasar body (none in the repo) would break.
- Resources: the limiter map is capped at 10k keys per bucket (a few MB at most), within the 256Mi limit.
- Risk: if the ingress replaces the client address and `TRUST_PROXY_HOPS` stays 0, all anonymous clients share one bucket, and a burst could 429 legitimate logins. Mitigations: generous defaults, MCP keyed by token, a follow-up gitops PR setting `TRUST_PROXY_HOPS=1` after the `X-Forwarded-For` header is verified, and env overrides to raise budgets without a rebuild.
- Risk: setting `TRUST_PROXY_HOPS` without a proxy lets clients spoof their key. It is documented as "only set behind a proxy you control".
- Risk: the 10 s timeout may be too short for slow Yandex QR polling. Each call site can override `timeoutMs`.
- Update `docs/plans/public-launch-readiness.md` to mark this slice verified, and update `/terms` copy only if the wording no longer matches.
