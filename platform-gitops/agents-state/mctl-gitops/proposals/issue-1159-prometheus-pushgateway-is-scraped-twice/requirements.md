# Remove the duplicate pushgateway scrape (VMPodScrape), keep the VMServiceScrape

## Context

`prometheus-pushgateway` in the `monitoring` namespace is discovered by two
independent VictoriaMetrics scrape objects that target the same container port
on the same pod: the `VMServiceScrape` in
`platform-gitops/infra-components/observability/pushgateway/servicescrape.yaml`
(via the labelled Service and its named port `http`) and the `VMPodScrape` in
`platform-gitops/infra-components/observability/vm-rules/pushgateway-podscrape.yaml`
(via `targetPort: 9091` on the pod, `interval: 30s`). Both are `up`, both set
`honorLabels: true`, so every metric pushed to the gateway lands in
VictoriaMetrics as two series that differ only in the scrape-derived `endpoint`
label (`"http"` vs `"9091"`) plus a `service` label on the serviceScrape copy.

The duplication is not cosmetic. None of the alert expressions on pushed
metrics aggregate, so each one matches both series and produces two identical
alerts, notifications and incidents for a single fact:
`VictoriaMetricsBackupStale` and `VictoriaMetricsBackupMetricAbsent` in
`vm-rules/backup-alerts.yaml`, and `MctlTelegramCanaryStale`,
`MctlTelegramCanaryTokenExpiring` and `MctlTelegramCanaryTokenRenewalFailing`
in `vm-rules/mctl-telegram-canary.yaml` (all of these route to the `mctl-agent`
receiver per `bootstrap/templates/observability/monitoring.yaml`, so each
duplicate becomes a second incident). It also doubles the sample count for
everything that goes through the gateway and spends a redundant scrape every
30s. The podScrape's own header explains it was added on 2026-06-26 to work
around a *live* Service that carried no labels and no named port; the
gitops-managed Service in `pushgateway/pushgateway.yaml` now carries both, so
the condition the workaround exists for no longer holds.

## User stories

- AS an on-call operator I WANT one alert per underlying fact SO THAT a stale
  backup or a stalled canary does not generate two notifications and two
  incidents that must each be triaged and closed.
- AS a platform engineer I WANT exactly one scrape object per target SO THAT
  the series count, sample rate and scrape cost of pushed metrics are what the
  configuration says they are.
- AS the next engineer touching pushgateway scraping I WANT the history of why
  a pod-level scrape was once needed recorded in the surviving file SO THAT I
  do not re-add a second scrape for a problem that is already fixed.

## Acceptance criteria (EARS)

- WHEN the change is merged and ArgoCD has synced the `monitoring`
  Application THE SYSTEM SHALL expose exactly one pushgateway scrape pool in
  vmagent's `/api/v1/targets`, namely
  `serviceScrape/monitoring/prometheus-pushgateway/0`, and its target SHALL be
  `up`.
- WHEN the change is merged THE SYSTEM SHALL no longer contain
  `platform-gitops/infra-components/observability/vm-rules/pushgateway-podscrape.yaml`,
  and ArgoCD (whose `monitoring` Application sets `syncPolicy.automated.prune:
  true`) SHALL prune the live `VMPodScrape/monitoring/prometheus-pushgateway`.
- WHILE only the `VMServiceScrape` remains THE SYSTEM SHALL keep
  `honorLabels: true` on it, so that labels pushed to the gateway
  (`job="mctl_telegram_canary"`, `job="vmbackup"`) survive the scrape and
  `push_time_seconds{job="mctl_telegram_canary"}` and
  `vmbackup_last_success_timestamp_seconds{job="vmbackup"}` still exist.
- WHEN a metric is pushed to the gateway after the change THE SYSTEM SHALL
  store it as a single series: `count by (__name__) (mctl_telegram_canary_success)`
  and `count by (__name__) (vmbackup_last_success_timestamp_seconds)` SHALL
  each evaluate to `1`.
- WHILE only the `VMServiceScrape` remains THE SYSTEM SHALL scrape the gateway
  at the vmagent-wide default `scrapeInterval: 1m`
  (`bootstrap/templates/observability/monitoring.yaml`), which stays far inside
  every consuming rule's tolerance (`> 1500` for `MctlTelegramCanaryStale`,
  `> 90000` for `VictoriaMetricsBackupStale`, `[25m]`/`[30m]` lookback windows
  on the canary's `max_over_time`/`absent_over_time` rules).
- WHEN the change is merged THE SYSTEM SHALL carry the load-bearing history
  from the deleted podScrape header (why a pod-level scrape was once needed,
  why `honorLabels` must stay, and that a second scrape must not be re-added)
  into `pushgateway/servicescrape.yaml`.
- IF vmalert is inspected after the sync THEN the alerts
  `MctlTelegramCanaryStale`, `MctlTelegramCanaryAbsent` and
  `VictoriaMetricsBackupStale` SHALL remain `inactive`/ok, i.e. removing the
  duplicate scrape SHALL NOT itself trigger a staleness or absence alert.
- IF a future change places a non-`VMRule` object under
  `infra-components/observability/vm-rules/` THEN `scripts/check-vm-rules.sh`
  SHALL fail rather than print `skip (kind=...)` and pass, so a scrape object
  cannot again hide unnoticed in a directory of alerting rules.
- WHEN CI runs on the pull request THE SYSTEM SHALL keep
  `.github/workflows/validate-manifests.yml` green (kubeconform over
  `platform-gitops/infra-components`, plus `scripts/check-vm-rules.sh`).

## Out of scope

- Aggregating the affected alert expressions (`max by (job, instance) (...)`)
  as a workaround. That hides the duplication rather than removing it and
  would have to be repeated in every future rule over a pushed metric.
- Any change to the alert thresholds, `for:` durations or routing in
  `vm-rules/backup-alerts.yaml` and `vm-rules/mctl-telegram-canary.yaml`.
- Any change to the pushgateway Deployment/Service itself
  (`pushgateway/pushgateway.yaml`), to the vmbackup sidecar, or to the
  mctl-telegram canary CronJob that pushes to the gateway.
- Deleting the already-duplicated historical samples from VictoriaMetrics.
  They age out with normal retention; the fix is forward-looking.
- Introducing a generic "two scrapes select the same pod" detector across the
  whole repo. The narrower `vm-rules/` kind check is what this proposal adds.

## Open questions

- Scrape interval: the podScrape scraped every 30s, the surviving
  serviceScrape inherits vmagent's 1m default. This proposal deliberately does
  NOT pin `interval: 30s` on the serviceScrape — the gateway's producers push
  every 10 minutes (canary) and daily (vmbackup), and every consuming rule
  tolerates minutes-to-hours. If a reviewer wants the previous resolution kept
  verbatim, adding `interval: 30s` to the single endpoint is a one-line
  amendment that does not otherwise change this proposal.
- Turning the `vm-rules/` non-`VMRule` skip into a hard failure changes CI
  behaviour for everyone. It is safe today (after the deletion, every file in
  that directory is a `VMRule`), but a reviewer may prefer to land it as a
  separate follow-up commit. Proceeding with it included, as one commit in the
  same PR, because it is the only thing that prevents an exact recurrence.
