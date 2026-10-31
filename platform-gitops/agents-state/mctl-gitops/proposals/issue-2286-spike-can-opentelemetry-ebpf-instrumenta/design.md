# Design: issue-2286-spike-can-opentelemetry-ebpf-instrumenta

Scope: step A of the amended #2286, a default-off sandbox. Live work is
mctl-gitops#2303. This revision replaces the earlier proposal for #2286.
That version asked step A to find "the minimum set that loads on the workers"
and to ship a load-generator CWFT. Under the amendment, both now belong to
#2303.

## Current state

**Trace pipeline.** `platform-gitops/bootstrap/templates/observability/otel-collector.yaml`
is an Argo CD Application for the upstream `opentelemetry-collector` chart
(`targetRevision: "0.173.0"`, image `otelcol-contrib` `0.160.0`). It runs a
gateway collector in `monitoring`. Only `traces` is wired; `logs: null` and
`metrics: null` (around line 328). The processor order is `memory_limiter`,
`k8sattributes`, `resource`, `redaction`, `filter/health`, `batch`, and the
exporter sends to Tempo (`docs/runbooks/otel-collector.md`,
`docs/runbooks/tempo.md`). Metrics go vmagent -> VMSingle
(`bootstrap/templates/observability/monitoring.yaml`) and logs go promtail ->
Loki. Neither passes through the collector.

**Tenant identity in telemetry today (finding).** `k8sattributes` (lines
~133-155) maps the pod labels `mctl.ai/team` -> `mctl.team` and
`mctl.ai/component` -> `mctl.component`, using the default pod association,
which falls back to the connection IP. `helm-charts/base-service` does not set
`mctl.ai/team`, and its `podLabels` are tenant-controlled through
`update-config`. `mctl.team` is therefore evidence, not authority. The
platform-controlled key is the namespace label `mctl.me/tenant`. It is written
by `tenant.labels` and `tenant.teamLabels` in
`helm-charts/tenant/templates/_helpers.tpl` onto every tenant namespace,
including `{tenant}-{team}` and preview namespaces. The platform already uses
it as identity: `infra-components/observability/otel-collector/networkpolicy.yaml`
admits ingress from `namespaceSelector: mctl.me/tenant Exists`. Platform
namespaces such as `mctl-api` and `monitoring` do not carry it.

**Collector ingress.** `networkpolicy.yaml` (`allow-otel-collector-ingress`,
selecting `app.kubernetes.io/name: opentelemetry-collector`,
`app.kubernetes.io/instance: otel-collector`) is a plain manifest in an
infra-components directory that `otel-collector.yaml` syncs from `path:`
(line ~356). It cannot be gated by a bootstrap value.

**Gated-sandbox precedent.** Issue #903, #1280 and #1355 created
`bootstrap/templates/observability/eval-namespace.yaml`. It is wrapped in
`{{- if .Values.otelCollector.eval.enabled }}`, carries the
`mctl.ai/teardown-after` annotation and `mctl.ai/purpose`, uses default-deny
NetworkPolicies with `podSelector: {}` (safe because the namespace is created
alongside the policy), and has a ResourceQuota and a LimitRange sized in
`bootstrap/values.yaml` (`otelCollector.eval.*`, lines ~42-80). The teardown
date is enforced by `scripts/validate-eval-teardown-date.py`
(`MAX_WINDOW_DAYS = 14`, `--today`, `--selftest`).
`.github/workflows/validate-manifests.yml` (lines ~100-134) renders an
enabled overlay from `tests/fixtures/otel-eval-candidates.example-values.yaml`
and validates it, because the default render shows nothing.
`tests/test_otel_collector_redaction_e2e.py` runs the real `otelcol-contrib`
binary in Docker against fixture spans. That pattern fits the attribution
test.

**Explicit instrumentation baseline.** `base-service` has a default-off
`otel:` block (`tests/test_base_service_otel_env.py`). In the deployed gitops,
only `admins/mctl-agents-worker{,-exec,-implement}` and `admins/mctl-support`
set it.

**Privilege precedents.** Tenant namespaces enforce PSA `baseline`
(`helm-charts/tenant/templates/namespace.yaml`). The only privileged
DaemonSet in bootstrap is `core-infra/image-prune.yaml`. No `hostPID` exists
in `bootstrap/` or `infra-components/`.

