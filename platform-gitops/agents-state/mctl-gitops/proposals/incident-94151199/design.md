# Design: incident-94151199

## Confidence: LOW

## Diagnosis
The implement workflow for proposal issue-953-feat-glovo-m1a-tenant-bound-synthetic-gl failed after about 140s. The primary implementer attempt failed (its own log was too large to read in full; the cause was not directly observed). The fallback could not run because the secret claude-code-oauth-token-2 is not set, so both attempts failed and the proposal was moved to needs-triage by the workflow. The most likely cause, per the workflow's own assertion message, is a Claude usage limit (HTTP 429) on the primary account combined with the missing second-account token. This is mostly operational (quota/secret), not a defect in a repo file. No tenant service logs exist for admins/mctl-agents (service not found), so none were used.

## Proposed Fix
1. Do not change code or Helm values blindly. Verify whether the secret reference for claude-code-oauth-token-2 is declared for the mctl-agents implement workflow in mctl-gitops; if the ExternalSecret/Vault mapping is missing or misnamed, add or correct it. Providing the token value itself is a manual Vault step and out of scope.
2. If the reference is already present and correct, make no file change; instead move the issue-953 proposal .status.yaml from needs-triage back to accepted so the implementer retries once quota is available.

## Scope
Minimal. Only the secret reference for the fallback token, or the single status field of the issue-953 proposal. Nothing else.
