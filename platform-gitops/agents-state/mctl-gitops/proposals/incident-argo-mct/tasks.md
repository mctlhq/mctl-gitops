# Tasks: incident-argo-mct

1. [ ] Open the Argo UI link from the incident summary and identify the failed step and its error message:
       https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-implement-1784072700

2. [ ] If the failure is a GitHub auth/API error: rotate the GitHub token stored in
       Vault at secret/data/teams/admins/mctl-agents/github-token, then annotate
       the ExternalSecret to force a re-sync.

3. [ ] If the failure is a timeout: locate the WorkflowTemplate manifest in
       platform-gitops/argo-workflows/ (filename contains "implement"), increase
       activeDeadlineSeconds from its current value to 1800, commit to mctl-gitops main.

4. [ ] If the failure is OOMKilled: locate the same WorkflowTemplate manifest,
       increase resources.limits.memory on the affected container from its current
       value to 1Gi, commit to mctl-gitops main.

5. [ ] After applying the fix, trigger a new implementer run via mctl_trigger_implementer
       (or re-queue the failed proposals) and confirm the workflow completes successfully.

6. [ ] Verify the previously accepted proposals now have status=implemented and
       corresponding PRs exist in the target service repos.
