# Tasks: issue-2291-security-agents-compute-resourcequota-an

- [ ] 1. Measure the live inputs and inventory every workload in `argo-workflows`. Collect:
  - `kubectl get priorityclass` (confirm no `globalDefault`, or record its value);
  - node allocatable CPU, memory and ephemeral storage;
  - live `init`/`wait` container resources and their 7-day peak `container_memory_working_set_bytes` and ephemeral usage;
  - whether `notify-completion` runs as a pod inside agent workflows;
  - that no service account in `config/sa-and-rbac.yaml` used by agent pods can create pods;
  - one rendered pod spec per agent kind (`kubectl get pod -o yaml` from a recent run), listing every container: workflow steps, exit hooks, global hook, init containers, sidecars, executor.

  DoD: a PR comment or runbook section records each value. The provisional executor values and the concurrency table in design.md are confirmed or adjusted, and the platform-reserve inequality (agent `requests.*` + platform reserve <= allocatable - system/DaemonSet) is shown to hold.
- [ ] 2. Add `scripts/validate-agent-quota-resources.py` with `--selftest`, wire it into `.github/workflows/validate-manifests.yml` next to `validate-agent-pod-security.py`, and run it against the current tree (depends on 1). DoD: on the current tree it lists every agent container missing one of the six values. The selftest proves it catches a missing value, a missing class, a non-agent template naming the class, and a concurrency x worst-case total above the quota.
- [ ] 3. Add explicit resources (requests and limits for cpu, memory and ephemeral-storage) to every agent container the validator flagged, plus a spec-level `podSpecPatch` for `init`/`wait` in the eight agent CWFTs. Add resources 50m/128Mi/16Mi to 500m/256Mi/256Mi on `notify-completion` in `cwft-global-workflow-completion-hook.yaml` (depends on 2). DoD: the validator's resource checks pass; existing CPU and memory values are unchanged; the hook's YAML comment records why its values equal the tenant LimitRange defaults.
- [ ] 4. Add `config/agent-quota-priority-class.yaml` (`mctl-agents-quota-scope`, value 0, `globalDefault: false`, `preemptionPolicy: Never`, sync-wave -1) with a comment that carries the no-semantics-change argument. Add `config/agent-compute-quota.yaml` (`mctl-agents-compute`, PriorityClass scopeSelector, the hard values from design.md, sync-wave -1). Do not add a LimitRange (depends on 1). DoD: `kubectl apply --dry-run=server` succeeds, and the quota's hard values match the validator's capacity table.
- [ ] 5. Add the `mctl.argo-agent-quota` alert group (`ArgoAgentComputeQuotaHigh`, `ArgoAgentComputeQuotaExhausted`) and exclude `argo-workflows` from `TenantCPUQuotaHigh` and `TenantMemoryQuotaHigh` in `vm-rules/mctl-alerts.yaml`, with unit tests in `vm-rules/tests/mctl-alerts_test.yaml`. DoD: `scripts/check-vm-rules.sh` passes and the new tests cover fire and no-fire cases.
- [ ] 6. Merge PR 1 (tasks 2-5), wait for the Argo CD sync (about 3 minutes), then run one agent workflow of each kind. Nothing is enforced yet (depends on 3, 4, 5). DoD: on each run's live pod spec every container shows all six values, and no wait-container OOMKill or ephemeral eviction occurs.
- [ ] 7. PR 2: add `spec.podPriorityClassName: mctl-agents-quota-scope` to the eight agent CWFTs, and turn on the validator's class check (depends on 6). DoD: the validator passes, and after sync agent pods show `priorityClassName: mctl-agents-quota-scope` and `priority: 0`.
- [ ] 8. Write `docs/runbooks/agent-compute-quota.md`: the capacity calculation, how to resize, how to read the alerts, and rollback. Link it from the CLAUDE.md "Secrets Management" runbook list (depends on 7). DoD: the runbook is merged and matches the objects.

## Tests

- [ ] T1. After PR 2, run one of each agent kind: approve, implement, investigate, reconcile, run (via daily or incidents), scout, shepherd and usage-collector, concurrently up to the intended concurrency. All schedule and succeed, `kube_resourcequota{resourcequota="mctl-agents-compute",type="used"}` stays below hard, and no Argo node message contains "exceeded quota".
- [ ] T2. Run one deploy-service (`mctl_deploy_service action=deploy` on a test service). It succeeds with unchanged pod resources. Its pods carry no `mctl-agents-quota-scope`, and the completion hook pod in the tenant namespace shows the same CPU and memory values as before.
- [ ] T3. Over-quota refusal. `kubectl create` a pod in `argo-workflows` with `priorityClassName: mctl-agents-quota-scope` and `requests.memory: 17Gi` (limits set). It is rejected with `403 ... exceeded quota: mctl-agents-compute`. Repeat with a pod that is under the per-pod size while the quota is filled by test pods: also rejected. With a test Workflow from an agent template, the node stays Pending with the quota message.
- [ ] T4. Platform headroom. While T3's filler pods hold the agent quota at 100%, run a platform workflow in `argo-workflows` (for example `wft-smoke-test` or `cwft-argo-local-workdir-canary`). It is admitted and completes.
- [ ] T5. Missing-value refusal. A test pod with the agent class and a container without `limits.ephemeral-storage` is rejected ("must specify limits.ephemeral-storage"). The validator selftest fails the equivalent template in CI.
- [ ] T6. Priority unchanged. `kubectl get pod -o jsonpath='{.spec.priority}'` returns 0 for an agent pod before and after PR 2. `preemptionPolicy` is `Never`. No `globalDefault` change is visible in `kubectl get priorityclass`.
- [ ] T7. Alerts. In the vmalert unit tests, `ArgoAgentComputeQuotaExhausted` fires at used=hard, and the unschedulable/FailedScheduling alerts do not fire for the same input. During T3, the live alert appears in Alertmanager under its own name.

## Rollback

Revert PR 2 first. Removing `podPriorityClassName` takes agent pods out of
the quota's scope immediately, for new pods. Then revert PR 1, or delete these
objects (prune), in this order:

1. ResourceQuota `mctl-agents-compute`;
2. PriorityClass `mctl-agents-quota-scope`, only after no pod names it;
3. the new alert group.

The explicit container resources and the executor `podSpecPatch` are
harmless to keep. Revert them only if a wait-container OOMKill is traced to
them. No LimitRange was added, so none needs removing.
