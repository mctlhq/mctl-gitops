# Tasks: issue-69-bound-request-sizes-rate-limits-and-upst

- [ ] 1. Add `src/server/request-limits.ts` with:
  - `PayloadTooLargeError`
  - `readBody(req, limit)`: `Content-Length` precheck plus a streaming byte
    count
  - `parseRequestBody(req, limit)`: today's form and JSON semantics
  - `parseJsonRpcBody(req, limit)`
  - `sendPayloadTooLarge(res)`
  - `BODY_LIMIT_SMALL` (16 KiB) and `BODY_LIMIT_MCP` (1 MiB)

  Make `readCapped` in `src/auth/oauth-controller.ts` share the capped-collect
  logic.
  DoD: unit tests T1 and T2 pass, and `npm run typecheck` is clean.
- [ ] 2. (depends on 1) Route every body read through the helper:
  - In `src/server/http-server.ts`, delete the local `parseRequestBody` and
    `parseJsonBody`.
  - Replace the inline readers in MCP POST, `/auth/save-token` and
    `/auth/save-cookie`.
  - Pre-parse `/messages` and call `transport.handlePostMessage(req, res, parsed)`.
    First confirm that the SDK 1.30 signature accepts `parsedBody`.
  - Map `PayloadTooLargeError` to 413 in each handler `catch`, including
    `/oauth/register`, `/oauth/token` and the REST handlers, and in the
    top-level `catch`.
  - Also use the helper in `src/auth/oauth-helper.ts` `/save-token`.

  DoD: running `rg "req.on\(\"data\"" src` finds nothing, and T3 passes.
- [ ] 3. Add `src/server/rate-limit.ts`:
  - `RateLimiter`: fixed window, lazy plus interval sweep, 50k key cap
  - `DEFAULT_RATE_LIMITS`, with the buckets `oauth-register`, `oauth-token`,
    `oauth-authorize`, `login` and `mcp`
  - `clientKey(req, trustProxyHops)`: rightmost-trusted `X-Forwarded-For`, or
    `socket.remoteAddress`

  DoD: T4 and T5 pass.
- [ ] 4. (depends on 3) Wire the limiter into `createHttpServer`:
  - Add a `routeBucket(pathname, method)` mapping. The `mcp` bucket is keyed by
    the token `fingerprint(req)` when a bearer token is present, and by IP
    otherwise.
  - On a failed check, answer 429 with `Retry-After`, `Cache-Control: no-store`
    and `{"error":"rate_limited"}`.
  - Add the options `rateLimits` (overrides, or `false`) and `trustProxyHops`,
    plus the env var `TRUST_PROXY_HOPS` (default 1 when `authRequired`).
  - Exempt `/healthz`, `/readyz`, static assets and public pages.
  - On 429, log the bucket and a hashed key only.

  DoD: T6 passes, and the existing suites pass unchanged (pass
  `rateLimits: false` where loops would otherwise trip the limits).
- [ ] 5. Add `src/client/upstream.ts` with:
  - `UPSTREAM_TIMEOUT_MS` (10 s, with an env and test override)
  - `upstreamSignal`
  - `upstreamFetch(name, url, init)`
  - `UpstreamTimeoutError` (status 504)
  - `UpstreamHttpError`
  - `upstreamError(name, status, body)`
  - `sanitizeUpstreamText(s, 200)`

  DoD: T7 passes.
- [ ] 6. (depends on 5) Apply timeouts and sanitized errors to every outbound
  Yandex call:
  - `src/client/quasar-client.ts`: `getCsrfToken`, both fetches in `request()`,
    `getAccountUid`. Remove the raw `text` from the error at line 312 and the
    `JSON.stringify(res)` at lines 393, 425 and 460.
  - `src/auth/token-storage.ts`: `exchangeCodeForToken`, `refreshAccessToken`.
  - `src/auth/oauth-helper.ts`: `fetchYandexProfile`,
    `validateTokenAndGetSpeakers`.
  - `src/auth/yandex-qr-auth.ts`: all five fetches. Drop `errBody` at line 158.
  - `src/client/yandex-api.ts`: use the shared timeout error and a sanitized
    message.

  DoD: running `rg "fetch\(" src` shows only `upstreamFetch` or calls that pass
  a `signal:`, excluding the browser script in the `oauth-helper` HTML and
  `oauth-controller` `https.get`. T8 and T9 pass.