**Cluster.** `infrastructure/k3s-preview/kube.tf` defines
`control-plane-fsn1` (`cx33`, `count = 1`, `taints = []`) and
`worker-cx43-fsn1` (`cx43`, `count = 3`, `taints = []`), with
`automatically_upgrade_os = false`. The control plane is untainted, so a
DaemonSet without affinity would land on it. That is why the anti-affinity is
required.

**Related spikes.** The #2211 OTTL proposal (status `proposed`) plans
values-driven OTTL processors in the production collector. This design uses
OTTL only inside the spike collector, so it does not depend on #2211.

Deployed state checked:
- `mctl_get_tenant mctl`: owner `mashkovd`, "no workloads", services `[]`,
  quota `pods: 1`, `requests.memory: 128Mi`, `requests.cpu: 100m`,
  `allowInternetEgress: false`. Chosen as tenant B. One tiny fixture fits.
- `mctl_get_tenant commerce-proof`: owner `mashkovd`, "Isolated tenant for the
  Agent Commerce C5 live proof ... no workloads", `pods: 2`. Not chosen, to
  keep the commerce proof isolated.
- `mctl_get_service_status admins/mctl-api`: Argo app `admins-mctl-api`, Healthy and
  Synced. The `service` block was null. The namespace `mctl-api` is taken from
  `bootstrap/templates/mctl-platform/mctl-api-*.yaml` (`namespace: mctl-api`).
- `$MCTL_GITOPS_ROOT/tenants/`: `admins, commerce-proof, erpact, karabu,
  labs, mctl, namax66`. `labs`, `mctl`, `admins` and `commerce-proof` each have
  `values.yaml` (no multi-team `teams:` seen in `labs` or `mctl`).
- `$MCTL_GITOPS_ROOT/services/admins/`: `mctl-agents-worker*`, `mctl-design`,
  `mctl-docs`, `mctl-support`, `mctl-web`, `umami`. There is no `mctl-api`
  values file there, because it is a bootstrap-managed platform workload.
- An earlier run of this investigation (proposal history) recorded:
  `mctl_list_tenants` refused ("requires admin access"); `labs` has 20 Synced
  base-service services; `otel:` is set only in the four `admins` services
  listed above.
- **Not observed:** worker kernel version, BTF presence, live namespace labels,
  whether `mctl-api` already emits spans, the current Tempo span rate and the
  VMSingle series baseline. These are recorded under Open questions and in
  Task 1.

## Proposed solution

Everything renders only under `obiSpike.enabled`, which is committed `false`.
With the flag off, the change set is limited to values, templates that render
nothing, tests, a CI guard and a document.

### 1. Values contract (`platform-gitops/bootstrap/values.yaml`)

```yaml
obiSpike:
  enabled: false
  teardownAfter: ""             # YYYY-MM-DD, required and <= 14 days out when enabled
  image:
    repository: ""              # OBI v1.0.0 image from the release notes (task 2)
    digest: ""                  # sha256:..., required when enabled
  allowPrivileged: false        # step A commits false; #2303 may flip with measured reason
  hostPID: true                 # process discovery across pods (OBI security doc)
  hostNetwork: false
  securityContext:
    privileged: false
    runAsUser: 0
    readOnlyRootFilesystem: true
    capabilities:
      drop: [ALL]
      add:                      # PROVISIONAL, from OBI v1.0.0 security doc; #2303 proves it
        - BPF                   # load BPF programs and maps
        - PERFMON               # kprobes/uprobes and perf events
        - SYS_PTRACE            # read /proc/<pid> of other containers (hostPID)
        - DAC_READ_SEARCH       # open target executables to place uprobes
        - CHECKPOINT_RESTORE    # resolve process namespaces / pidfd
  # Deliberately absent, each with its condition recorded in the doc:
  #   SYS_ADMIN  - only via allowPrivileged (fallback is #2303's decision)
  #   NET_ADMIN  - only for TC-based context propagation (off in step A)
  #   NET_RAW    - only for network-flow metrics / socket filter (off)
  #   SYS_RESOURCE - only for kernel < 5.11 (task 1 fact decides)
  mounts:
    - name: cgroup
      hostPath: /sys/fs/cgroup  # container-id -> pod resolution
      readOnly: true
  features:
    applicationTraces: true
    applicationMetrics: true
    networkMetrics: false
    contextPropagation: false   # off -> no NET_ADMIN; trace continuity measured as-is in #2303
    kubeMetadata: true          # needed so exported resources carry k8s.pod.uid
    k8sCache: false             # #2303 flips only if informer load breaches threshold
  targets:                      # exact (namespace, deployment); no globs
    - {namespace: labs, deployment: obi-fixture-tenant-a}
    - {namespace: labs, deployment: obi-fixture-forged}
    - {namespace: mctl, deployment: obi-fixture-tenant-b}
    - {namespace: mctl-api, deployment: mctl-api}
    - {namespace: observability-obi-spike, deployment: obi-fixture-unlabelled}
  fixtures:
    tenantA: labs
    tenantB: mctl
  resources: {}                 # OBI and collector requests/limits; sized in task 2
```

