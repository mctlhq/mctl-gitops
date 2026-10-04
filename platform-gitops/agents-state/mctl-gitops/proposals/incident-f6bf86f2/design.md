# Design: incident-f6bf86f2

## Confidence: LOW

## Diagnosis
vmalert reports that the recording rule `mctl_telegram:oauth_5xx:ratio_rate1h` in group `mctl-telegram-slo-sli` evaluates to an empty result. mctl-agent had no matching skill, and no service logs were available, so the root cause is not confirmed. The likely causes are: (1) the underlying request-counter metric used in the rule expression (the mctl-telegram OAuth endpoint request/5xx counters) is not being scraped or was renamed; (2) the rule is a ratio whose numerator is empty when there are no 5xx responses, so the division yields no series; (3) the mctl-telegram ServiceMonitor or PodMonitor is missing or mislabeled.

## Proposed Fix
1. Locate the rule `mctl_telegram:oauth_5xx:ratio_rate1h` in the mctl-gitops repo (grep for the name under platform-gitops, likely a VMRule or PrometheusRule for mctl-telegram).
2. Check that the metrics named in the expr exist and are scraped. If the metric was renamed, update the expr.
3. If the cause is an empty numerator when there are no errors, make the numerator always produce a series, for example `(sum(rate(<5xx_metric>[1h])) or vector(0)) / sum(rate(<total_metric>[1h]))`.
4. If the scrape target is missing, restore the monitor for mctl-telegram.
Verify the actual expr before editing; do not guess metric names.

## Scope
Minimal. Only touch the single rule or scrape config that causes this specific alert.
