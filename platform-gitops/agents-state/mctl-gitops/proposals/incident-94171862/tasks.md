# Tasks: incident-94171862

1. [ ] Locate the investigate WorkflowTemplate and the ExternalSecret that supplies `claude-code-oauth-token-2` in mctl-gitops.
2. [ ] Verify the fallback token key is mapped into the investigator step environment; if it is missing, add the mapping (single field only). If present, make no change and state that in the PR/notes.
3. [ ] Note in the PR description that the root cause is the 403 oauth_org_not_allowed account policy, requiring an operator to restore access or supply an API key / second token; then re-trigger issue 1051.
