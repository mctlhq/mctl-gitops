# Tasks: issue-1772-observability-drop-unused-apiserver-etcd

- [ ] 1. Measure the current state on vmsingle using GET-only queries via port-forward to `vmsingle-monitoring-victoria-metrics-k8s-stack.monitoring:8428`. Run `/api/v1/status/tsdb` (unfiltered and with `match[]={job="apiserver"}`, `topN=200`) and `/api/v1/label/__name__/values?match[]={job="apiserver",__name__=~"(apiserver|etcd)_.+_bucket"}`. — DoD: a table of every apiserver/etcd `_bucket` metric name with its series count, plus the total active series count, saved for the PR description.
- [ ] 2. Confirm the keep set against the chart's default rules and dashboards (depends on 1). Render `victoria-metrics-k8s-stack` 0.72.5 with the `monitoring.yaml` values and grep every rendered VMRule `expr` and dashboard target for `apiserver_|etcd_|aggregator_`. Re-grep `platform-gitops/infra-components/observability/vm-rules/` and `grafana-dashboards/`. — DoD: keep set confirmed as `apiserver_request_sli_duration_seconds_bucket` and `apiserver_client_certificate_expiration_seconds_bucket` (plus non-bucket inputs, which are untouched), or the change is recorded if the render differs. The drop list = measured names minus the keep set.
- [ ] 3. Add a `kubeApiServer` block to the chart values in `platform-gitops/bootstrap/templates/observability/monitoring.yaml` (depends on 2). Restate the chart-default endpoint (`bearerTokenFile`, `port: https`, `scheme: https`, `tlsConfig.caFile`, `tlsConfig.serverName: kubernetes`) and add `metricRelabelConfigs` with one `action: drop` on `__name__`, using an explicit name list. Add the comment block covering the measurement date and counts, the keep set with the rule that needs each kept metric, and the instruction for future consumers and chart bumps. — DoD: `helm template test platform-gitops/bootstrap -f platform-gitops/bootstrap/values.yaml` renders, and the rendered k8s-stack VMServiceScrape for kube-apiserver differs from the chart default only by `metricRelabelConfigs`.
- [ ] 4. Add `scripts/check-dropped-metrics.sh` with `--selftest`, and wire it into `.github/workflows/validate-manifests.yml` next to `scripts/check-vm-rules.sh` (depends on 3). It extracts the drop list from `monitoring.yaml` and fails if any name occurs in `vm-rules/*.yaml` or `grafana-dashboards/*.yaml`. — DoD: the script passes on the branch, `--selftest` proves it fails on a fixture that references a dropped name, and the CI job runs it.
- [ ] 5. Write the PR description (depends on 1-4). — DoD: it contains:
  - the per-metric drop table with series counts
  - the expected total reduction as an absolute figure and as a percentage of current active series
  - the list of deliberately kept metrics with reasons
  - the rule-input table showing every enabled rule that references an apiserver/etcd/aggregator metric still has its input
  - a note that `apiserver_request_sli_duration_seconds_bucket` was kept despite being named in the issue
- [ ] 6. Post-merge verification after ArgoCD sync and about 1h (depends on 5). — DoD:
  - `up{job="apiserver"}` is 1
  - `count({__name__=~"<drop list>"})` returns no data for fresh samples
  - `apiserver_request:burnrate1h`, `apiserver_request:burnrate5m` and `cluster_quantile:apiserver_request_sli_duration_seconds:histogram_quantile` are non-empty
  - no `KubeAPIDown`, `RecordingRulesNoData` or vmalert rule-error alerts fire
  - the reduction in active series and the vmsingle working set are recorded as a comment on the issue

## Tests
- [ ] T1. `helm lint` / `helm template` of `platform-gitops/bootstrap` succeed, and `validate-manifests.yml` passes.
- [ ] T2. Diff the rendered VMServiceScrape `monitoring-victoria-metrics-k8s-stack-kube-api-server` (name as rendered) before and after. The only delta is `endpoints[0].metricRelabelConfigs`.
- [ ] T3. `scripts/check-dropped-metrics.sh --selftest` fails on its fixture, and `scripts/check-dropped-metrics.sh` passes on the repo.
- [ ] T4. Run a static check that no drop-list name equals a keep-set name, and that no list entry contains regex metacharacters other than literal underscores and letters (explicit names only).
- [ ] T5. Post-deploy queries from task 6 (live, read-only).

## Rollback
Revert the PR commit that added the `kubeApiServer` block. ArgoCD restores the
chart-default VMServiceScrape and the bucket series resume on the next scrape.
The gap only covers the time the drop was active, and older data stays
queryable within the 28d retention. If the restated endpoint broke the scrape
(`KubeAPIDown`), the revert is urgent, and an ArgoCD sync of `monitoring`
applies it within one reconcile cycle. No data migration or vmsingle restart
is needed.
