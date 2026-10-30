# Design: incident-93297892

## Confidence: LOW

## Diagnosis
The shepherd run itself succeeded (merged=yes, shepherd=succeeded, status push ok). The workflow was marked Failed only by the post-deploy-verify step, which treats any ArgoCD app that became Degraded after the workflow creation time as caused by the merge. The flagged app is argocd/labs-mctl-telegram. The mctl-telegram pod is Running and ready (image 0.104.1, 0 restarts, created 2026-10-28, i.e. not changed by this run). The Degraded state correlates with the telegram canary job failing every 10 minutes with `no active session` for user_id 245 (tg_user_id 924671154): the stored Telegram session for the canary user is gone or expired. That is a runtime credential/session problem in the tenant service, not a result of the shepherd merge, and cannot be fixed by a gitops values change. The skill missed it because no skill covers workflow_failed from post-deploy-verify attribution. This diagnosis is unverified: the ArgoCD health detail for the app was not observed, only the service logs.

## Proposed Fix
Do not change labs/mctl-telegram. In the mctl-agents shepherd post-deploy-verify step, narrow attribution so a run is not failed for an app that was already unhealthy before the run, or whose last sync/image change predates the merge. Candidate rule: only count an app as newly Degraded if its last sync revision changed after the workflow creation timestamp (not merely its health transition time). The implementer must first locate the post-deploy-verify script in the mctl-agents repo, confirm how it selects apps, and apply the smallest change. If the script already filters by sync time and the app really was synced after the merge, make no change and mark the proposal needs-triage.

Out-of-band (human) action, not for the implementer: re-authenticate the Telegram canary user session (user_id 245) in labs/mctl-telegram.

## Scope
Minimal. Only the app-selection condition in post-deploy-verify. No changes to tenant services, secrets or sessions.
