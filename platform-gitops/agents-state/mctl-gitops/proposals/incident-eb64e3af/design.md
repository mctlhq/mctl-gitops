# Design: incident-eb64e3af

## Confidence: LOW

## Diagnosis
KubeJobFailed fired for tenant forgejo. The service label (monitoring-kube-state-metrics) is the exporter that reports the metric, not the failing workload; the failed Job is in some forgejo namespace Job. mctl-agent had no skill for this alert, and no logs were available from Loki for the exporter, so the failing Job's identity and failure reason are unknown. The alert is a single occurrence (occurrence_count 1) and may be a transient or one-off failed Job (for example a completed-with-failure CronJob run or migration Job) that persists until deleted.

## Proposed Fix
Verify before changing anything. Identify the failed Job from the alert's `job_name`/`namespace` labels in Alertmanager history or the kube_job_failed metric. If it is a stale failed Job from a CronJob/hook, set `failedJobsHistoryLimit` / `ttlSecondsAfterFinished` in the owning forgejo chart values under platform-gitops/services/forgejo/ so failed Jobs are cleaned up. If the Job fails for a real reason, fix that cause in the same values file. If no persistent cause can be found, make no change and close the task as no-op.

## Scope
Minimal. Only touch the single field in the forgejo service values that causes this specific alert.
