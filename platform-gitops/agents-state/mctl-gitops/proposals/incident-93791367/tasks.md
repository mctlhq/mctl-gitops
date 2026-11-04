# Tasks: incident-93791367

1. [ ] Check the node statuses of workflow mctl-agents-incidents-1793790900 to identify which step failed.
2. [ ] If the failed node is a clone-gitops error, apply the clone retry change described in incident-93791038; otherwise stop and record the actual failed step.
3. [ ] Verify the change looks correct and touches only the clone-gitops step.
