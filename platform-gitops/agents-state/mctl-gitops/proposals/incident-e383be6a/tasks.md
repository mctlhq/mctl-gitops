# Tasks: incident-e383be6a

1. [ ] Find where the admins tenant quota (admins-quota, requests.memory 2Gi) is defined in mctl-gitops.
2. [ ] Raise requests.memory from 2Gi to 2560Mi (keep other quota values unchanged).
3. [ ] Verify the diff touches only that value; if quota cannot change, instead verify the base-service chart supports a Recreate/maxSurge 0 strategy and set it in services/admins/mctl-agents-worker/values.yaml.
4. [ ] Confirm after sync that the 1.116.0 pod is created and ArgoCD health returns to Healthy.
