# Tasks: incident-91839511

1. [ ] Check whether the 403 oauth_org_not_allowed error still occurs in recent implement workflows; if the credential problem is already resolved, make no changes.
2. [ ] Confirm there is no repo-level misconfiguration (for example the auth mode setting in the mctl-agents Helm values) that selects OAuth instead of an API key; change it only if it is clearly wrong.
3. [ ] Do not modify any secret or token. If no repo change is warranted, open no PR and note that the fix is operational (credential provisioning).
