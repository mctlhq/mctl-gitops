# Tasks: incident-92337544

1. [ ] Check whether proposal incident-92337584 already covers this change; if so, treat this as a duplicate.
2. [ ] Locate the post-deploy-verify step in the shepherd workflow template in mctl-agents.
3. [ ] Gate post-deploy-verify on run-shepherd having merged at least one PR, and scope the Degraded check to apps affected by the merge.
4. [ ] Verify the change looks correct and does not alter behavior when a merge did occur.
