# Tasks: incident-92756025

1. [ ] Read platform-gitops/services/labs/mctl-telegram/values.yaml and identify the canary CronJob configuration and any ArgoCD health or ignore settings for it.
2. [ ] Confirm from the repo whether a failed canary Job can mark Application labs-mctl-telegram Degraded; if not, make no change and state that in the PR description.
3. [ ] If confirmed, apply the minimal change so canary Job failure does not degrade the parent application, matching existing conventions in this repo.
4. [ ] Verify the diff touches only the labs/mctl-telegram canary/health setting and no secrets.
