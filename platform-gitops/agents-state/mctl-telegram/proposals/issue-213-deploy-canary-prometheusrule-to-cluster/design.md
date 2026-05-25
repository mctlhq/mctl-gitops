# Design: issue-213-deploy-canary-prometheusrule-to-cluster

## Current state

### Observability stack

The cluster runs `victoria-metrics-k8s-stack` v0.72.5 deployed by the ArgoCD
`monitoring` Application defined in
`platform-gitops/bootstrap/templates/observability/monitoring.yaml`. Key components:

- **VMSingle** — single-node VictoriaMetrics time-series database.
- **VMAgent** — scrape engine replacing Prometheus; `selectAllByDefault: true`.
- **VMAlert** — alerting engine replacing Prometheus alerting; `selectAllByDefault: true`,
  `evaluationInterval: 1m`.
- **Alertmanager** — routing to `mctl-agent` webhook
  (`http://admins-mctl-agent-base-service.admins.svc.cluster.local:8080/api/v1/alerts`)
  via the root default receiver; also a named `mctl-agent` route that lists many alert
  names explicitly.
- **Prometheus Operator** — `prometheusOperator.enabled: true`, but
  `prometheus.enabled: false`. The operator is kept alive to handle ServiceMonitor CRDs;
  VictoriaMetrics Operator converts ServiceMonitors to VMServiceScrape. PrometheusRule
  CRDs are present in the cluster but VictoriaMetrics Operator converts them to VMRule
  only when configured to do so.

Alert rule manifests land in the cluster via the ArgoCD `monitoring` Application's third
source:

```yaml
- repoURL: https://github.com/mctlhq/mctl-gitops.git
  targetRevision: main
  path: platform-gitops/infra-components/observability/vm-rules
```

That directory currently contains:
- `mctl-alerts.yaml` — platform-wide alerts
- `mctl-telegram-alerts.yaml` — mctl-telegram service-level alerts (VMRule format)
- `mctl-agent-cleanup-alerts.yaml` — mctl-agent housekeeping alerts
- `openclaw-auth-alerts.yaml` — openclaw OAuth alerts
- `openclaw-llm-alerts.yaml` — openclaw LLM alerts

All are `operator.victoriametrics.com/v1beta1 VMRule` resources in the `monitoring`
namespace, consistent with VictoriaMetrics Operator conventions.

### Canary alert source

`deploy/alerts/canary.rules.yaml` in the mctl-telegram application repository
(`mctlhq/mctl-telegram`) defines three alert expressions:

| Alert | Expression | For |
|---|---|---|
| `MctlTelegramCanaryFailing` | `max_over_time(mctl_telegram_canary_success[10m]) == 0` | 5m |
| `MctlTelegramCanaryStale` | `time() - push_time_seconds{job="mctl_telegram_canary"} > 600` | 5m |
| `MctlTelegramCanaryAbsent` | `absent_over_time(mctl_telegram_canary_success[15m])` | 0m |

This file uses `monitoring.coreos.com/v1 PrometheusRule` with `prometheus:
kube-prometheus` labels. It has never been applied to the cluster and is not referenced
by any ArgoCD Application or Kustomize path.

### base-service Helm chart

The `base-service` chart
(`platform-gitops/helm-charts/base-service/`) is the universal Helm chart used by all
backend services including mctl-telegram. Its template directory contains:

- `extra-objects.yaml` — renders every element of `.Values.extraObjects` as a raw
  manifest using `tpl (toYaml $obj) $`:
  ```
  {{- range $obj := .Values.extraObjects }}
  ---
  {{ tpl (toYaml $obj) $ }}
  {{- end }}
  ```
- `servicemonitor.yaml` — conditional ServiceMonitor controlled by
  `.Values.metrics.enabled`.
- No `prometheusrule.yaml` or `vmrule.yaml` template exists.

Two other services already use `extraObjects` in their values files:

