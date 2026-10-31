# Tasks: issue-2286-spike-can-opentelemetry-ebpf-instrumenta

- [ ] 1. Record preconditions in `docs/spikes/2286-obi-evaluation.md` (new): the
  worker kernel version and BTF presence (`/sys/kernel/btf/vmlinux`) on the
  `worker-cx43-fsn1` nodes; the choice of two owner-controlled tenants for the synthetic
  fixtures (`labs` plus one of `mctl`, `admins`, `commerce-proof`; never a
  customer tenant) and the live `mctl.me/tenant` label on their namespaces and
  on `mctl-api`; whether `mctl-api` already emits spans to
  `otel-collector`; and the current span rate and VMSingle series baseline.
  Also record the decision thresholds from design.md before any measurement,
  including numeric limits for OBI RSS per node, API list/watch load and
  cardinality delta.
  - DoD: each fact is recorded with the command used to get it. Anything
    unobservable is marked "not observed", never "absent".
- [ ] 2. Add the `obiSpike` values block (default `enabled: false`) to
  `platform-gitops/bootstrap/values.yaml`. Pin the OBI v1.0.0 image and chart.
  Fill `securityContext.capabilities.add`, `hostPID` and `mounts` with the
  minimum set that loads on the workers (try without `SYS_ADMIN` or
  privileged first). (depends on 1)
  - DoD: the values block exists. Every capability and mount has a one-line
    comment saying which OBI feature needs it.
- [ ] 3. Add `platform-gitops/bootstrap/templates/observability/obi-spike.yaml`
  with the namespace (PSA privileged, teardown annotation, no
  `mctl.me/tenant`), default-deny NetworkPolicies, ResourceQuota, the OBI
  Application with the control-plane anti-affinity and an explicit
  `discovery.instrument` built from `obiSpike.targets`, the spike collector
  Deployment, its ClusterRole and Service, and the `VMServiceScrape`. Add the
  gated `observability-obi-spike` ingress peer to
  `infra-components/observability/otel-collector/networkpolicy.yaml`.
  (depends on 2)
  - DoD: `helm template` renders nothing with the flag off and the full set
    with it on. Existing render outputs are byte-identical with the flag off.
- [ ] 4. Implement the attribution chain in the spike collector config:
  `k8sattributes/obi` (pod-UID-only association, namespace label
  `mctl.me/tenant`), then `transform/attribution` (delete the incoming
  `mctl.tenant`, set it from the namespace label or mark `unattributed`), then
  the shared `redaction`/`filter/health` values, then `batch`. (depends on 3)
  - DoD: the rendered config contains no association source other than
    `k8s.pod.uid`, and no OTTL statement reads `mctl.team`.
- [ ] 5. Add the synthetic tenant fixtures `obi-fixture-tenant-a` and
  `obi-fixture-tenant-b` (tiny HTTP servers in the two tenants from task 1,
  rendered only while the spike is enabled), the negative fixture
  `obi-fixture-forged` (pod label `mctl.ai/team: <tenant A>`,
  `OTEL_RESOURCE_ATTRIBUTES=mctl.tenant=<tenant B>`) and the load CWFT
  `argo-workflows/cluster-templates/wft-obi-spike-load.yaml`, which sends a
  fixed request mix to the two tenant fixtures, `mctl-api` and the forged
  fixture. No customer host is a target. (depends on 3)
  - DoD: the CWFT is registered and inert until submitted. It has no
    CronWorkflow.
- [ ] 6. Out of scope: enabling the spike, measuring, the report's outcome and
  teardown (former tasks 6-8 and T4) are mctl-gitops#2303. This proposal's PR
  keeps `obiSpike.enabled: false`. — DoD: nothing new runs on the cluster;
  the report holds preconditions and all pre-registered thresholds, with
  `STATUS: PENDING_EXPERIMENT`.

## Tests

- [ ] T1. `tests/test_obi_spike_render.py`: with the flag off, nothing renders
  and every other bootstrap template is byte-identical. With the flag on, the
  test pins the exact capability set, `hostPID`, `hostNetwork: false`, the
  hostPath list, no tolerations, the control-plane anti-affinity, and
  `discovery.instrument` equal to `obiSpike.targets` with no wildcards.
- [ ] T2. A CI guard (extend `scripts/validate-eval-teardown-date.py` or add
  `scripts/validate-obi-spike.py` with `--selftest`): it fails when the spike
  is enabled with a missing, past or more-than-14-days `teardownAfter`, or
  when `privileged: true` is set without `obiSpike.allowPrivileged: true`.
  Wire it into `.github/workflows/validate-manifests.yml`.
- [ ] T3. `tests/test_obi_spike_attribution_e2e.py` (pattern of
  `test_otel_collector_redaction_e2e.py`): runs the rendered spike collector
  processors on fixture spans and checks four cases. The tenant A fixture pod resolves
  to tenant A. The tenant B fixture pod resolves to tenant B. A forged-label pod
  in a non-tenant namespace resolves to `unattributed` with no `mctl.tenant`.
  An unknown pod UID resolves to `unattributed`. A `--mutation` flag swaps
  association to connection IP or reads `mctl.team`, and the test must then
  fail.
- [ ] T4. Moved to mctl-gitops#2303 (live check during the experiment).

## Rollback

- Fastest: set `obiSpike.enabled: false` in `platform-gitops/bootstrap/values.yaml`
  and merge. ArgoCD prunes the OBI DaemonSet, spike collector, RBAC, fixture
  and namespace, and the production collector NetworkPolicy peer disappears
  with the flag. Production traces and metrics are untouched throughout,
  because the production collector config is not modified.
- Emergency (host instability on a worker): `kubectl -n argocd patch
  application obi-spike` to disable auto-sync, then
  `kubectl -n observability-obi-spike delete daemonset --all`, then land the
  values revert.
- Full: `git revert` of the spike PRs. No migrations or persistent state exist,
  apart from spans already in Tempo, which age out under Tempo retention.
