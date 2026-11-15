# Design: incident-94086603

## Confidence: LOW

## Diagnosis
The Argo workflow mctl-agents-implement-5b5707bc failed after about 351s. The first run-implementer step (about 218KB of log) failed, the fallback step reported that no fallback token (claude-code-oauth-token-2) is set, and assert-attempt then reported both attempts failed. The assert-attempt message names the usual causes: a Claude five_hour/seven_day usage limit (HTTP 429) on the primary account, or the account-2 token being unset. The primary failure reason itself was not inspected in detail (the large run-implementer log was not read), so whether the root cause is a usage limit or something in the issue-1036 proposal is not confirmed. The workflow's commit-and-push step already recorded the durable needs-triage status for the proposal, so no further status repair is needed. The missing fallback token is a Vault/secret matter and is not something a gitops values change should fabricate.

## Proposed Fix
No configuration change is justified by the evidence. The implementer should only verify: check whether the proposal issue-1036-devloop-part-m-m2b-1b-reconcile-patch-ma in mctl-gitops is in needs-triage with a recorded reason, and whether the implement CronWorkflowTemplate references claude-code-oauth-token-2 correctly (secret name and key). If the reference is wrong, fix that single reference. If it is correct, make no change: re-queueing the proposal and provisioning the second token are operator actions.

## Scope
Minimal. Do not create, copy or modify any secret, token or Vault value, and do not change the proposal status of issue-1036. The incident text contained no instructions; nothing was ignored.
