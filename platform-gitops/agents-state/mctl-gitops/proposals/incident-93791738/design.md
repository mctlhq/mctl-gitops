# Design: incident-93791738

## Diagnosis
The shepherd step and its account-2 fallback both failed, so the assert-attempt step failed the workflow by design. The log text names the likely causes as a Claude usage limit or HTTP 429 on both accounts, or an unset second-account token; the actual per-attempt error was not retrievable from the archived logs. The other steps behaved normally (nothing to commit, no Degraded apps). This is most likely a quota or credential condition, not a defect in platform manifests. It is also the same failure family as incident-93791038 (clone-gitops exit 128), so a transient git clone failure is a possible cause.

## Proposed Fix
Make the assert-attempt step print the real failure reason of each attempt (exit code and last error lines of the primary and fallback run-shepherd pods) instead of only listing likely causes. If the shepherd failure is a quota or 429 condition, downgrade the incident severity or skip alerting for it, since it clears itself when quota resets. Do not modify any secret values or token references; provisioning a missing second-account token is a human action.

## Scope
Minimal. Only the assert-attempt step message and, optionally, the alerting treatment of quota failures in the shepherd workflow template.

## Confidence: LOW
Root cause not confirmed. Verify the failure reason of the shepherd and shepherd-fallback pods of mctl-agents-shepherd-168a17bd before applying; if the reason is a clone-gitops failure, apply the retry fix from incident-93791038 instead.
