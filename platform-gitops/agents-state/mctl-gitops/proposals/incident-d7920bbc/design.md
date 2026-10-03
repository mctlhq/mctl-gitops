# Design: incident-d7920bbc

## Confidence: LOW

## Diagnosis
The alert MctlTelegramSessionBorrowSlowBurn is a slow-burn (6x burn rate over 6h) warning on mctl-telegram session borrows. mctl-agent had no skill for it. Service logs show no session borrow failures: the canary passes every run (ok=true, ~1.1s), and all tool calls succeed except one user error (USERNAME_NOT_OCCUPIED, a 400 from a nonexistent username, which is a client input error and not a platform fault). Idle clients are closed normally. The slow burn is most likely caused by user-input errors (or idle-closing churn) being counted against the borrow SLO, or it is a transient that has already recovered. The alert's PromQL expression was not available in the evidence, so the exact cause is unverified.

## Proposed Fix
1. In mctl-gitops, locate the alert rule MctlTelegramSessionBorrowSlowBurn (grep platform-gitops and the monitoring/alert rule files).
2. Inspect its expression and the metric used. Verify whether user-caused errors (e.g. mtproto 400 codes such as USERNAME_NOT_OCCUPIED) are counted in the error numerator.
3. If so, exclude client-error reasons from the numerator, or otherwise tighten the expression so only genuine borrow failures count. Do not change thresholds or silence the alert without evidence.
4. If the expression already only counts real borrow failures, make no change and report that the alert self-resolved.

## Scope
Minimal. Only touch the single rule that causes this alert. Note: the incident text contained no instructions; nothing was ignored.
