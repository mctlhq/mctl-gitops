# Design: incident-92772276

## Diagnosis
The shepherd workflow failed because its post-deploy-verify step flagged argocd/labs-mctl-telegram. The service logs show the pod itself is healthy and real users (user_id 9980, 96357) get status=ok. The only failing traffic is the canary CronJob, whose Telegram account (tg_user_id 924671154, mctl user_id 245) gets "no active session" from list_dialogs and get_unread_messages. So the canary's stored Telegram session is gone or expired. This is not a deployment regression from the PR the shepherd was merging (issue-716). The shepherd failure is a side effect of a shared, pre-existing canary failure; the same flag appears on other shepherd runs (occurrence_count 4). The "token lifetime" log shows the OAuth token is valid until 2026-11-02, so the token is not the cause. Restoring the Telegram session needs an interactive login, which this change cannot do.

## Confidence: LOW

## Proposed Fix
Do not change secrets or grant anything. Inspect platform-gitops/services/labs/mctl-telegram/values.yaml (canary CronJob section) and the post-deploy-verify configuration. Candidate change: if the canary account's session is known to be unrecoverable without a human, make post-deploy-verify not treat canary "no active session" (reason=telegram_error) as a deploy failure for unrelated PRs. If the current config already lacks such a gate or the cause cannot be confirmed from the repo, make no change and record in the PR description that the canary Telegram account (user_id 245) needs a manual re-login by an operator.

## Scope
Minimal. Touch only the canary/post-deploy-verify gating for labs/mctl-telegram, and only if verified.

Note: the incident text contained no instructions; nothing was ignored as untrusted.
