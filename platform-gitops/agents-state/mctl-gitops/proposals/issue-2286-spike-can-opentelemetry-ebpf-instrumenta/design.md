# Design: issue-2286-spike-can-opentelemetry-ebpf-instrumenta

## Current state

**Trace pipeline.** `platform-gitops/bootstrap/templates/observability/otel-collector.yaml`
is an ArgoCD Application that runs a 2-replica gateway Collector in
`monitoring`. Only a `traces` pipeline exists; metrics and logs are null. The
processor order is `memory_limiter` -> `k8sattributes` -> `resource` (insert
`k8s.cluster.name=mctl-preprod`, `deployment.environment.name`) -> `redaction`
-> `filter/health` -> `batch`. Exporters are `debug` and `otlp/backend` to
Tempo (`tempo.tracing.svc.cluster.local:4317`, see `docs/runbooks/tempo.md`
and `docs/runbooks/otel-collector.md`). Metrics take a separate path,
vmagent -> VMSingle (`bootstrap/templates/observability/monitoring.yaml`),
and logs go promtail -> Loki (`loki.yaml`). Neither passes through the
Collector.

**Current tenant identity in telemetry.** `k8sattributes` extracts pod labels
`mctl.ai/team` -> `mctl.team` and `mctl.ai/component` -> `mctl.component`
(lines ~133-155). promtail relabels the same pair for logs. These labels are
not authoritative:
- `helm-charts/base-service/templates/_helpers.tpl` never sets `mctl.ai/team`.
  The only places that set it are Argo CWFTs (`cwft-mctl-agents-*.yaml`,
  `mctl.ai/team: admins`).
- `base-service.podLabels` refuses only the `workflows.argoproj.io/` prefix. Its
  own comment says `podLabels` is tenant-controlled, because `update-config`
  applies a caller-supplied `config_patch`. A tenant could therefore label
  its pod `mctl.ai/team: <other-tenant>`.

**Canonical tenant key (platform-controlled).** `helm-charts/tenant/templates/_helpers.tpl`
`tenant.labels` writes `mctl.me/tenant: <tenant>` onto every tenant
namespace. That covers the legacy single namespace, `{tenant}-{team}` for
multi-team tenants (`namespace.yaml`), and the preview namespace
(`preview.yaml`, which also carries `mctl.me/preview: "true"`). Tenants have no
write verbs on Namespaces. `helm-charts/tenant/templates/kubectl-access.yaml`
grants only get/list/watch on workloads plus pod delete. The platform already
treats this label as tenant identity:
`infra-components/observability/otel-collector/networkpolicy.yaml` admits
ingress from `namespaceSelector: mctl.me/tenant Exists`. Platform namespaces
(`monitoring`, `mctl-api`, `argo-workflows`, `temporal`, `tracing`) do not
carry it.

**Explicit instrumentation coverage.** `base-service` has a default-off `otel:`
block (`tests/test_base_service_otel_env.py`). Under
`$MCTL_GITOPS_ROOT/services`, only four `admins` services set it.

**Privilege precedents.** Tenant namespaces enforce PSA `baseline` (audit/warn
`restricted`) through `helm-charts/tenant/templates/namespace.yaml`. The only
privileged DaemonSet in bootstrap is `core-infra/image-prune.yaml`
(`privileged: true`, `tolerations: operator: Exists`). Nothing in
`bootstrap/` or `infra-components/` uses `hostPID`.
`bootstrap/templates/system/admission-policies.yaml` holds the
ValidatingAdmissionPolicies. None of them restricts privileged pods.

**Spike-sandbox precedent.** Issue #903 / #1280 introduced a gated, self-expiring
evaluation namespace: `bootstrap/templates/observability/eval-namespace.yaml`
(default-deny NetworkPolicies, `mctl.ai/teardown-after` annotation, quota),
gated by `otelCollector.eval.enabled`, and `scripts/validate-eval-teardown-date.py`,
which turns CI red past a 14-day window. `tests/test_otel_collector_redaction_e2e.py`
runs the real collector binary in Docker against fixture spans. That pattern
fits an attribution test.

