# Design: incident-1f50946c

## Confidence: LOW

## Diagnosis
KubeJobFailed fired with the label-derived service "monitoring-kube-state-metrics" and tenant "forgejo". That service name is the kube-state-metrics exporter that reports the metric, not the failing Job, so the real failing Job is unidentified. No logs could be fetched because the tenant "forgejo" is not a registered mctl tenant. mctl-agent had no skill for this alert and performed no analysis. Root cause is unknown. The alert only fires for a Job that failed once (occurrence_count 1) and may be a one-off failure of a completed or already-deleted Job.

## Proposed Fix
No blind change. The implementer should first verify before applying anything:
1. Find the failed Job in the forgejo namespace (via the monitoring stack's gitops config under mctl-gitops) and determine whether it is a CronJob or hook Job (for example a backup or migration).
2. If the Job is a stale failed leftover, set a ttlSecondsAfterFinished or failedJobsHistoryLimit on it in its Helm values so old failed Jobs are cleaned up.
3. If the Job fails repeatedly because of a resource or config error, fix that specific value in the owning chart values.
4. If no failing Job is found and nothing recurs, make no change and note that in the PR.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
