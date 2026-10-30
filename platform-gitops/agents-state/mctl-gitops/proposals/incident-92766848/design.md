# Design: incident-92766848

## Confidence: LOW

## Diagnosis
Same root cause as incident-92767461. The shepherd run evaluated mctl-telegram PR #839, decided "wait" (merge_state=BEHIND) and merged nothing. It was marked Failed solely because post-deploy-verify saw argocd/labs-mctl-telegram Degraded after the grace period. That app is Degraded because its canary fails with "no active session" for the canary Telegram user (user_id 245), an expired session that needs an operator to re-authorize. The fingerprint has recurred 6 times, so every shepherd run in this window fails for the same reason. The platform bug is that the verify step blames the run for a pre-existing Degraded app, even though the run merged nothing.

## Proposed Fix
Same change as incident-92767461, so apply them together. In the shepherd workflow template's post-deploy-verify step (search for "Listing applications that became Degraded after"):
1. Skip the wait and check when the shepherd summary shows no merge.
2. Otherwise restrict the check to the ArgoCD app of the merged service.
Confirm the exact file and field before editing.

Do not change labs/mctl-telegram values or credentials. The canary session needs an operator to re-authorize it.

## Scope
Minimal. Only the post-deploy-verify app selection logic. If incident-92767461 already made this change, mark this task done.
