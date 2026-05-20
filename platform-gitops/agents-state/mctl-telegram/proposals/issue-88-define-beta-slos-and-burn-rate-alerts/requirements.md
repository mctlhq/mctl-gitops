# Define Beta SLOs and Burn-Rate Alerts for mctl-telegram

## Context

mctl-telegram is in beta (v0.x). It exposes Telegram user-account access via MCP
tools over HTTP, protected by an OAuth 2.1 authorization server. Raw Prometheus
metrics are emitted by `internal/metrics/metrics.go` and recorded by
`internal/mcp/tools.go` and `internal/metrics/middleware.go`, but no formal
service-level objectives exist. Without explicit targets, operators cannot
determine whether the service is healthy, whether a deployment degraded
reliability, or when to halt feature work to protect users.

Issue #88 establishes the first Beta-tier SLO targets for four SLIs: MCP tool
availability, MCP tool latency (read vs destructive tools), OAuth token-endpoint
availability, and session borrow success rate. It also calls for multi-window
burn-rate PrometheusRule alerts (fast burn 14.4x/1h, slow burn 6x/6h), an
error-budget policy, and a Grafana SLO dashboard panel. One new Prometheus
counter — `mctl_sessions_borrow_total{result}` — is required because the existing
`mctl_tool_invocations_total` counter conflates TTL-expiry borrow failures
(expected user-side state) with genuine service failures, making it impossible to
compute the session-borrow SLI accurately from existing metrics alone.

## User stories

- AS an operator I WANT a documented SLO target for MCP tool availability SO THAT
  I can answer objectively whether the service is meeting its availability promise.
- AS an operator I WANT multi-window burn-rate alerts SO THAT I am paged when the
  error budget is burning fast and notified by ticket when budget erodes slowly.
- AS an operator I WANT the error-budget policy in writing SO THAT the team has a
  shared agreement on what actions to take when the budget is exhausted.
- AS an operator I WANT an SLO panel in the Grafana dashboard SO THAT I can see
  the current burn rate and remaining budget at a glance without running PromQL
  by hand.
- AS a developer I WANT a clear definition of what counts as a service error SO
  THAT session TTL expirations and retried FLOOD_WAIT events are not mistakenly
  treated as reliability failures.

## Acceptance criteria (EARS)

- WHEN `docs/slo.md` is merged THE SYSTEM SHALL document MCP tool availability
  (99.5% over 30 days), MCP tool latency (p95 < 2s and p99 < 5s for read tools;
  p95 < 4s for destructive/send tools), OAuth token-endpoint availability (99.9%
  non-5xx over 30 days on `/oauth/token` and `/oauth/telegram/callback`), and
  session borrow success rate (99%, TTL expirations excluded).

- WHEN `internal/metrics/metrics.go` is updated THE SYSTEM SHALL declare a new
  `SessionsBorrowTotal *prometheus.CounterVec` field registered in `New()` with
  label `result` taking values: ok, expired_idle, expired_absolute, error.

- WHEN `telegram.ClientPool.Borrow()` in `internal/telegram/clientpool.go` is
  updated THE SYSTEM SHALL increment `mctl_sessions_borrow_total` on every Borrow
  call exit path: `result=ok` on successful `fn` return, `result=expired_idle`
  when `CheckSessionValid` returns `db.ErrSessionExpired` with reason `ReasonIdle`,
  `result=expired_absolute` when the reason is `ReasonAbsolute`, and `result=error`
  for all other non-nil errors.

- WHILE `db.ErrSessionExpired` is the reason for a borrow failure THE SYSTEM SHALL
  label the borrow counter with `result=expired_idle` or `result=expired_absolute`
  and SHALL NOT count that call as a service error in the session-borrow SLI
  PromQL expression.

- WHILE `mctl_telegram_flood_wait_events_total` increments and the subsequent
  retry ultimately succeeds THE SYSTEM SHALL record the final invocation status as
  "ok" in `mctl_tool_invocations_total` (this is the current behavior of
  `borrowWithRetry` in `internal/mcp/tools.go`; the SLO document SHALL confirm
  this exclusion is intentional).

- WHEN `deploy/alerts/mctl-telegram.rules.yaml` is created or updated THE SYSTEM
  SHALL include fast-burn alerts (14.4x burn over 1h, severity: page) and
  slow-burn alerts (6x burn over 6h, severity: ticket) for the MCP tool
  availability SLO and the OAuth token-endpoint availability SLO; each alert
  SHALL carry `summary` and `description` annotations referencing `docs/slo.md`.

- WHEN `deploy/grafana/mctl-telegram-beta.json` is updated THE SYSTEM SHALL
  include one new "SLO" dashboard row with panels for: current tool-availability
  SLI ratio, current OAuth-availability SLI ratio, burn-rate time series (1h and
  6h windows overlaid against the 14.4x and 6x thresholds), and remaining error
  budget in minutes for each SLO.

- IF the 30-day error budget for any SLO is exhausted THE SYSTEM SHALL trigger
  the error-budget policy documented in `docs/slo.md`: freeze non-critical feature
  merges until remaining budget is restored to at least 50%, and gate new deploys
  on a green (below 1x) burn rate over the prior 6h window.

- WHEN `docs/slo.md` is merged THE SYSTEM SHALL be cross-referenced from the
  operations section of `README.md` and from the "## Alerts" section of
  `docs/hpa.md`.

- WHEN `deploy/alerts/mctl-telegram.rules.yaml` is submitted to `promtool check
  rules` THE SYSTEM SHALL produce no errors.

## Out of scope

- Deployment plumbing for the PrometheusRule CRD (owned by #86).
- Deployment plumbing for the Grafana dashboard (owned by #87).
- SLO targets for the Local Bridge relay (`internal/bridge`) — M4, not Beta.
- Alerting for admin-only tools (`list_telegram_identities`, `set_telegram_access`,
  `get_user_audit_log`, `revoke_telegram_session`) — low frequency, no SLI defined.
- External synthetic (blackbox) monitoring probes — not deployed at Beta.
- API schema stability SLOs — deferred to v1.0.
- Sloth or other SLO-generation tooling integration — raw PromQL YAML is used.

## Open questions

1. **Tool classification label** — `mctl_tool_invocation_duration_seconds` is
   labeled only by `tool` name, not by a read/write dimension. The latency SLO
   distinguishes read vs. destructive tools. This proposal handles it via PromQL
   matchers on individual tool names. Should a `kind` label (read|destructive) be
   added to the histogram and invocation counter in a follow-up chore? Adding it
   now would be a breaking metric change requiring all dashboards to update.

2. **Borrow SLI denominator** — A single tool invocation may call `Pool.Borrow`
   zero times (dry-run sends, bridge-mode calls) or once (hosted-mode calls).
   `mctl_sessions_borrow_total` measures raw Borrow calls, not invocations. Should
   the denominator be borrow attempts (more precise) or tool invocations? This
   proposal uses borrow attempts; confirm that intent matches operator expectations.

3. **Alert routing** — The PrometheusRule YAML sets `severity: page` and
   `severity: ticket` labels. Actual routing to the on-call pager vs. issue
   tracker depends on the AlertManager configuration in mctl-gitops. Reviewers
   should confirm severity labels map to the expected receivers.

4. **Rolling-window approximation** — Prometheus does not natively support
   true 30-day rolling windows efficiently in recording rules. This proposal uses
   a 28-day range as the standard approximation (4 weeks, cache-friendly). If a
   strict 30-day window is required, confirm before implementation.
