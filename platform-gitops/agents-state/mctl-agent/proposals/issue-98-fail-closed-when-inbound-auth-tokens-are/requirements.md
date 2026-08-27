# Fail closed when inbound auth tokens are empty

## Context
`mctl-agent` gates several inbound HTTP surfaces — the AlertManager webhook,
the Telegram webhook, and the operator control-plane group (tickets, skills,
skill registration, webhook CRUD, and the `/mcp` JSON-RPC endpoint) — behind
bearer tokens or a shared secret configured via `AGENT_API_TOKEN`,
`ALERTMANAGER_WEBHOOK_TOKEN`, and `TELEGRAM_WEBHOOK_SECRET`. Today, per
`internal/api/auth.go:29-65`, an empty configured token disables the check
entirely: `requireBearer`, `requireBearerFunc`, and `telegramSecretOK` all
short-circuit to "allow" when `token == ""`. This was written to keep local
development and tests working without any secrets configured, but it means a
single missing Vault key in production silently turns every one of these
routes public — including `/mcp`, which can trigger skills, and
`/api/v1/skills/register`, which can register a remote skill that the
pipeline will delegate live diagnosis/fix traffic to. With `DRY_RUN=false`,
that chain reaches PR creation on `mctl-gitops`. `internal/api/router_test.go`
currently locks in the fail-open behavior by omitting `APIToken` and
`AlertWebhookToken` from several `NewRouter` calls and asserting 200/201
instead of 401, so a regression here would not be caught by CI today.

This proposal makes the missing-token case fail closed: when a token that
protects a route is unset, that route must reject every request with 401
rather than silently waving all requests through. `/healthz`, `/readyz`, and
`/metrics` remain intentionally public and are unaffected.

## User stories
- AS a platform operator I WANT protected mctl-agent routes to reject all
  traffic when their auth token is unconfigured SO THAT a missing Vault key
  cannot silently turn a webhook or the MCP control plane into an open,
  unauthenticated endpoint in production.
- AS an on-call engineer I WANT a clear startup signal when an expected token
  is unset SO THAT I can catch and fix a Vault misconfiguration before it
  becomes a live exposure, instead of discovering it during an incident.
- AS a contributor running `mctl-agent` locally with no secrets configured I
  WANT the router to still start (rather than panic or fail to boot) SO THAT
  local development stays possible, with the explicit tradeoff that
  token-protected routes return 401 until a token is set (see Open
  questions for the one exception, Telegram).

## Acceptance criteria (EARS)
- WHEN `AGENT_API_TOKEN` is unset and a request hits any route under the
  operator control-plane group (`/api/v1/tickets`, `/api/v1/skills`,
  `/api/v1/skills/{name}/metrics`, `/api/v1/skills/register`,
  `/api/v1/skills/{name}` DELETE, `/api/v1/skills/remote`, `/mcp`,
  `/api/v1/webhooks*`) THE SYSTEM SHALL respond `401 Unauthorized` without
  invoking the route handler.
- WHEN `ALERTMANAGER_WEBHOOK_TOKEN` is unset and a request hits
  `POST /api/v1/alerts` THE SYSTEM SHALL respond `401 Unauthorized` without
  invoking `OnAlert`.
- WHEN a bearer-protected route has its token configured and the request
  supplies a matching `Authorization: Bearer <token>` header THE SYSTEM
  SHALL invoke the route handler and respond normally.
- WHEN a bearer-protected route has its token configured and the request
  supplies a missing or non-matching `Authorization` header THE SYSTEM SHALL
  respond `401 Unauthorized`.
- WHILE `AGENT_API_TOKEN`, `ALERTMANAGER_WEBHOOK_TOKEN`, or
  `TELEGRAM_WEBHOOK_SECRET` is unset at process start THE SYSTEM SHALL log a
  startup warning naming the unset variable(s), so the misconfiguration is
  visible in boot logs rather than only inferable from request behavior.
- WHEN `GET /healthz`, `GET /readyz`, or `GET /metrics` is requested THE
  SYSTEM SHALL continue to respond without requiring any bearer token,
  regardless of token configuration.
- IF a test in `internal/api` constructs a router without setting `APIToken`
  or `AlertWebhookToken` and then asserts success (200/201) on a
  token-protected route THEN THE SYSTEM'S test suite SHALL be updated so
  that case instead asserts `401 Unauthorized`, and a new regression test
  SHALL assert 401 for each of `/api/v1/alerts`, `/api/v1/skills/register`,
  and `/mcp` specifically when their token is empty.

## Out of scope
- Path allowlisting for GitOps writes and remote-skill URL validation
  (tracked as a separate issue per the issue body).
- Changing the `AUTO_MERGE_ENABLED` default (tracked as a separate issue).
- Changing the GitHub Actions webhook (`OnGitHubWebhook`, HMAC-verified
  inside its own handler) or the external-agent callback routes
  (`/api/v1/tickets/{id}/external-claims`, `/external-results`, which already
  carry per-delivery HMAC/bearer secrets independent of `AGENT_API_TOKEN`) —
  neither uses the empty-token-disables-check pattern this issue targets.
- Rotating or provisioning the actual token values in Vault/GitOps; this
  proposal only changes application behavior when a token is absent.

## Open questions
- The issue lists `/telegram` among the routes that "must yield 401" when
  its token is empty. But `internal/api/router.go`'s
  `telegramWebhookHandler` always returns HTTP 200 to the Telegram Bot API
  by design (`TestTelegramFailClosedWithoutChatAllowlist` and
  `TestTelegramFailClosedWithoutWebhookSecret` both assert 200 even when
  auth fails) — returning non-200 to Telegram risks the platform being
  flagged unhealthy by Telegram's webhook delivery and retried/dropped.
  Interpretation adopted here: keep the HTTP-level 200-to-Telegram contract
  intact (that is a Telegram API delivery requirement, not a security
  control), but change the *command-execution* authorization so that an
  unset `TELEGRAM_WEBHOOK_SECRET` no longer falls into the current
  fully-open "local dev" branch (`TestTelegramOpenModeWhenFullyUnconfigured`)
  — commands SHALL NOT execute when the secret is unset, matching every
  other partial-misconfiguration case already handled in
  `telegramWebhookHandler`. This is flagged for reviewer confirmation since
  it changes an existing, deliberately-commented local-dev affordance.
- Whether "protected route" should also include the GitHub Actions webhook
  path is not addressed by the issue; this proposal leaves it out of scope
  since it already fails closed via HMAC verification, not the
  empty-token-disables-check pattern.
- Exact wording/format of the startup misconfiguration log is not specified
  by the issue ("consider a startup log/metric"); this proposal implements
  it as a single `slog.Warn` at boot (extending the existing
  `"mctl-agent starting"` log block in `cmd/agent/main.go:197-206`, which
  already carries `api_auth`/`telegram_webhook_auth`/`alert_webhook_auth`
  booleans) rather than a new metric, to stay consistent with the existing
  `slog.Warn` misconfiguration pattern already used for the Telegram
  secret/allowlist mismatch in `internal/api/router.go:74-79`. A Prometheus
  metric can be added later if operators want alerting on it, not just logs.
