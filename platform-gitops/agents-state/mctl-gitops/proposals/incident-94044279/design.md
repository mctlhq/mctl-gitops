# Design: incident-94044279

## Confidence: LOW

## Diagnosis
The Argo workflow mctl-agents-implement-21c96820 failed at the run-implementer step. The primary implement attempt failed (the 157 KB primary log was too large to read in full and the cause inside it was not identified), and the fallback step reported that no fallback token (claude-code-oauth-token-2) is set, so no fallback ran. The assert-attempt step lists the usual causes as a Claude five_hour/seven_day usage limit (HTTP 429) or an unset token-2. This looks like a transient quota failure plus a missing fallback credential, not a defect in a config value. The workflow then pushed a status update to mctl-gitops, so the proposal issue-1026-devloop-part-m-m2b-1a-worker-restart-gap should now be in needs-triage. The incident was not handled by a skill (generic workflow_failed, empty analysis).

## Proposed Fix
No automatic code or secret change is justified. The implementer must verify first:
1. Read platform-gitops/agents-state/mctl-agents/proposals/issue-1026-devloop-part-m-m2b-1a-worker-restart-gap/.status.yaml and its needs-triage reason.
2. If the reason is a usage limit or HTTP 429, no repo change is needed. Report this in the PR description or tasks and take no further action. A human or the next scheduled run re-queues the proposal once quota resets.
3. If the reason is something else (for example an error in the implementer step), make the minimal fix it points to.
Secrets (claude-code-oauth-token-2) must not be created or altered by this proposal; provisioning the fallback token is an operator task.

## Scope
Minimal. Do not change any file other than, if warranted, the single field identified in step 3.
