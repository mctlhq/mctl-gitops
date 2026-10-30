# Design: issue-2264-feat-observability-deliver-the-gated-off

## Current state

**Slice 1 (#2250, open, not on `main`).** `gh pr view 2250` shows it is OPEN
and unmerged. It touches:
- `docs/adr/0002-log-backend.md` and `docs/adr/0002-rubric.yaml`;
- `tests/test_adr0002_rubric_frozen.py`, plus a CI step in
  `.github/workflows/validate-manifests.yml`;
- `scripts/validate-eval-teardown-date.py`, generalised to a `SANDBOXES`
  list that includes `(logsEval.enabled, logsEval.teardownAfter)`;
- `platform-gitops/bootstrap/values.yaml`, which gains:

```yaml
logsEval:
  enabled: false
  teardownAfter: ""
  quota: {requests.cpu: 500m, requests.memory: 1Gi, limits.cpu: "1",
          limits.memory: 2Gi, persistentvolumeclaims: "1", requests.storage: 20Gi}
  candidate:
    enabled: false
    repoURL: ""
    chart: ""
    targetRevision: ""
    values: {server: {retentionPeriod: 14d, serviceMonitor: {enabled: false}}}
```

The clone (`main` at a217936) has none of these, so this proposal builds on
#2250.

**Log path.** `platform-gitops/bootstrap/templates/observability/loki.yaml`
is the Application `loki-stack` (chart `loki-stack` 2.10.2, Loki
`grafana/loki:2.9.17`, R2 bucket `loki`, `retention_period: 336h`, Vault
audit `retention_stream` 720h). Its values are an inline `helm.values: |`
string inside a Helm template, so `{{ }}` directives inside that string are
evaluated by the bootstrap chart. Promtail has exactly one client:

```yaml
          config:
            clients:
              - url: http://loki-stack:3100/loki/api/v1/push
```

**Promtail metrics.** `promtail-podscrape.yaml` (VMPodScrape, port
`http-metrics`, `honorLabels: true`) scrapes Promtail's own `promtail_*`
series. Promtail's client metrics (`promtail_sent_entries_total`,
`promtail_dropped_entries_total`, `promtail_request_duration_seconds`) carry
a `host` label per client. Loki itself has no scrape: no `loki_*` series is
referenced anywhere under `infra-components/observability/`. A Loki
ingestion drop is therefore observable today only from the shipper side.

**Grafana.** `monitoring.yaml` (victoria-metrics-k8s-stack) sets
`GF_INSTALL_PLUGINS: victoriametrics-metrics-datasource` (line ~520). The
datasource sidecar picks up ConfigMaps labelled `grafana_datasource: "1"`
(e.g. `loki-datasource.yaml`, `tempo-datasource.yaml`). The Loki datasource
already shows the pattern of rendering a field only while a sandbox is open
(`$tempo` derived from `otelCollector.eval`).

**Precedent sandbox (issue 903 / #1280, closed).**
- `eval-namespace.yaml`: a namespace gated on `otelCollector.eval.enabled`
  with the teardown annotation, default-deny, intra-namespace, DNS and
  cluster egress, ingress from `monitoring` on the OTLP ports, and a
  ResourceQuota plus LimitRange in the same guard.
- `eval-candidates.yaml`: a candidate Application with `prune: true` and no
  `selfHeal`, plus an optional second source `manifestsPath`.
- `infra-components/observability/eval/tempo/servicescrape.yaml`: the one
  VMServiceScrape, because the chart's ServiceMonitor is off (the #1159
  double-scrape).
- `templates/projects/project-default.yaml`: appends `observability-eval`
  and each enabled candidate's `repoURL` to the `default` AppProject.
- The bake-off's alerts lived in `vm-rules/` (now `tempo-alerts.yaml`,
  renamed from `tempo-eval-alerts.yaml`). That directory is synced
  unconditionally by the `monitoring` Application
  (`monitoring.yaml:1312`). The rules were "gated" by data: with no Tempo
  series they stay silent, and `tests/tempo-alerts_test.yaml` proves the
  quiet case "no series at all".

