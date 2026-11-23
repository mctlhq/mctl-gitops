# Design: incident-50557b9f

## Confidence: LOW

## Diagnosis
The KubeJobFailed alert fired from kube-state-metrics (service label monitoring-kube-state-metrics), with tenant label "forgejo". The label identifies the metrics exporter, not the failed Job, so the actual failing Job is unknown. No logs could be fetched: the platform reports "tenant not found: forgejo", so forgejo is probably not a registered mctl tenant (likely a namespace or an externally managed app). mctl-agent had no skill for KubeJobFailed. Root cause could not be determined from available evidence.

## Proposed Fix
No code or config change is justified yet. The implementer should first verify:
1. Find the failed Job in the forgejo namespace (for example a CronJob such as backup or cleanup) via the GitOps manifests under platform-gitops for forgejo.
2. If the Job is a stale one-off failure whose CronJob now succeeds, set failedJobsHistoryLimit / ttlSecondsAfterFinished in its values so old failed Jobs are cleaned up and the alert clears.
3. If the Job fails persistently, fix its cause (image, resources, command) in the owning values.yaml.
If no failing Job definition is found in mctl-gitops, make no change and note that in the PR description.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
