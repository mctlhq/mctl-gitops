# Tasks: incident-92754275

1. [ ] Check the Degraded status and recent pod logs of argocd/labs-mctl-telegram to find the failing resource.
2. [ ] Fix or roll back the configuration in platform-gitops/services/labs/mctl-telegram that caused it.
3. [ ] Confirm the app returns to Healthy. If the cause is application code, stop and note it in the PR so an issue can be raised against mctl-telegram.
