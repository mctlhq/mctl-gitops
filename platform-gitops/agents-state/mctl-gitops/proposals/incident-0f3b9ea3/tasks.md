# Tasks: incident-0f3b9ea3

1. [ ] Check mctl-agents Helm values (`service-templates/mctl-agents/values.yaml` or similar) for workflow timeout settings.
2. [ ] Review the Argo Workflow definition for the implement job — verify `activeDeadlineSeconds` or workflow timeout is set to a reasonable value (e.g., >= 14400 for 4 hour max).
3. [ ] If timeout is too low, increase it by 25-50% (e.g., from 10800 to 14400) in the Helm values.
4. [ ] Alternatively, check mctl-agents pod resource limits (memory/CPU) — if memory limit is < 1Gi, increase to 1Gi or higher.
5. [ ] Verify mctl-agents has no batch-size caps on proposal processing; if it does, ensure it can handle "all accepted" batches in a single run or splits into smaller batches automatically.
6. [ ] Deploy the updated values and verify the next implement workflow run completes without timeout.
7. [ ] (Optional) Monitor the workflow run time in the next cycle to ensure it stays well below the new timeout threshold.
