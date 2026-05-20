# Ship PrometheusRule manifests for production alerts (pool, FLOOD_WAIT, OAuth state)

## Context

`docs/hpa.md` in `mctlhq/mctl-telegram` already documents several alert
expressions as inline code-block examples, but they are not deployed anywhere.
`internal/metrics/metrics.go` defines eight Prometheus metric families — pool
gauges, flood-wait counters, OAuth pending auth gauge, auth failures, client
errors, rate-limit counters, tool invocations — all exposed at `/metrics` by
`cmd/server/main.go`. For the Beta tier, SRE must be paged before users notice
degraded service, so the alert expressions need to move from documentation prose
into a real `PrometheusRule` custom resource that Prometheus Operator evaluates.

The issue also requires `docs/hpa.md` to reference the new manifest file instead
of re-stating the rules inline, so the document is never out of sync with what
is actually deployed.

## User stories

- AS an SRE I WANT to receive a warning page when the Telegram client pool exceeds
  85% of its configured capacity for 5 minutes SO THAT I can scale replicas before
  the pool fills and requests fail.
- AS an SRE I WANT to receive a critical page when the pool exceeds 95% capacity
  for 2 minutes SO THAT I can act on an imminent hard cap breach.
- AS an SRE I WANT to be alerted when FLOOD_WAIT events spike above 0.5 per second
  (warning) or 2 per second (critical) SO THAT I can identify which MCP tool is
  triggering Telegram rate limits.
- AS an SRE I WANT to be alerted when `mctl_oauth_pending_auth_size` stays above
  100 for 15 minutes SO THAT I can detect abandoned or bot-driven OAuth flows
  before they exhaust database or memory resources.
- AS an SRE I WANT to be alerted when auth failures spike above 1 per second
  SO THAT I can detect credential-stuffing or misconfigured client deployments.
- AS an SRE I WANT to be alerted when Telegram client errors spike above 0.2
  per second SO THAT I can detect MTProto transport instability.
- AS an SRE I WANT to be alerted when rate-limit events exceed 1 per second
  SO THAT I can detect abusive or misconfigured callers.
- AS a platform contributor I WANT `docs/hpa.md` to reference the deployed
  manifest rather than duplicating alert YAML SO THAT documentation and runtime
  configuration cannot diverge.

## Acceptance criteria (EARS)

- WHEN `mctl_telegram_client_pool_size / mctl_telegram_pool_capacity > 0.85`
  persists for 5 minutes THE SYSTEM SHALL fire the `MctlTelegramPoolNearCapacity`
  alert with `severity: warning`.
- WHEN `mctl_telegram_client_pool_size / mctl_telegram_pool_capacity > 0.95`
  persists for 2 minutes THE SYSTEM SHALL fire the `MctlTelegramPoolNearCapacity`
  alert with `severity: critical`.
- WHEN `sum(rate(mctl_telegram_flood_wait_events_total[5m])) > 0.5` THE SYSTEM
  SHALL fire `MctlTelegramFloodWaitSpike` with `severity: warning`.
- WHEN `sum(rate(mctl_telegram_flood_wait_events_total[5m])) > 2` THE SYSTEM
  SHALL fire `MctlTelegramFloodWaitSpike` with `severity: critical`.
- WHEN `mctl_oauth_pending_auth_size > 100` persists for 15 minutes THE SYSTEM
  SHALL fire `MctlTelegramOAuthPendingStuck` with `severity: warning`.
- WHEN `sum(rate(mctl_auth_failures_total[5m])) > 1` THE SYSTEM SHALL fire
  `MctlTelegramAuthFailuresSpike` with `severity: warning`.
- WHEN `sum(rate(mctl_telegram_client_errors_total[5m])) > 0.2` THE SYSTEM SHALL
  fire `MctlTelegramClientErrorsSpike` with `severity: warning`.
- WHEN `sum(rate(mctl_rate_limit_events_total[5m])) > 1` THE SYSTEM SHALL fire
  `MctlTelegramRateLimitWave` with `severity: warning`.
- WHILE the `PrometheusRule` manifest is deployed THE SYSTEM SHALL include
  `summary`, `description`, `runbook_url`, and `severity` annotations/labels on
  every alert rule.
- IF `docs/hpa.md` is updated THE SYSTEM SHALL no longer contain the duplicated
  inline alert YAML block, replacing it with a reference to
  `deploy/alerts/mctl-telegram.rules.yaml`.
- WHEN the `deploy/alerts/mctl-telegram.rules.yaml` file is merged THE SYSTEM
  SHALL document in `docs/hpa.md` the path operators must use to mirror the
  manifest into their cluster (or the path within `mctl-gitops`).

## Out of scope

- Burn-rate / error-budget SLO alerts (tracked separately).
- Synthetic canary alerts (tracked separately).
- Prometheus Adapter configuration for HPA custom metrics (already covered by
  `docs/hpa.md` and `mctl-gitops/platform-gitops/k8s/prometheus-adapter/`).
- Changes to Go metric instrumentation code in `internal/metrics/`.
- Runbook content beyond placeholder URLs (runbook authoring is a follow-up).

## Open questions

1. **Namespace and label selector**: The `PrometheusRule` needs a `namespace`
   field and a set of labels that match the `Prometheus` CR's `ruleSelector`.
   The issue does not specify the target namespace (likely `mctl` based on HPA
   stanza in `docs/hpa.md`) or the required label set for the operator.
   Reasonable default: `namespace: mctl`, labels `app: mctl-telegram` and
   `release: kube-prometheus-stack` (common convention for kube-prometheus-stack
   installs). Implementer should confirm with the gitops operator config.

2. **`for` clause on rate-based alerts**: `MctlTelegramFloodWaitSpike`,
   `MctlTelegramAuthFailuresSpike`, `MctlTelegramClientErrorsSpike`, and
   `MctlTelegramRateLimitWave` have no explicit `for` duration in the issue.
   Omitting `for` means the alert fires on the first evaluation that exceeds the
   threshold. A short stabilisation window (e.g. `for: 2m`) would reduce
   flapping; the issue is silent on this. Proposal adopts `for: 2m` for warning
   rate alerts to avoid flapping on brief spikes.

3. **Pool capacity guard**: When `TELEGRAM_MAX_SESSIONS` is unset, the gauge is
   set to `-1` (see `cmd/server/main.go` lines 90-95). The pool-capacity ratio
   expression produces a negative value in that case. The alert should be guarded
   by `mctl_telegram_pool_capacity > 0`; the issue text does not mention this
   guard explicitly but `docs/hpa.md` notes the `-1` sentinel. Proposal adds the
   guard.

4. **Runbook base URL**: No runbook repository or URL pattern is referenced in
   the issue. Placeholder URLs of the form
   `https://github.com/mctlhq/mctl-telegram/wiki/runbook-<alertname>` are used;
   a follow-up issue should replace them with real content.

5. **`mctl-gitops` PR**: The issue asks to "open a follow-up PR in `mctl-gitops`
   to apply the manifest". That is an action item for the implementer, not a
   code change in this repo. The proposal captures it as a task and documents the
   expected gitops path, but cannot automate the PR creation.
