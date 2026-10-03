# Tasks: incident-39295844

1. [ ] Find the rule group `mctl-telegram-slo-sli` and the rule `mctl_telegram:oauth_5xx:ratio_rate1h` in platform-gitops, and identify the source metric(s) it uses.
2. [ ] Verify the source metric and label selectors match series currently exported by mctl-telegram; fix the selector or scrape config if they do not.
3. [ ] If the metric exists but the 5xx series is absent at low traffic, make the numerator default to zero with `or vector(0)` and guard the denominator.
4. [ ] Verify the edited expression is valid PromQL and the change is limited to this one rule.
