# Tasks: incident-8b02f191

1. [ ] Find the rule for MctlTelegramOAuthAvailabilitySlowBurn in mctl-gitops and read its SLI expression.
2. [ ] If canary/unknown_state traffic is counted as errors, edit the expression to exclude it; otherwise make no change and note that in the PR.
3. [ ] Verify the change is consistent with the FastBurn rule (incident-68c12fc2) and that both rules stay in sync.