**Rule tests.** `scripts/check-vm-rules.sh` extracts each VMRule `.spec` in
`vm-rules/` into `tests/generated/`, then runs `promtool check rules` and
`promtool test rules` on `vm-rules/tests/*_test.yaml`. It also rejects any
non-VMRule kind in `vm-rules/`. It runs in `validate-manifests.yml:388`.

**Render CI.** `validate-manifests.yml` renders the bootstrap chart with the
committed values, and separately with
`tests/fixtures/otel-eval-candidates.example-values.yaml`:
- kubeconform (lines ~124-134);
- `scripts/validate-argocd-project-scope.py` (lines ~104-117);
- `tests/test_otel_collector_backends_render.py`, a plain-python
  `helm template` plus parse test (line ~803).

**Alert routing.** `monitoring.yaml` routes alerts by name prefix, e.g.
`alertname =~ "Tempo.*"` goes to `telegram` (line ~808). Unmatched alerts
go to the default route.

Deployed state checked:
- `gh pr view 2250 --repo mctlhq/mctl-gitops`: state OPEN, mergedAt null.
  Its diff was read for the exact `logsEval` block above.
- `mctl_get_service_logs(admins, mctl-web, 15m, 3)`: 3 lines returned at
  2026-10-29T18:08Z. Loki is live and serving mctl-api queries. Stream labels
  include `namespace, pod, container, job, node_name, filename, stream`.
- `mctl_list_services(admins)`: complete=true, 8 catalogue services.
  `loki-stack`, `monitoring` and Grafana are bootstrap Applications, not
  tenant services, so their deployed config was taken from the clone
  (bootstrap templates), not from a tool.
- Not observed: the live `host` label values on `promtail_sent_entries_total`,
  the current Promtail sent-entries rate, and Grafana's installed plugin
  list. No read-only tool in this run queries VictoriaMetrics or Grafana.
  These are recorded under Open questions and become the runbook's
  pre-open checks.

## Proposed solution

All changes are additive and keyed on `logsEval.*`. With the committed
defaults the bootstrap render of every existing object is unchanged.

### 1. Values (extends #2250's block)

Add to `logsEval.candidate`:
- `endpoint: ""`: the base HTTP URL of the candidate Service, e.g.
  `http://<svc>.logs-eval.svc.cluster.local:9428`. It is filled with the
  pins in the live round.
- `port: 9428`: VictoriaLogs' default HTTP port, used by NetworkPolicy.
- `metricsPortName: http`: used by the VMServiceScrape; verified at pin
  time.

Add to `logsEval`:
- `limits` (LimitRange `default`, `defaultRequest`, `max`, mirroring
  `otelCollector.eval.limits`);
- `promtailClient: {maxRetries: 2, minPeriod: 500ms, maxPeriod: 5s,
  timeout: 5s}`.

A helper `logsEval.candidateOpen` (in a new
`templates/observability/_logs-eval.tpl`) evaluates to true only when
`logsEval.enabled` and `logsEval.candidate.enabled` are both set. When it is
true, the helper calls `fail` if `endpoint` is empty or does not match
`\.logs-eval\.svc`. One definition is used by every template below, so the
gates cannot drift apart.

### 2. Sandbox namespace: `templates/observability/logs-eval-namespace.yaml`

This mirrors `eval-namespace.yaml`, gated on `logsEval.enabled` only. It
renders:
- Namespace `logs-eval` (label `mctl.ai/purpose: issue-2245-spike`,
  annotation `mctl.ai/teardown-after`);
- `default-deny-all`;
- `allow-intra-namespace`;
- `allow-dns-egress` (kube-system:53 only; the candidate has no reason to
  reach anything else);
- `allow-ingress-from-monitoring`: from namespace `monitoring` with
  podSelector `app.kubernetes.io/name` In [`promtail`, `vmagent`,
  `grafana`], on `logsEval.candidate.port` only;
