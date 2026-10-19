# Tasks: incident-92411154

1. [ ] Locate the mctl-agents implement workflow template and its secret/ExternalSecret mapping in mctl-gitops; check whether claude-code-oauth-token-2 is mapped into the run-implementer container env.
2. [ ] If the mapping is missing, add it as an optional reference to the existing Vault-backed secret key. Do not add or change any secret values.
3. [ ] If the mapping is present, make no change and note in the PR/summary that an operator must populate the Vault value and re-accept the issue-1980 proposal after the quota resets.
4. [ ] Verify the change renders cleanly and touches no unrelated files.
