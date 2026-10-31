# Design: issue-2291-security-agents-compute-resourcequota-an

## Current state

- **Quota today.** `platform-gitops/argo-workflows/config/local-workdir-quota.yaml`
  is the only ResourceQuota in `argo-workflows` (`argo-workdir-local`, storage
  class `requests.storage: 48Gi`). Nothing under `platform-gitops/` defines a
  LimitRange for that namespace. The only LimitRange in the repo is the
  per-tenant one in `helm-charts/tenant/templates/limitrange.yaml` (defaults
  50m/128Mi request, 500m/256Mi limit, max 1500m/3Gi).
- **Who deploys into the namespace.** The `argo-workflows-config` Application
  (`bootstrap/templates/core-infra/argo-workflows-config.yaml`, project
  `default`, path `platform-gitops/argo-workflows`, `directory.recurse: true`)
  syncs `config/` and `cluster-templates/` into `argo-workflows`. The
  `argo-workflows` Helm Application (`core-infra/argo-workflows.yaml`, chart
  0.47.5) deploys the controller (250m/256Mi request, 900m/512Mi limit) and
  the server (50m/128Mi, 250m/384Mi) there.
- **Controller config.** The controller config sets no `executor.resources`.
  `workflowDefaults` adds a global exit hook,
  `cwft-global-workflow-completion-hook.yaml` (`notify-completion`,
  `python:3.12-alpine`), whose container declares **no resources**.
  `workflowRestrictions.templateReferencing: Strict`, so a Workflow cannot
  carry its own `podSpecPatch`, but a ClusterWorkflowTemplate can.
- **Agent templates.** `cluster-templates/cwft-mctl-agents-{approve,implement,investigate,reconcile,run,scout,shepherd,usage-collector}.yaml`.
  `cwft-mctl-agents-daily.yaml` and `cronworkflow-mctl-agents-incidents.yaml`
  reference `mctl-agents-run`. All of them set
  `podMetadata.labels.app.kubernetes.io/name: mctl-agents`, a spec-level
  `activeDeadlineSeconds` (600 to 28800) and `onExit: notify-telegram`. None
  sets a `priorityClassName` or a `podSpecPatch`. Measured per-container
  values:

  | Template / step | requests (cpu/mem/eph) | limits (cpu/mem/eph) |
  |---|---|---|
  | implement `run-implementer` | 200m / 3Gi / 10Gi | 3000m / 8Gi / 11Gi |
  | shepherd main | 200m / 1Gi / 8Gi | 2000m / 8Gi / 9Gi |
  | investigate main | 200m / 1Gi / 4Gi | 2000m / 4Gi / 5Gi |
  | run main | 200m / 512Mi / 1Gi | 2000m / 2Gi / 2Gi |
  | reconcile main | 100m / 256Mi / 2Gi | 1000m / 1Gi / 3Gi |
  | scout main | 100m / 256Mi / 256Mi | 1 / 1Gi / 512Mi |
  | usage-collector main | 100m / 128Mi / 256Mi | 500m / 512Mi / 512Mi |
  | approve heaviest step | 50m / 128Mi / 1Gi | 500m / 512Mi / 2Gi |
  | clone/commit helper steps | 50m / 64Mi / 1-10Gi | 200-500m / 256Mi / 2-11Gi |
  | `wait-egress-proxy` initContainer (every agent template) | 10m / 8Mi / **none** | 50m / 16Mi / **none** |

  Argo's own `init` and `wait` containers get **no declared resources** from
  any template. The only fan-out bounds are template-level mutexes:
  `mctl-agents-proposal-claims` (implement line 465) and
  `mctl-gitops-main-writes` (commit steps). `run-implementer` "carries no
  mutex" (its own comment). The CronWorkflows (incidents, scout, shepherd,
  usage-collector) use `concurrencyPolicy: Forbid`. investigate and implement
  are also submitted by mctl-api DevLoop and epic waves without a concurrency
  bound.
