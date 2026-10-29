# Tasks: incident-c5455c17

1. [ ] Read platform-gitops/services/labs/mctl-telegram/values.yaml and the MctlTelegramSessionBorrowFastBurn alert rule; confirm the canary user and whether the alert mixes canary and real-user traffic.
2. [ ] If the rule conflates them, make the minimal alert-expression change; otherwise make no change and document that the canary Telegram session needs a manual re-login.
3. [ ] Verify the change looks correct and touches no secrets, roles or egress settings.
