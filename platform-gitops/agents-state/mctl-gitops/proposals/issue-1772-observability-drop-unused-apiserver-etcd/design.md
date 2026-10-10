# Design: issue-1772-observability-drop-unused-apiserver-etcd

## Current state

- `platform-gitops/bootstrap/templates/observability/monitoring.yaml` defines the
  `monitoring` ArgoCD Application from chart `victoria-metrics-k8s-stack`
  `0.72.5`. vmagent scrapes (`selectAllByDefault: true`, `scrapeInterval: 1m`)
  and remote-writes to vmsingle (`retentionPeriod: 28d`, memory limit `2Gi`,
  request `1400Mi`).
- The values set no `kubeApiServer` block, so the chart default applies (chart
  `values.yaml`, `kubeApiServer:`). That default is `enabled: true` and one
  VMServiceScrape endpoint with `port: https`, `scheme: https`,
  `bearerTokenFile: /var/run/secrets/kubernetes.io/serviceaccount/token` and
  `tlsConfig {caFile: .../ca.crt, serverName: kubernetes}`, plus
  `jobLabel: component`, `namespaceSelector: default` and the selector
  `component: apiserver, provider: kubernetes`. The resulting `job` label is
  `apiserver`. No `metricRelabelConfigs` are set.
- `kubeEtcd`, `kubeScheduler` and `kubeControllerManager` are `enabled: false`.
  `defaultRules.groups.etcd`, `kubeScheduler`, `kubernetesSystemScheduler` and
  `kubernetesSystemControllerManager` have `create: false`. Every `etcd_*`
  series in vmsingle therefore comes from the apiserver scrape: its storage
  client (`etcd_request_duration_seconds`, `etcd_bookmark_counts`, ...) and,
  on k3s with embedded etcd, any etcd server metrics k3s exposes there.
- Consumers of apiserver/etcd metrics. I grepped the repo and the chart
  tarball 0.72.5 (`files/rules/generated/*`, `files/dashboards/generated/*`).
  - Repo `vm-rules/` (21 VMRule files) and `grafana-dashboards/` (10
    ConfigMaps, including the patched `k8s-views-global`): **no** reference to
    any `apiserver_*` or `etcd_*` metric.
  - Chart default rules that are enabled:
    - `kube-apiserver-burnrate.rules` and `kube-apiserver-availability.rules`
      read `apiserver_request_sli_duration_seconds_bucket`, `..._count` and
      `apiserver_request_total`.
    - `kube-apiserver-histogram.rules` reads
      `apiserver_request_sli_duration_seconds_bucket`.
    - `kube-apiserver-slos` (`KubeAPIErrorBudgetBurn`) reads the
      `apiserver_request:burnrate*` records above.
    - `kubernetes-system-apiserver` reads
      `apiserver_client_certificate_expiration_seconds_bucket`/`_count`
      (`KubeClientCertificateExpiration`),
      `aggregator_unavailable_apiservice[_total]`,
      `apiserver_request_terminations_total`, `apiserver_request_total` and
      `up{job="apiserver"}`.
  - Chart default rules that are disabled: the `etcd` group (it would read
    `etcd_disk_wal_fsync_duration_seconds_bucket`,
    `etcd_disk_backend_commit_duration_seconds_bucket` and
    `etcd_network_peer_round_trip_time_seconds_bucket`). It is not rendered.
  - Chart dashboards:
    - `kubernetes-system-api-server` (condition `kubeApiServer.enabled`,
      rendered) reads only `apiserver_request_duration_seconds_count`/`_sum`,
      `apiserver_request_total` and `apiserver_requested_deprecated_apis`.
      There are **no bucket series**.
    - `etcd` (condition `kubeEtcd.enabled`) is not rendered.
- Conclusion: of all apiserver/etcd `_bucket` metrics, only
  `apiserver_request_sli_duration_seconds_bucket` and
  `apiserver_client_certificate_expiration_seconds_bucket` are read.
- CI: `.github/workflows/validate-manifests.yml` renders
  `platform-gitops/bootstrap` with `helm template` and runs
  `scripts/check-vm-rules.sh` (promtool check/test over `vm-rules/`).

## Proposed solution

### 1. Enumerate and measure (read-only, before editing)
Run these queries against vmsingle (port-forward to
`vmsingle-monitoring-victoria-metrics-k8s-stack.monitoring:8428`, GET only):
- `GET /api/v1/label/__name__/values?match[]={job="apiserver",__name__=~"(apiserver|etcd)_.+_bucket"}`
  gives the candidate names.
