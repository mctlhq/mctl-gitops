# Tasks: incident-b738c48a

1. [ ] Fetch the full Argo Workflow logs for `mctl-agents-implement-1785057300` from the workflow UI to identify the exact failure reason (timeout, OOM, or code error).

2. [ ] If resource exhaustion: Edit mctl-agents Helm values (check `mctl-gitops/agents-state/mctl-agents/values.yaml` or equivalent) and increase CPU requests/limits by 2x and memory by 2x.

3. [ ] If workflow timeout: Locate the Argo Workflow template or ArgoCD ApplicationSet for mctl-agents and increase `activeDeadlineSeconds` from 600 to 900.

4. [ ] Verify changes look correct by reviewing the diff (no unrelated changes, values are reasonable).

5. [ ] Commit and push to trigger mctl-agents redeployment.

6. [ ] Monitor the next `mctl-agents-implement` workflow run (should occur on the next cron trigger or manual run) to confirm it completes without failure.
