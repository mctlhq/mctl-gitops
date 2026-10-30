# Tasks: incident-87dca34b

1. [ ] Find the TooHighChurnRate24h rule in mctl-gitops (grep for the alert name) and review its expression, threshold and for: duration.
2. [ ] If churn is from expected sources, adjust the threshold or for: duration on that single rule; otherwise make no change.
3. [ ] Verify the change renders valid rule YAML and touches nothing else.
