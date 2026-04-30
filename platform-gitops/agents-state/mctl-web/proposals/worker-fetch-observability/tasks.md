# Tasks: worker-fetch-observability

- [ ] 1. Define `WorkerError` base class and subclasses — DoD: `cloudflare-worker/src/errors.js` (or `.ts`) exports `WorkerError`, `BackstageError`, `GitHubOAuthError`, `ResendError`, `TelegramError`, `RateLimitError`, `ValidationError`; each carries `code`, `httpStatus`, and optional `upstreamStatus`; file has unit tests passing (see T1).

- [ ] 2. Implement `errorBoundary` middleware (depends on 1) — DoD: `cloudflare-worker/src/middleware/errorBoundary.js` wraps any async handler; catches `WorkerError` and unknown errors; emits a `console.error(JSON.stringify({...}))` log entry including `requestId`, `errorCode`, `upstreamStatus`, and `message`; returns `Response` with `Content-Type: application/json` and body `{ error, code, requestId }`; stack trace is in the log but not in the response body; unit tests pass (see T2).

- [ ] 3. Implement `fetchUpstream` helper (depends on 1) — DoD: `cloudflare-worker/src/lib/fetchUpstream.js` wraps `fetch()`; throws the supplied `ErrorClass` on network failure or non-2xx upstream status; `upstreamStatus` is populated from the HTTP status code; unit tests pass (see T3).

- [ ] 4. Refactor `/api/submit` handler (depends on 2, 3) — DoD: the handler uses `fetchUpstream` for every outbound call to Backstage, Telegram Bot, and Resend; all ad-hoc `if (!res.ok)` checks replaced; handler is wrapped in `errorBoundary`; existing behavior (rate limit, HMAC validation) preserved; no regression in manual smoke test.

- [ ] 5. Refactor `/api/contact` handler (depends on 2, 3) — DoD: same as task 4 for the Telegram Bot call in `/api/contact`; wrapped in `errorBoundary`.

- [ ] 6. Refactor `/api/github/login` and `/api/github/callback` handlers (depends on 2, 3) — DoD: both handlers wrapped in `errorBoundary`; `fetchUpstream` used for the GitHub token exchange in `/callback`; `GitHubOAuthError` thrown on OAuth error field in the GitHub response body.

- [ ] 7. Generate `requestId` at Worker entry point (depends on 2) — DoD: the top-level `fetch(request, env, ctx)` handler calls `crypto.randomUUID()` and passes the value into every `errorBoundary` call; `requestId` appears in both the error response body and the `console.error` log for every failed request.

- [ ] 8. Update Nuxt composables for structured error handling (depends on 4, 5) — DoD: composables that call `/api/submit` and `/api/contact` (and any OAuth error redirect handler) attempt to parse the JSON error body on non-2xx responses; display `data.error` as the form-level error message; render `data.requestId` as "Reference: <id>" near the error message; `fetch()` network failures show a static fallback message; no existing vee-validate or yup logic modified.

- [ ] 9. Update `wrangler.toml` / CI documentation (depends on 7) — DoD: a comment in `wrangler.toml` (or `deploy.yml`) notes that `wrangler tail --format=json` is the recommended way to inspect structured error logs; no functional CI change required.

## Tests

- [ ] T1. Unit tests for error classes: each subclass instantiates correctly; `code` and `httpStatus` match the spec table in `design.md`; `upstreamStatus` is stored when provided.

- [ ] T2. Unit tests for `errorBoundary`: (a) wrapping a handler that throws `BackstageError` returns HTTP 502 JSON with `code: "BACKSTAGE_ERROR"` and a `requestId`; (b) wrapping a handler that throws a plain `Error` returns HTTP 500 with `code: "INTERNAL_ERROR"`; (c) the `console.error` mock was called once with a JSON-parseable string; (d) wrapping a handler that resolves normally passes the response through unchanged.

- [ ] T3. Unit tests for `fetchUpstream`: (a) a mocked `fetch` that rejects throws the supplied `ErrorClass` with a message containing "Network error"; (b) a mocked `fetch` returning status 503 throws the supplied `ErrorClass` with `upstreamStatus: 503`; (c) a mocked `fetch` returning 200 resolves normally.

- [ ] T4. Integration test for `/api/submit` error path: mock Backstage to return 503; assert the Worker response is HTTP 502, `Content-Type: application/json`, body matches `{ error: string, code: "BACKSTAGE_ERROR", requestId: string }`.

- [ ] T5. Integration test for `/api/contact` error path: mock Telegram Bot to return 400; assert the Worker response is HTTP 502, `code: "TELEGRAM_ERROR"`, `requestId` is a valid UUID.

- [ ] T6. Integration test for `/api/github/callback` OAuth error: mock GitHub to return `{ error: "bad_verification_code" }` in the token response body; assert the Worker response is HTTP 502, `code: "GITHUB_OAUTH_ERROR"`.

- [ ] T7. Frontend smoke test: submit the tenant request form with the Worker returning a mocked `BACKSTAGE_ERROR` response; assert the form displays the `error` string and the "Reference: <requestId>" element without a JavaScript exception.

- [ ] T8. Frontend smoke test: simulate a network failure (`fetch` rejects); assert the form shows the static fallback message and does not crash.

## Rollback

1. The change is entirely within `cloudflare-worker/` and deployed via `deploy.yml` through a Wrangler deploy step.
2. To roll back: re-run the `deploy.yml` workflow pointing at the previous commit SHA, or run `wrangler rollback` from the CLI (Wrangler retains the previous deployment).
3. The Nuxt SSG build is deployed separately. If the Nuxt composable changes must also be rolled back, redeploy the previous Nuxt build artifact via Cloudflare Pages. The frontend changes are backward-compatible with the old Worker (the old Worker never returned the structured schema, so the new parsing code is defensive and falls back gracefully).
4. No database migrations or Kubernetes changes were made, so there is no infrastructure rollback step.
