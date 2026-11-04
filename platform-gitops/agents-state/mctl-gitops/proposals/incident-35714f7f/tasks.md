# Tasks: incident-35714f7f

1. [ ] Find the TooHighChurnRate24h alert rule definition in mctl-gitops.
2. [ ] If churn is explained by normal pod and preview rollover, raise its threshold or `for` duration modestly; otherwise make no change and say why in the PR.
3. [ ] Verify the rule YAML still renders and that only that one field changed.
