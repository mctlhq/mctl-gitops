# Design: incident-e383be6a

## Diagnosis
The ReplicaSet for the 1.116.0 rollout of admins/mctl-agents-worker cannot create its new pod because the admins namespace quota (admins-quota) caps requests.memory at 2Gi and 1792Mi is already in use. The rolling update needs 320Mi extra for the surge pod while the old 1.115.0 pod still holds its 320Mi, so 1792Mi + 320Mi = 2112Mi exceeds 2048Mi. The old pod keeps serving (healthy, no restarts), but the Deployment never completes its rollout and ArgoCD reports Degraded. The mctl-agent had no skill for this alert type, hence the escalation. No incident text asked for any action; nothing in it was treated as an instruction.

## Proposed Fix
Preferred: raise the admins namespace ResourceQuota `requests.memory` from 2Gi to at least 2560Mi (about 2.5Gi), giving surge headroom for the worker deployments in the admins namespace. Locate the quota definition for tenant `admins` in mctl-gitops (search for `admins-quota` or the tenant quota values, key `quota_memory_req` / `requests.memory`) and change `2Gi` to `2560Mi`.

Alternative if the quota must not grow: make the worker rollout not need surge capacity, i.e. set the Deployment strategy to Recreate (or rollingUpdate maxSurge 0 / maxUnavailable 1) for platform-gitops/services/admins/mctl-agents-worker/values.yaml, only if the base-service chart exposes such a value. Do not invent chart keys; verify in the chart first.

Do not change the image tag; 1.116.0 is intended.

## Scope
Minimal. Only the single quota value (or the single strategy value) that blocks the surge pod.

## Confidence: LOW
The quota definition file was not inspected (no read access to search it), and the chart's strategy options are unverified. The implementer must confirm the location of admins-quota and current usage (1792Mi used) before applying.