- `platform-gitops/services/labs/openclaw/values.yaml` — adds a second ServiceMonitor.
- `platform-gitops/services/labs/trading-data/values.yaml` — adds a NetworkPolicy.

### mctl-telegram gitops values

`platform-gitops/services/labs/mctl-telegram/values.yaml` does not contain an
`extraObjects` key and has no alert rule wiring.

## Proposed solution

### Phase 1 (this issue): add a VMRule manifest to vm-rules/

Add a new file `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-canary-alerts.yaml`
in the `mctl-gitops` repository, following the format and conventions of the existing
`mctl-telegram-alerts.yaml` in the same directory.

```yaml
# Alert rules for the mctl-telegram synthetic canary.
# Canary CronJob: deploy/canary/cronjob.yaml (namespace: labs, schedule: */2 * * * *)
# Metrics are pushed to Pushgateway by cmd/canary after every run.
# Runbook: https://github.com/mctlhq/mctl-telegram/blob/main/docs/runbooks/canary.md
apiVersion: operator.victoriametrics.com/v1beta1
kind: VMRule
metadata:
  name: mctl-telegram-canary
  namespace: monitoring
  labels:
    app.kubernetes.io/part-of: mctl-platform
    app.kubernetes.io/component: mctl-telegram
spec:
  groups:
    - name: mctl-telegram-canary
      interval: 60s
      rules:
        - alert: MctlTelegramCanaryFailing
          expr: max_over_time(mctl_telegram_canary_success[10m]) == 0
          for: 5m
          labels:
            severity: critical
            service: mctl-telegram
          annotations:
            summary: "mctl-telegram canary probe has been failing for ~15 minutes"
            description: >
              The synthetic end-to-end canary for mctl-telegram has reported
              mctl_telegram_canary_success=0 for every run in the last 10 minutes,
              and the condition has persisted for at least 5 more minutes (~15 minutes
              of continuous failure total). Check mctl_telegram_canary_step_failure_total
              to identify which probe step is failing.
              Runbook: https://github.com/mctlhq/mctl-telegram/blob/main/docs/runbooks/canary.md

        - alert: MctlTelegramCanaryStale
          expr: time() - push_time_seconds{job="mctl_telegram_canary"} > 600
          for: 5m
          labels:
            severity: warning
            service: mctl-telegram
          annotations:
            summary: "mctl-telegram canary has not pushed metrics in 10 minutes"
            description: >
              The canary CronJob has not successfully pushed metrics to Pushgateway in
              the last 10 minutes (schedule is */2 * * * *). The CronJob may be failing
              to start or complete. Check pod logs and CronJob status in the labs
              namespace.
              Runbook: https://github.com/mctlhq/mctl-telegram/blob/main/docs/runbooks/canary.md

        - alert: MctlTelegramCanaryAbsent
          expr: absent_over_time(mctl_telegram_canary_success[15m])
          for: 0m
          labels:
            severity: warning
            service: mctl-telegram
          annotations:
            summary: "mctl-telegram canary metrics absent for 15 minutes"
            description: >
              No mctl_telegram_canary_success samples have arrived in the last 15
              minutes. Pushgateway may be down or the metric group was deleted. Check
              Pushgateway health and CronJob pod logs.
              Runbook: https://github.com/mctlhq/mctl-telegram/blob/main/docs/runbooks/canary.md
```

This file is picked up automatically by the existing ArgoCD `monitoring` Application
source; no ArgoCD Application change is required. With `syncPolicy.automated.prune:
true` and `selfHeal: true`, the VMRule will appear in the cluster within one ArgoCD
sync cycle after the PR merges to `main`.

**Why not use `extraObjects` in `values.yaml`?**