- [ ] 7. (depends on 6) Bound account cleanup:
  - Give `cleanupAllProxyScenarios` an overall deadline (default 20 s) that it
    combines with the per-call signals.
  - `removeProxyScenarios` in `http-server.ts` relies on it, so
    `/account/delete`, `/account/delete-all` and `/account/disconnect-quasar`
    finish with `scenarios_left=true` on a timeout.
  - Map `UpstreamTimeoutError` to 504 in `/auth/qr-code` and `/auth/qr-status`.

  DoD: T10 passes.
- [ ] 8. Update `docs/plans/public-launch-readiness.md` to mark S5 slice (a) as
  implemented and verified, with the chosen limits and env vars. Check that
  `/terms` (`src/server/pages.ts`) now describes behaviour that exists.
  DoD: the plan document is updated in the same PR.

## Tests

Each test must fail when its fix is reverted.

- [ ] T1. `tests/request-limits.test.ts`: `readBody` rejects with
  `PayloadTooLargeError` when `Content-Length` > limit, before any data is read.
- [ ] T2. `tests/request-limits.test.ts`: a chunked or undeclared body that
  crosses the limit mid-stream is rejected. Bodies at the limit are accepted.
  JSON and form parsing results match the old `parseRequestBody`.
- [ ] T3. `tests/http-server.test.ts`: a 17 KiB `POST /oauth/register`,
  `/oauth/token` and `/api/say` each return 413. A 1.1 MiB `POST /mcp` returns
  413. A normal-sized request still succeeds.
- [ ] T4. `tests/rate-limit.test.ts`: `RateLimiter` allows `limit` calls per
  window, denies the next one with the correct `retryAfterSec`, resets after
  the window (injected `now`), and evicts or does not grow past the key cap.
- [ ] T5. `tests/rate-limit.test.ts`: `clientKey` uses the rightmost
  `X-Forwarded-For` entry with `trustProxyHops=1`, so a spoofed left entry is
  ignored. It uses `remoteAddress` with 0.
- [ ] T6. `tests/http-server.test.ts`: a server with tiny budgets returns 429
  with a numeric `Retry-After` for:
  - `/oauth/register`
  - `/oauth/token`
  - `/oauth/authorize`
  - `/auth/login`
  - `POST /mcp`

  `/healthz` is never limited. Different `X-Forwarded-For` clients have
  independent budgets.
- [ ] T7. `tests/upstream.test.ts`: `sanitizeUpstreamText` truncates to 200,
  strips control characters and redacts `Session_id=...` and `Bearer ...`.
  `upstreamError` never includes a raw HTML body.
- [ ] T8. `tests/quasar-client.test.ts`: a stubbed `fetch` that never resolves
  but honours `signal` leads to `UpstreamTimeoutError` within the (test-shortened)
  timeout, for `getCsrfToken` and `request()`. A 500 response with a body
  containing `Session_id=secret` produces an error message that contains `500`
  and not `secret`.
- [ ] T9. `tests/yandex-api.test.ts`, `tests/qr-auth.test.ts` and a token-storage
  test: a hanging `fetch` on `oauth.yandex.ru/token`, `login.yandex.ru/info` and
  `passport.yandex.ru` produces `UpstreamTimeoutError` with a clear message.
  The QR error no longer echoes the upstream body.
- [ ] T10. `tests/hosted-access.test.ts` (or a new
  `tests/account-timeout.test.ts`): with a stored Quasar cookie and a stubbed
  hanging Quasar `fetch`, `POST /account/delete` and
  `/account/disconnect-quasar` complete within the deadline. They redirect with
  `scenarios_left=true`, and for deletion the user record is gone.

## Rollback

- All changes are application code in one PR, with no schema or gitops change.
  Roll back by reverting the PR and redeploying the previous image tag:
  `mctl_rollback_service` for `labs/mctl-alice` to `2.2.4`, or reverting the
  image tag in `services/labs/mctl-alice/values.yaml`.
- To soften the behaviour without reverting, raise `UPSTREAM_TIMEOUT_MS` or set
  `TRUST_PROXY_HOPS` through the service env. The rate-limit table is a code
  constant, so changing budgets requires a patch release.
