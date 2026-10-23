# Tasks: incident-3ee9371a

1. [ ] Locate the MctlTelegramSessionBorrowFastBurn rule in mctl-gitops and read its expression, window and `for:` value.
2. [ ] Verify whether the alert is still firing; if it has cleared and no persistent fault is evident, make no change and note it in the PR/summary.
3. [ ] If the rule is noisy during DB restarts or rollouts, apply a minimal tuning (for: duration) to that single rule only.
