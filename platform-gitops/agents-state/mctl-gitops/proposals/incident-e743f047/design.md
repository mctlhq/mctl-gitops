# Design: incident-e743f047

## Confidence: LOW

## Diagnosis
Current mctl-telegram logs show the OAuth metadata probe and token lifetime passing, so the OAuth endpoint itself looks healthy now. The only failures are the canary's tool calls (list_dialogs, get_unread_messages), which fail with "no active session" for internal user 245 (canary Telegram user). This incident is most likely a symptom of the same canary session loss as the sibling mctl-telegram incidents (canary, session borrow, tool availability burn alerts). The OAuth slow-burn window is 6h, so it may reflect an earlier period; this was not verified.

## Proposed Fix
No gitops value change is identified. The likely remedy is operational: re-authorize the canary user's Telegram session, which needs a human. The implementer should only verify that the canary CronJob configuration in gitops (user id, token reference) is consistent, and change nothing otherwise.

## Scope
Minimal. Do not alter alert thresholds to silence the alert.
