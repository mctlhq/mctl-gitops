# Tasks: incident-6b0018ea

1. [ ] Locate the MctlTelegramOAuthAvailabilitySlowBurn rule in mctl-gitops and read its expr.
2. [ ] Confirm whether the selector includes the preview instance or non-token-endpoint series; if so, add a matcher restricting it to the production instance only.
3. [ ] If the selector is already correct, make no change and state that the alert appears transient.
4. [ ] Verify the edited rule is valid YAML/PromQL and that the burn-rate threshold and windows are unchanged.
