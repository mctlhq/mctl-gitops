# Tasks: incident-93286203

1. [ ] Read platform-gitops/services/labs/mctl-telegram/values.yaml and locate the canary CronJob settings.
2. [ ] Verify the diagnosis: the canary fails with "no active session", which is account state and not manifest content. Do not edit secrets or credentials.
3. [ ] If the manifest has no defect, make no change and note that a human must re-authenticate the canary Telegram user (tg id 924671154) for labs/mctl-telegram.
4. [ ] Do not suspend the canary CronJob unless a human has confirmed it.
