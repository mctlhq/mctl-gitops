# Spike step A: default-off OBI v1.0.0 sandbox with a pinned provisional privilege set, canonical tenant attribution and pre-registered thresholds

## Context

Issue mctlhq/mctl-gitops#2286 asks whether OpenTelemetry eBPF Instrumentation
(OBI) v1.0.0 can add useful zero-code RED metrics and traces on MCTL clusters.
Three conditions apply: tenant attribution must be deterministically correct,
runtime and API-server overhead must be acceptable, and the host-privilege
footprint must be acceptable. The owner's amendment of 2026-10-31 splits the
spike in two. **This proposal is step A only.** It ships a sandbox that is off
by default (`obiSpike.enabled: false`), a provisional least-privilege
capability set pinned by a render test, the canonical tenant-attribution
contract proven offline on fixture spans, and the evaluation document with
preconditions and pre-registered numeric thresholds
(`STATUS: PENDING_EXPERIMENT`). Enabling the sandbox, BPF loading, capability
trials, every live measurement and the final outcome
(`NO_FIT | PILOT_SELECTED_WORKLOADS | ADOPT_BOUNDED_OBI_LAYER`) belong to
step B, mctl-gitops#2303. Step B needs a separate explicit OK from the owner.

Step A matters for two reasons. The first is that today's telemetry tenant
identity is forgeable. The production collector
(`platform-gitops/bootstrap/templates/observability/otel-collector.yaml`,
`k8sattributes`) maps the pod label `mctl.ai/team` to `mctl.team`. That label
is not set by `base-service`, and tenants can set it themselves through
`podLabels`. The platform-controlled tenant key is the namespace label
`mctl.me/tenant`, which `helm-charts/tenant/templates/_helpers.tpl` writes.
Step A has to fix the attribution contract to that key before any OBI data
exists. The second reason is that OBI's privileges (`hostPID`, BPF-class
capabilities, host mounts) must be written explicitly in reviewed manifests
before step B, rather than inherited from a chart default.

## User stories

