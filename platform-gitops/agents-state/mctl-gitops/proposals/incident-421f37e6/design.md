# Design: incident-421f37e6

## Confidence: LOW

## Diagnosis
The vmalert recording rule `mctl_telegram:oauth_5xx:ratio_rate1h` in the rule group `mctl-telegram-slo-sli` evaluates to an empty result, which triggers RecordingRulesNoData. mctl-agent had no skill for this alert, and no service logs were available. Likely causes: the numerator/denominator metric (the OAuth request counter exported by mctl-telegram) is not scraped, is renamed or relabeled, or the service emits no 5xx series (a ratio of an absent numerator yields no data rather than 0). The rule was not inspected directly; verify before applying.

## Proposed Fix
1. Locate the rule `mctl_telegram:oauth_5xx:ratio_rate1h` in mctl-gitops (search platform-gitops for `mctl-telegram-slo-sli`).
2. Check that the source metric names and labels exist (ServiceMonitor/VMServiceScrape for mctl-telegram present and matching).
3. If the numerator is legitimately absent when there are no errors, make the expression robust, e.g. `sum(rate(errors[1h])) / sum(rate(total[1h]))` becomes `(sum(rate(errors[1h])) or vector(0)) / sum(rate(total[1h]))`. If the metric was renamed or the scrape is missing, fix the metric name or add the scrape config instead.

## Scope
Minimal. Only touch the single recording rule or scrape config causing this alert.
