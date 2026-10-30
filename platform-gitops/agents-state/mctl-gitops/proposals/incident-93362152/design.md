# Design: incident-93362152

## Confidence: LOW

## Diagnosis
The implement workflow mctl-agents-implement-62d43db3 failed in the run-implementer step: the primary Claude attempt failed, and the fallback was skipped because the secret key claude-code-oauth-token-2 is not set. The assert-attempt step reports both attempts Failed. The workflow logs do not show the primary failure reason in the readable portion (the 58k-character primary log was not fully inspected). The most likely cause per the workflow's own message is a Claude usage limit / HTTP 429 on the primary account, which is transient, combined with the fallback token being absent. The service admins/mctl-agents is not a running service in the workspace, so no service logs exist. The workflow already moved the proposal to needs-triage via a status commit.

## Proposed Fix
Verify before changing anything:
1. Check whether the fallback token claude-code-oauth-token-2 is referenced in the mctl-agents implement workflow template/ExternalSecret in mctl-gitops and whether its Vault key is wired. If the reference is missing or misnamed in gitops, fix that single reference. If it is simply an unset Vault value, no gitops change is possible; record that a human must populate it.
2. If the cause was a transient usage limit, no code change is needed; the proposal issue-866-feat-deploy-deploy-plan-with-a-server-co can be moved back to accepted by an operator-reviewed change.

## Scope
Minimal. Only touch the single secret reference for the fallback token, and only if verification shows it is misconfigured in gitops. Otherwise make no change.
