# Tasks: incident-19770fcd

1. [ ] Read platform-gitops/services/labs/mctl-telegram/values.yaml and locate the canary CronJob configuration.
2. [ ] Verify the canary user reference matches the account that has an active Telegram session; fix only if clearly wrong.
3. [ ] If nothing is wrong in gitops, make no change and state in the PR/notes that an operator must re-authenticate the canary account session.
