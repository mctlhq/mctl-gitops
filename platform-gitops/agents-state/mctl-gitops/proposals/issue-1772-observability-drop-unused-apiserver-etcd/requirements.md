# Drop unused apiserver/etcd histogram bucket series at the apiserver scrape

## Context
vmsingle is the only metrics and alert-evaluation store on the platform and runs
close to its memory limit (about 1657Mi of the 2Gi limit set in
`platform-gitops/bootstrap/templates/observability/monitoring.yaml`, audit
findings OBS-N104 and OPS-105). The 2026-10-10 audit snapshot shows about 499k
active series. Roughly 110k (22%) are `apiserver_*_bucket` / `etcd_*_bucket`
histogram series from the kube-apiserver scrape. The `kubeApiServer` scrape of
the `victoria-metrics-k8s-stack` chart (0.72.5) is enabled by default and has no
`metricRelabelConfigs` in this repo, so vmagent ships every apiserver series
to vmsingle.

The investigation found that no VMRule under
`platform-gitops/infra-components/observability/vm-rules/` and no dashboard
under `platform-gitops/infra-components/observability/grafana-dashboards/`
references any `apiserver_*` or `etcd_*` metric. The only consumers are the
chart's built-in rule groups and dashboards. Two bucket metrics are in use
there and must be kept:
- `apiserver_request_sli_duration_seconds_bucket`, used by
  `kube-apiserver-burnrate.rules`, `kube-apiserver-availability.rules` and
  `kube-apiserver-histogram.rules`. `KubeAPIErrorBudgetBurn` depends on these
  rules. The issue listed this metric as a drop example, but that is wrong.
- `apiserver_client_certificate_expiration_seconds_bucket`, used by
  `KubeClientCertificateExpiration` in `kubernetes-system-apiserver`.

Every other apiserver/etcd `_bucket` metric is unused and can be dropped by
explicit name. That includes `apiserver_request_duration_seconds_bucket`,
`apiserver_response_sizes_bucket` and `etcd_request_duration_seconds_bucket`.

## User stories
- AS a platform operator I WANT vmsingle to stop ingesting histogram buckets nobody reads SO THAT its memory working set moves away from the 2Gi limit without raising the limit.
- AS an on-call engineer I WANT every apiserver/etcd alert and recording rule to keep its input series SO THAT cutting cardinality does not silently disable an alert.
- AS a dashboard author I WANT the drop list to be an explicit list of metric names SO THAT a metric I start using later is not lost to a broad regex without anyone noticing.

## Acceptance criteria (EARS)
- WHEN vmagent scrapes the kube-apiserver through the `kubeApiServer` VMServiceScrape THE SYSTEM SHALL drop, with `action: drop` in `metricRelabelConfigs`, exactly the metric names on the committed explicit drop list.
- THE SYSTEM SHALL express the drop list as literal metric names, with no wildcard such as `apiserver_.*_bucket`.
- WHILE the drop is active THE SYSTEM SHALL keep ingesting `apiserver_request_sli_duration_seconds_bucket`, `apiserver_request_sli_duration_seconds_count`, `apiserver_client_certificate_expiration_seconds_bucket`, `apiserver_client_certificate_expiration_seconds_count`, `apiserver_request_total`, `apiserver_request_terminations_total`, `apiserver_request_duration_seconds_count`, `apiserver_request_duration_seconds_sum`, `apiserver_requested_deprecated_apis`, `aggregator_unavailable_apiservice_total`, `aggregator_unavailable_apiservice` and `up{job="apiserver"}`.
- WHILE the drop is active THE SYSTEM SHALL keep producing the recording rules `apiserver_request:burnrate{5m,30m,1h,2h,6h,1d,3d}`, `apiserver_request:availability30d` (and the other availability records) and `cluster_quantile:apiserver_request_sli_duration_seconds:histogram_quantile` with non-empty results.
- WHEN the change is rendered (`helm template` of `platform-gitops/bootstrap`) THE SYSTEM SHALL keep the existing apiserver endpoint settings: `port: https`, `scheme: https`, `bearerTokenFile`, and `tlsConfig.caFile`/`serverName: kubernetes`. Helm replaces lists, so overriding `endpoints` restates the whole entry.
- IF a metric on the drop list is referenced by any VMRule in `vm-rules/` or any dashboard ConfigMap in `grafana-dashboards/` THEN CI SHALL fail and name the metric and the referencing file.
- WHEN the PR is opened THE SYSTEM SHALL document the following:
  - the per-metric series counts and the expected total reduction, taken from read-only vmsingle `/api/v1/status/tsdb` and `/api/v1/series/count`-style queries
  - the list of deliberately kept metrics and why each is kept
  - a rule-by-rule table showing that every enabled rule that references an apiserver/etcd metric still has its input
- WHEN about 1h has passed after rollout THE SYSTEM SHALL show a lower vmsingle active series count (`vm_cache_entries{type="storage/hour_metric_ids"}` or `/api/v1/status/tsdb` `totalSeries`), consistent with the documented estimate.

## Out of scope
- Raising the vmsingle memory limit or request, or adding a liveness probe (excluded by the issue).
- Dropping non-histogram apiserver series (counters, gauges), `_count`/`_sum` series, or series from other scrape jobs (kubelet, cAdvisor, node-exporter, kube-state-metrics).
- Re-enabling or changing `kubeEtcd`, `defaultRules.groups.etcd`, or the etcd dashboard (all disabled today).
- Deleting already-stored historical samples. They age out under the 28d retention.
- Upgrading the `victoria-metrics-k8s-stack` chart.

## Open questions
- The exact drop list depends on which bucket metrics the live k3s apiserver exposes, which varies by Kubernetes version and k3s embedded-etcd settings. The proposal requires the implementer to enumerate them from vmsingle (read-only) and commit the measured names. The design gives an expected baseline list. If live enumeration is not possible from the implementer's environment, the baseline list goes in and the PR states that the numbers are estimates.
- The issue names `apiserver_request_sli_duration_seconds_bucket` as a drop candidate, but the stack's enabled default rules (`KubeAPIErrorBudgetBurn` inputs) need it. This proposal keeps it, in line with issue point 1 ("keep anything used"). It is probably one of the larger contributors, so the achieved reduction may fall short of the full ~110k.
