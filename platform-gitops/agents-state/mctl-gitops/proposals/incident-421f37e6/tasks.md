# Tasks: incident-421f37e6

1. [ ] Find the rule group mctl-telegram-slo-sli and the rule mctl_telegram:oauth_5xx:ratio_rate1h in mctl-gitops; confirm the source metrics and the mctl-telegram scrape config exist.
2. [ ] Fix the expression (add `or vector(0)` to the numerator) or correct the metric name or scrape config, whichever the check shows.
3. [ ] Verify the edited rule is valid PromQL/MetricsQL and does not alter other rules in the group.