- `GET /api/v1/status/tsdb?topN=200&match[]={job="apiserver"}` gives the
  per-metric `seriesCountByMetricName` and the total. Also run the unfiltered
  call for the cluster total (about 499k).
- Drop list = candidates minus the keep set
  {`apiserver_request_sli_duration_seconds_bucket`,
  `apiserver_client_certificate_expiration_seconds_bucket`}.
- Expected reduction = sum of the drop-list series counts.

The expected baseline drop list, to be confirmed against the live output
(names absent from the live output are omitted, live names not listed here
are added):
`apiserver_request_duration_seconds_bucket`,
`apiserver_response_sizes_bucket`,
`apiserver_request_body_size_bytes_bucket`,
`apiserver_watch_events_sizes_bucket`,
`apiserver_watch_list_duration_seconds_bucket`,
`apiserver_watch_cache_read_wait_seconds_bucket`,
`apiserver_admission_controller_admission_duration_seconds_bucket`,
`apiserver_admission_step_admission_duration_seconds_bucket`,
`apiserver_admission_webhook_admission_duration_seconds_bucket`,
`apiserver_flowcontrol_request_wait_duration_seconds_bucket`,
`apiserver_flowcontrol_request_execution_seconds_bucket`,
`apiserver_flowcontrol_work_estimated_seats_bucket`,
`apiserver_flowcontrol_priority_level_seat_utilization_bucket`,
`apiserver_flowcontrol_priority_level_request_utilization_bucket`,
`apiserver_flowcontrol_read_vs_write_current_requests_bucket`,
`apiserver_flowcontrol_demand_seats_bucket`,
`apiserver_crd_conversion_webhook_duration_seconds_bucket`,
`apiserver_storage_list_*`-family buckets if present,
`etcd_request_duration_seconds_bucket`,
`etcd_request_objects_size_bytes_bucket`-style storage-client buckets if present,
and any `etcd_disk_*`/`etcd_network_*` buckets k3s exposes on this job.
`_count`/`_sum` series are not touched.

### 2. Values change in `monitoring.yaml`
Add a `kubeApiServer` block next to `kubeControllerManager`/`kubeEtcd` in the
chart values:

```yaml
kubeApiServer:
  enabled: true
  vmScrape:
    spec:
      endpoints:
        # Helm replaces lists wholesale: this entry restates the chart default
        # endpoint (chart 0.72.5 values.yaml) and only adds metricRelabelConfigs.
        - bearerTokenFile: /var/run/secrets/kubernetes.io/serviceaccount/token
          port: https
          scheme: https
          tlsConfig:
            caFile: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
            serverName: kubernetes
          metricRelabelConfigs:
            # Explicit names only, never a pattern -- see comment block.
            - action: drop
              source_labels: [__name__]
              regex:
                - apiserver_request_duration_seconds_bucket
                - apiserver_response_sizes_bucket
                - etcd_request_duration_seconds_bucket
                # ... rest of the measured list
```

- The comment above the list records three things: the measured series count
  and date, the KEEP set and the rule that needs each kept metric, and a note
  that a dashboard or rule which starts using a dropped metric must remove it
  from this list.
- `regex` as a YAML list is the VictoriaMetrics relabeling extension: the
  entries are OR-ed and each one is fully anchored. The VMServiceScrape CRD
  types `regex` as `StringOrArray`. If the rendered VMServiceScrape or the
  operator rejects it, fall back to one anchored alternation string,
  `regex: "(name1|name2|...)"`. Relabel regexes are already anchored, so an
  exact name still matches only itself.
- Use `source_labels` (the VM operator field name), not Prometheus
  `sourceLabels`. Match the field name the operator CRD in this cluster
  accepts, and confirm it in the rendered manifest.
- Dropping at vmagent (scrape-time relabel) means the series are never sent
  to vmsingle. There is no change to remote write, vmsingle flags or
  retention.

### 3. CI guard: `scripts/check-dropped-metrics.sh`
- A small script, wired into `validate-manifests.yml` next to
  `check-vm-rules.sh`.
- It extracts the drop list from the rendered bootstrap output: the
  `monitoring` Application's helm values, `kubeApiServer` endpoints,
  `metricRelabelConfigs` with `action: drop`.
- It fails if any listed name appears in
  `platform-gitops/infra-components/observability/vm-rules/*.yaml` or
  `.../grafana-dashboards/*.yaml`.
- It has a `--selftest` that uses a fixture to prove it fails, following the
  `check-vm-rules.sh` convention.
- This satisfies "a future dashboard does not lose data silently" for
  everything in this repo. The chart's own rules are covered by the
  PR-time verification below, and again on every chart bump: the chart
  version is pinned, so default rules only change through a reviewed PR.

