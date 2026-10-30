# Tasks: incident-872e25fa

1. [ ] Read platform-gitops/services/labs/mctl-telegram/values.yaml and locate the canary CronJob config and the session/secret references for tg_user_id 924671154.
2. [ ] Locate the MctlTelegramToolAvailabilityFastBurn rule and check whether canary errors are included in the availability SLI.
3. [ ] If a config or secret reference is wrong, fix that single field. If the cause is an expired session needing manual re-login, make no change and note that operator action is required.
4. [ ] Verify the change looks correct and touches only the field related to this alert.
