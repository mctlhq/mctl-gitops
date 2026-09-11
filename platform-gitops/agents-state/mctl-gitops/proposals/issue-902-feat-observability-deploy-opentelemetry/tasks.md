# Tasks: issue-902-feat-observability-deploy-opentelemetry

- [ ] 1. Pin the chart and distribution. Resolve the exact latest released
      version of `opentelemetry-collector` from
      `https://open-telemetry.github.io/opentelemetry-helm-charts` and record it
      in a comment next to `targetRevision`. Confirm the chart's default image
      is overridden to the **contrib** distribution
      (`otel/opentelemetry-collector-contrib`, command `otelcol-contrib`).
      — DoD: an exact version string (no range, no `*`), matching the pinning
      style of `bootstrap/templates/core-infra/argo-rollouts.yaml:13`; a note in
      the file stating that contrib is mandatory because `k8sattributes`,
      `redaction` and the OTTL `filter` processor do not exist in the core
      distribution.

- [ ] 2. Add the ArgoCD Application
      `platform-gitops/bootstrap/templates/observability/otel-collector.yaml`
      (depends on 1). Multi-source: the pinned chart with inline `helm.values`,
      plus `path: platform-gitops/infra-components/observability/otel-collector`.
      `project: default`, `destination.namespace: monitoring`,
      `server: {{ .Values.spec.destination.server }}`. syncPolicy copied from
      `loki.yaml:229-241` (automated prune+selfHeal, `CreateNamespace=true`,
      `ApplyOutOfSyncOnly=true`, retry 5 / 5s / factor 2 / 3m). Do **not** copy
      `ServerSideApply` / `RespectIgnoreDifferences` / `ServerSideDiff=false`
      from `monitoring.yaml:754-786`, and add no `ignoreDifferences` block.
      — DoD: `helm template test platform-gitops/bootstrap -f
      platform-gitops/bootstrap/values.yaml` renders the Application and
      `kubeconform -strict` passes on the output; a comment explains why the
      minimal sync set was chosen over monitoring.yaml's.

- [ ] 3. Add `otelCollector` keys to `platform-gitops/bootstrap/values.yaml`
      (depends on 2): `clusterName`, `environment`, and `backendEndpoint`
      (empty string by default). Wire them into the Application's inline values
      so `deployment.environment` / `k8s.cluster.name` are parameterised per
      cluster rather than hard-coded.
      — DoD: `helm lint platform-gitops/bootstrap` passes; with
      `backendEndpoint` empty the rendered config lists only the `debug`
      exporter in the traces pipeline.

- [ ] 4. Write the collector config in the Application's inline `helm.values`
      (depends on 2, 3). `mode: deployment`, `replicaCount: 2`,
      `fullnameOverride: otel-collector`, `service.type: ClusterIP`,
      `ingress.enabled: false`, ports `otlp` 4317 / `otlp-http` 4318 / named
      `metrics` 8888, `presets.kubernetesAttributes: true`, and explicit
      resources (requests 100m/192Mi, limits 500m/512Mi).
      Pipeline `traces`: receivers `[otlp]`; processors, in order,
      `[memory_limiter, k8sattributes, resource, redaction, filter/health,
      batch]`; exporters `[debug]` plus `otlp/backend` only when
      `backendEndpoint` is set.
      — DoD: rendered ConfigMap contains all six processors in that exact order
      with `memory_limiter` first and `batch` last; `resource` uses
      `action: insert` (not `upsert`); `otlp/backend` carries both
      `sending_queue` and `retry_on_failure`; `health_check` extension on
      `:13133` is wired to the liveness and readiness probes; `pprof` and
      `zpages` are absent.

- [ ] 5. Disable the chart's own scrape objects (depends on 4). Set the chart's
      `serviceMonitor` / `podMonitor` presets to `false` with a comment citing
      `vmagent`'s `selectAllByDefault: true` (`monitoring.yaml:287`) and the
      pushgateway double-scrape incident (#1159,
      `infra-components/observability/pushgateway/servicescrape.yaml:14-21`).
      — DoD: `helm template` of the chart renders zero `ServiceMonitor`,
      `PodMonitor`, `VMServiceScrape` or `VMPodScrape` objects.

- [ ] 6. Create
      `platform-gitops/infra-components/observability/otel-collector/servicescrape.yaml`
      (depends on 5): a `VMServiceScrape` in `monitoring` selecting the
      collector Service by a label the Service actually carries, on the **named**
      port `metrics`. Follow the header conventions of
      `pushgateway/servicescrape.yaml`.
      — DoD: `kubeconform -strict` passes under the `infra-components` sweep
      (`validate-manifests.yml:214-219`); after sync, the collector scrape pool
      shows exactly one target, and `otelcol_receiver_accepted_spans` is
      queryable in Grafana with no duplicate series.

