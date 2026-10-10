# Design: issue-1774-data-resources-and-a-priorityclass-for-t

## Current state
- `platform-gitops/infra-components/data/cnpg/shared/pooler.yaml`: `Pooler`
  `shared-pg-pooler-rw`, `instances: 2`, `type: rw`, PgBouncer in transaction mode
  (`max_client_conn: 400`, `default_pool_size: 20`). It has no `spec.template`, so CNPG
  generates a pod with no resources -> QoS `BestEffort`, and no priority class.
- `platform-gitops/infra-components/data/cnpg/shared/cluster.yaml`: `Cluster` `shared-pg`,
  `instances: 2`, `spec.resources` already set (requests 500m / 2Gi, limits 2 CPU / 2Gi, with
  OOM and throttling history in comments). No `spec.priorityClassName`.
- Both files are synced by the `shared-pg` Application
  (`platform-gitops/bootstrap/templates/data/shared-pg.yaml`, path
  `platform-gitops/infra-components/data/cnpg/shared`, namespace `platform-db`,
  `ignoreDifferences` on Cluster annotations/labels/status only).
- `platform-gitops/bootstrap/templates/data/cloudnative-pg.yaml`: Application installing the
  upstream chart `cloudnative-pg` 0.23.0 into `cnpg-system` with only `crds.create: true`, so
  chart defaults apply (`resources: {}`, `priorityClassName: ""`) -> `BestEffort`.
- No custom `PriorityClass` exists anywhere in the repo. The only `priorityClassName` in
  gitops is `system-node-critical` on the local-path-provisioner helper pod
  (`platform-gitops/bootstrap/templates/core-infra/local-path-provisioner.yaml`).
- Cluster-scoped platform objects that are not part of a third-party chart are rendered
  directly by the root-app Helm chart (`platform-gitops/bootstrap`, chart `mctl-apps`), e.g.
  `platform-gitops/bootstrap/templates/system/admission-policies.yaml`
  (ValidatingAdmissionPolicies). root-app manages itself
  (`platform-gitops/bootstrap/templates/bootstrap/root-app.yaml`).
- Nodes (`infrastructure/k3s-preview/kube.tf`): 1 x `cx33` control plane (4 vCPU / 8 GB,
  untainted) and 3 x `cx43` workers (8 vCPU / 16 GB). hcloud-csi (StorageClass
  `hcloud-volumes`, used by `cluster.yaml`) and system-upgrade-controller
  (`system_upgrade_use_drain = true`, `install_k3s_version` pinning the Plans) are installed by
  the kube-hetzner module; no ArgoCD Application in this repo manages them. The repo only
  alerts on them (`platform-gitops/infra-components/observability/vm-rules/mctl-alerts.yaml`,
  `namespace="system-upgrade"`).

## Proposed solution

### 1. PriorityClass (new file)
`platform-gitops/bootstrap/templates/system/priority-classes.yaml`:
```yaml
# Data-path priority (REL-103). Above every tenant/default (0) workload,
# below system-cluster-critical (2000000000), within the user range (<= 1e9).
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: platform-data-critical
  annotations:
    argocd.argoproj.io/sync-wave: "-1"
value: 1000000
globalDefault: false
preemptionPolicy: PreemptLowerPriority
description: >-
  Shared Postgres data path: shared-pg instances, the PgBouncer pooler and the
  CloudNativePG operator. Do not assign to tenant workloads.
```
It lives next to `admission-policies.yaml` because it is a cluster-scoped platform primitive,
not part of any one data component. The negative sync wave makes root-app create it before
the child Applications are (re)applied; pods referencing a missing PriorityClass are rejected
at admission, so ordering matters on first rollout and on from-zero rebuilds. `value` leaves
room for a future lower tier (e.g. `platform-critical` at 100000) without renumbering.

### 2. Pooler resources and priority
Add to `pooler.yaml`:
```yaml
  template:
    metadata: {}
    spec:
      priorityClassName: platform-data-critical
      containers:
        - name: pgbouncer   # CNPG merges by this name; must match exactly
          resources:
            requests:
              cpu: <p95 cpu, floor 50m>
              memory: <p95 working set x1.25, floor 64Mi>
            limits:
              memory: <max(2x request, observed max x1.5), floor 128Mi>
```
No CPU limit: PgBouncer is single-threaded and latency-sensitive; throttling it throttles every
database client. The memory limit protects the node from a runaway pool.

### 3. shared-pg Cluster priority
Add `priorityClassName: platform-data-critical` under `spec` in `cluster.yaml`. Instance
resources are untouched (already Burstable with explicit sizing). CNPG rolls the pods to apply
it; with `primaryUpdateMethod: restart` / `primaryUpdateStrategy: unsupervised` it updates the
standby first, then restarts the primary in place.

