# Design: incident-5324e3ea

## Confidence: LOW

## Diagnosis
The recording rule mctl_telegram:oauth_5xx:ratio_rate1h in rule group mctl-telegram-slo-sli evaluates to an empty result in vmalert. mctl-agent had no skill for RecordingRulesNoData, and no vmalert logs were available. Likely causes: the underlying metric (OAuth request counter exposed by mctl-telegram) is not scraped or was renamed, there is no 5xx traffic so the ratio has an empty numerator series (a ratio like rate(5xx)/rate(total) yields no data when the 5xx series does not exist), or the scrape target lacks a ServiceMonitor. Verify before applying.

## Proposed Fix
1. Locate the rule group mctl-telegram-slo-sli in mctl-gitops (grep for mctl_telegram:oauth_5xx:ratio_rate1h).
2. Check that the metric names used in its expr exist for the mctl-telegram service (ServiceMonitor/scrape config present).
3. If the cause is a missing 5xx series, make the expr tolerant, e.g. `sum(rate(errors[1h])) / sum(rate(total[1h]))` becomes `(sum(rate(errors[1h])) or vector(0)) / sum(rate(total[1h]))`.
4. If the metric was renamed or is not scraped, fix the metric name or add the scrape config instead.

## Scope
Minimal. Only touch the single recording rule (or its scrape config) that causes this alert.
