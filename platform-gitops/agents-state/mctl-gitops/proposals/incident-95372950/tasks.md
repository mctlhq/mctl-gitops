# Tasks: incident-95372950

1. [ ] Locate the ExternalSecret / workflow template config that provides claude-code-oauth-token-2 to the mctl-agents-investigate workflow; add the missing key mapping only if absent (no secret values).
2. [ ] Delete platform-gitops/agents-state/mctl-api/proposals/.staging-kptjmuhc if present on main.
3. [ ] If nothing in gitops needs changing, make no edit and note in the PR/status that the failure was a transient quota issue and issue 549 needs a re-run.
