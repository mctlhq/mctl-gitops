# Design: worker-fetch-observability

## Current state

The Cloudflare Worker lives in `cloudflare-worker/` and is deployed via Wrangler through `deploy.yml`. It exposes four endpoints:

- `GET /api/github/login` — generates OAuth redirect with HMAC-signed state
- `GET /api/github/callback` — exchanges code for token, creates session cookie
- `POST /api/submit` — validates tenant request, calls Backstage API, sends Telegram notification and Resend welcome email
- `POST /api/contact` — sends Telegram notification

Each route handler is responsible for its own error handling. In practice this means:
- Upstream `fetch()` failures may propagate as unhandled exceptions, causing the Worker runtime to return a generic 500 with no JSON body.
- Caught errors are returned as plain-text or ad-hoc JSON without a shared schema.
- `console.log` / `console.error` calls, if present, are unstructured strings.
- The Nuxt frontend (`useSubmit`, `useContact`, or similar composables) checks `response.ok` but cannot reliably parse error details because the shape varies per endpoint.

workerd v1.20260430.1 now surfaces richer `fetch()` error context in `wrangler tail` (e.g., DNS failures, TLS errors, connection refused), but this only matters if the Worker logs the error in a structured, identifiable way.

See `context/architecture.md` for the full integration map and secrets inventory.

## Proposed solution

### 1. `requestId` generation at the entry point

At the top of the Worker `fetch` handler (before routing), generate a UUID v4 as `requestId`. Use the `crypto.randomUUID()` API available in workerd. Attach this value to a request-scoped context object that is threaded through every handler call.

```
fetch(request, env, ctx) {
  const requestId = crypto.randomUUID();
  return router(request, env, ctx, requestId);
}
```

### 2. Typed error class hierarchy

Introduce a small set of Worker-internal error classes (no external dependency required):

```
WorkerError          — base: message, code, httpStatus, upstreamStatus?
  BackstageError     — code: BACKSTAGE_ERROR,     httpStatus: 502
  GitHubOAuthError   — code: GITHUB_OAUTH_ERROR,  httpStatus: 502
  ResendError        — code: RESEND_ERROR,         httpStatus: 502
  TelegramError      — code: TELEGRAM_ERROR,       httpStatus: 502
  RateLimitError     — code: RATE_LIMITED,         httpStatus: 429
  ValidationError    — code: VALIDATION_ERROR,     httpStatus: 400
```

Route handlers throw the appropriate subclass. The centralized handler catches all `WorkerError` instances and falls back to `INTERNAL_ERROR` / 500 for unknown throws.

### 3. Centralized error middleware (`errorBoundary`)

A higher-order function wraps every route handler:

```
async function errorBoundary(handler, requestId) {
  try {
    return await handler();
  } catch (err) {
    const code    = err instanceof WorkerError ? err.code    : 'INTERNAL_ERROR';
    const status  = err instanceof WorkerError ? err.httpStatus : 500;
    const message = err instanceof WorkerError ? err.message : 'An unexpected error occurred';

    console.error(JSON.stringify({
      requestId,
      errorCode: code,
      message: err.message,
      upstreamStatus: err.upstreamStatus ?? null,
      stack: err instanceof WorkerError ? undefined : err.stack,
    }));

    return new Response(
      JSON.stringify({ error: message, code, requestId }),
      { status, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
```

Note: `err.stack` is included in the `console.error` payload (visible only in `wrangler tail`) but is never sent to the client.

### 4. Upstream fetch wrapper

A shared `fetchUpstream(url, options, ErrorClass)` helper wraps every outbound `fetch()`:

```
async function fetchUpstream(url, init, ErrorClass) {
  let res;
  try {
    res = await fetch(url, init);
  } catch (networkErr) {
    throw new ErrorClass(`Network error reaching ${url}: ${networkErr.message}`);
  }
  if (!res.ok) {
    throw new ErrorClass(`Upstream returned ${res.status}`, res.status);
  }
  return res;
}
```

This replaces ad-hoc `if (!res.ok)` checks scattered across route handlers.

### 5. Structured JSON error response schema

Every error response from the Worker will conform to:

```json
{
  "error": "Human-readable message safe for display",
  "code": "BACKSTAGE_ERROR",
  "requestId": "550e8400-e29b-41d4-a716-446655440000"
}
```

The `code` field is machine-readable; the `error` field is safe for display. No stack traces, no secret names, no internal paths are included in the response body.

### 6. Nuxt frontend updates

In the composables that call `/api/submit` and `/api/contact` (and any OAuth redirect error page):

- Parse the JSON body on non-2xx responses.
- Display `data.error` as the form-level error message.
- Render `data.requestId` as a small "Reference: <id>" element to assist support requests.
- Handle `fetch()` network failures (Worker unreachable) with a static fallback message.

The `vee-validate` + `yup` validation layer on the frontend is unchanged.

## Alternatives

### Alternative A: Sentry (or similar) SDK in the Worker

Sentry provides Worker-compatible error capture with automatic `requestId` correlation. This would give persistent error storage and alerting out of the box.

Dropped because: it introduces an external SDK dependency into the Worker bundle, increases cold-start size, requires managing another secret (`SENTRY_DSN`), and is disproportionate for a Worker with four endpoints. `wrangler tail` already provides real-time log streaming; persistent storage is out of scope.

### Alternative B: Hono or itty-router middleware framework

Using a micro-framework like Hono would provide a built-in error handler middleware pattern and reduce boilerplate.

Dropped because: the Worker currently has no routing framework and adding one is a non-trivial migration requiring a separate decision. The `errorBoundary` higher-order function achieves the same goal with zero new dependencies and zero risk of routing behavior changes.

### Alternative C: Return all errors as HTTP 200 with an `ok: false` envelope

Some APIs wrap all responses in `{ ok: boolean, ... }` to avoid frontend `fetch()` error-branch handling.

Dropped because: it violates HTTP semantics, breaks standard monitoring tools that count non-2xx responses, and makes Cloudflare rate-limit and WAF rules harder to reason about.

## Platform impact

### Migrations
None. The change is entirely within `cloudflare-worker/`. No database schema, no Kubernetes manifests, no ArgoCD application changes.

### Backward compatibility
The Worker currently returns inconsistent error shapes. Any Nuxt code that parses error bodies today is necessarily defensive and will continue to work; the new schema is strictly more informative. The one breaking change is that responses that previously returned a plain-text body (or empty body) on error will now return JSON — the `Content-Type: application/json` header will be set. This is a safe improvement.

### Resource impact (`labs` tenant)
This proposal makes zero changes to any Kubernetes workload. The Worker runs on Cloudflare's edge, entirely outside the cluster. There is no memory, CPU, or storage impact on the `labs` tenant.

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| `errorBoundary` wrapper swallows a panic and returns 500 instead of propagating | Low | Unit-test all known error classes; keep the fallback path simple |
| `console.error` JSON serialization throws on circular references | Low | Use `JSON.stringify` with a replacer that omits non-serializable values |
| New `Content-Type: application/json` header on errors breaks a client that expected plain text | Low | Audit all frontend fetch calls before deploy; add integration test for error shape |
| `crypto.randomUUID()` not available in older workerd pinned in CI | Very Low | workerd >= 1.20230512.0 supports `crypto.randomUUID()`; current is 1.20260430.1 |
