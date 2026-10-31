# Spike: bounded OBI v1.0.0 experiment with canonical tenant attribution, overhead and privilege measurement

## Context

Issue mctlhq/mctl-gitops#2286 asks whether OpenTelemetry eBPF Instrumentation
(OBI) v1.0.0 can add useful zero-code RED metrics and traces on the MCTL
cluster. It sets three conditions: tenant attribution must be deterministically
correct, runtime and API-server overhead must be acceptable, and the
host-privilege footprint must be acceptable. The spike must end in exactly one
outcome: `NO_FIT`, `PILOT_SELECTED_WORKLOADS` or `ADOPT_BOUNDED_OBI_LAYER`.

This matters because explicit instrumentation covers very little today. Only
four `admins` services set `otel.enabled` in their `values.yaml`
(`mctl-agents-worker`, `mctl-agents-worker-exec`,
`mctl-agents-worker-implement`, `mctl-support`). Tenant workloads such as
`karabu/draw-with-friends` and the 20 `labs` services emit no traces at all.

There is also a correctness problem in today's tenant identity. The production
collector (`platform-gitops/bootstrap/templates/observability/otel-collector.yaml`,
`k8sattributes`) derives `mctl.team` from the pod label `mctl.ai/team`. The
`base-service` chart does not set that label, and tenants can set arbitrary
`podLabels` through `update-config`. The spike therefore needs to define an
attribution contract anchored on platform-controlled data: the namespace label
`mctl.me/tenant`, written by `helm-charts/tenant`. It must prove that contract
before deciding whether OBI is worth its privileges: `hostPID`, BPF-class
capabilities and kernel filesystem mounts.

## User stories

- AS a platform operator I WANT RED metrics and server/client spans for tenant
  workloads that have no explicit instrumentation SO THAT I can see errors and
  latency without asking each tenant to change code.
- AS a tenant owner I WANT telemetry about my workload attributed only to my
  tenant SO THAT another tenant's label choices can never cause my data to be
  attributed to them, or theirs to me.
- AS a security reviewer I WANT the exact host privileges, capabilities and
  mounts OBI needs written explicitly in reviewed manifests SO THAT I can weigh
  them against measured value instead of trusting a Helm default.
- AS the spike owner I WANT a self-expiring, default-off sandbox SO THAT the
  experiment cannot silently become a cluster-wide privileged rollout.

## Acceptance criteria (EARS)

> **Amendment 2026-10-31.** (1) Scope: this proposal is step A, the sandbox
> shipped with `obiSpike.enabled: false`, plus preconditions, offline tests
> and pre-registered thresholds. Enabling it, measuring, the report's outcome
> and teardown are mctl-gitops#2303 (step B). (2) Targets: no customer tenant
> workload is instrumented. The two-tenant proof uses synthetic HTTP fixture
> deployments in two owner-controlled tenants chosen in task 1 (`labs` plus one
> of `mctl`, `admins` or `commerce-proof` that carries `mctl.me/tenant`), and
> `mctl-api` as the platform workload. (3) Thresholds: the decision rule must
> also carry numeric thresholds for OBI RSS per node, Kubernetes API list/watch
> load from OBI service accounts and span/series cardinality delta, written to
> the report in step A before any measurement.

### Sandbox bounds
- WHILE `obiSpike.enabled` is `false` in `platform-gitops/bootstrap/values.yaml`
  THE SYSTEM SHALL render no OBI-related object, and every existing bootstrap
  template shall render byte-identical to its pre-change output.
- WHEN `obiSpike.enabled` is `true` THE SYSTEM SHALL require
  `obiSpike.teardownAfter` to be a `YYYY-MM-DD` date no more than 14 days in the
  future, and CI (`validate-manifests.yml`) SHALL fail otherwise.
- WHILE the spike is enabled THE SYSTEM SHALL run OBI only as a DaemonSet in the
  dedicated namespace `observability-obi-spike`, excluded from the
  control-plane node, and shall instrument only the processes matched by the
  explicit `obiSpike.targets` allowlist (namespace plus deployment name). No
  wildcard discovery is allowed.
- IF a rendered OBI pod spec sets `privileged: true` THEN CI SHALL fail, unless
  `obiSpike.allowPrivileged` is explicitly `true` and a comment records the
  measured reason.
