# Design: incident-39b614f8

## Confidence: LOW

## Diagnosis
The KubeQuotaAlmostFull alert fired for the labs namespace. mctl-agent has no skill for this alert, so nothing was analysed. Independent observation of the labs ResourceQuota shows the Service count is the tightest resource at 23 of 25 (92%), which is the most likely trigger given the usual 90% threshold. Memory limits (75%) and pods (67%) are below it. The alert's own labels were not available, so which resource tripped it is inferred, not confirmed. Logs could not be fetched because the alert source (kube-state-metrics) is not an onboarded tenant service.

## Proposed Fix
Verify first which resource the alert refers to (check the alert expression and labels in the monitoring rules). If it is the Service count, raise the `services` quota for the labs tenant from "25" to a value with headroom (for example "40") in the labs tenant quota definition in mctl-gitops (the tenant's ResourceQuota values; locate with a search for `labs` quota / `services:`). Do not change other quota fields. If the stale-Service count is caused by orphaned Services, prefer cleanup over raising the quota, and note this in the PR.

## Scope
Minimal. Only touch the single quota field behind this alert for the labs tenant.
