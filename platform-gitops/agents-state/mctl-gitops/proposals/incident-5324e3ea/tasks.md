# Tasks: incident-5324e3ea

1. [ ] Find rule mctl_telegram:oauth_5xx:ratio_rate1h in group mctl-telegram-slo-sli and identify the metrics in its expr.
2. [ ] Verify those metrics are scraped from mctl-telegram; fix the metric name or scrape config if not, otherwise add `or vector(0)` to the numerator.
3. [ ] Verify the edited rule expression is valid and the change is limited to this rule.
