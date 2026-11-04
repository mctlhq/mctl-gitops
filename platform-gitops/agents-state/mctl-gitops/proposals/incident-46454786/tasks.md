# Tasks: incident-46454786

1. [ ] Find the alert rule MctlTelegramConnectorNoFirstCall in mctl-gitops and read its expression, window and `for:` value.
2. [ ] If the rule can fire during a pod restart or rolling deploy, increase `for:` or the window on that rule only; otherwise make no change.
3. [ ] Verify the diff touches only that rule, and note in the PR that diagnosis confidence is LOW.