**Cluster.** `infrastructure/k3s-preview/kube.tf` defines one control-plane
node (`cx33`, no taints) and three `cx43` workers (`worker-cx43-fsn1`). The
control-plane node has no taint, so a DaemonSet without affinity would also
land there.

Deployed state checked:
- `mctl_list_tenants`: failed ("requires admin access"). The full tenant list was not
  observed; `$MCTL_GITOPS_ROOT/tenants/` lists `admins, commerce-proof,
  erpact, karabu, labs, mctl, namax66`.
- `mctl_get_tenant karabu`: tenant exists, has 1 service, quota `pods: 10`,
  `requests.memory: 512Mi`, `allowInternetEgress: false`.
- `mctl_list_services karabu`: `draw-with-friends` 0.2.0, base-service, port 8080,
  hosts `draw-with-friends.mctl.ai`, `karabu-draw-with-friends.mctl.ai`, Synced.
- `mctl_list_services labs`: 20 Synced base-service services with ingress, e.g.
  `portfolio` (port 80, `labs-portfolio.mctl.ai`) and `mctl-telegram`
  (`tg.mctl.ai`).
- `mctl_list_services namax66`: `news-factory` 0.2.2, no host (fallback only).
- `mctl_get_service_config admins/mctl-support`: 0.4.0, `support.mctl.ai`.
- `$MCTL_GITOPS_ROOT/services/*/*/values.yaml`: `otel:` appears only in
  `admins/mctl-agents-worker{,-exec,-implement}` and `admins/mctl-support`.
  `karabu/draw-with-friends/values.yaml` has no `otel:` and no `podLabels`.
- Not observed: node kernel/BTF, live namespace labels, `mctl-api`
  namespace contents and its current span emission, and live collector span
  rates. All of these are under Open questions in requirements.md and are
  measured in Task 1 and Task 6.

## Proposed solution

The spike runs as a gated, self-expiring sandbox in this repository. It
mirrors the #903 eval-namespace pattern, and nothing in it changes
production telemetry paths.

### 1. Values contract (`platform-gitops/bootstrap/values.yaml`)

```yaml
obiSpike:
  enabled: false
  teardownAfter: ""            # YYYY-MM-DD, <= 14 days out while enabled
  chartVersion: ""              # OBI Helm chart pinned to the app v1.0.0 release
  image: "otel/ebpf-instrument:v1.0.0"   # exact tag/digest confirmed in Task 2
  allowPrivileged: false
  securityContext:              # explicit, never inherited from chart default
    privileged: false
    runAsUser: 0
    capabilities:
      drop: [ALL]
      add: []                   # filled in Task 2 from measured minimum set
  hostPID: true                 # required for process discovery; recorded, not hidden
  hostNetwork: false
  mounts: []                    # e.g. /sys/fs/cgroup, /sys/kernel/security, /sys/fs/bpf
  targets:                      # explicit allowlist, no wildcard discovery
    # Amendment 2026-10-31: synthetic fixtures only, no customer workloads.
    - namespace: labs
      deployment: obi-fixture-tenant-a
    - namespace: <tenant B, owner-controlled, chosen in task 1>
      deployment: obi-fixture-tenant-b
    - namespace: mctl-api
      deployment: mctl-api
  k8sCache: false               # flip only if Task 6 shows material informer load
```

According to OBI's security documentation, the expected candidate capability
set is `BPF`, `PERFMON`, `SYS_PTRACE`, `DAC_READ_SEARCH`,
`CHECKPOINT_RESTORE`, `NET_RAW`, plus `NET_ADMIN` only if TC-based context
propagation is enabled, and `SYS_RESOURCE` only on kernels below 5.11. That
list is a hypothesis. Task 2 replaces it with the minimum set that actually
loads on the workers. A render test pins the result, so a change in chart
defaults cannot widen it silently.

### 2. Templates (`platform-gitops/bootstrap/templates/observability/obi-spike.yaml`)

Everything below renders only when `obiSpike.enabled`:
- Namespace `observability-obi-spike` with PSA `enforce: privileged` (the
  only way `hostPID` is admitted), the `mctl.ai/teardown-after` annotation and
  `mctl.ai/purpose: issue-2286-spike`. It has no `mctl.me/tenant` label, which
  is intentional: the namespace is platform-owned.
