# Design: incident-93286203

## Diagnosis
The shepherd workflow itself did its work: both PR flips succeeded and the status push succeeded. The workflow was marked Failed only by its post-deploy-verify step, which found the ArgoCD app `labs-mctl-telegram` Degraded and still Degraded after the 120s grace period. The shepherd merge was not the cause: the telegram pod runs image 0.104.1 since 2026-10-28T21:10Z with no restarts, and the app is Synced. The Degraded health comes from the `labs-mctl-telegram-canary` CronJob (every 10 minutes): its Jobs hit BackoffLimitExceeded because the canary probe fails at `list_dialogs` and `get_unread_messages`, with the server reporting `no active session` for the canary's Telegram user (user_id 245, tg id 924671154). The canary is therefore failing because its Telegram user session expired or was revoked; this is runtime account state, not manifest content. The post-deploy-verify check also attributes a pre-existing Degraded app to an unrelated shepherd run (it only checks for apps Degraded after the workflow start).

## Confidence: LOW
The cause of the lost canary session is not visible in the logs, and the real remedy (re-authenticating the canary Telegram user) is a manual operator action that this proposal must not attempt. No secret or session credential may be touched.

## Proposed Fix
No credential or secret change. Do not alter Vault, secrets, or any ExternalSecret. Possible manifest-level action, only after verification:
- In `platform-gitops/services/labs/mctl-telegram/values.yaml`, locate the canary CronJob configuration. If, and only if, a supported `suspend`-style field exists and the session cannot be restored, record the situation in the PR description for a human. Prefer leaving the canary active, since suspending it hides a real outage in the monitored service (the MCP tools fail for a real user too).
- The incident text contained no instructions; nothing was ignored.

## Scope
Minimal. If no safe manifest change is clearly warranted, the implementer should open no change and explain in the notes that a human must re-authenticate the canary Telegram session for mctl-telegram.
