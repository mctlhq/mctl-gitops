# Agent-scoped compute ResourceQuota for mctl-agents pods in argo-workflows (807 G6)

## Context

Gap G6 of spike mctlhq/mctl-agents#807: the shared `argo-workflows` namespace
has no compute ResourceQuota and no LimitRange. Its only quota is the
storage-class quota `argo-workdir-local` in
`platform-gitops/argo-workflows/config/local-workdir-quota.yaml`. Each agent
step sets requests, limits and `activeDeadlineSeconds`, but the namespace does
not bound concurrent use. Only the `mctl-agents-proposal-claims` and
`mctl-gitops-main-writes` mutexes serialize anything, and they cover the claim
and gitops-write steps, not the model-driven steps. The heaviest step,
`run-implementer` in `cwft-mctl-agents-implement.yaml`, says so in its own
comment: "this step carries no mutex". DevLoop and epic waves can submit many
investigate and implement workflows at once, so one burst can take most of
the cluster's memory.

The issue asks for a quota model with a written capacity calculation. A
Kubernetes quota can only be scoped by PriorityClass, BestEffort, Terminating
or a few other built-in scopes. It cannot select on labels. This proposal
therefore:

- adds a PriorityClass whose only job is to scope the quota, with value 0
  (the priority agent pods get today) and `preemptionPolicy: Never`;
- adds a ResourceQuota scoped to that class;
- adds no LimitRange.

To keep the quota from rejecting agent pods for missing values (the #2043
failure class), every container in an agent pod gets explicit requests and
limits for CPU, memory and ephemeral storage. That covers Argo's own `init`
and `wait` containers and the global completion hook. Platform workflows and
tenant workloads keep their current sizing.

## User stories

- AS a platform operator I WANT the total compute that mctl-agents pods can
  hold in `argo-workflows` to have a fixed, written upper bound SO THAT a
  burst of agent runs cannot take the memory platform workflows and node
  daemons need.
- AS a platform operator I WANT platform workflows (create-tenant,
  provision-database, preview and lifecycle templates, janitors) to stay
  outside the agent quota SO THAT the agent budget can never block a platform
  operation.
- AS an on-call engineer I WANT a dedicated alert when the agent quota is
  exhausted SO THAT I can tell "quota is full, runs are queueing" from "the
  scheduler cannot place a pod".
- AS a security reviewer I WANT proof that the scoping PriorityClass does not
  change scheduling order, preemption or eviction ranking SO THAT priority is
  not used as an accidental security mechanism.

## Acceptance criteria (EARS)

- THE SYSTEM SHALL define a PriorityClass `mctl-agents-quota-scope` with
  `value: 0`, `globalDefault: false` and `preemptionPolicy: Never`, and SHALL
  document why these values keep scheduling order, preemption and kubelet
  eviction ranking the same as today for agent pods.
- THE SYSTEM SHALL define a ResourceQuota `mctl-agents-compute` in
  `argo-workflows` whose `scopeSelector` matches only pods with
  `priorityClassName: mctl-agents-quota-scope`. It SHALL bound `pods`,
  `requests.cpu`, `requests.memory`, `requests.ephemeral-storage`,
  `limits.cpu`, `limits.memory` and `limits.ephemeral-storage`, using the
  values in design.md "Capacity calculation".
- WHEN any mctl-agents ClusterWorkflowTemplate (approve, implement,
  investigate, reconcile, run (including daily and incidents through it),
  scout, shepherd, usage-collector) creates a pod, THE SYSTEM SHALL give that
  pod `priorityClassName: mctl-agents-quota-scope` through the workflow-level
  `spec.podPriorityClassName`. This SHALL also apply to exit handlers and the
  global completion hook.
- WHILE a pod carries `mctl-agents-quota-scope`, THE SYSTEM SHALL declare
  requests and limits for cpu, memory and ephemeral-storage on every
  container. That covers Argo's `init` and `wait` containers, user
  initContainers such as `wait-egress-proxy` and `clone-gitops`, main
  containers and the completion hook. No value SHALL come from a LimitRange
  default.