The capability list above is a hypothesis drawn from the OBI security doc, and
task 2 replaces it with a verbatim transcription of that doc (with its URL and
revision) for the selected feature subset: application traces and metrics,
with no network metrics and no TC propagation. Task 2 also applies the read-only
kernel facts from task 1. The render test (T1) pins the result. Step A never
tests whether it loads.

### 2. Template (`platform-gitops/bootstrap/templates/observability/obi-spike.yaml`)

The whole file is wrapped in `{{- if .Values.obiSpike.enabled }}`. The
DaemonSet is written in this repository rather than taken from an upstream
OBI chart, so every privilege field is visible in a reviewed diff (see
Alternatives). It renders:

- **Namespace** `observability-obi-spike`, with PSA `enforce: privileged`
  (needed to admit `hostPID` and host mounts), the `mctl.ai/teardown-after`
  annotation and `mctl.ai/purpose: issue-2286-spike`. It deliberately has no
  `mctl.me/tenant` label: the namespace is platform-owned, and the unlabelled
  negative fixture depends on that.
- **Default-deny NetworkPolicies** in the shape of `eval-namespace.yaml`.
  Egress is allowed to DNS and to the API server (OBI informers), and from OBI
  to the spike collector on 4317. Egress from the spike collector is allowed
  to the API server and to `monitoring/otel-collector:4317`. Ingress to the
  spike collector's metrics port is allowed from `monitoring`. The policies
  also cover a ResourceQuota and a LimitRange.
- **Additive NetworkPolicy in `monitoring`**: `allow-otel-collector-ingress-obi-spike`,
  with the same `podSelector` as `allow-otel-collector-ingress`, allowing
  ingress from `kubernetes.io/metadata.name: observability-obi-spike` on 4317.
  NetworkPolicies are a union, so the plain manifest stays untouched and the
  permission disappears with the flag.
- **OBI DaemonSet**. `hostPID`, `hostNetwork` and the `securityContext` come
  verbatim from `obiSpike.*`. It has no tolerations and a required
  `nodeAffinity` with `node-role.kubernetes.io/control-plane DoesNotExist`.
  The image is pinned by `repository@digest`, and the mounts come from
  `obiSpike.mounts`. A ConfigMap holds the OBI config, with
  `discovery.instrument` generated from `obiSpike.targets` (exact
  `k8s_namespace` and `k8s_deployment_name`), the feature toggles from
  `obiSpike.features`, and the OTLP exporter pointed at the spike collector
  only.
- **OBI RBAC**: a ServiceAccount `obi` and a ClusterRole with `get/list/watch`
  on pods, replicasets, services and nodes. Its own service account makes its
  API load separable in `apiserver_request_total` for #2303.
- **Spike collector**: a 1-replica `otelcol-contrib:0.160.0` Deployment
  (the same tag as production), with a ServiceAccount and a ClusterRole for
  `get/list/watch` on pods, namespaces and replicasets. It exports traces to
  `otel-collector.monitoring:4317` and exposes metrics through a `prometheus`
  exporter plus a `VMServiceScrape`. The production collector stays without a
  metrics pipeline.