- Default-deny NetworkPolicies, copied in shape from `eval-namespace.yaml`.
  Egress is allowed to the API server, DNS and the spike collector. Ingress is
  allowed from `monitoring` on the metrics port.
- ArgoCD Application for the upstream OBI chart, pinned. Values come only from
  `obiSpike.*`. The affinity excludes `node-role.kubernetes.io/control-plane`
  and there are no tolerations. Discovery uses `discovery.instrument` entries
  generated from `obiSpike.targets` (`k8s_namespace` plus
  `k8s_deployment_name`). OBI exports OTLP traces and metrics only to the spike
  collector.
- **Spike collector**: a 1-replica `otelcol-contrib` Deployment at the same
  image tag as production (`0.160.0`). Its `redaction` and `filter/health`
  blocks come from the same values helper the production collector uses, so
  redaction behaviour is reused rather than forked. It runs a `traces` and a
  `metrics` pipeline with the attribution chain below. Traces export to the
  production `otel-collector.monitoring:4317`, which forwards them to Tempo
  unchanged because `insert` does not overwrite. Metrics are exposed on a
  Prometheus exporter port scraped by a `VMServiceScrape`, so OBI series land
  in VMSingle with `mctl_tenant` and stay off the production collector,
  which has no metrics pipeline.
- A ClusterRole for the spike collector with get/list/watch on pods,
  namespaces and replicasets. OBI's own RBAC comes from the chart and is
  reviewed; the render test pins both.
- The production collector NetworkPolicy gains one ingress peer,
  `kubernetes.io/metadata.name: observability-obi-spike`, gated by the same
  flag.

### 3. Attribution contract (spike collector)

The production `k8sattributes` default pod association falls back to the
connection IP. For OBI that IP is the OBI pod's own, so the spike collector
must not use that fallback. The chain is:

1. `k8sattributes/obi` with `pod_association: [{sources: [{from:
   resource_attribute, name: k8s.pod.uid}]}]` only. OBI derives pod UID from
   cgroup data in the kernel, not from application output. It extracts
   `k8s.namespace.name`, `k8s.pod.name`, `k8s.deployment.name`, and the
   namespace label `mctl.me/tenant` (`from: namespace`) into a temporary key
   `mctl.tenant.resolved`. It also extracts pod labels `mctl.ai/team` and
   `mctl.ai/component` as evidence only.
2. `transform/attribution` (OTTL, resource context, `error_mode: propagate`):
   delete any incoming `mctl.tenant`. Set `mctl.tenant` from
   `mctl.tenant.resolved` when it is present and non-empty, and set
   `mctl.tenant.attribution` to `namespace-label`. Otherwise set
   `mctl.tenant.attribution` to `unattributed`. Then delete
   `mctl.tenant.resolved`. No branch ever reads `mctl.team`.
3. The same processors as production follow: `resource`, `redaction`,
   `filter/health`, `batch`.

A platform workload such as `mctl-api` therefore appears as `unattributed` with
`k8s.namespace.name=mctl-api`. No second tenant identity (for example a
synthetic "platform" tenant) is invented.

**Negative fixtures**, rendered only while the spike is enabled, live in
`observability-obi-spike`:
- `obi-fixture-forged`: a tiny HTTP server with pod label `mctl.ai/team:
  <tenant A>` and `OTEL_RESOURCE_ATTRIBUTES=mctl.tenant=labs`. Expected:
  `unattributed` every time.
- An offline e2e test, `tests/test_obi_spike_attribution_e2e.py`, modelled on
  `test_otel_collector_redaction_e2e.py`. It runs the spike collector config
  with a fake k8s metadata source, or with the processors driven by
  pre-resolved fixtures where the binary allows that, and checks four cases:
  correct tenant A, correct tenant B, forged label, and an unknown pod UID.

### 4. Experiment procedure and report

A `ClusterWorkflowTemplate` `obi-spike-load`
(`argo-workflows/cluster-templates/wft-obi-spike-load.yaml`) drives a fixed
request mix at the public hosts of the targets, through Traefik, plus the
fixture. It produces the traffic for coverage and the latency comparison.
Measurements come from existing sources only:
- vmagent/VMSingle: container CPU and RSS, OBI's self-metrics, and series count
  per `mctl_tenant`.