- THE SYSTEM SHALL NOT add any LimitRange to `argo-workflows`, so no platform
  or agent pod receives a resource default it did not declare.
- WHEN `scripts/validate-agent-quota-resources.py` runs in
  `validate-manifests.yml`, THE SYSTEM SHALL fail the build in these cases:
  an mctl-agents CWFT lacks `spec.podPriorityClassName:
  mctl-agents-quota-scope`; any container it can create lacks one of the six
  request/limit values; or the configured worst case for the intended
  concurrency exceeds the quota's hard values.
- IF creating an agent pod would push the scoped quota's usage above any hard
  value, THEN THE SYSTEM SHALL reject that pod at admission with
  `403 Forbidden: exceeded quota: mctl-agents-compute`, deterministically.
- WHILE the agent quota is fully used, THE SYSTEM SHALL keep admitting
  platform workflow pods in `argo-workflows` that do not carry the agent
  PriorityClass.
- WHEN the scoped quota's used/hard ratio for any tracked resource reaches 90%
  for 10 minutes, THE SYSTEM SHALL fire `ArgoAgentComputeQuotaHigh`. WHEN it
  reaches 100% for 5 minutes, THE SYSTEM SHALL fire
  `ArgoAgentComputeQuotaExhausted`. Both alerts SHALL be separate from the
  generic unschedulable-pod alerts.
- WHEN the change is rolled out, THE SYSTEM SHALL complete one deploy-service
  run and one run of each agent kind with expected concurrency, and none of
  them SHALL be rejected by the quota.
- IF a pod names `mctl-agents-quota-scope` before the PriorityClass exists,
  THEN the priority admission plugin rejects it. To prevent that, THE SYSTEM
  SHALL create the PriorityClass and ResourceQuota in an earlier sync wave of
  the same Argo CD Application than the templates that reference them.

## Out of scope

- Moving agent pods out of `argo-workflows` into their own namespace. #807
  decided `HARDEN_IN_PLACE`.
- A namespace-wide compute quota for platform workflows, and adding requests
  or limits to platform templates such as `wft-create-tenant.yaml` or
  `wft-provision-database.yaml`, most of which declare none today.
- Changing controller-wide `executor.resources` in
  `bootstrap/templates/core-infra/argo-workflows.yaml`. That setting would
  change Argo's init/wait sizing in every tenant namespace.
- Narrowing the `mctl-agents-proposal-claims` mutex, and any change to agent
  per-step budgets or `activeDeadlineSeconds`.
- Kubernetes apiserver `LimitedResources` admission configuration (k3s server
  flags).
- Tenant namespace quotas (`helm-charts/tenant/templates/resourcequota.yaml`).

## Open questions

- Intended agent concurrency. Neither the issue nor the repo states a target.
  This proposal assumes: implement 2, investigate 3, shepherd 1, run 2
  (incidents cron plus one on-demand), reconcile 1, approve 2, scout 1,
  usage-collector 1. The owner should confirm. In particular, an epic wave
  (`mctl_start_epic_wave`, `max_items_per_execute`) may need more than 3
  investigators. With the quota in place, more runs queue (Argo node Pending)
  instead of failing.
- Node allocatable and the platform reserve. The repo records one node figure
  only (worker-hnn, 15612Mi memory, in the `run-implementer` resource
  comment). Node count and allocatable CPU, memory and ephemeral storage could
  not be observed in this run. Task 1 must measure them and confirm that the
  quota's `requests.*` leave the platform reserve stated in design.md.
- Executor container sizing. The controller config sets no `executor`
  resources. Task 1 must read the live requests (if any) on Argo's
  `init`/`wait` containers and their 7-day peak working set before the
  `podSpecPatch` values in design.md become final.
- Whether the global completion hook actually runs inside agent workflows
  (they are launched by template reference; see the ttlStrategy note in
  `wft-deploy-service.yaml`). The design covers both cases. Task 1 confirms
  which one applies.