### 4. CNPG operator values
Extend the Helm `values` in `cloudnative-pg.yaml`:
```yaml
        crds:
          create: true
        priorityClassName: platform-data-critical
        resources:
          requests:
            cpu: <p95 cpu, floor 50m>
            memory: <p95 working set x1.25, floor 128Mi>
          limits:
            memory: <max(2x request, observed max x1.5), floor 256Mi>
```
Both keys exist in chart 0.23.0's `values.yaml` and are templated into the operator
Deployment. The implementer verifies with
`helm template cnpg cloudnative-pg/cloudnative-pg --version 0.23.0 -f <values>`.

### 5. Sizing procedure (PR body)
VictoriaMetrics, 7-day window:
```
quantile_over_time(0.95, sum by (pod) (container_memory_working_set_bytes{namespace="platform-db", pod=~"shared-pg-pooler-rw-.*", container="pgbouncer"})[7d:5m])
quantile_over_time(0.95, sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="platform-db", pod=~"shared-pg-pooler-rw-.*", container="pgbouncer"}[5m]))[7d:5m])
max_over_time(sum by (pod) (container_memory_working_set_bytes{namespace="platform-db", pod=~"shared-pg-pooler-rw-.*", container="pgbouncer"})[7d])
```
and the same three with `namespace="cnpg-system", container="manager"` for the operator
(confirm the container name from the live Deployment). Fallback: several
`kubectl top pod -n platform-db` / `-n cnpg-system --containers` samples. Requests = p95 x1.25
rounded up, never below the floors above.

### 6. Headroom (PR body)
For each of the 4 nodes: `kubectl describe node` -> Allocatable and "Allocated resources"
(requests) before; after = before + delta (pooler requests land on whichever 2 nodes host the
pooler pods, the operator on its node). Expected delta is small (order of 100-150m CPU and
<=400Mi memory cluster-wide), well inside a cx43's ~15 GiB allocatable, but the numbers must
be measured. If any node's request total would exceed allocatable, lower the requests to the
p95 without the x1.25 factor rather than touching nodes/replicas.

### 7. hcloud-csi and system-upgrade-controller
No change. The PR states they are installed and owned by the kube-hetzner module in
`infrastructure/k3s-preview/kube.tf`; bringing them under gitops is a separate task.

## Alternatives
- **Use `system-cluster-critical` directly.** Rejected: the issue asks for a value below it,
  and that class is reserved for components whose loss breaks the cluster itself; reusing it
  would let data pods outrank kube-system essentials during preemption.
- **Put the PriorityClass in `infra-components/data/cnpg/shared/` (shared-pg Application).**
  Rejected: the CNPG operator Application in `cnpg-system` would then depend on a resource owned
  by a downstream Application (the operator must exist for the Cluster CRD to reconcile, so the
  ordering is backwards), and deleting shared-pg would prune a class the operator still uses.
  root-app is the common ancestor of both.
- **Guaranteed QoS (requests == limits, including CPU).** Rejected for the pooler and operator:
  a CPU cap reintroduces the CFS-throttling failure mode documented in `cluster.yaml`, and
  Burstable with a memory request already moves the pods out of the first eviction tier.
- **Only add resources, no PriorityClass.** Rejected: kubelet eviction ranks by usage above
  request first, then priority; scheduler preemption only uses priority. Both levers are
  needed, and the issue explicitly requests the class.

## Platform impact
- **Rollout:** the PriorityClass is additive. The pooler pods, operator pod and both shared-pg
  instances restart once. The pooler rolls one pod at a time (2 instances); the operator
  restarting does not interrupt running Postgres; shared-pg restarts the standby then the
  primary (a brief primary restart, as on any CNPG spec change). Merge outside peak hours.
- **Backward compatibility:** no API or connection-string change; `shared-pg-pooler-rw` and
  `shared-pg-rw` services are unchanged.
- **Resource impact:** adds modest requests on up to 3 nodes; reduces the overcommit gap for
  these pods. Headroom before/after is documented in the PR.
- **Risk: memory limit too low -> OOMKill of PgBouncer.** Mitigation: limit at >= 2x request
  and >= 1.5x observed max; the existing `resource_limit` alerting in VM rules will surface it.
- **Risk: preemption evicts tenant pods.** With `PreemptLowerPriority` a pending data-path pod
  may preempt tenant pods on a full node. This is the intended outcome; flip to `Never` if
  reviewers disagree (open question).
- **Risk: ArgoCD diff noise.** CNPG may default fields in the Pooler template (e.g.
  `metadata: {}`); declare the template minimally and, if a persistent OutOfSync appears, add an
  `ignoreDifferences` entry scoped to the Pooler's defaulted fields in `shared-pg.yaml`.
- **Risk: missing PriorityClass on from-zero rebuild.** Mitigated by sync-wave `-1` in root-app.
