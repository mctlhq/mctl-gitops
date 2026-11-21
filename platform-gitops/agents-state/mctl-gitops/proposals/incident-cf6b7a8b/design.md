# Design: incident-cf6b7a8b

## Confidence: LOW

## Diagnosis
KubeQuotaFullyUsed fired for the admins namespace. mctl-agent had no skill for it. Live quota usage shows the `services` object count is at its hard limit (10 of 10); this is the resource that is fully used. Pods (14/16) and limits.memory (4032Mi of 5Gi, about 79%) are high but not full. The monitoring-kube-state-metrics service is only the metric source, not the cause, and has no workload of its own in the admins workspace. This is a capacity condition, not a fault. Verify the live state before applying, since usage may have changed.

## Proposed Fix
Locate the admins tenant ResourceQuota definition in mctl-gitops (search platform-gitops for the admins tenant quota, field `count/services` or `services`). Raise `services` from 10 to 15. Optionally raise `pods` from 16 to 24 and `limits.memory` from 5Gi to 6Gi if headroom is wanted. If the quota is intended to be strict, the alternative is to tune the KubeQuotaFullyUsed rule for this namespace instead; prefer the quota raise.

## Scope
Minimal. Only touch the admins tenant quota values (primarily `services`).
