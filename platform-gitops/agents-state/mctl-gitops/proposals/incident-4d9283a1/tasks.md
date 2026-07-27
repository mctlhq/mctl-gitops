# Tasks: incident-4d9283a1

1. [ ] Verify diagnosis: check Argo Workflows logs and pod events for the failed implement workflow to confirm timeout vs. resource starvation
2. [ ] If timeout: Increase activeDeadlineSeconds from 600 to 1800 in platform-gitops/services/mctl-agents/workflows/implement-workflow.yaml
3. [ ] If resource starvation: Increase CPU/memory requests and limits by 50% in platform-gitops/services/mctl-agents/values.yaml
4. [ ] Commit and push changes to main branch
5. [ ] Monitor next implement workflow run (triggered by accepted proposals) to confirm it completes successfully
6. [ ] Verify the mctl-agents service remains stable and no new workflow_failed incidents fire for implement job
