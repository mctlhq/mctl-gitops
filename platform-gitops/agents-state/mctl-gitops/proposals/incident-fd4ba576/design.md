# Design: incident-fd4ba576

## Confidence: LOW

## Diagnosis
KubeJobFailed fired in tenant erpact. The alert series carries the kube-state-metrics service label, but that is only the metrics exporter reporting on a failed Job. The failing Job itself is a different workload in the erpact namespace (likely a backup or batch job, possibly related to the erpact-backup KubeContainerWaiting incident). mctl-agent had no skill for this alert, and no logs or labels were available, so the failing Job name and cause are unknown.

## Proposed Fix
Verify before applying. Identify the failed Job in the erpact namespace (via kube_job_status_failed labels), then inspect its pod logs and events. If it is a stale, completed-and-failed Job, set ttlSecondsAfterFinished or a successful/failed history limit on its CronJob in platform-gitops/services/erpact/. If the Job has a real config error (image, secret, resources), fix that value in the same service's values.yaml. Do not alter the kube-state-metrics service itself.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
