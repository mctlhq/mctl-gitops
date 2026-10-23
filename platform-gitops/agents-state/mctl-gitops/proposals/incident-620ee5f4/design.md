# Design: incident-620ee5f4

## Confidence: LOW

## Diagnosis
The app is Synced at image 0.88.3 and the main base-service pod serves real users normally (user_id 183623 tool calls succeed; CHANNEL_INVALID errors are caller errors classified as slo_status=caller_error). The failing component is the canary CronJob (labs-mctl-telegram-canary), which probes as mctl user_id 245 / tg_user_id 924671154. Every canary run fails on list_dialogs and get_unread_messages with "no active session": the canary account has no live Telegram session in the service. The likely reason ArgoCD reports Degraded is that the canary Job/CronJob resources are failing (or are marked unhealthy by a health check) as a result. This is a runtime state problem (expired or revoked canary Telegram session), not a Helm values defect, so a config-only fix may not exist. The same root cause explains the MctlTelegramCanaryFailing and slow-burn session-borrow incidents and the shepherd post-deploy-verify failures.

## Proposed Fix
1. Verify in platform-gitops/services/labs/mctl-telegram/values.yaml how the canary CronJob is defined and which credential/user it uses. Do not change secrets.
2. If ArgoCD Degraded is caused by failed canary Jobs (failedJobsHistoryLimit / Job health), set the CronJob so that a failed probe does not mark the Application Degraded (for example keep failedJobsHistoryLimit low and add an ArgoCD ignore/health customization for the canary Job), since probe failure is already signalled by the MctlTelegramCanaryFailing alert.
3. Re-establishing the canary Telegram session itself requires operator action (re-login of the canary account) and is out of scope for a gitops change; note it in the PR description.

## Scope
Minimal. Only touch the canary-related fields of the labs/mctl-telegram service values. If no config cause is confirmed, make no change and document this in the PR.