The `extraObjects` path ties the alert rule lifecycle to the Helm release of the
mctl-telegram service. If the chart is rolled back (e.g. via the `wft-rollback-service`
Argo Workflow template), the alert rule would also be rolled back or potentially pruned.
Alert rules are infrastructure concerns that should outlive any single service release.
Co-locating with other `vm-rules/` manifests keeps all alerting definitions in one
discoverable location and follows the pattern already established for mctl-telegram
alerts.

**Why not use PrometheusRule?**

The cluster's `prometheus.enabled: false` means no Prometheus instance evaluates
`monitoring.coreos.com/v1 PrometheusRule` resources. The VictoriaMetrics Operator CAN
be configured to convert PrometheusRules to VMRules, but that conversion is not
confirmed to be active in this cluster (the monitoring.yaml does not set
`victoriametricsOperator.enabledPrometheusConverter: true`). All existing alert
deployments use `VMRule` directly; this proposal follows that established pattern.

### Phase 2 (follow-on): `prometheusrule.yaml` template in base-service

As a separate, lower-priority improvement, add a `vmrule.yaml` (or `prometheusrule.yaml`
if the operator conversion is confirmed) template to the `base-service` chart:

```yaml
{{- if .Values.alertRules.enabled }}
apiVersion: operator.victoriametrics.com/v1beta1
kind: VMRule
metadata:
  name: {{ include "base-service.fullname" . }}
  namespace: monitoring
  labels:
    {{- include "base-service.labels" . | nindent 4 }}
spec:
  groups:
    {{- toYaml .Values.alertRules.groups | nindent 4 }}
{{- end }}
```

With a default values entry of `alertRules: { enabled: false, groups: [] }`. Any service
could then opt in by adding `alertRules.enabled: true` and providing rule groups in its
own values file. This is strictly out of scope for issue #213 and should be its own PR.

## Alternatives

### A: Add the alert rule as `extraObjects` in mctl-telegram's values.yaml

The `base-service` chart's `extra-objects.yaml` template already supports arbitrary
objects. The canary VMRule could be inlined as an entry in
`platform-gitops/services/labs/mctl-telegram/values.yaml`. This works and requires
touching only one file, but it has two drawbacks: (1) the alert rule is coupled to the
Helm release lifecycle, (2) it creates an inconsistency with the existing pattern where
all alert rules live in `vm-rules/`. **Dropped** in favour of the `vm-rules/` path.

### B: Deploy the PrometheusRule from the app repo via Kustomize

The issue mentions referencing `deploy/alerts/canary.rules.yaml` inline via a Kustomize
patch in the gitops values. This would require either a Kustomize Application pointing
at the app repo or an inline raw manifest in the values. The file is in `PrometheusRule`
format (wrong CRD for this cluster), and adding a cross-repo Kustomize dependency
introduces a fragile reference to a specific git revision of the app repo.
**Dropped** because it adds complexity and the CRD format is wrong.

### C: Update the Alertmanager routing config to add explicit canary routes

The issue requires the alerts to reach Telegram via mctl-agent. The current Alertmanager
root route already sends all unmatched alerts to `mctl-agent`. No routing change is
needed. Adding explicit routes for the canary alerts would add maintenance burden without
benefit. **Dropped** as unnecessary.

## Platform impact

- **Migrations**: none. The VMRule is a new object; no existing resource is modified.
- **Backward compatibility**: no service code change; no chart version bump required.
  The VMRule is invisible until it starts firing.
- **Resource impact**: VMAlert evaluates the three new rules every 60 seconds. Three
  additional PromQL evaluations per minute have negligible impact on VMSingle or VMAlert
  resource consumption.
- **Risk**: if the `push_time_seconds{job="mctl_telegram_canary"}` job label does not
  match the actual label the canary binary uses when pushing to Pushgateway,
  `MctlTelegramCanaryStale` will either never fire (label mismatch) or always fire
  (Pushgateway not targeted). Verify the label before merging.
- **Rollback**: delete the VMRule manifest from `vm-rules/` and merge. ArgoCD
  (prune: true) will remove the resource from the cluster on the next sync.