- **#2043 failure class in this namespace.** A quota that tracks a resource
  requires every container in every pod it counts to declare that resource.
  Today such a quota would reject:
  - every pod, because of the init/wait containers;
  - the completion hook;
  - `wait-egress-proxy` and any other container without ephemeral-storage;
  - every platform template that declares no resources at all. These are
    0 `resources:` blocks in `wft-create-tenant.yaml`,
    `wft-provision-database.yaml`, `wft-retire-service.yaml`,
    `wft-delete-tenant-safe.yaml`, `wft-smoke-test.yaml`,
    `wft-add-custom-domain.yaml`, `wft-rollback-service.yaml`,
    `tpl-git-commit.yaml`, `tpl-vault-write.yaml`,
    `cwft-rotate-github-token.yaml`, `cwft-zitadel-login-consolidation.yaml`
    and `cwft-global-workflow-completion-hook.yaml`.
- **deploy-service** (`wft-deploy-service.yaml`) runs in the tenant namespace
  (its comment: "this workflow runs in the tenant namespace (mctl-api
  operations.WorkflowNamespace)"). It already patches Argo's `init` and `wait`
  containers with a spec-level `podSpecPatch`. That is the precedent this
  design reuses, and it shows the emissary `init` container is always present.
- **Other workloads in the namespace.** The `pvc-janitor`,
  `stuck-pv-janitor` and `mutex-forensics-watchdog` CronJobs in `config/`
  declare resources (10m/32-64Mi, 200m/128Mi+) and carry no PriorityClass.
- **PriorityClasses.** The only one in git is `platform-data-critical`
  (`infra-components/data/cnpg/shared/priority-class.yaml`, value 100000000,
  `globalDefault: false`). Its comment states that unclassed pods "tie with
  every tenant workload at priority 0". No `globalDefault` class is defined
  in git.
- **Alerts.** `infra-components/observability/vm-rules/mctl-alerts.yaml` has
  `TenantCPUQuotaHigh` and `TenantMemoryQuotaHigh`, which sum
  `kube_resourcequota{type="hard",resource="limits.cpu|memory"}` **by
  namespace**, and `ArgoLocalWorkdirQuotaHigh/Critical` for the storage
  quota. CI check: `scripts/check-vm-rules.sh` plus
  `vm-rules/tests/mctl-alerts_test.yaml`.
- **Validator precedent.** `scripts/validate-agent-pod-security.py` (with
  `--selftest`, wired in `.github/workflows/validate-manifests.yml` around
  line 265) walks the CWFTs and fails on agent steps that miss a posture.

Deployed state checked:
- `mctl_list_recent_agent_runs`: **error**, "admin group membership
  required". Live agent concurrency was not observed. The intended
  concurrency below is an assumption (see Open questions).
- Node allocatable, live executor container resources, live PriorityClasses
  (including whether k3s or the cluster has a `globalDefault` class not in
  git) and live `kube_resourcequota` series: **not observable** with the
  read-only tools in this run. Task 1 measures them. Absence in git is not
  treated as absence in the cluster.
- `$MCTL_GITOPS_ROOT/services` and `tenants`: not relevant. No tenant service
  config is changed by this proposal.
- The #807 report `docs/spikes/807-agent-isolation-k8s.md` lives in
  mctl-agents and is not in this clone. The issue's summary of G6 was used.

## Proposed solution

### Model choice: option 1, an agent-scoped quota through a PriorityClass