- ResourceQuota from `logsEval.quota`, and LimitRange from `logsEval.limits`.

Quota and limits stay in the same guard, so "namespace without quota" cannot
be represented (the #1355 lesson).

### 3. Candidate Application: `templates/observability/logs-eval-candidate.yaml`

Gated on `logsEval.candidateOpen`. It renders one Application,
`logs-eval-victorialogs`, in `argocd`:
- `sources`: the chart from `logsEval.candidate.{repoURL, chart,
  targetRevision}` with `helm.valuesObject: logsEval.candidate.values`,
  plus this repo at `platform-gitops/infra-components/observability/logs-eval`;
- destination `logs-eval`;
- `automated.prune: true` and no `selfHeal` (the outage test scales it to 0);
- `CreateNamespace=false`;
- the same retry block as `eval-candidates.yaml`.

`templates/projects/project-default.yaml` appends `logs-eval` to the
destination namespaces when `logsEval.enabled`, and appends
`logsEval.candidate.repoURL` to the source repos when `candidateOpen`.

### 4. Scrape: `infra-components/observability/logs-eval/servicescrape.yaml`

A plain manifest synced by the candidate Application, so it exists only while
the candidate does. It is a VMServiceScrape in `logs-eval` that selects
`app.kubernetes.io/instance: logs-eval-victorialogs` (the Helm release label
Argo CD sets from the Application name) and its endpoint port by name,
`http`, path `/metrics`. It is the single scrape, because #2250 already
disables the chart's ServiceMonitor. Ports in a plain manifest cannot read
values, so the runbook's pin step checks the port name against the pinned
chart and edits this file in the same PR if it differs.

### 5. Grafana datasource and plugin

- `templates/observability/victorialogs-eval-datasource.yaml`, gated on
  `candidateOpen`: ConfigMap `victorialogs-eval-grafana-datasource` in
  `monitoring` (label `grafana_datasource: "1"`), datasource `name:
  VictoriaLogs (eval)`, `uid: victorialogs-eval`, `type:
  victoriametrics-logs-datasource`, `url: logsEval.candidate.endpoint`,
  `access: proxy`, `isDefault: false`.
- In `monitoring.yaml`, `GF_INSTALL_PLUGINS` becomes
  `victoriametrics-metrics-datasource{{ if candidateOpen }},victoriametrics-logs-datasource{{ end }}`.
  The default render is unchanged. Opening the sandbox restarts Grafana once
  to install the plugin, and closing it restarts Grafana again. The runbook
  states this.

### 6. Promtail dual-write (in `loki.yaml`)

Directly after the existing client line:

```yaml
            clients:
              - url: http://loki-stack:3100/loki/api/v1/push
{{- if (include "logsEval.candidateOpen" .) }}
              # issue-2245 bake-off: candidate second client. Bounded so a
              # candidate outage cannot hold Promtail's fan-out for long.
              - url: {{ trimSuffix "/" .Values.logsEval.candidate.endpoint }}/insert/loki/api/v1/push
                timeout: {{ .Values.logsEval.promtailClient.timeout }}
                backoff_config:
                  min_period: {{ .Values.logsEval.promtailClient.minPeriod }}
                  max_period: {{ .Values.logsEval.promtailClient.maxPeriod }}
                  max_retries: {{ .Values.logsEval.promtailClient.maxRetries }}
                external_labels: {}
{{- end }}
```

The `{{-` trims the newline, so the default string is byte-identical. The
Loki client keeps Promtail's defaults (unbounded-in-practice retries); only
the candidate is bounded. Promtail fans each entry out to every client, and a
client that is retrying can delay the hand-off to the others. Bounding the
retries and timeout caps that delay at about `timeout * (maxRetries + 1) +`
backoff, roughly 20s with the defaults. It does not remove the delay, which
is why section 7 exists.

### 7. Alerts: `infra-components/observability/vm-rules/logs-eval-alerts.yaml`

This follows the Tempo bake-off precedent. The file lives in the
always-synced `vm-rules/` and is gated by data. Every rule is ANDed with
`on() (count(promtail_sent_entries_total{host=~".+\\.logs-eval\\.svc.*"}) > 0)`,
a series that exists only while Promtail has the candidate client (the
endpoint guard in section 1 forces that host shape).

Group `logs-eval.shipper`:
- `LogsEvalLokiIngestionDrop` (warning, `for: 10m`):
  `sum(rate(promtail_sent_entries_total{host="loki-stack:3100"}[15m]))
  < 0.5 * sum(rate(promtail_sent_entries_total{host="loki-stack:3100"}[15m] offset 1h))`
  plus the gate.
- `LogsEvalLokiDroppedEntries` (warning, `for: 5m`):
  `sum(increase(promtail_dropped_entries_total{host="loki-stack:3100"}[15m])) > 0`
  plus the gate. Dropped entries are loss of production logs, including the
  Vault audit stream.

Both annotations name the kill switch (`logsEval.enabled: false`) and the
runbook. Unit tests go in
`vm-rules/tests/logs-eval-alerts_test.yaml`:
- fires on a 60% drop with the candidate series present;
- silent on a steady rate;
- silent on the same drop with no candidate series (sandbox closed);
- silent on a 30% drop;
- dropped-entries fires and stays silent accordingly.

Routing: in `monitoring.yaml`, add a route `alertname =~ "LogsEval.*"` to
`telegram`, rendered only when `logsEval.enabled`. The route sits before the
default route and follows the `Tempo.*` route's reasoning (operator remedy,
not an agent ticket).

