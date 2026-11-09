# Tasks: incident-09094f4f

1. [ ] Find the MctlTelegramToolAvailabilitySlowBurn rule in mctl-gitops and read its expression.
2. [ ] Verify whether the expression counts jwt_expired auth failures or canary unknown_state probes as unavailability; if not, make no change and stop.
3. [ ] If it does, edit only that expression to exclude the non-failure case and confirm the edit looks correct.