Option 2, a namespace-wide quota, is rejected for two reasons. It would count
platform workflow pods, and at least 12 platform templates declare no
resources at all, so they would be rejected outright (#2043). Fixing that
would mean adding resources to every platform template or adding a LimitRange
default, and the issue forbids unreviewed defaults. A namespace-wide limit
would also let an agent burst use up platform headroom, which is the exact
failure G6 describes.

Kubernetes `ResourceQuota.spec.scopeSelector` supports only `PriorityClass`,
`Terminating`/`NotTerminating`, `BestEffort`/`NotBestEffort`,
`CrossNamespacePodAffinity` and `VolumeAttributesClass`. It has no label
selector, so a PriorityClass is the only supported way to scope a quota to
agent pods.

### New objects (in `platform-gitops/argo-workflows/config/`)

1. `agent-quota-priority-class.yaml`:
   ```yaml
   apiVersion: scheduling.k8s.io/v1
   kind: PriorityClass
   metadata:
     name: mctl-agents-quota-scope
     annotations:
       argocd.argoproj.io/sync-wave: "-1"
   value: 0
   globalDefault: false
   preemptionPolicy: Never
   description: Quota scoping only (gitops#2291). Same priority as an unclassed pod.
   ```
   **Why scheduling semantics do not change.**
   - Priority: a pod without `priorityClassName` gets priority 0 when no
     `globalDefault` class exists (task 1 verifies this live). With
     `value: 0`, agent pods keep exactly the priority they have now.
   - Scheduling queue: the queue orders by priority, then by timestamp.
     Equal priority means equal order.
   - Preempting others: a pod can only preempt pods of strictly lower
     priority. Today an agent pod at 0 could preempt only negative-priority
     pods, and none exist. `preemptionPolicy: Never` removes even that
     possibility, so agents gain no preemption ability. Today they have none
     in practice.
   - Being preempted: a pod is a preemption victim based on its own priority
     value (0), not on its own preemptionPolicy. So `platform-data-critical` and the
     system classes can still preempt agent pods, exactly as today.
   - Kubelet eviction ranking: this uses usage above requests, then priority.
     Priority is unchanged at 0, so ranking is unchanged.
   - Other pods: `globalDefault: false`, so no other pod is affected.

   The YAML comment records this argument, in the same style as the
   `platform-data-critical` comment.

2. `agent-compute-quota.yaml`: ResourceQuota `mctl-agents-compute` with
   `scopeSelector.matchExpressions: [{scopeName: PriorityClass, operator: In, values: [mctl-agents-quota-scope]}]`,
   sync-wave `-1`, and the hard values from the capacity calculation below.

3. **No LimitRange.** A Container-type LimitRange is namespace-wide. A `max`
   without a `default` makes the LimitRanger use the max as the default
   limit, and a Pod-type `max` requires limits on every container. Either
   would change or reject the platform templates that declare nothing. Not
   adding a LimitRange is what makes acceptance "no pod admitted merely
   because LimitRange injected a default" true by construction.

### Template changes (agent CWFTs only)

For each of `cwft-mctl-agents-{approve,implement,investigate,reconcile,run,scout,shepherd,usage-collector}.yaml`:

- Add `spec.podPriorityClassName: mctl-agents-quota-scope`. A spec-level
  field covers every pod of the workflow, including `onExit` handlers and the
  global hook. daily and incidents inherit it through
  `workflowTemplateRef: mctl-agents-run`.
- Add a spec-level `podSpecPatch` that sizes Argo's executor containers. The
  shape follows `wft-deploy-service.yaml`:
  ```yaml
  podSpecPatch: |
    initContainers:
      - name: init
        resources:
          requests: {cpu: 10m, memory: 64Mi, ephemeral-storage: 16Mi}
          limits:   {cpu: 200m, memory: 128Mi, ephemeral-storage: 128Mi}
    containers:
      - name: wait
        resources:
          requests: {cpu: 10m, memory: 64Mi, ephemeral-storage: 64Mi}
          limits:   {cpu: 500m, memory: 256Mi, ephemeral-storage: 1Gi}
  ```
  These are provisional. Task 1 replaces them with the live requests plus at
  least 2x the measured 7-day peak working set. This keeps the change limited
  to agent pods. The controller-wide `executor.resources` is left unchanged,
  so tenant namespaces keep their current executor sizing.
- Add `ephemeral-storage` (request 8Mi, limit 64Mi) to every
  `wait-egress-proxy` initContainer. Add whatever task 2's validator finds
  missing on any other agent container. CPU and memory values that already
  exist are not changed.

### Shared template change

`cwft-global-workflow-completion-hook.yaml` `notify-completion` gets explicit
resources: requests 50m/128Mi/16Mi, limits 500m/256Mi/256Mi.

- CPU and memory equal the tenant LimitRange defaults
  (`helm-charts/tenant/values.yaml` `limitRange`), which the hook already
  receives in tenant namespaces today. Tenant quota consumption is therefore
  unchanged.
- In `argo-workflows` the hook moves from BestEffort to Burstable. That only
  makes it less likely to be evicted.
- Tenant quotas do not track ephemeral storage, so the new
  ephemeral-storage values affect no tenant quota.
- This is the one workload that receives new values outside agent
  templates. It is recorded here and in the YAML comment.

### Validator

New `scripts/validate-agent-quota-resources.py` (with `--selftest`, wired in
`validate-manifests.yml` next to `validate-agent-pod-security.py`). It
fails:

- if a CWFT with `podMetadata.labels.app.kubernetes.io/name: mctl-agents`
  lacks `podPriorityClassName: mctl-agents-quota-scope` or the executor
  `podSpecPatch`;
- if any container reachable from it (initContainers, sidecars, containers,
  scripts, templateRef targets, the global hook) lacks requests or limits
  for cpu, memory or ephemeral-storage;
- if a non-agent template names `mctl-agents-quota-scope`;
- if the per-kind worst-case pod multiplied by `CONCURRENCY` (a table in the
  script that mirrors the capacity calculation) is larger than the hard
  values parsed from `agent-compute-quota.yaml`. This keeps the calculation
  and the object from drifting apart.

### Capacity calculation

Each Argo workflow runs one step pod at a time (sequential steps), and
exit-handler pods follow the main steps. A pod's footprint is its main
container plus `wait`. The `init` and user initContainers are smaller than
main and do not add to it, because the effective value is
max(sum(containers), max(initContainers)). With the provisional `wait`
values (10m/64Mi/64Mi request, 500m/256Mi/1Gi limit), the worst-case pod per
kind is:

| Kind | Intended concurrency | req cpu | req mem | req eph | lim cpu | lim mem | lim eph |
|---|---|---|---|---|---|---|---|
| implement | 2 | 210m | 3136Mi | 10.06Gi | 3.5 | 8.25Gi | 12Gi |
| investigate | 3 | 210m | 1088Mi | 4.06Gi | 2.5 | 4.25Gi | 6Gi |
| shepherd | 1 | 210m | 1088Mi | 8.06Gi | 2.5 | 8.25Gi | 10Gi |
| run (daily/incidents/on-demand) | 2 | 210m | 576Mi | 1.06Gi | 2.5 | 2.25Gi | 3Gi |
| reconcile | 1 | 110m | 320Mi | 2.06Gi | 1.5 | 1.25Gi | 4Gi |
| approve | 2 | 60m | 192Mi | 1.06Gi | 1.0 | 768Mi | 3Gi |
| scout | 1 | 110m | 320Mi | 0.3Gi | 1.5 | 1.25Gi | 1.5Gi |
| usage-collector | 1 | 110m | 192Mi | 0.3Gi | 1.0 | 768Mi | 1.5Gi |
| **Sum (13 pods)** | | **2.13** | **12.7Gi** | **47.3Gi** | **28** | **46.75Gi** | **71Gi** |

- **Burst headroom.** 25% on top of the sum covers exit-handler and
  completion-hook pods that overlap a workflow's last step, and one extra
  short run. Values are rounded up.
- **Hard values:**
  - `pods: "20"`
  - `requests.cpu: "3"`
  - `requests.memory: 16Gi`
  - `requests.ephemeral-storage: 60Gi`
  - `limits.cpu: "36"`
  - `limits.memory: 60Gi`
  - `limits.ephemeral-storage: 90Gi`
- **Platform reserve.** The scheduler places pods by requests, so
  `requests.*` is the real bound on what agents can take from platform
  workflows. Limits are overcommitted by design, exactly as today. Bounding
  their total caps the worst-case burst that a node can see. Task 1 must show
  that agent `requests.memory` (16Gi) plus the platform reserve fits within
  cluster allocatable minus DaemonSet and system-reserved usage. The platform
  reserve is the sum of controller, server, janitors, and 3 concurrent
  platform workflows at the tenant-default sizing of 500m/256Mi per
  container. If it does not fit, the concurrency table is reduced; the
  platform reserve is not. The reserve is protected because platform pods
  are outside the scope: the quota never counts them, so an exhausted agent
  quota cannot block them.
- **Over-quota behaviour.**
  - The apiserver rejects a pod creation deterministically with `403
    exceeded quota: mctl-agents-compute`.
  - Argo treats that error as transient. The node stays Pending with the
    quota message and is retried, so excess agent runs queue instead of
    failing.
  - A single pod larger than the remaining quota stays Pending until its
    workflow `activeDeadlineSeconds`. One larger than the whole quota (for
    example memory request above 16Gi) can never be admitted, and the
    validator blocks it in CI.

### Alerts

New group `mctl.argo-agent-quota` in `vm-rules/mctl-alerts.yaml`:

- `ArgoAgentComputeQuotaHigh`:
  `kube_resourcequota{namespace="argo-workflows",resourcequota="mctl-agents-compute",type="used"} / ignoring(type) kube_resourcequota{...,type="hard"} > 0.9`
  for 10m, severity warning.
- `ArgoAgentComputeQuotaExhausted`: the same expression `>= 1` for 5m,
  severity warning. The annotation says "agent runs are queueing on quota,
  not on node capacity".

Quota rejection means no pod object is created, so it cannot trigger the
unschedulable-pod or FailedScheduling alerts. Those fire only for pods that
exist. The two causes are therefore distinguishable by alert name.

`TenantCPUQuotaHigh` and `TenantMemoryQuotaHigh` get
`namespace!="argo-workflows"` on the hard side. Otherwise they would divide
the whole namespace's usage, platform pods included, by the agent-only hard
value. Tests are added in `vm-rules/tests/mctl-alerts_test.yaml`.

### Rollout order

- PriorityClass and ResourceQuota use sync-wave `-1` in the same
  `argo-workflows-config` Application as the CWFTs. The priority admission
  plugin rejects a pod that names a missing class, so the class must exist
  first.
- Ship in two PRs:
  1. PR 1: resources, executor patch, hook resources, PriorityClass,
     validator and alerts. Nothing is enforced yet; the quota is created with
     the hard values but nothing names the class.
  2. PR 2: `podPriorityClassName` on the agent templates, which activates
     the quota. AMENDMENT 2026-10-31: PR 2 is OUT OF SCOPE of this proposal
     and is mctl-gitops#2299 (step B), started only after the owner confirms
     the measured per-kind concurrency. This proposal implements PR 1 only.

  Between them, task 6 confirms on live pods that every container has all
  six values.

## Alternatives

1. **Namespace-wide quota with platform headroom (option 2).** Dropped. It
   rejects about 12 resource-less platform templates unless they are all
   resized or a LimitRange injects defaults. It also lets agents use up
   platform headroom.
2. **Scope by `Terminating` (pods with `activeDeadlineSeconds`).** No
   PriorityClass is needed, but it also matches platform workflow pods that
   inherit a deadline. Argo sets pod `activeDeadlineSeconds` from the
   workflow deadline, so the scope would be ambiguous and unstable. Dropped.
3. **Set controller `executor.resources` and add a LimitRange for
   defaults.** Simpler templates, but it changes init/wait sizing in every
   tenant namespace and gives defaults to platform pods. Both are things the
   issue asks not to do silently. Dropped in favour of a per-template
   `podSpecPatch`.
4. **More mutexes or semaphores (Argo `synchronization` with a ConfigMap
   semaphore per kind).** These bound workflow concurrency, not resources,
   and they do not reject an oversize pod. They could complement the quota
   later. Not chosen as the G6 control.

## Platform impact

- **Migration and backward compatibility.** Additive objects only. Agent
  CPU and memory values are unchanged; agent pods gain executor and
  ephemeral-storage values. Agent QoS stays Burstable. No tenant namespace
  sizing changes. The completion hook gets CPU and memory values equal to
  what tenant LimitRanges already inject.
- **Resource impact.**
  - Explicit `wait` limits could OOM-kill the wait container on large log or
    artifact uploads. Mitigation: size from 7-day peak x2 (task 1), and
    watch `kube_pod_container_status_last_terminated_reason{container="wait"}`
    during the rollout.
  - The ephemeral-storage limit on `wait-egress-proxy` and executor
    containers could cause evictions if exceeded. These containers write
    almost nothing; this is measured in task 1.
- **Risk: agent queueing.** Runs beyond the intended concurrency now wait as
  Pending instead of starting, and their spec-level `activeDeadlineSeconds`
  keeps running. implement already accounts for queueing (28800s); for
  investigate (7200s) a deep wave could expire while queued. Mitigation:
  `ArgoAgentComputeQuotaExhausted` alerts first, and the open question on
  wave size is resolved before PR 2.
- **Risk: a missing value on a future template.** The new validator fails
  CI, which is the guard against #2043 recurring.
- **Risk: a hidden live `globalDefault` PriorityClass with a non-zero value.**
  In that case value 0 would lower agent priority. Task 1 checks this, and
  the PriorityClass value must equal the live default, or the PR stops for
  approval.
- **Security.** The quota bounds the namespace-level compute that agent pods
  can use. Strict template referencing prevents a submitter from removing
  the class through a Workflow-level override. Task 1 also confirms, from
  `config/sa-and-rbac.yaml`, that no agent service account can create pods
  directly and so bypass the class.
  Rollback is deleting the objects and template fields.
