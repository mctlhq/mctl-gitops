# Deploy canary alert rules to cluster so alerts reach AlertManager

## Context

`deploy/alerts/canary.rules.yaml` in the `mctlhq/mctl-telegram` repository defines
three alert rules — `MctlTelegramCanaryFailing`, `MctlTelegramCanaryStale`, and
`MctlTelegramCanaryAbsent` — that guard the end-to-end canary CronJob introduced in
PR #211 (released as 0.38.0). The CronJob runs every two minutes, exercises the full
OAuth + MCP + Telegram tooling path against tg.mctl.ai, and pushes
`mctl_telegram_canary_success` to Pushgateway. However, no alert rule object has ever
been deployed to the cluster, so VictoriaMetrics/VMAlert never evaluates the canary
metrics, and no alert ever reaches AlertManager or the downstream mctl-agent Telegram
notification path.

The cluster runs `victoria-metrics-k8s-stack` (VMSingle + VMAlert + VMAgent +
Alertmanager) deployed by the ArgoCD `monitoring` Application
(`platform-gitops/bootstrap/templates/observability/monitoring.yaml`). Alert rules are
managed as `VMRule` custom resources (API group `operator.victoriametrics.com/v1beta1`)
in the `monitoring` namespace. The canonical location for new VMRule manifests is
`platform-gitops/infra-components/observability/vm-rules/`, which the ArgoCD
`monitoring` Application already sources and auto-syncs. The existing
`mctl-telegram-alerts.yaml` file in that directory demonstrates the correct format and
label conventions for this cluster.

## User stories

- AS an on-call engineer I WANT `MctlTelegramCanaryFailing` to fire in AlertManager
  when the canary probe fails for ~15 minutes SO THAT I learn of user-visible outages
  before users report them.
- AS an on-call engineer I WANT `MctlTelegramCanaryStale` to fire when the CronJob
  stops pushing metrics SO THAT a broken or suspended CronJob is surfaced as a
  detectable incident, not silent data loss.
- AS an on-call engineer I WANT `MctlTelegramCanaryAbsent` to fire when canary metrics
  disappear entirely SO THAT Pushgateway failures or metric group deletion are caught.
- AS a platform team member I WANT a reusable `alertRules` gate in the `base-service`
  Helm chart SO THAT any service can opt in to deploying Prometheus-compatible alert
  rules without hand-crafting an `extraObjects` stanza.

## Acceptance criteria (EARS)

- WHEN `mctl_telegram_canary_success` equals 0 for every push in the previous 10
  minutes AND that condition persists for a further 5 minutes THE SYSTEM SHALL fire
  `MctlTelegramCanaryFailing` at severity `critical` in AlertManager.
- WHEN the canary CronJob has not pushed metrics to Pushgateway for more than 10
  minutes AND that condition persists for a further 5 minutes THE SYSTEM SHALL fire
  `MctlTelegramCanaryStale` at severity `warning` in AlertManager.
- WHEN no `mctl_telegram_canary_success` samples have arrived in the past 15 minutes
  THE SYSTEM SHALL fire `MctlTelegramCanaryAbsent` at severity `warning` in
  AlertManager immediately (for: 0m).
- WHEN any of the three canary alerts fires THE SYSTEM SHALL route it to the
  `mctl-agent` AlertManager receiver via the existing default root route so that the
  mctl-agent webhook delivers a Telegram notification.
- WHEN `kubectl -n monitoring get vmrule mctl-telegram-canary` is run THE SYSTEM SHALL
  return the VMRule resource without error.
- WHILE the canary CronJob is suspended for more than 10 minutes THE SYSTEM SHALL
  show `MctlTelegramCanaryStale` as `FIRING` in the AlertManager UI.
- IF a `prometheusrule.yaml` template is added to the `base-service` Helm chart with
  an `alertRules.enabled: false` default THEN THE SYSTEM SHALL not render any
  VMRule/PrometheusRule resource for services that do not set `alertRules.enabled:
  true`.

## Out of scope

- Changes to the Alertmanager routing config (existing default root route already
  delivers all unmatched alerts to `mctl-agent`; no new matchers are needed for the
  canary alerts).
- Updating the `deploy/alerts/canary.rules.yaml` file in the mctl-telegram repository
  from PrometheusRule to VMRule format (the source file in the app repo is not what
  gets deployed; the gitops manifest is the authoritative deployed form).
- Adding Grafana dashboards for canary metrics (canary metrics are already present in
  Pushgateway and can be queried; a dashboard is a separate improvement).
- Any changes to the canary CronJob itself (fixed in PR #211, 0.38.0).
- Alerting on `mctl_telegram_canary_step_failure_total` per-step breakdowns (the three
  top-level alerts are sufficient; per-step analysis belongs in the runbook).

## Open questions

- **VMRule vs PrometheusRule format**: The `deploy/alerts/canary.rules.yaml` source
  file uses `monitoring.coreos.com/v1 PrometheusRule` with `prometheus: kube-prometheus`
  labels. The cluster runs VictoriaMetrics (`prometheusOperator.enabled: true` but
  `prometheus.enabled: false`), and all existing deployed alert rules use
  `operator.victoriametrics.com/v1beta1 VMRule`. The gitops manifest should use VMRule.
  Verify that the VictoriaMetrics Operator CRD is registered and VMAlert is configured
  with `selectAllByDefault: true` (it is, per `monitoring.yaml`) before merging.
- **Pushgateway job label**: `MctlTelegramCanaryStale` filters on
  `job="mctl_telegram_canary"`. The canary binary (`cmd/canary`) sets this job label
  when it pushes to Pushgateway. Confirm the actual label value by inspecting
  Pushgateway's `/metrics` endpoint before deploying, or by reading the canary source.
  A mismatch would cause `MctlTelegramCanaryStale` to never fire.
- **Alertmanager canary alert routing**: The current Alertmanager config routes alerts
  to `mctl-agent` by default but lists specific `alertname` patterns only for the
  `mctl-agent` named route. The canary alert names (`MctlTelegramCanaryFailing`, etc.)
  are absent from the named route matchers. Under the current config they fall through
  to the default (root) `mctl-agent` receiver, which is correct. No change is needed,
  but this should be verified by triggering the alert in a test environment.
