# Tasks: issue-2286-spike-can-opentelemetry-ebpf-instrumenta

Step A only (default-off sandbox). Nothing in these tasks enables
`obiSpike`, loads BPF or runs a capability trial. That is mctl-gitops#2303.

- [ ] 1. Create `docs/spikes/2286-obi-evaluation.md` with
  `STATUS: PENDING_EXPERIMENT` and record the preconditions read-only, each with
  the command or source used:
  - the worker kernel version and `osImage`
    (`kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo}'`);
  - BTF presence (`/sys/kernel/btf/vmlinux`) and the kernel lockdown mode on
    `worker-cx43-fsn1`;
  - fixture tenants `labs` and `mctl`, and the platform workload
    `mctl-api/mctl-api`;
  - the expected `mctl.me/tenant` labels (from `helm-charts/tenant`);
  - the explicit `otel:` coverage (overlap-map skeleton);
  - the selected OBI feature subset;
  - the "Tenant identity today" finding (forgeable `mctl.team`).

  Copy the threshold table and the decision rule from design.md section 4
  verbatim, and add empty sections for #2303. — DoD: every fact has a source or
  says "not observed" (never "absent"); there are no measured values and no
  outcome.
- [ ] 2. Transcribe the OBI v1.0.0 security doc's capability and mount table
  (URL and revision recorded) for the selected subset. Apply the task 1
  kernel facts: add `SYS_RESOURCE` only if the kernel is below 5.11, and leave
  it out if that fact is not observed. Fix the provisional
  `capabilities.add` and `mounts`, and record the withheld capabilities
  (`SYS_ADMIN`, `NET_ADMIN`, `NET_RAW`, `SYS_RESOURCE`) with their conditions in
  the document. (depends on 1) — DoD: the doc table and design.md section 1
  agree, and every entry cites the doc.
- [ ] 3. Add the `obiSpike` block to `platform-gitops/bootstrap/values.yaml`
  exactly as in design.md section 1, with the task 2 results. It contains
  `enabled: false`, `allowPrivileged: false`, an empty `teardownAfter` and an
  empty `digest`, a comment on every capability and mount, the targets
  allowlist and the fixtures `tenantA: labs` and `tenantB: mctl`. Record the
  OBI v1.0.0 image repository and digest from the release notes. (depends on 2)
  — DoD: `helm template` of bootstrap with the default values is byte-identical
  to `main`.
- [ ] 4. Add `platform-gitops/bootstrap/templates/observability/obi-spike.yaml`,
  fully gated by `obiSpike.enabled`. It contains:
  - the namespace `observability-obi-spike` (PSA `privileged`, teardown
    annotation, `mctl.ai/purpose`, no `mctl.me/tenant`);
  - the default-deny and allow NetworkPolicies, ResourceQuota and LimitRange;
  - the additive `allow-otel-collector-ingress-obi-spike` policy in
    `monitoring`;
  - the OBI ServiceAccount, ClusterRole and DaemonSet (control-plane
    anti-affinity, no tolerations, digest image, explicit `securityContext`,
    `hostPID` and mounts from values), plus a ConfigMap whose
    `discovery.instrument` is generated from `obiSpike.targets`.

  (depends on 3) — DoD: the enabled overlay renders and passes `kubeconform`;
  the default render is unchanged.
- [ ] 5. Add the spike collector to `obi-spike.yaml`: Deployment
  (`otelcol-contrib:0.160.0`), ServiceAccount, ClusterRole, Service and
  `VMServiceScrape`. Wire the pipeline `transform/pre` -> `k8sattributes/obi`
  (association on `k8s.pod.uid` only; namespace label `mctl.me/tenant` ->
  `mctl.tenant.resolved`) -> `transform/attribution` -> shared `resource`,
  `redaction`, `filter/health` -> `batch`. Render `redaction` and
  `filter/health` from the same values as `otel-collector.yaml`. (depends on 4)
  — DoD: the rendered config has no association source other than
  `k8s.pod.uid`, no OTTL statement reads `mctl.team`, and the redaction blocks
  equal production's.