- **Fixtures**: four tiny HTTP servers (the same pinned image, about
  10m/16Mi), each one replica.
  - `obi-fixture-tenant-a` in `labs`.
  - `obi-fixture-tenant-b` in `mctl`.
  - `obi-fixture-forged` in `labs`, with pod label `mctl.ai/team: mctl` and
    env `OTEL_RESOURCE_ATTRIBUTES=mctl.tenant=mctl`.
  - `obi-fixture-unlabelled` in the spike namespace, with the same forged label
    and attribute.

  No customer namespace is touched.

### 3. Attribution contract (spike collector pipeline)

`otlp` -> `memory_limiter` -> `transform/pre` -> `k8sattributes/obi` ->
`transform/attribution` -> `resource` -> `redaction` -> `filter/health` ->
`batch`.

0. `transform/pre` (resource context) deletes any incoming `mctl.tenant`,
   `mctl.tenant.resolved` and `mctl.tenant.attribution`. Values the producer
   supplied can then never survive into the result, including when the
   namespace has no label and `k8sattributes` writes nothing.
1. `k8sattributes/obi`: `pod_association` has the single source
   `resource_attribute k8s.pod.uid`. There is no connection-IP fallback,
   because every OBI export would otherwise come from the OBI pod's own IP.
   The processor extracts `k8s.namespace.name`, `k8s.pod.name` and
   `k8s.deployment.name`. It extracts the namespace label `mctl.me/tenant`
   (`from: namespace`) into the temporary key `mctl.tenant.resolved`, and the
   pod labels `mctl.ai/team` and `mctl.ai/component` into `mctl.team` and
   `mctl.component` as evidence.
2. `transform/attribution` (OTTL, resource context, `error_mode: propagate`):
   - `set(attributes["mctl.tenant"], attributes["mctl.tenant.resolved"]) where attributes["mctl.tenant.resolved"] != nil and attributes["mctl.tenant.resolved"] != ""`
   - `set(attributes["mctl.tenant.attribution"], "namespace-label") where attributes["mctl.tenant"] != nil`
   - `set(attributes["mctl.tenant.attribution"], "unattributed") where attributes["mctl.tenant"] == nil`
   - `delete_key(attributes, "mctl.tenant.resolved")`

   No statement reads `mctl.team`.
3. `resource`, `redaction` and `filter/health` are rendered from the same
   values the production collector uses (factored into a shared helper, or
   copied with a test asserting equality), so redaction is reused, not
   forked.

`mctl-api` therefore appears as `unattributed` with
`k8s.namespace.name=mctl-api`. No synthetic platform tenant is invented.

### 4. Evaluation document (`docs/spikes/2286-obi-evaluation.md`)

The document opens with `STATUS: PENDING_EXPERIMENT` and contains:

- **Preconditions** (Task 1), each with the command or source used, or
  "not observed": worker kernel and `osImage` (`kubectl get nodes -o
  jsonpath='{.items[*].status.nodeInfo}'`); BTF presence (a read-only `ls
  /sys/kernel/btf/vmlinux` on a worker, or the MicroOS kernel config); the
  kernel lockdown mode; the chosen fixture tenants; the expected
  `mctl.me/tenant` labels; the current explicit-instrumentation coverage
  (overlap-map skeleton); and the selected OBI feature subset.
- **Pinned provisional privilege set**: the table from section 1, with the
  OBI doc citation per capability and mount, and the list of withheld
  capabilities with their conditions.
