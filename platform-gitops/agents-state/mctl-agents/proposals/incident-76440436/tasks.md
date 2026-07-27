# Tasks: incident-76440436

1. [ ] Locate the Argo Workflow template for mctl-agents implementer task (likely in mctl-agents/.argo/ or mctl-gitops/services/admins/mctl-agents/)
2. [ ] Verify the current activeDeadlineSeconds or task timeout setting (confirm it is 391 seconds or similar)
3. [ ] Either:
   - Increase activeDeadlineSeconds to 1800 seconds (30 minutes), OR
   - Implement parallel processing: fan-out batch of proposals into N concurrent worker tasks (5-10 concurrent PR opens per batch)
4. [ ] Test the change locally or in preview: queue a batch of 5+ accepted proposals and verify the implementer completes within the new timeout
5. [ ] Merge the fix to mctl-agents main branch and trigger a deploy
