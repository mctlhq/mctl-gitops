# Tasks: incident-c0697358

1. [ ] Locate the MctlTelegramOAuthAvailabilityFastBurn rule in mctl-gitops and review its expression and thresholds.
2. [ ] Verify whether the alert is still firing and whether the burn coincides with shared-pg-rw restarts; if it is a resolved transient, make no change and note this in the PR.
3. [ ] If the rule counts non-5xx or client-caused responses as errors, narrow it to 5xx on the token endpoint only.
