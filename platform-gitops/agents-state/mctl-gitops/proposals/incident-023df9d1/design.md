# Design: incident-023df9d1

## Confidence: LOW

## Diagnosis
The PreviewReaperFailing alert fired for tenant erpact: the preview-reaper job (a CronJob or workflow that deletes expired preview environments) has had no successful run in 3 hours. No skill matched, the incident carries no service name or labels, and the Loki query for erpact/preview-reaper returned zero lines, so the root cause is not established. Likely candidates, none verified: the CronJob is failing (RBAC, image pull, or API error), its pods are not producing logs in Loki because they are short-lived job pods, or the alert rule is firing on a stale or suspended CronJob.

## Proposed Fix
Verify before changing anything. In mctl-gitops, locate the preview-reaper definition for the erpact tenant and the PreviewReaperFailing alert rule. Check the CronJob schedule, suspend flag, image tag, service account and RBAC, and the alert expression and its time window. Fix only the single field found to be wrong. If the cause is only missing logs or a mis-scoped alert, adjust the alert rule rather than the workload. If no defect is found in the repository, make no change and report that a human needs to inspect the cluster.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
