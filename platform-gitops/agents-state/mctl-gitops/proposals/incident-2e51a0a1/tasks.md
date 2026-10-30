# Tasks: incident-2e51a0a1

1. [ ] Find the rule `mctl_telegram:oauth_5xx:ratio_rate1h` in group `mctl-telegram-slo-sli` in the repo and read its expression.
2. [ ] Verify the referenced metric names match what mctl-telegram exports and that a scrape target exists; fix the name or scrape config if not.
3. [ ] If the numerator can legitimately be empty, add `or vector(0)` to the numerator so the ratio yields 0 rather than no data.
4. [ ] Verify the change looks correct and touches only this rule.
