# Design: incident-bfe41a4c

## Confidence: LOW

## Diagnosis
The alert is correct and the pushgateway is not at fault: it only holds the metrics the canary pushes (canary ok=false). The canary passes oauth_metadata and mcp_init, then fails list_dialogs and get_unread_messages because the service reports "no active session" for the canary identity (mctl user_id 245, tg_user_id 924671154). The canary's Telegram session is missing, expired or revoked. Real users (for example user_id 183623) are served successfully, so this is not a service-wide outage. This is the same root cause as incident eb51f2c9 (ArgoCD Degraded) and the session-borrow slow-burn alert.

## Proposed Fix
No Helm or alert-rule change fixes a missing session. The only gitops-side action is to make the alert actionable: add a runbook annotation or summary to the MctlTelegramCanaryFailing rule noting that "no active session" means the canary Telegram account must be re-logged-in by an operator. Locate the rule in the monitoring rules under platform-gitops and edit only its annotations. Do not touch thresholds, silences, or secrets.

## Scope
Minimal. Annotation text on the single MctlTelegramCanaryFailing rule. If the rule cannot be found, make no change and say so in the PR.
