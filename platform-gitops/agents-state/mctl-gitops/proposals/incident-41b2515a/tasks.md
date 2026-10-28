# Tasks: incident-41b2515a

1. [ ] Read platform-gitops/services/labs/mctl-telegram/values.yaml and the canary CronJob config; confirm canary user and session storage references are correct.
2. [ ] If a wrong reference is found, correct that single field; otherwise make no change.
3. [ ] Report that a human must re-authorize the canary Telegram session (no active session for user_id 245).
