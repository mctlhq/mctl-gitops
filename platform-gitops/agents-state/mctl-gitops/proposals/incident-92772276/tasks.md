# Tasks: incident-92772276

1. [ ] Read platform-gitops/services/labs/mctl-telegram/values.yaml and the post-deploy-verify gating; confirm the canary is what fails.
2. [ ] If confirmed and a safe gating change exists, edit only that field; otherwise make no file change and document that the canary Telegram session needs a manual operator re-login.
3. [ ] Verify the diff touches nothing outside labs/mctl-telegram canary or verify config and no secrets.