- [ ] 7. Create
      `platform-gitops/infra-components/observability/otel-collector/networkpolicy.yaml`
      (depends on 2). `allow-otel-collector-ingress` in `monitoring`,
      `policyTypes: [Ingress]`, `podSelector` matching **the collector pods
      only**. Allowed sources: namespaces `admins`, `mctl-api`,
      `argo-workflows`, `temporal`, `monitoring`, and any namespace labelled
      `mctl.me/tenant`. Ports 4317 and 4318 only. Header comment must state, in
      the style of `core-infra/vault-netpol.yaml:1-10`, that `monitoring` has no
      namespace-wide policy today
      (`blackbox/blackbox-exporter.yaml:19-26`) and that a `podSelector: {}`
      here would convert the whole namespace into an allowlist.
      — DoD: `kubectl get netpol -n monitoring` shows the new policy; Grafana,
      VMSingle, vmagent and Loki remain Healthy and reachable after sync; a pod
      in a namespace not on the list is refused on 4317.

- [ ] 8. Add `platform-gitops/infra-components/observability/vm-rules/otel-collector-alerts.yaml`
      (depends on 6). A single `VMRule` in `monitoring` with
      `app.kubernetes.io/part-of: mctl-platform`, group
      `otel-collector.pipeline`, alerts `OtelCollectorDown`,
      `OtelCollectorRefusedSpans`, `OtelCollectorExportFailures`,
      `OtelCollectorQueueNearFull`. Every rule carries `severity: warning` and
      `mctl_agent_self: "true"`.
      — DoD: `scripts/check-vm-rules.sh` passes (`promtool check rules`); no
      non-`VMRule` object is added to `vm-rules/`; every alert's labels include
      `mctl_agent_self: "true"`.

- [ ] 9. Add the optional, default-off `otel` block to
      `platform-gitops/helm-charts/base-service` (values.yaml + deployment.yaml).
      `otel.enabled: false`, `otel.endpoint:
      http://otel-collector.monitoring.svc.cluster.local:4318`. When enabled it
      renders `OTEL_EXPORTER_OTLP_ENDPOINT`,
      `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_SERVICE_NAME` and
      `OTEL_RESOURCE_ATTRIBUTES` alongside the existing `env` handling at
      `deployment.yaml:119-136`, with `.Values.env` winning on conflict.
      — DoD: rendering every `platform-gitops/services/*/*/values.yaml` produces
      a byte-identical Deployment to before the change (no service opts in);
      rendering with `--set otel.enabled=true` adds exactly the four env vars;
      `helm lint platform-gitops/helm-charts/base-service` passes.

- [ ] 10. Write `docs/runbooks/otel-collector.md` (depends on 4, 7, 8) in the
      house style of `docs/runbooks/` — conclusion first, rules in bold, dated
      and measured claims, explicit residuals. Cover: the two endpoints and the
      Service DNS name; the redaction key patterns and value patterns and how to
      extend them when #38 / #195 add attributes; the batching and
      retry/queue settings and what each buys; the one-key backend-swap
      procedure via `otelCollector.backendEndpoint`; verification commands; the
      accepted residuals (no backend selected, no sampling, in-memory queue lost
      on restart, no mTLS on the receiver, `monitoring` still has no
      namespace-wide NetworkPolicy).
      — DoD: the runbook names real paths and real values; an operator who has
      never seen the collector can swap the backend from it alone.

- [ ] 11. Open the PR and let CI run (depends on 1-10). Expect
      `validate-manifests.yml` (helm lint, bootstrap render + kubeconform, the
      `infra-components` sweep, `check-vm-rules.sh`), `yamllint.yml`, and
      `claude-review.yml` — whose conventions block explicitly reviews ArgoCD
      Application specs, namespace declarations, permissive RBAC, missing
      NetworkPolicies, resource limit/request mismatches and missing health
      checks.
      — DoD: all required checks green; no new `-ignore-filename-pattern` added
      to `validate-manifests.yml` (if one is needed, the design was wrong and
      the operator path should be reconsidered).

- [ ] 12. Sync and verify in cluster (depends on 11). Wait for ArgoCD to
      reconcile `root-app` and the new `otel-collector` Application.
      — DoD: Application Synced + Healthy; 2/2 replicas Ready; the RBAC created
      by `presets.kubernetesAttributes` is get/list/watch on pods, namespaces
      and replicasets only, with no secrets and no write verbs.

## Tests

- [ ] T1. **OTLP gRPC acceptance.** From a throwaway pod in `admins`, send a
      trace to `otel-collector.monitoring.svc.cluster.local:4317`. Expect a
      success response and `otelcol_receiver_accepted_spans` to increase.

- [ ] T2. **OTLP HTTP acceptance.** Same, `POST` to `:4318/v1/traces`. Expect
      2xx and the receiver counter to increase.

- [ ] T3. **Internal-only.** Confirm no `Ingress`, no `NodePort`, and no Traefik
      route references the collector; confirm 4317/4318 are not reachable from
      outside the cluster.

- [ ] T4. **NetworkPolicy enforcement.** From a namespace not on the allow list,
      a connection to 4317 times out. From an allowed namespace it succeeds.
      Separately confirm Grafana, VMSingle, vmagent and Loki are still healthy —
      this is the regression that a mis-scoped `podSelector` would cause.

