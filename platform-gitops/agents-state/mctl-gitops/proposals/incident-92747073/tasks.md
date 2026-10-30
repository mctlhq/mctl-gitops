# Tasks: incident-92747073

1. [ ] Find the post-deploy-verify step in the shepherd workflow template and the Degraded-app check it runs.
2. [ ] Restrict the check to apps of the service touched by the merged PR, and skip it when the run performed no merge.
3. [ ] Verify the change looks correct and does not weaken detection for the merged service.
