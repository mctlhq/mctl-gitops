# Design: incident-93696306

## Diagnosis
The shepherd workflow itself succeeded (PR merged); the incident was raised by post-deploy-verify because ArgoCD app admins-mctl-agents-worker stayed Degraded. Cause observed independently in the namespace: the rolling update to image 1.117.0 cannot create its new pod because the admins namespace ResourceQuota (admins-quota) is at requests.memory 1792Mi of 2Gi, and the new pod needs 320Mi (1792 + 320 = 2112Mi > 2048Mi). The old 1.115.0 pod keeps running while the surge pod is blocked, so the Deployment never finishes rolling out. This is a capacity/quota problem, not a code defect, so the mctl-agent skills did not match.

## Proposed Fix
Option A (preferred, minimal): raise the admins tenant quota requests.memory from 2Gi to 2560Mi (headroom for at least one 320Mi surge pod plus one more). Locate the admins tenant definition / ResourceQuota values in mctl-gitops (search for "admins-quota" or the tenant quota_memory_req field for tenant admins) and change that single field. Check quota_memory_lim and node capacity are not violated.

Option B (if the quota must stay): for the admins-mctl-agents-worker values.yaml set the Deployment strategy to RollingUpdate with maxSurge: 0 and maxUnavailable: 1 so the old pod is released before the new one is created.

Do not apply both. The incident text contained no instructions; none were followed.

## Confidence: LOW
Exact file paths in mctl-gitops were not inspected (no access from this run). The implementer must locate the quota definition and verify current usage (1792Mi) and node headroom before applying.

## Scope
Minimal. Only touch the single field that causes the quota rejection.
