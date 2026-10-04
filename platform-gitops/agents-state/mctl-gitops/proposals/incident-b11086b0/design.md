# Design: incident-b11086b0

## Confidence: LOW

## Diagnosis
KubeJobFailed fired for tenant erpact. The alert is emitted from kube-state-metrics, so the service named in the incident is the metrics exporter and not the failing workload. The failing Job is therefore unidentified. mctl-agent has no skill for this alert and escalated it. No logs were available, and the incident carries no labels, so the failing Job name and the root cause could not be determined. The incident has not recurred (occurrence_count 1).

## Proposed Fix
No concrete change can be justified from the available evidence. The implementer should first verify the current state: look in the team-erpact namespace for Jobs or CronJobs with failed status, and check whether the alert is still firing. If the Job was a one-off that has been cleaned up or has since succeeded, make no change. If a recurring CronJob is failing, fix its values in platform-gitops/services/erpact/ (resources, command, image tag) as indicated by that Job's pod logs. Optionally, consider adding a KubeJobFailed diagnostic skill to mctl-agent as a separate follow-up.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert. If nothing is found to be failing, make no change.
