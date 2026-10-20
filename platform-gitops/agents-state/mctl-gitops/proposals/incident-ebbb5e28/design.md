# Design: incident-ebbb5e28

## Confidence: LOW

## Diagnosis
The KubeJobFailed alert fired for tenant erpact, reported through the monitoring-kube-state-metrics service. That service only exports Job state; it is the reporter, not the failing workload. mctl-agent had no skill for this alert, and no logs were available, so the failing Job name and failure reason are unknown. The summary ("Job failed to complete.") is the only content and is a generic alert description. A one-off failed Job (for example a finished-but-failed migration, site-creation or cron Job in the erpact namespace) that was never cleaned up is the most likely cause, but this is unverified.

## Proposed Fix
Do not change anything blindly. The implementer should:
1. Look in platform-gitops for the erpact workload definitions (Jobs, CronJobs, hooks) and for the KubeJobFailed rule in the monitoring values.
2. Identify any Job in the erpact namespace with a failed status. If it is a one-off Job whose failure is stale, set ttlSecondsAfterFinished and a sensible backoffLimit on its template so failed Jobs are garbage-collected.
3. If the Job is a real recurring job with a configuration fault (image tag, resources, env), fix that field only.
4. If no failing Job definition can be found in the repo, make no change and mark the proposal needs-triage with a note.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
