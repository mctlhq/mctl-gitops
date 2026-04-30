# Worker Fetch Observability: Structured Error Handling

## Context
The mctl-web Cloudflare Worker handles four endpoints (`/api/github/login`, `/api/github/callback`, `/api/submit`, `/api/contact`) and integrates with four external services: GitHub OAuth, Backstage API, Telegram Bot, and Resend. When any of these upstream integrations fails — Backstage unreachable, GitHub OAuth error, Resend rate-limit exceeded — the Worker currently returns inconsistent, opaque error responses to the Nuxt frontend. There is no shared error schema, no request correlation identifier, and no guarantee that errors are logged in a machine-readable form.

workerd v1.20260430.1 (released 2026-04-30) introduces improved fetch error messaging that surfaces richer diagnostics in `wrangler tail`. Without a structured logging layer, these richer runtime diagnostics are discarded. Operators debugging a production incident must reconstruct the failure from incomplete traces, and the Nuxt frontend cannot distinguish between a temporary upstream outage, a validation failure, or a permanent configuration error.

## User stories
- AS an operator I WANT every Worker error to emit a structured log entry via `console.error` SO THAT `wrangler tail` gives me full context (endpoint, upstream, HTTP status, requestId) without grepping raw strings.
- AS a frontend developer I WANT every `/api/*` error response to conform to `{ error: string, code: string, requestId: string }` SO THAT Nuxt composables can render meaningful messages without ad-hoc response parsing.
- AS an end user I WANT the contact and submit forms to display a clear, specific error message (e.g., "Service temporarily unavailable, please try again") SO THAT I understand what went wrong and what to do next.
- AS a security-conscious operator I WANT internal details (stack traces, secret names) to be stripped from client-facing error responses SO THAT sensitive context stays in `wrangler tail` logs only.

## Acceptance criteria (EARS)

### Centralized error handler
- WHEN any route handler throws an unhandled exception THE SYSTEM SHALL catch it in a top-level middleware and return an HTTP response with the structured JSON body `{ "error": "<human-readable message>", "code": "<ERROR_CODE>", "requestId": "<uuid-v4>" }`.
- WHEN a route handler returns a non-2xx response from an upstream fetch THE SYSTEM SHALL normalize it into the structured error schema before forwarding to the client.
- WHILE processing any request THE SYSTEM SHALL generate a unique `requestId` at the Worker entry point and attach it to every log entry and every error response for that request.

### Error codes
- WHEN the Backstage API returns a non-2xx status THE SYSTEM SHALL respond with HTTP 502 and code `BACKSTAGE_ERROR`.
- WHEN the GitHub OAuth API returns an error THE SYSTEM SHALL respond with HTTP 502 and code `GITHUB_OAUTH_ERROR`.
- WHEN Resend returns a non-2xx status THE SYSTEM SHALL respond with HTTP 502 and code `RESEND_ERROR`.
- WHEN the Telegram Bot API returns a non-2xx status THE SYSTEM SHALL respond with HTTP 502 and code `TELEGRAM_ERROR`.
- WHEN rate limiting is triggered THE SYSTEM SHALL respond with HTTP 429 and code `RATE_LIMITED`.
- WHEN request validation fails THE SYSTEM SHALL respond with HTTP 400 and code `VALIDATION_ERROR`.
- IF no specific error code applies THEN THE SYSTEM SHALL use code `INTERNAL_ERROR` and HTTP 500.

### Structured logging
- WHEN an error is caught by the centralized handler THE SYSTEM SHALL call `console.error` with a JSON-serializable object containing at minimum: `requestId`, `endpoint`, `errorCode`, `upstreamStatus` (if applicable), and the error message.
- WHILE the Worker is running THE SYSTEM SHALL NOT include secret values, authorization tokens, or stack trace internals in the client-facing `error` string.

### Frontend error handling
- WHEN the Nuxt frontend receives a structured error response from any `/api/*` endpoint THE SYSTEM SHALL display a user-facing message derived from the `error` field.
- WHEN the Nuxt frontend receives a structured error response THE SYSTEM SHALL expose the `requestId` in the UI (e.g., as a small "Reference: <id>" line) to assist support.
- IF the fetch itself fails (network error, Worker unreachable) THEN THE SYSTEM SHALL display a generic connectivity error message and not crash the page.

## Out of scope
- Replacing or modifying the Cloudflare Worker with any other runtime or platform.
- Replacing vee-validate or yup for frontend form validation.
- Distributed tracing (OpenTelemetry spans, trace propagation to Backstage).
- Persistent log storage or log aggregation pipelines (Loki, Datadog, etc.).
- Changes to the Nuxt SSG build or prerendered pages.
- Alerting or on-call routing based on error codes.
- Changes to Kubernetes deployments or any `labs` tenant workloads (this proposal is Worker-only; zero k8s memory impact).
