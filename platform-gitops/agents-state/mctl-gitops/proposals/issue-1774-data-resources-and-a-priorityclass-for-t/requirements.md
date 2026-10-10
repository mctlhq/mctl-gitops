# Requests, limits and a PriorityClass for the shared-pg data path (PgBouncer pooler, CNPG operator, shared-pg instances)

## Context
The 2026-10-10 platform audit (finding REL-103) found that the pods on the critical
database path run without resources and without a custom PriorityClass. The PgBouncer
`Pooler` `shared-pg-pooler-rw` (`platform-gitops/infra-components/data/cnpg/shared/pooler.yaml`)
declares no `spec.template`, so both pooler pods are `BestEffort` and are the first pods the
kubelet evicts under node memory pressure. The CloudNativePG operator
(`platform-gitops/bootstrap/templates/data/cloudnative-pg.yaml`, chart `cloudnative-pg` 0.23.0)
is installed with chart defaults (`resources: {}`), so it is `BestEffort` too. The cluster
is memory-overcommitted (finding OPS-104), so eviction order decides whether a pressure
event takes down every database-backed service or just a low-value workload.

The issue asks for (1) requests/limits sized from observed p95 usage for the pooler and the
operator, (2) a gitops-declared `PriorityClass` (e.g. `platform-data-critical`, below
`system-cluster-critical`) assigned to the pooler, the operator and the `shared-pg` `Cluster`
instances, (3) no replica/node changes with before/after allocatable headroom stated in the
PR, and (4) the same treatment for hcloud-csi and system-upgrade-controller only if this
repo manages them. In this repo both are installed by the kube-hetzner Terraform module
(`infrastructure/k3s-preview/kube.tf`), not by ArgoCD, so they are left untouched.

## User stories
- AS a platform operator I WANT the PgBouncer pooler and the CNPG operator to run with
  explicit requests and limits SO THAT they are no longer `BestEffort` and are not the first
  pods evicted under node memory pressure.
- AS a platform operator I WANT a single gitops-declared PriorityClass for data-path
  components SO THAT the scheduler and kubelet rank shared Postgres, its pooler and its
  operator above ordinary tenant workloads.
- AS a tenant service owner I WANT the shared database path to survive node pressure SO THAT
  my service does not lose its database because a neighbour used too much memory.
- AS a reviewer I WANT the sizing query, the observed numbers and the per-node headroom in
  the PR SO THAT I can verify the new requests fit the current nodes.

## Acceptance criteria (EARS)
- WHEN root-app syncs THE SYSTEM SHALL create a cluster-scoped `PriorityClass` named
  `platform-data-critical` with `value: 1000000`, `globalDefault: false` and a description
  naming the data-path scope, declared in `platform-gitops/bootstrap/templates/system/priority-classes.yaml`.
- THE SYSTEM SHALL keep the `platform-data-critical` value strictly below
  `system-cluster-critical` (2000000000) and within the user-definable range (<= 1000000000).
- WHEN the `shared-pg` Application syncs THE SYSTEM SHALL render the `Pooler`
  `shared-pg-pooler-rw` with `spec.template.spec.containers[name=pgbouncer]` carrying CPU and
  memory requests and a memory limit, and `spec.template.spec.priorityClassName: platform-data-critical`.
- WHEN the `shared-pg` Application syncs THE SYSTEM SHALL render the `Cluster` `shared-pg`
  with `spec.priorityClassName: platform-data-critical`, leaving `spec.resources`,
  `spec.instances` and all other fields unchanged.
- WHEN the `cloudnative-pg` Application syncs THE SYSTEM SHALL pass Helm values
  `resources` (CPU and memory requests, memory limit) and `priorityClassName: platform-data-critical`
  to the chart, keeping `targetRevision: 0.23.0` and `crds.create: true`.
- WHILE the change is applied THE SYSTEM SHALL keep pooler `instances: 2`, Cluster
  `instances: 2`, the operator replica count and the node pools in `infrastructure/k3s-preview/kube.tf` unchanged.
- WHILE any pooler or operator pod runs THE SYSTEM SHALL report QoS class `Burstable` or
  `Guaranteed`, never `BestEffort`.
- WHEN the implementer sizes the requests THE SYSTEM SHALL use the p95 of
  `container_memory_working_set_bytes` and of CPU usage over at least the last 7 days from
  VictoriaMetrics (or `kubectl top` samples if history is unavailable), and the PR SHALL
  include the exact queries, the observed values and the chosen values.
- WHEN the PR is opened THE SYSTEM SHALL state, per node, allocatable minus summed requests
  (CPU and memory) before and after the change, and IF any node would drop below 0 headroom
  THEN the implementer SHALL reduce the new requests to fit rather than change nodes or replicas.
- IF hcloud-csi or system-upgrade-controller are not managed by any ArgoCD Application in
  this repo THEN THE SYSTEM SHALL leave them unchanged and the PR SHALL say they are installed
  by the kube-hetzner OpenTofu/Terraform layer.
- IF the `platform-data-critical` PriorityClass does not exist when a consumer pod is created
  THEN the pod is rejected by admission; therefore THE SYSTEM SHALL create the PriorityClass in
  an earlier sync wave of root-app than the child Applications that consume it.

## Out of scope
- Vault, Forgejo and MariaDB resources.
- The general requests-from-p95 recalculation for other workloads.
- Changing `shared-pg` instance resources (`spec.resources` in `cluster.yaml` is already sized).
- Changing replica counts, node counts or server types.
- Assigning the new PriorityClass to any other workload (Valkey, Temporal, MinIO, tenant apps).
- hcloud-csi and system-upgrade-controller (installed by `infrastructure/k3s-preview/kube.tf`).

## Open questions
- Whether the PriorityClass should use `preemptionPolicy: PreemptLowerPriority` (default) or
  `Never`. This proposal uses the default so a pending pooler/operator/Postgres pod can
  preempt tenant pods on a full node; reviewers who prefer no scheduler preemption can flip
  it to `Never` (kubelet eviction ordering still benefits either way).
- Whether to set a CPU limit on the pooler and operator. This proposal sets a CPU request and
  a memory limit but no CPU limit, to avoid CFS throttling of a latency-sensitive proxy (the
  shared-pg primary already hit 100% throttling on a CPU cap, see `cluster.yaml`). If the
  cluster's convention requires CPU limits, use a generous one (>= 4x the request).
- The exact numbers depend on live metrics the investigator could not read; the design gives
  floor values and the formula, and the implementer fills in measured values.
