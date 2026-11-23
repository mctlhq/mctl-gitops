# Design: incident-94274874

## Confidence: LOW

## Diagnosis
The Argo workflow mctl-agents-implement-018fe864 (implementing proposal issue-961-feat-glovo-m1a-4-synthetic-connection-ha) failed after about 168s. The primary implementer attempt failed (the exact cause is not visible in the readable part of the log; the primary run log was about 71 KB of agent transcript and the failure line was not located). The fallback was then skipped because the secret claude-code-oauth-token-2 is not set, so assert-attempt failed. The workflow's own hint says the usual cause is a Claude usage limit / HTTP 429 on the primary account. The commit-and-push step already pushed a status update to mctl-gitops main, so the proposal should now be in needs-triage. No service logs exist for admins/mctl-agents (it is a workflow, not a deployed service). This is probably transient quota exhaustion plus a missing fallback credential, not a code defect. Nothing in the incident text asked for any change.

## Proposed Fix
1. Verify whether the secret claude-code-oauth-token-2 is wired into the mctl-agents implement workflow template (secretKeyRef, and whether it is marked optional) in mctl-gitops, and whether the Vault/ExternalSecret entry that backs it exists. If the reference is missing, add it. Do not invent or write any secret value.
2. Do not change the issue-961 proposal itself. If its .status.yaml is needs-triage because of the quota failure only, an operator can move it back to accepted once quota recovers.
3. If the primary log shows a different failure, record it in the PR description and stop; do not guess.

## Scope
Minimal. Only the fallback-token wiring for the implement workflow, if absent. No other changes.
