# Tasks: issue-1774-data-resources-and-a-priorityclass-for-t

- [ ] 1. Measure current usage: run the VictoriaMetrics p95/max queries from design.md section 5 for `pgbouncer` in `platform-db` and the CNPG operator container in `cnpg-system` (7-day window; `kubectl top` fallback), and record per-node allocatable vs allocated requests (`kubectl describe node`) for all 4 nodes — DoD: numbers and queries captured for the PR body.
- [ ] 2. Add `platform-gitops/bootstrap/templates/system/priority-classes.yaml` with `PriorityClass` `platform-data-critical` (`value: 1000000`, `globalDefault: false`, `preemptionPolicy: PreemptLowerPriority`, sync-wave `-1`, description) — DoD: `helm template` of `platform-gitops/bootstrap` renders it; value < 2000000000.
- [ ] 3. (depends on 1, 2) Add `spec.template` to `platform-gitops/infra-components/data/cnpg/shared/pooler.yaml`: `priorityClassName: platform-data-critical`, container `pgbouncer` with CPU/memory requests and a memory limit sized per design.md (floors 50m / 64Mi / 128Mi); keep `instances: 2` — DoD: manifest validates against the CNPG Pooler schema; comment cites REL-103 and the measured p95.
- [ ] 4. (depends on 2) Add `spec.priorityClassName: platform-data-critical` to `platform-gitops/infra-components/data/cnpg/shared/cluster.yaml`; no other field changes — DoD: diff is that one line plus a short comment.
- [ ] 5. (depends on 1, 2) Extend Helm values in `platform-gitops/bootstrap/templates/data/cloudnative-pg.yaml` with `priorityClassName: platform-data-critical` and `resources` (floors 50m / 128Mi / 256Mi), keeping `targetRevision: 0.23.0` and `crds.create: true` — DoD: `helm template cloudnative-pg/cloudnative-pg --version 0.23.0` with these values shows both on the operator Deployment.
- [ ] 6. (depends on 1, 3, 5) Compute per-node headroom after the change and confirm no node exceeds allocatable; reduce requests if needed — DoD: before/after table in PR.
- [ ] 7. Write the PR body: sizing queries, observed values, chosen values, headroom table, and a statement that hcloud-csi and system-upgrade-controller are installed by the kube-hetzner module in `infrastructure/k3s-preview/kube.tf` and are left unchanged — DoD: PR opened from a feature branch, `validate-manifests.yml` green.
- [ ] 8. (after merge) Verify in cluster: PriorityClass exists; pooler, operator and shared-pg pods show `priorityClassName: platform-data-critical`, non-zero `.spec.priority`, and QoS `Burstable`; shared-pg Cluster is healthy with primary + standby; ArgoCD apps `root-app`, `shared-pg`, `cloudnative-pg` Synced/Healthy — DoD: commands and output noted on the issue.

## Tests
- [ ] T1. `helm template test platform-gitops/bootstrap` renders `PriorityClass/platform-data-critical` with value 1000000 and the sync-wave annotation; `cloudnative-pg` Application values contain `priorityClassName` and `resources`.
- [ ] T2. Optional pytest (pattern of `tests/test_*.py`): load `pooler.yaml`, `cluster.yaml` and the rendered `cloudnative-pg.yaml` and assert every data-path pod spec references `platform-data-critical`, the pooler container is named `pgbouncer` with memory request and limit set, and replica counts are unchanged (pooler 2, Cluster 2).
- [ ] T3. `kubeconform`/`validate-manifests.yml` passes on the changed manifests (CNPG CRD schemas).
- [ ] T4. Post-sync: `kubectl get pod -n platform-db -o custom-columns=NAME:.metadata.name,PC:.spec.priorityClassName,QOS:.status.qosClass` and the same for `cnpg-system` show no `BestEffort` and the new class.
- [ ] T5. Post-sync: a tenant service using `shared-pg-pooler-rw` (e.g. mctl-api) keeps serving; no new OOMKilled events on pgbouncer within 24h.

## Rollback
Revert the PR. ArgoCD restores the previous Pooler, Cluster and operator specs (pods roll back
to `BestEffort` without a priority class, with one more restart). Remove the consumers before the
PriorityClass. root-app and the child Applications sync on their own schedules, so a single
revert could prune the class while a pod that still references it is being recreated, and
admission would reject that pod. Revert in two commits instead: first drop `priorityClassName`
(and the resources, if needed) from `pooler.yaml`, `cluster.yaml` and `cloudnative-pg.yaml`,
wait for `shared-pg` and `cloudnative-pg` to be Synced/Healthy, then delete
`priority-classes.yaml`. If pods are already failing admission over a missing class, re-add
`priority-classes.yaml` first. For an OOMKill
loop on PgBouncer only, raise the pooler memory limit in `pooler.yaml` instead of reverting.
