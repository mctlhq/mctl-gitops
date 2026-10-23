# Tasks: incident-92738461

1. [ ] Inspect the investigator agent release binding / execution profile in the gitops agent-platform manifests for a reason the run token exchange returns 403 agent_run_exchange_refused.
2. [ ] If a concrete misconfiguration is found, fix that single field; otherwise make no change.
3. [ ] Check that the fallback token secret reference (claude-code-oauth-token-2) is wired in the workflow template; report if the Vault value is missing (do not create secrets).