### 4. Rule-input verification (in the PR description)
Render the chart's default rules once (`helm template` of
victoria-metrics-k8s-stack 0.72.5 with the monitoring values) and grep every
`expr` for `apiserver_`/`etcd_`/`aggregator_`. Then show a table of rule →
metrics referenced → kept? (yes for all). The expected table:

| Rule / group | Inputs | Status |
|---|---|---|
| kube-apiserver-burnrate.rules (`apiserver_request:burnrate*`) | `apiserver_request_sli_duration_seconds_bucket`, `_count`, `apiserver_request_total` | kept |
| kube-apiserver-availability.rules | same plus records | kept |
| kube-apiserver-histogram.rules | `apiserver_request_sli_duration_seconds_bucket` | kept |
| kube-apiserver-slos (`KubeAPIErrorBudgetBurn`) | `apiserver_request:burnrate*` | kept (records) |
| kubernetes-system-apiserver (`KubeClientCertificateExpiration`) | `apiserver_client_certificate_expiration_seconds_bucket`, `_count` | kept |
| kubernetes-system-apiserver (`KubeAggregatedAPIErrors/Down`, `KubeAPIDown`, `KubeAPITerminatedRequests`) | `aggregator_unavailable_apiservice[_total]`, `up`, `apiserver_request_terminations_total`, `apiserver_request_total` | not buckets, untouched |
| etcd group | etcd_disk/network buckets | group disabled (`create: false`), not evaluated |
| repo vm-rules | none | n/a |

## Alternatives

1. **Broad regex `(apiserver|etcd)_.+_bucket` with a keep-exception.**
   Smallest diff and auto-covers new metrics after Kubernetes upgrades.
   Rejected because the issue explicitly prefers explicit names: any new
   consumer would silently get no data.
2. **Global drop in vmagent (`inlineRelabelConfig`/`-remoteWrite.relabelConfig`) or in vmsingle (`-relabelConfig`).**
   This applies to every job, which is a larger blast radius, and it hides
   the drop away from the scrape it concerns. Rejected. The per-scrape
   `metricRelabelConfigs` is what the issue asks for and is self-documenting.
3. **Stream aggregation / downsampling instead of dropping.**
   This keeps some histogram value, but it costs vmagent CPU (already raised
   to 500m after throttling) and adds complexity for data nobody reads.
   Rejected. A future need can re-add a specific metric.
4. **Disable the `kubeApiServer` scrape entirely.**
   Rejected: it would break `KubeAPIErrorBudgetBurn`, `KubeAPIDown` and the
   other alerts in the table above.

## Platform impact
- **Resources:** the expected cut is in the order of the measured drop-list
  total. The upper bound is ~110k of ~499k active series. The realistic
  figure is that bound minus the kept `apiserver_request_sli_duration_seconds_bucket`
  series, which is one of the largest families, so the cut may be well below
  110k. The PR states the measured number.
  - vmsingle memory falls once dropped series leave the hourly/daily active
    index caches (about 1h for the hour cache, up to a day for per-day
    indexes). That is a gradual drop, not an instant one.
  - vmagent also does slightly less remote-write work. Scrape parsing work is
    unchanged.
- **Backward compatibility:** historical samples of dropped metrics remain
  queryable until they age out of the 28d retention. Ad-hoc Explore queries
  on them return data only up to the rollout.
- **Migration:** none. ArgoCD syncs the updated VMServiceScrape and the
  operator reconciles the vmagent scrape config.
- **Risks and mitigations:**
  - Restating the endpoint wrongly (Helm list replacement) breaks the
    apiserver scrape and fires `KubeAPIDown`. Mitigations: diff the rendered
    VMServiceScrape against the chart default in the PR, and check
    `up{job="apiserver"} == 1` after sync.
  - A relabel field-name or `regex`-list type mismatch with the operator
    CRD. The ArgoCD sync fails or the field is ignored. Mitigations: validate
    the rendered manifest against the CRD, and check
    `count({__name__="apiserver_request_duration_seconds_bucket"})` → 0 after
    about 2 scrape intervals.
  - A kept metric dropped by mistake. Mitigations: the explicit list, the
    post-deploy check that `apiserver_request:burnrate1h` and
    `cluster_quantile:apiserver_request_sli_duration_seconds:histogram_quantile`
    are non-empty, and the CI guard for repo consumers.
  - A future chart bump adds a default rule on a dropped metric. Mitigation:
    the keep/drop comment instructs chart-bump PRs to re-run the step 4 grep.
