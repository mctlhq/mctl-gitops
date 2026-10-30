# Tasks: incident-92978300

1. [ ] Check how claude-code-oauth-token-2 is wired into the mctl-agents implement workflow (ExternalSecret / Vault key reference) in mctl-gitops; add the missing reference if absent, without any secret values.
2. [ ] Review the resulting change to confirm it only adds the secret reference.
3. [ ] Set .status.yaml of mctl-agents/proposals/issue-778-feat-agents-securityfinding-remediation from needs-triage to accepted for one retry.
