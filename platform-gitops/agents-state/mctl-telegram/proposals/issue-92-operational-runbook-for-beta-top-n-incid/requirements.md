# Operational Runbook for Beta: Top-N Incident Playbooks

## Context

Alerts defined by issues #86 (PrometheusRule resources) and #88 (SLO burn-rate
alerts) will page on-call engineers when thresholds are breached. Without a
structured guide, each incident requires the on-call to reconstruct diagnostic
steps from scratch, leading to slow, inconsistent responses and longer MTTR
during the Beta period.

Issue #92 requests a `docs/runbook.md` that covers seven alert conditions: pool
capacity pressure, Telegram flood-wait spikes, stuck OAuth pending flows, JWT
auth failure spikes, MTProto client errors, canary probe failures, and SLO
fast-burn / slow-burn. Each entry must carry a Symptom, ranked Likely Causes,
concrete Diagnostic Queries, bounded Mitigation actions, Escalation criteria,
and a Postmortem Trigger. Alert rules in `deploy/alerts/mctl-telegram.rules.yaml`
(from #86) are to be annotated with `runbook_url` values pointing at stable HTML
anchors in the runbook file.

## User stories

- AS an on-call engineer I WANT a per-alert playbook I can follow without prior
  context SO THAT I can diagnose and contain incidents in minutes rather than
  hours.
- AS a platform operator I WANT `runbook_url` annotations in PrometheusRule
  resources SO THAT Alertmanager and PagerDuty pages link directly to the
  relevant runbook section.
- AS a new team member I WANT consistent escalation and postmortem-trigger
  criteria SO THAT I know when to wake senior staff and when a writeup is
  required.
- AS a future on-call engineer I WANT stable section anchors SO THAT runbook
  URLs in alert annotations remain valid even if the runbook is reorganised.

## Acceptance criteria (EARS)

- WHEN `docs/runbook.md` is merged, THE SYSTEM SHALL contain a distinct section
  for each of the following alert names: `MctlTelegramPoolNearCapacity`,
  `MctlTelegramFloodWaitSpike`, `MctlTelegramOAuthPendingStuck`,
  `MctlTelegramAuthFailuresSpike`, `MctlTelegramClientErrorsSpike`,
  `MctlTelegramCanaryFailing`, and `SLOBurnRate`.

- WHEN a runbook section exists, THE SYSTEM SHALL include all six mandatory
  subsections: Symptom, Likely causes, Diagnostic queries, Mitigation,
  Escalation, and Postmortem trigger.

- WHEN a Diagnostic query references a Prometheus metric, THE SYSTEM SHALL use
  the exact metric name as registered in `internal/metrics/metrics.go` (e.g.
  `mctl_telegram_client_pool_size`, `mctl_telegram_pool_capacity`,
  `mctl_telegram_flood_wait_events_total`, `mctl_oauth_pending_auth_size`,
  `mctl_auth_failures_total`, `mctl_telegram_client_errors_total`,
  `mctl_telegram_canary_step_failure_total`).

- WHEN a Diagnostic query references a log field, THE SYSTEM SHALL use the
  structured slog JSON key as emitted by the server (e.g. `user_id`, `err`,
  `reason`, `idle`).

- WHEN `deploy/alerts/mctl-telegram.rules.yaml` exists (from #86), THE SYSTEM
  SHALL include a `runbook_url` annotation on each PrometheusRule alert whose
  name matches a runbook section, pointing to the canonical public URL of
  `docs/runbook.md` with the corresponding anchor fragment.

- WHILE sections within `docs/runbook.md` are reordered, THE SYSTEM SHALL
  preserve the named HTML anchors (`<a id="...">`) so that existing
  `runbook_url` links remain valid.

- IF the pool utilization ratio `mctl_telegram_client_pool_size /
  mctl_telegram_pool_capacity` exceeds 0.85 and a pod restart is being
  considered, THEN the runbook SHALL instruct the on-call to verify available
  RAM headroom against the 3 MB-per-session estimate (from `docs/hpa.md`)
  before raising `TELEGRAM_MAX_SESSIONS`.

- IF `mctl_telegram_pool_capacity` equals -1 (uncapped; `TELEGRAM_MAX_SESSIONS`
  is 0 or unset), THEN the runbook SHALL note that HPA and pool-capacity alerts
  are disabled and instruct the on-call to set a cap before enabling either.

- WHEN `mctl_auth_failures_total` spikes, THE SYSTEM SHALL instruct the on-call
  to break down the counter by the `reason` label using the values classified in
  `internal/auth/middleware.go` (jwt_expired, jwt_invalid_signature,
  jwt_invalid_issuer, jwt_missing_audience, jwt_wrong_audience,
  bearer_scheme_error, other).

- WHEN `UseDBForOAuth=true` is active and `mctl_oauth_pending_auth_size`
  is elevated, THE SYSTEM SHALL include a `psql` query against the
  `oauth_pending_auth` table (`CountOAuthPending` in `internal/db/store_oauth.go`)
  as a corroborating diagnostic step.

## Out of scope

- Creating or modifying PrometheusRule YAML for #86 or #88 (those issues own
  their own alert definitions).
- Implementing the canary probe or its metrics (`mctl_telegram_canary_*` family
  from #89).
- Automated remediation scripts, runbook-as-code tooling, or self-healing
  operators.
- Loki or log-aggregation infrastructure setup.
- Postmortem template creation.
- Any changes to Go source files; this proposal produces documentation only.

## Open questions

1. `deploy/alerts/mctl-telegram.rules.yaml` does not exist in the current clone.
   The file path and exact rule names are assumed from the alert names listed in
   the issue and from the example in `docs/hpa.md`. If #86 uses a different
   file path or rule names, the `runbook_url` task (task 2) must adjust
   accordingly. Resolution: coordinate with the #86 implementer before merging
   task 2.

2. The `MctlTelegramCanaryFailing` alert and the metric
   `mctl_telegram_canary_step_failure_total` are referenced by issue #92 but
   not yet implemented in the codebase (#89 is the upstream). The runbook
   section for this alert is written against the stated intent from the issue.
   If the canary implementation chooses different metric or label names, the
   diagnostic queries must be updated post-#89.

3. The SLO burn-rate section references "feature-freeze policy per #88" but
   #88 is not present in the clone. The runbook describes the policy
   conceptually (halt non-critical rollouts, increase scrape frequency) pending
   the canonical definition from #88. Reviewers should confirm whether #88
   defines a specific freeze procedure to link to.

4. The issue specifies `mctl_telegram_flood_wait_events_total` is labeled by
   tool name. The per-user audit log is referenced for identifying the abusing
   `user_id`. The audit log's exact query mechanism (Loki label, `kubectl logs`
   grep, or psql) is left as an operator choice in the runbook since the audit
   log backend is deployment-specific.
