# Tasks: incident-f6bf86f2

1. [ ] Find the definition of recording rule mctl_telegram:oauth_5xx:ratio_rate1h in mctl-gitops and read its expr.
2. [ ] Confirm the source metrics exist and are scraped; fix the expr (rename or `or vector(0)` on the numerator) or restore the missing scrape monitor.
3. [ ] Verify the change looks correct and touches only this rule.
