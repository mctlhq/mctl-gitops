# Tasks: incident-c8259a4a

1. [ ] Open platform-gitops/services/labs/mctl-telegram/values.yaml and locate the canary CronJob and its token secret reference.
2. [ ] Verify the token is read from a Vault-backed ExternalSecret and not hardcoded; if hardcoded, replace it with an ExternalSecret reference (no token values in the PR).
3. [ ] If no gitops change applies, record in the PR/notes that the canary token for tg:8745115872 must be re-minted by a human.
