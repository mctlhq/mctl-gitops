# Design: incident-4f0d5877

## Confidence: LOW

## Diagnosis
KubeJobFailed fired with the series attributed to the monitoring-kube-state-metrics service (kube-state-metrics is the metric source, not the failing workload). The failing Job itself is not identified: the incident carries no labels, and the tenant "mctl-glovo" is not known to the platform, so no logs could be fetched. mctl-agent found no skill for this alert. The tenant may have been deleted, in which case the alert is stale or the failed Job is an orphan left in a namespace that no longer maps to a tenant.

## Proposed Fix
Do not change anything blindly. The implementer should first verify in mctl-gitops:
1. Whether a tenant or namespace "mctl-glovo" still exists in platform-gitops (tenant definitions, ArgoCD apps).
2. If it was removed: check for leftover Job manifests or monitoring rules referencing it, and remove the stale references (or add a namespace filter to the KubeJobFailed rule).
3. If it exists: identify the failing Job (a CronJob or hook Job in that namespace) and fix its image, command or resource limits, or set ttlSecondsAfterFinished / failedJobsHistoryLimit so old failed Jobs are cleaned up.
If none of these can be confirmed from the repository, make no change and report that the alert needs human review.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
