# Tasks: incident-94151199

1. [ ] Search mctl-gitops for the claude-code-oauth-token-2 secret reference used by the mctl-agents implement workflow; confirm it is declared.
2. [ ] If missing or misnamed, add or fix the reference; otherwise make no change there.
3. [ ] Locate the issue-953-feat-glovo-m1a-tenant-bound-synthetic-gl proposal .status.yaml; if status is needs-triage, set it back to accepted.
4. [ ] Verify the diff touches only those files and note that the token value itself must be set in Vault manually.
