# Design: issue-98-fail-closed-when-inbound-auth-tokens-are

## Current state

Inbound HTTP auth for `mctl-agent` lives in `internal/api/auth.go` and is
consumed by `internal/api/router.go`:

- `requireBearer(token string) func(http.Handler) http.Handler` (auth.go:32-46)
  wraps a chi middleware group. If `token == ""` it returns `next` directly —
  the check is skipped. Otherwise it 401s on any request whose
  `Authorization: Bearer` value doesn't `subtle.ConstantTimeCompare` to
  `token` (via `secretEqual`, auth.go:19-27, which itself already treats
  `want == ""` as "never match" — but that branch is unreachable from
  `requireBearer`/`requireBearerFunc` today because they bail out before
  calling it).
- `requireBearerFunc(token string, next http.HandlerFunc) http.HandlerFunc`
  (auth.go:47-58) is the single-handler equivalent, used for
  `POST /api/v1/alerts` (router.go:99).
- `telegramSecretOK(r *http.Request, secret string) bool` (auth.go:60-65)
  returns `true` unconditionally when `secret == ""`.
- `router.go:117-119` applies `requireBearer(opts.APIToken)` as middleware
  over a `chi.Router` group that covers `/api/v1/tickets`, `/api/v1/skills`,
  `/api/v1/skills/{name}/metrics`, `/api/v1/skills/register`,
  `/api/v1/skills/{name}` (DELETE), `/api/v1/skills/remote`, `/mcp`
  (`mcpServer.ServeHTTP`), and `/api/v1/webhooks*`. All of these currently
  become fully public when `AGENT_API_TOKEN` is unset.
- `router.go:99` gates `POST /api/v1/alerts` with
  `requireBearerFunc(opts.AlertWebhookToken, opts.OnAlert)` — public when
  `ALERTMANAGER_WEBHOOK_TOKEN` is unset.
- `telegramWebhookHandler` (router.go:167-215) calls `telegramSecretOK` first,
  then separately checks that `TelegramWebhookSecret != ""` has the same
  truthiness as `opts.Telegram.HasChatAllowlist()` before allowing commands
  to execute (router.go:196-206) — this is where the deliberate two-factor
  design (secret proves Telegram-origin, chat allowlist proves sender) lives.
  Critically, when *both* are unset, this handler currently treats that as
  "local dev, fully open" and lets commands run
  (`TestTelegramOpenModeWhenFullyUnconfigured`). The handler always writes
  HTTP 200 regardless of auth outcome — this is a Telegram Bot API delivery
  contract (a non-200 response causes Telegram to treat the webhook as
  failing and retry/back off), not a security signal, and is out of scope to
  change.
- `/healthz`, `/readyz`, `/metrics` are registered directly on the root
  `chi.Router` (router.go:88-96) and never touch any of the above — they
  stay public by construction and need no code change.