- AS the spike owner I WANT the whole OBI sandbox committed but inert SO THAT
  step B (#2303) is a reviewed values flip and nothing runs before I approve it.
- AS a security reviewer I WANT every capability, `hostPID` setting and host
  mount OBI would get written in `bootstrap/values.yaml` and pinned by a test
  SO THAT no privilege can be widened silently, by a chart default or by an
  unreviewed edit.
- AS a tenant owner I WANT OBI telemetry attributed only through the
  platform-controlled namespace label SO THAT labels or resource attributes
  set by another workload can never cause cross-tenant attribution.
- AS a reviewer of the eventual outcome I WANT numeric decision thresholds
  recorded before any measurement SO THAT step B cannot tune them to fit the
  results.

## Acceptance criteria (EARS)

### Default-off sandbox
- WHILE `obiSpike.enabled` is `false` (the committed default in
  `platform-gitops/bootstrap/values.yaml`) THE SYSTEM SHALL render no
  OBI-related object: no namespace, DaemonSet, collector, RBAC, fixture or
  NetworkPolicy peer. Every existing bootstrap template SHALL render
  byte-identical to its pre-change output.
- WHEN this proposal's PR merges THE SYSTEM SHALL NOT run any new workload,
  load any BPF program or grant any new capability on the cluster.
- WHEN `obiSpike.enabled` is `true` in any rendered overlay THE SYSTEM SHALL
  render the OBI DaemonSet with required node anti-affinity against
  `node-role.kubernetes.io/control-plane` and no tolerations.
- WHEN `obiSpike.enabled` is `true` THE SYSTEM SHALL build OBI's
  `discovery.instrument` only from the explicit `obiSpike.targets` list of
  (namespace, deployment) pairs. IF any target is empty or contains a glob
  metacharacter (`*`, `?`, `[`) THEN CI SHALL fail.

### Privilege pinning
- WHILE the sandbox is defined THE SYSTEM SHALL state the OBI container's
  `privileged`, `hostPID`, `hostNetwork`, `capabilities.drop`,
  `capabilities.add` and hostPath mounts explicitly under
  `obiSpike.securityContext` and `obiSpike.mounts`. Every added capability and
  every mount SHALL carry a comment naming the OBI feature that needs it and
  the source (the OBI v1.0.0 security docs or a recorded worker kernel/BTF
  fact).
- WHEN the enabled overlay is rendered THE SYSTEM SHALL produce exactly the
  pinned provisional set: `privileged: false`, `hostPID: true`,
  `hostNetwork: false`, `drop: [ALL]`, `add` equal to the pinned list, and the
  pinned mount list. A render test SHALL fail on any difference.
- IF a rendered OBI pod spec has `privileged: true` or adds `SYS_ADMIN` THEN CI
  SHALL fail, unless `obiSpike.allowPrivileged` is `true`. Step A commits
  `allowPrivileged: false`.
- WHEN `obiSpike.enabled` is `true` THE SYSTEM SHALL require
  `obiSpike.teardownAfter` to be a `YYYY-MM-DD` date that is not in the past and
  is at most 14 days ahead, and SHALL require an image pinned by digest. CI
  SHALL fail otherwise.

### Tenant attribution contract (proven offline)
- WHEN OBI telemetry reaches the spike collector THE SYSTEM SHALL resolve the
  tenant only through this chain: OBI-reported `k8s.pod.uid`, then pod, then
  namespace, then the namespace label `mctl.me/tenant`. It SHALL write the
  result to `mctl.tenant` and set `mctl.tenant.attribution=namespace-label`.
- WHEN a resource arrives with a producer-supplied `mctl.tenant` THE SYSTEM
  SHALL delete it before resolution, so that no application-controlled value
  survives.
- IF the pod cannot be resolved, or its namespace has no `mctl.me/tenant` label,
  THEN THE SYSTEM SHALL leave `mctl.tenant` unset and set
  `mctl.tenant.attribution=unattributed`. It SHALL never default to another
  tenant, to `admins`, to a synthetic "platform" tenant, or to a value from a
  pod label or resource attribute.
- WHILE attributing THE SYSTEM SHALL keep `mctl.ai/team`/`mctl.ai/component` only
  as evidence (`mctl.team`, `mctl.component`) and SHALL NOT read them to derive
  `mctl.tenant`.
- WHEN the offline attribution test runs THE SYSTEM SHALL show these results.
  The `labs` fixture resolves to `labs`. The `mctl` fixture resolves to `mctl`.
  The `mctl-api` platform workload resolves to `unattributed`. The forged
  fixture in `labs` (pod label `mctl.ai/team: mctl`, resource attribute
  `mctl.tenant=mctl`) resolves to `labs`. The forged fixture in the
  label-less spike namespace resolves to `unattributed`. An unknown pod UID
  resolves to `unattributed`. IF the test is run in mutation mode (association
  by connection IP, attribution read from `mctl.team`, or incoming
  `mctl.tenant` not deleted) THEN the test SHALL fail.

### Pre-registered evaluation document
- WHEN this proposal merges THE SYSTEM SHALL contain
  `docs/spikes/2286-obi-evaluation.md` with `STATUS: PENDING_EXPERIMENT`. The
  document SHALL record the preconditions (each with the command used to obtain
  it, or "not observed") and the numeric thresholds for: attribution (false,
  cross-tenant, unattributed), privilege, node CPU p95, OBI RSS per node,
  application latency p95, Kubernetes API list/watch load from OBI service
  accounts, and span/series cardinality delta. It SHALL also record the
  decision rule that maps those thresholds to exactly one outcome.
- WHILE the report status is `PENDING_EXPERIMENT` THE SYSTEM SHALL contain no
  measured values and no outcome.

## Out of scope

- Enabling the sandbox, loading BPF, trying capability reductions or a
  `privileged`/`CAP_SYS_ADMIN` fallback, any live measurement, the load
  generator, the outcome and teardown. All of these are mctl-gitops#2303.
- Any customer tenant workload as a target, including `karabu`, `namax66` and
  `erpact`.
- Changes to the production `otel-collector` pipeline or to
  `infra-components/observability/otel-collector/networkpolicy.yaml`. That
  file is a plain manifest and cannot be gated. The ingress for the spike
  collector is instead an additive NetworkPolicy in `obi-spike.yaml`, rendered
  only when the flag is on.
- Fixing the forgeable `mctl.team` in production. Step A records it as a
  finding, and a follow-up issue owns it.
- A sidecar deployment shape. It is assessed on paper only (design.md).
- Replacing the Collector, Tempo, VictoriaMetrics or Loki.

## Open questions

- **Worker kernel and BTF facts were not observed by this run.** No node read
  tool was available. Whether `/sys/kernel/btf/vmlinux` exists and the kernel is
  at least 5.11 on the three `worker-cx43-fsn1` nodes (kube-hetzner MicroOS,
  `automatically_upgrade_os = false` in `infrastructure/k3s-preview/kube.tf`)
  decides whether `SYS_RESOURCE` belongs in the provisional set. Task 1 records
  these facts read-only. If they stay unobserved, the pinned set keeps
  `SYS_RESOURCE` out, the document marks the fact "not observed", and #2303
  verifies it before enabling.
- The exact OBI v1.0.0 capability list per feature (application traces/metrics
  versus network metrics versus TC context propagation) is taken from the
  upstream security doc, which this run did not fetch. Task 2 transcribes it
  with the doc's revision. The provisional set in design.md is a starting
  hypothesis, and the doc wins if they differ.
- Whether OBI v1.0.0 emits `k8s.pod.uid` on exported resources depends on its
  own Kubernetes metadata decoration, which needs OBI's own informers and
  therefore API-server watches. The contract associates on pod UID only. If
  OBI cannot provide the UID, #2303 must record that every signal is
  `unattributed` (fails closed), which would push the outcome toward
  `NO_FIT`.
- Tenant B is `mctl`. It is owner-controlled and holds no workloads, but its
  quota is `pods: 1` and `requests.memory: 128Mi`, so the fixture must fit
  there. `commerce-proof` (`pods: 2`) was not chosen because it is reserved
  for the Agent Commerce live proof. The owner can swap tenant B by editing
  `obiSpike.fixtures`.
- The live `mctl.me/tenant` labels on the `labs` and `mctl` namespaces, and their
  absence on `mctl-api`, were not observed. The chart guarantees them, and
  #2303 verifies them live.
- The pre-registered threshold values in design.md are proposed by this
  investigation. The owner may adjust them in this PR's review. They freeze at
  merge.