### 8. Render and CI coverage

- `tests/fixtures/logs-eval.example-values.yaml`: a test overlay with
  `logsEval.enabled: true`, `teardownAfter` a fixed date, the candidate on,
  dummy but shape-valid pins (`repoURL: https://charts.example.invalid`,
  `chart: victoria-logs-single`, `targetRevision: "0.0.0-fixture"`) and
  `endpoint: http://logs-eval-victorialogs-server.logs-eval.svc.cluster.local:9428`.
  The header says it is never applied.
- `tests/test_logs_eval_render.py` (plain python, like
  `test_otel_collector_backends_render.py`):
  - **Off**, rendered with `--set logsEval.enabled=false`:
    - no object with namespace or name `logs-eval`;
    - Promtail `clients` parsed from the `loki-stack` values string equals
      `[{"url": "http://loki-stack:3100/loki/api/v1/push"}]`;
    - `GF_INSTALL_PLUGINS == "victoriametrics-metrics-datasource"`;
    - no `LogsEval` route;
    - no `victorialogs-eval` ConfigMap.
  - **On**, with the overlay:
    - Namespace with both annotations;
    - quota keys equal `logsEval.quota`;
    - a `podSelector: {}` default-deny in `logs-eval`;
    - the ingress policy only from `monitoring`, on port 9428;
    - the Application has `prune: true`, no `selfHeal`, and two sources, the
      second of which has the `logs-eval` path;
    - Promtail clients has length 2 with Loki first, and the second has
      `max_retries <= 3`, `max_period` <= 10s and `timeout` <= 10s;
    - the datasource and plugin are present;
    - `default` AppProject destinations include `logs-eval`.
  - **Guard**: the overlay with `endpoint: ""` and with an endpoint outside
    `logs-eval` must both make `helm template` exit non-zero.
- `validate-manifests.yml`:
  - a step "Render and validate the logs-eval overlay (issue-2245)" (render
    plus kubeconform, mirroring the issue-903 step);
  - add the overlay render to the AppProject scope step;
  - run `python3 tests/test_logs_eval_render.py`.

  `check-vm-rules.sh` already picks up the new rule and test files.
- Implementer check (recorded in the PR body, not CI): on the branch, run
  `helm template` of the bootstrap chart with committed values and diff it
  against the same render on `main`. The diff must be empty.