- [ ] 6. Add the gated fixture Deployments: `obi-fixture-tenant-a` (`labs`),
  `obi-fixture-tenant-b` (`mctl`), `obi-fixture-forged` (`labs`, with label
  `mctl.ai/team: mctl` and `OTEL_RESOURCE_ATTRIBUTES=mctl.tenant=mctl`) and
  `obi-fixture-unlabelled` (spike namespace, same forgery). Each is one replica
  at 10m/16Mi. (depends on 4) — DoD: the fixtures render only when enabled; no
  customer namespace appears in any rendered object.
- [ ] 7. Add `scripts/validate-obi-spike.py` with `--selftest`, and an enabled
  overlay `tests/fixtures/obi-spike.example-values.yaml` (a dummy digest and a
  `teardownAfter` injected relative to `--today`). Wire both into
  `.github/workflows/validate-manifests.yml` next to the otel-eval overlay
  step. (depends on 4-6) — DoD: the CI job is green on the PR, and the selftest
  proves every failure case in T2.

## Tests

- [ ] T1. `tests/test_obi_spike_render.py`: flag off renders zero OBI objects
  and the bootstrap output is byte-identical to the baseline. With the flag on,
  the test pins:
  - the exact `capabilities.add` list, `drop: [ALL]`, `privileged: false`,
    `hostPID: true`, `hostNetwork: false` and the hostPath list;
  - no tolerations and the required control-plane `DoesNotExist` affinity;
  - `discovery.instrument` equal to `obiSpike.targets` with no glob
    characters;
  - the ClusterRole verbs (`get`/`list`/`watch` only);
  - the absence of `mctl.me/tenant` on the spike namespace.
- [ ] T2. `scripts/validate-obi-spike.py --selftest` fails each of these when
  the spike is enabled:
  - missing, past or more than 14 days out `teardownAfter` (reuse the date
    logic of `scripts/validate-eval-teardown-date.py`);
  - empty image digest;
  - `privileged: true` or `SYS_ADMIN` in `add` while `allowPrivileged: false`;
  - any capability in `add` outside the pinned list;
  - an empty or globbed target;
  - any toleration.

  The default values pass.
- [ ] T3. `tests/test_obi_spike_attribution_e2e.py`, modelled on
  `tests/test_otel_collector_redaction_e2e.py` (Docker, real
  `otelcol-contrib:0.160.0`). It renders the spike collector config and swaps
  only `k8sattributes/obi` for a test-only `transform/fixture-metadata` that
  sets `mctl.tenant.resolved` and the namespace by `k8s.pod.uid` lookup. A
  static assertion separately pins the real `k8sattributes/obi` block. The test
  sends fixture spans and checks:
  - tenant A UID -> `mctl.tenant=labs`;
  - tenant B UID -> `mctl`;
  - `mctl-api` UID -> `unattributed`;
  - the forged-in-`labs` UID with `mctl.tenant=mctl` in its resource ->
    `labs`;
  - the unlabelled forged UID -> `unattributed` with no `mctl.tenant`;
  - an unknown UID -> `unattributed`.

  `--mutation {ip-association,read-team,keep-incoming}` must make the test
  fail.

## Rollback

- Nothing runs at merge, so rollback is `git revert` of the step A PR. There
  is no cluster state, no migration and no persisted data.
- If #2303 later enables the flag and something goes wrong, set
  `obiSpike.enabled: false` and merge. Argo CD then prunes the namespace,
  DaemonSet, collector, RBAC, fixtures and the additive `monitoring` policy.
  Production telemetry is untouched throughout, because the production
  collector config and `networkpolicy.yaml` are not modified.
- Emergency (worker instability during #2303): disable auto-sync on the root
  app, `kubectl -n observability-obi-spike delete daemonset obi`, then land
  the values revert.