- WHILE the spike is enabled THE SYSTEM SHALL state every Linux capability,
  `hostPID`/`hostNetwork` setting and hostPath mount of the OBI container
  explicitly in `bootstrap/values.yaml`, and a render test SHALL pin that exact
  set.

### Tenant attribution contract
- WHEN a span or metric from OBI reaches the spike collector THE SYSTEM SHALL
  resolve its tenant only as follows: OBI-reported pod UID, then pod, then
  namespace, then the namespace's `mctl.me/tenant` label. It shall write the
  result as `mctl.tenant` with `upsert`, so any producer-supplied value is
  overwritten.
- IF the namespace has no `mctl.me/tenant` label, or the pod cannot be resolved,
  THEN THE SYSTEM SHALL leave `mctl.tenant` unset and set
  `mctl.tenant.attribution=unattributed`. It shall never default to another
  tenant, `admins`, or a value taken from a pod label or resource attribute.
- WHEN a fixture pod in a non-tenant namespace carries pod label
  `mctl.ai/team: <tenant A>` and emits `mctl.tenant=<tenant B>` in its own resource
  attributes THE SYSTEM SHALL attribute its telemetry as `unattributed`.
- WHILE OBI telemetry is attributed THE SYSTEM SHALL keep `mctl.ai/team` and
  `mctl.ai/component` only as evidence attributes (`mctl.team`,
  `mctl.component`) and shall not use them to derive `mctl.tenant`.

### Experiment and measurement
- WHEN the experiment runs THE SYSTEM SHALL exercise at least the synthetic
  fixture deployments in two owner-controlled tenants and the platform workload
  `mctl-api`, and no customer tenant workload, and shall record per-workload span and metric coverage next to
  the existing explicit-instrumentation path.
- WHEN the experiment completes THE SYSTEM SHALL produce a report at
  `docs/spikes/2286-obi-evaluation.md`. The report shall contain the
  overlap map, the attribution evidence (including the negative case), a
  protocol/runtime coverage matrix, CPU/RSS per node, application latency delta,
  telemetry volume and series cardinality, Kubernetes API list/watch load,
  the exact privilege set, failure behaviour with the API server, Collector and
  metadata unavailable, and exactly one outcome from `NO_FIT`,
  `PILOT_SELECTED_WORKLOADS` or `ADOPT_BOUNDED_OBI_LAYER`.
- IF any false or cross-tenant attribution is observed THEN THE SYSTEM SHALL
  record the outcome as `NO_FIT` unless the cause is fixed in the attribution
  pipeline and the full attribution test set is re-run clean.
- WHEN `obiSpike.teardownAfter` is reached or the report is merged, whichever is
  first, THE SYSTEM SHALL return to `obiSpike.enabled: false`, and ArgoCD
  pruning SHALL remove the namespace, DaemonSet, spike collector and RBAC.

## Out of scope

- A cluster-wide or production rollout of OBI.
- Changing the production `otel-collector` processor pipeline. A follow-up issue
  may move `mctl.tenant` resolution there if the spike recommends adoption.
- Replacing the OTel Collector, Tempo, VictoriaMetrics, Loki, or picking a
  storage backend.
- Editing any tenant's `values.yaml` or pod labels.
- Treating Kubernetes metadata as proof of tenant isolation.
- A sidecar-mode comparison. It is assessed on paper only (see design.md).

## Open questions

- Node kernel version and BTF availability on the kube-hetzner worker nodes
  (`worker-cx43-fsn1`, MicroOS image) could not be observed from this run. It
  determines whether OBI's minimal capability set works or
  `CAP_SYS_ADMIN`/privileged is needed. This becomes Task 1.
- The deployed namespaces' `mctl.me/tenant` labels could not be read (no
  kubectl or namespace read tool in this run). If a tenant namespace was created
  by the ApplicationSet `CreateNamespace=true` fallback without the label, its
  telemetry is `unattributed`. That fails closed, but it lowers coverage.
- Whether `labs` should count as an independent "MCTL tenant" for the
  two-tenant proof, given that it hosts platform-adjacent services. The spike
  originally used `karabu` and `labs` because both have HTTP ingress workloads
  deployed. RESOLVED by the 2026-10-31 amendment: synthetic fixtures in two
  owner-controlled tenants; no customer workload.
  `namax66/news-factory` has no host and is a fallback only.
- `mctl-api`'s namespace and whether it already emits spans to the collector
  (mctl-api proposal issue-285) were not verified. The spike measures overlap
  rather than assuming it.
