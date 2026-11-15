# Design: incident-b489d959

## Diagnosis
KubeJobFailed fired for a Job in the "forgejo" namespace, reported via the monitoring-kube-state-metrics scrape target (the service label is the exporter, not the failing workload). The failed Job name is not present in the incident fields and no logs were retrievable. It is probably related to the forgejo application being Degraded (incidents bf37f062 and 8893fe90), for example a failed install/migration/hook Job. Root cause is unconfirmed.

## Proposed Fix
In mctl-gitops, find Job/hook definitions in the forgejo application manifests and check their image, command, resource limits and backoffLimit. Fix the specific misconfiguration found. Failed Job objects normally need a ttlSecondsAfterFinished or deletion to clear the alert; add ttlSecondsAfterFinished only if the Job is chart-managed in gitops values.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.

## Confidence: LOW
The failing Job could not be identified. Verify before applying; make no change if no concrete defect is found.
