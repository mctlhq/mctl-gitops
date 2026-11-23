# Tasks: incident-94274874

1. [ ] Find where the mctl-agents implement workflow template reads claude-code-oauth-token-2 and check that the reference and its ExternalSecret/Vault key mapping exist.
2. [ ] If the reference is missing, add it as an optional secretKeyRef; do not add any secret values.
3. [ ] Verify the change renders cleanly and touches nothing else.
4. [ ] If the reference already exists, make no change and note in the PR that the Vault value must be provisioned by an operator.
