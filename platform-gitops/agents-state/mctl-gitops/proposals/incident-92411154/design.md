# Design: incident-92411154

## Confidence: LOW

## Diagnosis
The implement workflow mctl-agents-implement-811dbde6 failed after about 129 seconds. The primary implementer run hit a Claude subscription rate limit (the run log contains rate_limit, 429 and "resets" markers). The fallback path then could not run because the second-account token (claude-code-oauth-token-2) is not set in the workflow environment, so both attempts were marked Failed and the proposal for issue-1980-governance-productionize-policy-approval moved to needs-triage. This is a quota/configuration problem, not a code defect. mctl-agent skills did not match because the failure is workflow-level. The service pod logs for mctl-agents show only routine polling and are unrelated. The service logs and workflow logs were not fully read (the primary run log was large and only searched by keyword), hence low confidence.

## Proposed Fix
1. Verify in the mctl-gitops workflow template / ExternalSecret definition for the mctl-agents implement workflow that the key claude-code-oauth-token-2 is mapped to the container environment. If the mapping is missing, add it (optional secretKeyRef or ExternalSecret remoteRef to the existing Vault path). Do not write or alter any secret value.
2. If the mapping exists, no gitops change is needed: the Vault value for claude-code-oauth-token-2 must be populated by an operator. Record this in the PR description and stop.
3. Do not re-queue the proposal automatically; an operator moves it from needs-triage to accepted after quota resets.

## Scope
Minimal. Only the secret-to-env mapping for the fallback token, if it is absent. No other workflow behaviour changes.
