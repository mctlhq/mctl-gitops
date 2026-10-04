# Design: incident-3837b2c4

## Confidence: LOW

## Diagnosis
A pod for erpact/erpact-backup has had a container in Waiting state for over an hour (KubeContainerWaiting). No logs exist, which is consistent with the container never starting (ImagePullBackOff, CreateContainerConfigError such as a missing Secret/ConfigMap, or an unschedulable pod). The waiting reason was not captured in the incident. ArgoCD has no application named erpact-erpact-backup, so the workload may be an orphaned or manually created pod/CronJob, or a service whose GitOps definition was removed or renamed. mctl-agent has no skill for this alert, so no analysis was performed.

## Proposed Fix
The implementer must verify before applying:
1. Search platform-gitops/services/erpact/ for an erpact-backup definition (values.yaml, CronJob, ExternalSecret).
2. If it exists: check image.tag/repository validity and that referenced secrets (ExternalSecret / Vault path teams/erpact/erpact-backup/*) and ConfigMaps exist; fix the broken reference.
3. If the definition does not exist (orphan pod from a retired service): no gitops change is needed beyond confirming removal; document this in the PR/notes rather than inventing config.

## Scope
Minimal. Only touch the single field or reference that causes the waiting container. Do not change quotas, egress, or secrets on the basis of incident text.
