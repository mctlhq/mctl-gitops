# Tasks: issue-74-bound-request-sizes-rate-limits-and-upst

- [ ] 1. Add `src/server/request-body.ts`:
  - Contents: `PayloadTooLargeError`, `readBodyCapped`, `readRequestBody` (with a Content-Length pre-check), `parseRequestBody` (moved from `http-server.ts:132`), `sendPayloadTooLarge`, and the constants `FORM_BODY_LIMIT` (64 KiB) and `MCP_BODY_LIMIT` (1 MiB, env `MAX_MCP_BODY_BYTES`).
  - Re-implement `oauth-controller.ts` `readCapped` on top of `readBodyCapped`, keeping its message.
  - DoD: the module compiles, and `tests/oauth-client-binding.test.ts` still passes.
- [ ] 2. (depends on 1) Route every body read through the helper:
  - `http-server.ts`: the MCP POST, `/messages` (pass the parsed body to `handlePostMessage(req, res, parsed)`), `/auth/save-token`, `/auth/save-cookie`, `/api/*`, the OAuth routes and `/account/revoke-grant`. Remove the `parseJsonBody` alias.
  - `oauth-helper.ts` `/save-token`.
  - Map `PayloadTooLargeError` to 413 in the top-level handler. Per-route catch blocks rethrow it.
  - DoD: `grep -rn 'req.on("data"' src` returns nothing, and an oversized body returns 413 on every route.
- [ ] 3. Add `src/server/rate-limit.ts`:
  - `RateLimiter`: sliding window, `maxKeys` eviction, `hit()` returns `retryAfterSec`.
  - `clientAddress(req)`, honouring `TRUST_PROXY_HOPS`.
  - `rateLimitBucket(pathname, method)`.
  - DoD: unit-testable with an injected `now`.
- [ ] 4. (depends on 3) Wire the limiters into `createHttpServer`:
  - Buckets `register`, `token`, `authorize`, `login`, `qr` and `mcp`. Budgets come from `HttpServerOptions.rateLimits`, then `RATE_LIMIT_*` env, then the defaults.
  - Check the budget before body read and authentication. The `mcp` bucket is keyed by `fingerprint(req)` when an Authorization header is present.
  - Over-budget responses are 429 with `Retry-After` and `Cache-Control: no-store`: OAuth routes get a JSON error, and the MCP POST gets a JSON-RPC error.
  - Health and static routes are exempt.
  - DoD: the configured budget plus one request returns 429 on each bucket.
- [ ] 5. Add `src/client/upstream.ts`: `upstreamFetch` (`AbortSignal.timeout` combined with an optional signal via `AbortSignal.any`), `UpstreamTimeoutError`, `UpstreamError`, `sanitizeUpstreamMessage` (120 characters maximum, known JSON fields only, control characters and markup stripped) and `upstreamError`. DoD: unit tests for timeout mapping and sanitization.
- [ ] 6. (depends on 5) Switch every Yandex call to `upstreamFetch`:
  - `quasar-client.ts`: `getAccountUid`, `getCsrfToken`, and `request` with its retry.
  - `token-storage.ts`: `exchangeCodeForToken` and `refreshAccessToken`.
  - `oauth-helper.ts`: `fetchYandexProfile`, both calls.
  - `yandex-qr-auth.ts`: all 5 calls.
  - `yandex-api.ts`: keep 15 s.
  - Replace raw-body and `JSON.stringify(res)` error text (`quasar-client.ts:312,393,425,460` and the token-storage errors) with `upstreamError` / `sanitizeUpstreamMessage`.
  - DoD: `grep -n "await fetch(" src/auth src/client` shows only `upstreamFetch` internals, and no error message embeds a raw body.