- Startup config: `internal/config/config.go:231-233` reads
  `AGENT_API_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `ALERTMANAGER_WEBHOOK_TOKEN`
  via `strings.TrimSpace(os.Getenv(...))` — already normalized to `""` when
  unset or whitespace-only. `cmd/agent/main.go:196-206` already logs an
  `"mctl-agent starting"` line with `api_auth`, `telegram_webhook_auth`,
  `alert_webhook_auth` booleans, but at `Info` level mixed in with routine
  boot info, not as a distinct warning an operator would notice.
- `internal/api/router_test.go` and `internal/api/webhook_handlers_test.go`
  construct `Options{}` without `APIToken`/`AlertWebhookToken` in most
  non-`auth_test.go` tests (`TestTicketListEndpoint`,
  `TestTicketListEndpointFilters`, `TestSkillListEndpoint`,
  `TestRemoteSkillEndpoints`, `TestMCPEndpoint`,
  `TestWebhookRegisterListDelete`) and assert success — this is the
  "existing tests lock in fail-open" evidence from the issue.

## Proposed solution

1. **Flip the empty-token branches in `internal/api/auth.go` from
   "skip check" to "always reject".**
   - `requireBearer`: remove the `if token == "" { return next }`
     short-circuit. Instead, always wrap with the checking handler; rely on
     `secretEqual(got, want)`'s existing `if want == "" { return false }`
     branch (auth.go:20-22) to make the check unconditionally fail when
     `token == ""`. This is a minimal, surgical change — `secretEqual`
     already encodes exactly the fail-closed behavior we want, it was just
     unreachable.
   - `requireBearerFunc`: same change — drop its own
     `if token == "" { return next }` (auth.go:48-50) and let it always
     delegate to the `secretEqual` check.
   - `telegramSecretOK`: drop the `if secret == "" { return true }`
     short-circuit (auth.go:61-63) so an empty configured secret always
     fails the header check. This alone does not change command-execution
     behavior for the "fully unconfigured" case — see point 3.
   - Update the doc comment on `requireBearer` (auth.go:29-31), which
     currently documents the fail-open rationale, to instead state the
     fail-closed contract.

2. **No router.go route wiring changes are needed.** Every route this issue
   targets (`/api/v1/alerts`, `/api/v1/skills/register` and siblings via the
   `APIToken` group, `/mcp`) already goes through `requireBearer` /
   `requireBearerFunc`; fixing the shared `auth.go` helpers fixes all call
   sites at once, including `/api/v1/tickets`, `/api/v1/skills/*`, and
   `/api/v1/webhooks*`, which the issue doesn't name explicitly but are
   protected by the same `APIToken` and share the same exposure.

3. **Telegram command execution: remove the "fully unconfigured = open"
   branch, keep the HTTP 200 contract.** In `telegramWebhookHandler`
   (router.go:196-206), the existing check
   `if (opts.TelegramWebhookSecret != "") != opts.Telegram.HasChatAllowlist()`
   already rejects execution when exactly one of {secret, allowlist} is set.
   Change the condition so it also rejects when *neither* is set — i.e.
   replace the XOR-style mismatch check with: reject unless both
   `TelegramWebhookSecret != ""` AND `HasChatAllowlist()` are true. The
   handler still writes `w.WriteHeader(http.StatusOK)` in the rejection
   path (Telegram delivery contract, unchanged) but no command executes.
   This directly addresses the issue's "empty token must yield 401 on
   ... /telegram" intent at the authorization-decision level while
   preserving the documented Telegram-retry-avoidance behavior at the
   transport level (see Open Questions in requirements.md — flagged for
   reviewer sign-off since it removes a previously-intentional local-dev
   affordance).

4. **Startup visibility.** In `cmd/agent/main.go`, before the existing
   `slog.Info("mctl-agent starting", ...)` block (main.go:197-206), add a
   loop that checks `cfg.AgentAPIToken`, `cfg.AlertWebhookToken`, and
   `cfg.TelegramWebhookSecret` and, for each unset one, calls
   `slog.Warn("inbound auth token not configured; affected routes will reject all requests", "variable", "AGENT_API_TOKEN")`
   (one call per unset var, naming the exact env var so operators can grep
   boot logs directly for the Vault key to fix). This mirrors the existing
   `slog.Warn` misconfiguration pattern already used for the Telegram
   secret/allowlist mismatch (router.go:74-79) rather than introducing a new
   mechanism. A metric is not added in this pass (see Open Questions) — logs
   are consistent with how the existing Telegram misconfiguration is
   surfaced today.

5. **Test updates in `internal/api`:**
   - `router_test.go`: `TestTicketListEndpoint`,
     `TestTicketListEndpointFilters`, `TestSkillListEndpoint` need an
     `APIToken` set and the `Authorization` header attached to their
     requests (or split into an authenticated-path variant) since their
     current assertions target 200 through what will become a
     token-required route once no token means 401 either way — with no
     token in `Options`, they will now get 401 instead of the handler
     response. Simplest fix consistent with `auth_test.go`'s existing
     pattern: set `APIToken: "test-token"` in these tests' `Options` and add
     `Authorization: Bearer test-token` to each request, so the tests keep
     verifying handler behavior (filtering, listing) rather than auth.
   - `TestRemoteSkillEndpoints`, `TestMCPEndpoint`: same treatment —
     add `APIToken` + header.
   - `webhook_handlers_test.go`'s `newWebhookEnabledRouter` /
     `TestWebhookRegisterListDelete`: same treatment.
   - Add new regression tests (co-located in `auth_test.go`, following its
     existing naming style) asserting 401 with empty token for the three
     routes the issue names explicitly:
     `TestAlertWebhookFailsClosedWhenTokenEmpty`,
     `TestSkillsRegisterFailsClosedWhenTokenEmpty` (or fold into a
     table-driven `TestControlPlaneFailsClosedWhenTokenEmpty` covering
     tickets/skills/register/mcp/webhooks in one table, matching this
     repo's stated table-driven-tests convention from `CLAUDE.md`), and
     `TestMCPFailsClosedWhenTokenEmpty`.
   - Update `TestTelegramOpenModeWhenFullyUnconfigured` (auth_test.go) to
     assert `pipe.IsPaused()` is `false` (command does NOT execute) instead
     of `true`, and rename it to reflect the new behavior (e.g.
     `TestTelegramFailsClosedWhenFullyUnconfigured`) — or, if the reviewer
     rejects the Telegram open-question interpretation, leave it as today
     and drop point 3 from the change (see Open Questions; this is called
     out explicitly so the reviewer can choose either path in review rather
     than the change silently picking one).

## Alternatives

1. **Require tokens to be non-empty at startup (panic/exit if any is
   unset) instead of returning 401 per-request.** Rejected: this would break
   local development and any deployment that intentionally runs without one
   of these subsystems configured (e.g. a cluster with no AlertManager
   webhook wired up yet), and is a much larger blast radius than the issue
   asks for. The issue explicitly asks for a per-route 401, not a boot
   failure, and keeps `/healthz` reachable so the pod still reports healthy
   even in a misconfigured-but-running state that the startup warning
   (point 4) surfaces.

2. **Add a new explicit `RequireAuth bool` / "strict mode" config flag
   defaulting to false, so operators opt in to fail-closed.** Rejected:
   this preserves the current fail-open default and requires every
   production deployment to remember to flip a new flag — exactly the
   silent-misconfiguration risk the issue is about. Fail-closed should be
   the only behavior, not an opt-in, since there is no safe reason to want
   an unauthenticated control plane in production, and dev/test environments
   don't need the routes to succeed unauthenticated — they need the router
   to still construct and serve `/healthz`, which is unaffected by this
   change.

3. **Leave `telegramSecretOK`/command-execution behavior untouched and
   only change `requireBearer`/`requireBearerFunc`.** Considered as the
   conservative option for point 3. This satisfies the literal letter of
   "empty token must yield 401" for `/api/v1/alerts`, `/skills/register`,
   `/mcp` cleanly, but leaves `/telegram` command execution fully open when
   unconfigured, which is exactly the class of gap the issue is about and
   arguably the most likely real misconfiguration (Vault key never set) in
   a still-unwired-for-Telegram cluster. Not adopted as the primary
   proposal, but recorded as the fallback if the reviewer wants to keep the
   Telegram local-dev affordance — see Open Questions and design point 3.

## Platform impact

- **Migrations:** none. No schema, storage, or API contract changes beyond
  HTTP status codes on already-existing routes.
- **Backward compatibility:** breaking for any deployment currently running
  with one or more of `AGENT_API_TOKEN` / `ALERTMANAGER_WEBHOOK_TOKEN` /
  `TELEGRAM_WEBHOOK_SECRET` unset and relying on the endpoint being reachable
  without a token. Per the issue and `CLAUDE.md`'s API endpoint doc (which
  already documents these as "bearer when set", implying they're meant to be
  set in real deployments), any such deployment is a misconfiguration this
  issue exists to close, not a supported mode. Operators should check
  `mctl_get_service_logs` / boot logs for the new startup warning (point 4)
  immediately after this ships, for every environment running mctl-agent.
- **Resource impact:** negligible — same request path, one comparison
  instead of an early return.
- **Risks + mitigations:**
  - *Risk:* a production deployment currently has one of these three tokens
    unset (intentionally or by oversight) and will suddenly 401 on real
    traffic (AlertManager alerts stop creating tickets, or the MCP control
    plane stops responding) after this ships.
    *Mitigation:* the startup warning (point 4) should be shipped and
    observed for at least one deploy cycle before/alongside this change so
    operators can confirm all three tokens are set in every environment;
    `mctl_get_service_logs` can be used to check current boot logs for
    `api_auth=false` etc. before the fail-closed change reaches prod.
  - *Risk:* the Telegram behavior change (point 3) surprises a reviewer who
    values the local-dev fully-open affordance.
    *Mitigation:* called out explicitly in Open Questions and as Alternative
    3; easy to drop independently of the rest of the change since it's a
    single conditional in `telegramWebhookHandler`.
  - *Risk:* CI or any downstream consumer (e.g. `internal/mcp` tests, if
    any construct a router the same fail-open way) breaks silently.
    *Mitigation:* task list includes a full-repo grep for `NewRouter(` call
    sites in tests as a checklist item (see tasks.md) so no test is missed.
