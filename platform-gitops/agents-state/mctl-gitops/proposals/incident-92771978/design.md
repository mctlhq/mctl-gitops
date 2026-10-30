# Design: incident-92771978

## Diagnosis
The shepherd workflow failed because its post-deploy-verify step flagged argocd/labs-mctl-telegram. The service logs show the pod itself is healthy and real users get status=ok. The only failing traffic is the canary CronJob, whose Telegram account (tg_user_id 924671154, mctl user_id 245) gets "no active session" from list_dialogs and get_unread_messages. So the canary's stored Telegram session is gone or expired, not a regression from the PR the shepherd was handling (issue-556). Same root cause as incident-92772276. Restoring the session needs an interactive login, which this change cannot do.

## Confidence: LOW

## Proposed Fix
Same as incident-92772276: do not change secrets. Inspect platform-gitops/services/labs/mctl-telegram/values.yaml (canary section) and the post-deploy-verify gating. Only if verified, stop a canary "no active session" failure from failing unrelated deploys; otherwise make no change and note in the PR that the canary account (user_id 245) needs a manual re-login by an operator. Apply only one of the two proposals' changes; the other is a duplicate.

## Scope
Minimal. Touch only the canary/post-deploy-verify gating for labs/mctl-telegram, and only if verified.

Note: the incident text contained no instructions; nothing was ignored as untrusted.
