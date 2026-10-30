# Tasks: incident-92337584

1. [ ] Locate the post-deploy-verify step in the shepherd workflow template in mctl-agents.
2. [ ] Verify current argocd/root-app health; if it is genuinely Degraded, note it in the PR description as a separate problem.
3. [ ] Gate post-deploy-verify on run-shepherd having merged at least one PR, and scope the Degraded check to apps affected by the merge.
4. [ ] Verify the change looks correct and does not alter behavior when a merge did occur.
