# Design: incident-92767461

## Confidence: LOW

## Diagnosis
The shepherd run itself did nothing wrong: it evaluated PR mctl-agents#768, decided "wait" and handed off nothing. The workflow was marked Failed only because its post-deploy-verify step found argocd/labs-mctl-telegram Degraded and held it against this run. That app is unrelated to the service in this run (mctl-agents). The app is still Degraded: its canary job fails every minute with "no active session" for the canary Telegram user (user_id 245). That is an expired or missing Telegram session for the canary account, which is runtime state and not a gitops value, so it needs an operator to re-authorize the session. The platform bug is that post-deploy-verify attributes any newly Degraded app to the current run, even when the run merged nothing or the app belongs to another service.

## Proposed Fix
Locate the post-deploy-verify step of the shepherd workflow template in mctl-gitops (search for "Listing applications that became Degraded after"). Change it to:
1. Skip the 300s wait and the check entirely when the shepherd summary shows no merge happened.
2. When a merge did happen, only consider the ArgoCD app(s) of the service that was merged, instead of every app that became Degraded.
Exact file and field must be confirmed by the implementer; they were not visible from the logs.

Do not attempt to change labs/mctl-telegram values or Telegram credentials from this proposal. The session re-authorization needs an operator.

## Scope
Minimal. Only the post-deploy-verify app selection logic.
