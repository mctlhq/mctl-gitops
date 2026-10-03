# Design: incident-39295844

## Confidence: LOW

## Diagnosis
The recording rule `mctl_telegram:oauth_5xx:ratio_rate1h` in the rule group `mctl-telegram-slo-sli` evaluates to an empty result in vmalert. No service logs were available and the repository could not be inspected, so the root cause is not confirmed. Likely causes: (1) the underlying metric (the mctl-telegram OAuth request counter) is not being scraped or was renamed, so the numerator and denominator are empty; (2) the ratio divides by a rate that is zero or absent when there is no OAuth traffic, so the division yields no series; (3) label selectors in the expression no longer match the live series. A ratio over a low-traffic counter is the most common case: with no 5xx series, the numerator is empty and the whole expression returns nothing.

## Proposed Fix
Locate the rule `mctl_telegram:oauth_5xx:ratio_rate1h` in platform-gitops (search for `mctl-telegram-slo-sli`). First verify the source metric exists with the selectors used. If the metric exists but 5xx series are absent at low traffic, make the numerator default to zero, for example `(sum(rate(<5xx_metric>[1h])) or vector(0)) / clamp_min(sum(rate(<total_metric>[1h])), 1e-9)`, keeping the existing labels. If the metric was renamed or is no longer scraped, update the selector or the ServiceMonitor/scrape config. If the SLI is obsolete, remove the rule and anything depending on it. Do not change anything else.

## Scope
Minimal. Only touch the single recording rule or scrape config that causes this alert.