- `apiserver_request_total` for API list/watch load, by user agent and
  service account.
- Tempo: span counts per service.
- Traefik metrics: request latency for the before/off/on windows.

Failure modes are exercised by scaling the spike collector to 0, blocking API
egress with a NetworkPolicy toggle, and restarting OBI. The report
`docs/spikes/2286-obi-evaluation.md` records the results and the single
outcome.

**Decision rule.** Any unfixed false or cross-tenant attribution gives
`NO_FIT`. If attribution is clean but privileged mode or `CAP_SYS_ADMIN` is
required, or node CPU overhead exceeds 3% at p95, or latency overhead exceeds
5% at p95, the outcome is at most `PILOT_SELECTED_WORKLOADS`.
`ADOPT_BOUNDED_OBI_LAYER` requires clean attribution, the non-privileged
capability set, and coverage the explicit path does not already provide. The
thresholds are recorded in the report before measurement, so they cannot be
tuned afterwards. Amendment 2026-10-31: the same pre-registration must also
set numeric limits for OBI RSS per node, Kubernetes API list/watch load from
OBI service accounts and span/series cardinality delta; exceeding any of them
caps the outcome at `PILOT_SELECTED_WORKLOADS`.

### Sidecar vs DaemonSet

This is assessed on paper only. A sidecar would need a `shareProcessNamespace`
container that carries the same BPF capabilities inside the tenant pod. That
breaks PSA `baseline` in tenant namespaces and requires editing tenant
`values.yaml`. It is not operationally plausible for MCTL, so per the issue it
is not built.

## Alternatives

1. **Add `mctl.tenant` resolution and OBI export straight into the production
   collector.** This was dropped for the spike for two reasons. First, the
   production pipeline's connection-IP pod association would mis-associate
   OBI traffic. Second, changing the production pipeline is a rollout, not a
   bounded experiment. If attribution proves out, the follow-up is to move the
   `mctl.me/tenant` chain into production. That would also fix the existing
   forgeable `mctl.team`.
2. **Trust OBI's own Kubernetes decoration (`k8s.namespace.name`) and map it to a
   tenant at query time.** Dropped because it creates a second, query-side
   tenant mapping and fails open for multi-team (`{tenant}-{team}`) and preview
   namespaces unless every query reimplements the tenant chart's naming.
3. **Use OBI's Prometheus exporter scraped directly by vmagent.** Dropped
   because no server-side attribution step runs before storage, so tenant
   identity would come from OBI's labels.
4. **Use explicit OTel SDK opt-in (`otel.enabled`) per tenant service instead
   of OBI.** This is the current path and the comparison baseline. It is not
   dropped. The report quantifies how much OBI adds over it.

## Platform impact

- **Default-off.** With `obiSpike.enabled: false`, nothing renders. A render
  test asserts that every existing bootstrap template is byte-identical.
- **Privilege.** While enabled, three worker nodes run a `hostPID` container
  with BPF-class capabilities, and possibly privileged mode if the kernel
  forces it, which the CI gate makes explicit. A container escape there means
  host access. Mitigations: a 14-day CI-enforced teardown; a dedicated
  namespace with default-deny network policies; an explicit target allowlist;
  pinned image and chart; and no tolerations, so OBI never runs on the
  untainted control-plane node.
- **Resources.** Expected cost is one OBI pod per worker plus one spike
  collector. Requests are sized in Task 2 (initial guess 100m/256Mi per OBI
  pod and 100m/256Mi for the collector). A namespace ResourceQuota caps them.
- **API server.** OBI on 3 nodes plus the spike collector add 4 informer sets
  on pods, replicasets, services and nodes. This is measured, and `k8sCache`
  is enabled only if the load is material.
- **Telemetry volume.** Traces add to the production collector and Tempo, and
  metrics add VMSingle series. The allowlist bounds both, and the report
  measures them.
- **Tenants.** No tenant manifest changes. Tenant pods are observed from the
  host, so the spike is announced in the issue. The data stays platform-internal,
  in the same trust tier as Loki and Tempo.
- **Migrations / backward compatibility.** None. All spike objects are pruned
  by ArgoCD when the flag returns to false.
