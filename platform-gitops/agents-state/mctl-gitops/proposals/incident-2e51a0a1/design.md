# Design: incident-2e51a0a1

## Confidence: LOW

## Diagnosis
The vmalert recording rule `mctl_telegram:oauth_5xx:ratio_rate1h` in group `mctl-telegram-slo-sli` returns an empty result. mctl-agent had no skill for RecordingRulesNoData, and no service logs were available, so the root cause is not confirmed. Likely causes: (a) the rule's source metric (an OAuth request counter exported by mctl-telegram) is not scraped or was renamed; (b) the ratio's numerator is an empty vector because no 5xx series exist (a healthy service), so the expression yields no data instead of 0; (c) the ServiceMonitor/scrape target for mctl-telegram is missing or relabelled.

## Proposed Fix
Locate the rule definition in mctl-gitops (search for `oauth_5xx:ratio_rate1h` and group `mctl-telegram-slo-sli`). Verify the metric names used exist in the metrics backend and that mctl-telegram is scraped. If the cause is an absent numerator series, make the expression yield 0, for example `(sum(rate(<5xx_metric>[1h])) or vector(0)) / sum(rate(<total_metric>[1h]))`. If the metric was renamed or is not scraped, fix the metric name or the scrape config. If the SLI is intentionally unused, remove the rule. Do not change anything else.

## Scope
Minimal. Only touch the single recording rule (or its scrape target) that causes this alert.