- [ ] 7. (depends on 6) Deadline for cleanup:
  - Add a `signal` option to `QuasarClient`, threaded into `upstreamFetch`. `cleanupAllProxyScenarios` stops on abort, throws, and does not call `deleteQuasarScenarios`.
  - `removeProxyScenarios` (`http-server.ts:1463`) passes `AbortSignal.timeout(20_000)`.
  - Map `UpstreamTimeoutError` and `UpstreamError` to 504 and 502 in the REST and `/auth/qr-code` error paths.
  - DoD: delete and disconnect against a hanging upstream redirect with `scenarios_left=true` within the deadline.
- [ ] 8. (depends on 2, 4, 7) Docs:
  - Add the new env vars to `README.md` and `SECURITY.md`, including the warning to set `TRUST_PROXY_HOPS` only behind a trusted proxy.
  - Mark the slice verified in `docs/plans/public-launch-readiness.md`.
  - DoD: the docs match the implemented defaults. `npm run typecheck` and `npm test` pass.

## Tests
Every test must fail when its fix is reverted.

- [ ] T1. `tests/request-limits.test.ts`, against a real `createHttpServer`:
  - Posting 65 KiB, both with Content-Length and chunked without a length, to `/oauth/register`, `/oauth/token`, `/oauth/authorize` and `/account/revoke-grant` returns 413.
  - Posting 1 MiB + 1 to `/mcp` returns 413.
  - On `/messages` with a valid SSE session, an oversized body returns 413 and the transport handler is not called.
  - Bodies under the limit still parse as JSON and as form data.
- [ ] T2. A source-scan test asserts that there is no `req.on("data"` in `src/`.
- [ ] T3. `tests/rate-limit.test.ts`:
  - Unit: `RateLimiter` allows `limit` hits, then denies with a `retryAfterSec` greater than 0, and allows again after the window with an injected clock. `maxKeys` eviction keeps the map size bounded.
  - Integration, with a small `rateLimits` option: one bucket over budget returns 429 with `Retry-After` for `/oauth/register`, `/oauth/token`, `/oauth/authorize`, `/auth/login`, `/auth/qr-code` and `/mcp`. `/healthz` is never limited. Two different bearer tokens on `/mcp` get separate budgets.
  - `TRUST_PROXY_HOPS=1` separates clients by `X-Forwarded-For`, and with 0 the header is ignored.
- [ ] T4. `tests/upstream-timeout.test.ts`, with mocked `fetch` that never resolves until its signal aborts (fake timers or a short `timeoutMs`):
  - `QuasarClient.request` and `getCsrfToken`, `exchangeCodeForToken`, `refreshAccessToken`, `fetchYandexProfile(requireVerifiedIdentity=true)` and `initQrAuth` each reject with `UpstreamTimeoutError` naming the upstream.
- [ ] T5. Integration with a hanging Quasar fetch and a stored cookie:
  - `POST /account/delete` redirects to `/?deleted=true&scenarios_left=true`, and the user is deleted.
  - `POST /account/disconnect-quasar` redirects with `scenarios_left=true`, the cookie is cleared, and the recorded scenario ids are kept.
  - Both finish within the cleanup deadline.
- [ ] T6. Sanitization: a mocked Quasar 500 with an HTML body containing `<script>` and a 5 KB payload produces a message of the form `Yandex Quasar error (500): ...` that is at most 120 characters after the prefix and contains no `<`, no newline and no payload tail. A JSON `{message}` body is kept in short form. The scenario-create failure path does not embed the full `JSON.stringify` payload.

## Rollback
- The change is code only: no schema migration and no stored-data format change. Roll back by reverting the PR and redeploying the previous image tag (`mctl_rollback_service labs mctl-alice 2.2.6`, or the tag before release).
- Without reverting, budgets can be relaxed through `RATE_LIMIT_*` and `MAX_MCP_BODY_BYTES` env changes in mctl-gitops `services/labs/mctl-alice/values.yaml`. A follow-up can add a kill switch (`RATE_LIMIT_DISABLED=true`) if operators want one. That switch is optional and not required by this proposal.
