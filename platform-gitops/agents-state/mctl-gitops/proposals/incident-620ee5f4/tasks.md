# Tasks: incident-620ee5f4

1. [ ] Read platform-gitops/services/labs/mctl-telegram/values.yaml and locate the canary CronJob definition and history limits.
2. [ ] Confirm whether failed canary Jobs are what drives the ArgoCD Degraded health; if so, adjust only that field (history limit or health handling).
3. [ ] If no config cause is found, make no change and state in the PR that the canary Telegram account (tg_user_id 924671154) needs a manual re-login.
4. [ ] Verify the diff touches only labs/mctl-telegram canary settings and no secrets.