- **Pre-registered thresholds**, frozen at merge:

  | Dimension | Threshold | Breach effect |
  |---|---|---|
  | False / cross-tenant attribution | 0 across all fixture requests | `NO_FIT` unless fixed and the full set re-run clean |
  | Platform/unlabelled fixtures unattributed | 100% | `NO_FIT` |
  | Fixture span coverage | >= 95% of generated requests produce a server span | caps at `PILOT_SELECTED_WORKLOADS` |
  | Privilege | no `privileged`, no `SYS_ADMIN`; `NET_ADMIN` only if propagation is selected | caps at `PILOT_SELECTED_WORKLOADS` |
  | Node CPU overhead p95 (OBI container) | <= 3% of node allocatable (<= 240m on cx43) | caps at `PILOT_SELECTED_WORKLOADS` |
  | OBI RSS per node p95 | <= 300Mi | caps at `PILOT_SELECTED_WORKLOADS` |
  | Application latency p95 delta (on vs off) | <= max(5%, 2 ms) | caps at `PILOT_SELECTED_WORKLOADS` |
  | API load from OBI service accounts (steady state, after initial sync) | LIST <= 0.1 req/s aggregate; WATCH streams <= 6 per OBI pod | evaluate `k8sCache`; if still breached, caps at `PILOT_SELECTED_WORKLOADS` |
  | Series cardinality delta in VMSingle | <= 5,000 new series for the allowlist | caps at `PILOT_SELECTED_WORKLOADS` |
  | Span volume delta | <= 50 spans/s at the #2303 load mix | caps at `PILOT_SELECTED_WORKLOADS` |

- **Decision rule**: `ADOPT_BOUNDED_OBI_LAYER` requires every row within its
  threshold, plus coverage that the explicit `otel:` path does not already
  give. Any attribution breach that is not fixed gives `NO_FIT`. Everything
  else gives `PILOT_SELECTED_WORKLOADS`.
- **Empty sections for #2303**: overlap map, coverage matrix, measurements,
  failure behaviour, outcome.

### 5. Sidecar vs DaemonSet

This is assessed on paper only. A sidecar would place the same BPF
capabilities and `shareProcessNamespace` inside tenant pods, which violates
PSA `baseline` and requires editing tenant `values.yaml`. It is not
operationally plausible here, so per the issue it is not built.

## Alternatives

1. **Use the upstream OBI Helm chart through an Argo CD Application.** Dropped
   for step A because the effective privileges would be the chart's defaults
   merged with our overrides. That is exactly the "privilege hidden inside a
   Helm default" the issue forbids, and a chart bump could widen them without
   a diff in this repo. A self-authored DaemonSet keeps every field in a
   reviewed template that T1 pins. #2303 can revisit this if chart features
   are needed.
2. **Resolve `mctl.tenant` in the production collector.** Dropped. The
   production pipeline's connection-IP pod association would misattribute OBI
   exports to the OBI pod, and changing production is a rollout, not a
   sandbox. If step B is positive, a follow-up moves this chain into
   production and also retires the forgeable `mctl.team`.
3. **Map `k8s.namespace.name` to a tenant at query time.** Dropped. It creates
   a second tenant mapping that must reimplement the tenant chart's
   `{tenant}-{team}` and preview naming in every query, and it fails open.
4. **Scrape OBI's Prometheus endpoint directly with vmagent.** Dropped because
   no server-side attribution step would run before storage.
5. **Measure the capability set empirically now.** Dropped by the amendment:
   loading BPF is live work, which belongs to #2303.

## Platform impact

- **Runtime:** none at merge. `obiSpike.enabled: false` renders nothing, and
  T1 proves the default render is byte-identical.
- **CI:** adds `scripts/validate-obi-spike.py` (with `--selftest`), an enabled
  render overlay `tests/fixtures/obi-spike.example-values.yaml` in
  `validate-manifests.yml`, and the tests T1 to T3. T3 needs Docker like the
  existing redaction e2e, so it uses the same CI job and skip rules.
- **Security when #2303 enables it:** three workers run a `hostPID` root
  container with BPF-class capabilities. A container escape there means host
  access. Mitigations: the pinned set; the privileged and `SYS_ADMIN` guard;
  a 14-day teardown; a dedicated default-deny namespace; an exact allowlist; a
  digest-pinned image; and no scheduling on the control plane. The data is
  platform-internal, in the same trust tier as Tempo and Loki.
- **Tenant quotas when enabled:** one fixture pod in `mctl` (quota `pods: 1`,
  `128Mi`) and two in `labs`. #2303 must confirm `labs` headroom before
  enabling.
- **Backward compatibility / migrations:** none. Argo CD prunes all spike
  objects when the flag returns to false. The new values keys are additive.
- **Risk:** the provisional set may not load in #2303. That is the intended
  outcome to be measured there. A widening requires an explicit
  `allowPrivileged` change and review, never a silent default.
