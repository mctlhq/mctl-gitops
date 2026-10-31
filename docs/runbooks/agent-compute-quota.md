# Agent compute quota (argo-workflows)

Source: gitops#2291, spike mctl-agents#807 gap G6.

## Status

The PriorityClass `mctl-agents-quota-scope` and ResourceQuota
`mctl-agents-compute` exist, but **nothing enforces them yet**: no pod names
the class. Enforcement (`podPriorityClassName` on the agent CWFTs, explicit
resources on every agent container including Argo `init`/`wait`, the
validator) is pending mctl-gitops#2299. Until measured inputs are confirmed
(node allocatable, live executor sizing, per-kind concurrency), the numbers
below are provisional.

## Capacity calculation

Worst-case pod per kind (main container plus `wait`), times intended
concurrency (implement 2, investigate 3, shepherd 1, run 2, reconcile 1,
approve 2, scout 1, usage-collector 1 = 13 pods):

| Resource | Sum | Hard value (+~25% burst, rounded) |
|---|---|---|
| pods | 13 | 20 |
| requests.cpu | 2.13 | 3 |
| requests.memory | 12.7Gi | 16Gi |
| requests.ephemeral-storage | 47.3Gi | not in the quota (see below) |
| limits.cpu | 28 | 36 |
| limits.memory | 46.75Gi | 60Gi |
| limits.ephemeral-storage | 71Gi | not in the quota (see below) |

Ephemeral storage cannot be part of this quota. The API server accepts only
pods, cpu and memory (requests/limits) under a `PriorityClass` scope, and
rejects `requests.ephemeral-storage` / `limits.ephemeral-storage` with
"unsupported scope applied to resource" (confirmed by server dry-run on
2026-10-31). An unscoped quota would count every platform pod in the
namespace, which this design rules out. Ephemeral storage is bounded per pod
by the agent templates' own `ephemeral-storage` limits. Every agent pod
template sets one; `cwft-mctl-agents-daily` defines no pods of its own (it is
a CronWorkflow that runs `mctl-agents-run`, which does). The sums above remain
the capacity reference.

`requests.*` is the real bound on what agents take from platform workflows;
limits are overcommitted by design. Agent `requests.memory` plus the platform
reserve must fit in allocatable minus DaemonSets; if not, reduce concurrency,
not the reserve.

## Resizing

Edit `platform-gitops/argo-workflows/config/agent-compute-quota.yaml` and
update the table above in the same PR.

## Alerts

- `ArgoAgentComputeQuotaHigh`: any tracked resource >= 90% for 10m.
- `ArgoAgentComputeQuotaExhausted`: >= 100% for 5m. Agent runs are queueing
  (`403 exceeded quota: mctl-agents-compute`, Argo node Pending); this is not
  a node-capacity problem and does not fire the unschedulable-pod alerts.

`TenantCPUQuotaHigh` / `TenantMemoryQuotaHigh` exclude `argo-workflows`
because the quota there is agent-scoped.

## Rollback

Delete, in order: the ResourceQuota, the PriorityClass (only once no pod
names it), the alert group.
