# Tasks: incident-92771978

1. [ ] Check whether incident-92772276 already made the change; if so, do nothing further.
2. [ ] Otherwise read platform-gitops/services/labs/mctl-telegram/values.yaml and the post-deploy-verify gating; apply only a verified, minimal change, or document that the canary session needs manual re-login.
3. [ ] Verify the diff touches no secrets.