- [ ] T5. **Enrichment visible.** Send a span from a labelled pod; read the
      `debug` exporter output in Loki (`{namespace="monitoring"}` filtered to
      the collector pod) and confirm `k8s.namespace.name`, `k8s.pod.name`,
      `k8s.deployment.name`, `k8s.node.name`, `mctl.team`, `mctl.component`,
      `k8s.cluster.name` and `deployment.environment` are all present.

- [ ] T6. **Producer attributes preserved.** Send a span that already sets
      `deployment.environment` and `k8s.cluster.name` to sentinel values.
      Confirm the sentinels survive — proving `insert`, not `upsert`.

- [ ] T7. **Redaction.** Send a span carrying `authorization`,
      `http.request.header.cookie`, `gen_ai.prompt.0.content`,
      `mcp.tool.arguments`, `db.statement`, a `vault.token` key, and a benign
      key `note` whose *value* is `ghp_` + 36 chars. Confirm every sensitive
      attribute is absent or masked, the high-entropy value under `note` is
      masked by `blocked_values`, and adjacent non-sensitive attributes are
      untouched.

- [ ] T8. **Backend outage does not affect workloads.** Point
      `otelCollector.backendEndpoint` at an unroutable address. Confirm
      `otelcol_exporter_send_failed_spans` rises, the queue fills, and a
      representative workload (for example `labs/mctl-telegram`) keeps its
      readiness probe green with no elevated error rate for 15 minutes.

- [ ] T9. **Collector outage does not affect workloads.** Scale the collector to
      0 replicas for 10 minutes with a workload opted in to `otel.enabled:true`.
      Confirm the workload stays Ready and its own error-rate SLI is unchanged.
      Scale back and confirm recovery.

- [ ] T10. **Memory limiter / backpressure.** Drive a burst past the soft limit.
      Confirm `otelcol_receiver_refused_spans` increases and the pod is **not**
      OOM-killed (`kubectl get pod -o jsonpath` shows no `OOMKilled` last state).

- [ ] T11. **Alert unit tests.** `scripts/check-vm-rules.sh --selftest` then the
      real pass. Add `vm-rules/tests/otel-collector-alerts_test.yaml` with
      `input_series` for each of the four alerts, asserting `exp_labels`
      including `mctl_agent_self: "true"`.

- [ ] T12. **No double-scrape.** Query
      `count by (pod) (otelcol_receiver_accepted_spans)` and confirm one series
      per collector pod, not two.

- [ ] T13. **Existing pipelines unchanged.** `git diff` touches no
      `vmagent`/`vmsingle`/`promtail`/`loki` configuration. Confirm metric
      ingestion rate and Loki ingestion rate are flat across the deploy, and
      that no `VMRule` other than the new file changed.

- [ ] T14. **base-service is inert by default.** `helm template` every
      `platform-gitops/services/*/*/values.yaml` before and after task 9 and
      diff: expect no change.

- [ ] T15. **Backend swap without code change.** Set
      `otelCollector.backendEndpoint` to a second OTLP sink, sync, and confirm
      spans arrive there — with no image rebuild, no restart of any producer,
      and no change in `mctl-agent` or `mctl-agents`.

## Rollback

Three levels, cheapest first.

1. **Disable the backend exporter only.** Set
   `otelCollector.backendEndpoint` back to `""` in
   `platform-gitops/bootstrap/values.yaml` and let ArgoCD sync. The collector
   keeps running with just the `debug` exporter; nothing downstream is written.
   Use this if the problem is the backend, not the gateway.

2. **Remove the NetworkPolicy.** If T4 reveals collateral damage in the
   `monitoring` namespace, delete
   `infra-components/observability/otel-collector/networkpolicy.yaml` and sync.
   `monitoring` returns to its prior no-policy state (which is the documented
   status quo per `blackbox/blackbox-exporter.yaml:19-26`), and the collector
   stays reachable. This is the one step that may warrant an out-of-band
   `kubectl delete netpol -n monitoring allow-otel-collector-ingress` before the
   PR revert lands, because it can affect Grafana and VMSingle.

3. **Full revert.** `git revert` the merge commit. ArgoCD prunes the
   `otel-collector` Application (`prune: true`, plus the
   `resources-finalizer.argocd.argoproj.io` finalizer) and every object it owns:
   Deployment, Service, ConfigMap, ClusterRole/ClusterRoleBinding,
   VMServiceScrape, NetworkPolicy, VMRule. Removing the `base-service` `otel`
   block is safe in the same revert because it is default-off and no service
   values file references it. Nothing else is touched, so metrics and logs are
   unaffected by construction.

**Blast radius if this goes wrong:** confined to the `monitoring` namespace plus
one optional, unused chart values block. No tenant namespace NetworkPolicy is
modified, so the `mctl-tenant-networkpolicy-allowlist` admission policy at
`bootstrap/templates/system/admission-policies.yaml:80-105` is never touched —
which is exactly why the collector was placed in `monitoring` rather than a new
namespace. No data migration and no persistent storage means rollback is
stateless; the only loss is whatever spans were in flight.