### 9. Runbook: `docs/runbooks/log-backend-bake-off.md`

The sections, in order:
1. **Pre-open checks:**
   - confirm the `host` label values on `promtail_sent_entries_total`;
   - record the 7-day Loki ingestion baseline;
   - check node headroom from VictoriaMetrics against `logsEval.quota`.
2. **Pin verification:** chart `index.yaml` URL and date, version, license,
   Service name and labels, metrics port name, the Loki-push path
   `/insert/loki/api/v1/push`, and the retention flag name.
3. **Opening:** one PR that sets the pins, `endpoint`, `candidate.enabled`,
   `enabled` and `teardownAfter` (14 days or less).
4. **The soak:** at least 7 days.
5. **Measurement steps mapped to each rubric key:**
   - `ingest_resources`
   - `storage_cost`
   - `query_latency` (the five-query set from the issue-2245 design)
   - `retention`
   - `tenant_isolation`
   - `ha_recovery` (pod kill, node drain)
   - `consumer_compat`
   - `migration_cost`
6. **Kill switch:** set `logsEval.enabled: false`.
7. **Teardown:** includes deleting the PVC and the Grafana restart.
8. **Filling the rubric**, under the ADR 0002 rules.

`CLAUDE.md` gains a one-line pointer in its runbook list.

## Alternatives

- **Template the VMRule in the bootstrap chart behind `logsEval.enabled`.**
  Dropped:
  - `check-vm-rules.sh` only reads `vm-rules/`, so the rule would escape
    promtool tests or need a second extraction path;
  - alert annotations would need `{{`{{ $value }}`}}` escaping;
  - the issue asks for the test "under the existing vm-rules test path".

  The data-gated rule is the precedent from the Tempo bake-off.
- **Put the VMRule in `infra-components/observability/logs-eval/`, synced by
  the candidate Application.** Dropped: if the candidate Application is
  broken or scaled away, the alert that protects Loki disappears with it.
  The alert must not depend on the thing it watches for. It would also sit
  outside the vm-rules test path.
- **Reuse `observability-eval` and `otelCollector.eval`.** Dropped for the
  reasons in the issue-2245 design: the OTLP-specific NetworkPolicies, the
  closed ADR 0001 round and coupled teardown windows.
- **Separate `pushURL` and `queryURL` values.** Dropped in favour of one
  `endpoint`. VictoriaLogs serves push, query and metrics on one HTTP port,
  and one value keeps the alert's host gate and the datasource consistent.

## Platform impact

- **Default render.** No new objects, and `loki-stack`, `monitoring` and
  AppProject `default` are byte-identical (test T1 and the implementer diff).
  The only always-on addition is `vm-rules/logs-eval-alerts.yaml`, which is
  silent without the candidate series. The `monitoring` Application syncs
  one extra VMRule object at no runtime cost.
- **Dependency.** Requires #2250 merged first. Otherwise `.Values.logsEval`
  is nil and every template's `if` must use the guarded helper. The helper
  uses `dig` so a missing block renders nothing rather than erroring.
- **When opened (live round, not here):**
  - one candidate pod within quota (1 CPU / 2Gi limits, a PVC of 20Gi or
    less);
  - one Grafana restart for the plugin;
  - a per-node Promtail CPU and memory increase for the second client;
  - a copy of the logs, including HMAC'd Vault audit lines, in a
    default-deny namespace, deleted at teardown.
- **Risks:**
  - Candidate back-pressure delays Loki delivery. Mitigations: the bounded
    client, the Loki client first, both `LogsEval*` alerts, and the kill
    switch.
  - The wrong `host` label assumption makes the alert silent. Mitigation:
    the runbook pre-open check is mandatory, and the unit tests pin the
    expected label shape.
  - An unverified chart port name breaks the scrape. Mitigation: the runbook
    pin step, plus `up{namespace="logs-eval"}` checked on day 0.
- **Migrations:** none. mctl-api `LOKI_URL`, the Loki datasource, retention
  and R2 are untouched.
