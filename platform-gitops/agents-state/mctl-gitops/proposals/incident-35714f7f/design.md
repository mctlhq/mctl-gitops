# Design: incident-35714f7f

## Confidence: LOW

## Diagnosis
TooHighChurnRate24h is a stock VictoriaMetrics alerting rule that fires when the number of new time series created over 24h is large relative to the active series count. mctl-agent has no skill for it, so no analysis was done. No service logs were available (the incident's service field is the alert name, not a workload). Likely causes are a recent deploy or preview environments creating short-lived pods and therefore new label sets, or a high-cardinality label on a metric. This is unverified. The incident has occurrence_count 1 and severity warning.

## Proposed Fix
Verify before applying. Locate the TooHighChurnRate24h rule in mctl-gitops (search the monitoring / VictoriaMetrics rule values). If the churn is explained by normal pod and preview rollover, relax the rule: raise the churn ratio threshold or lengthen its `for` duration, noting the current and new values in the PR. Do not change anything else. If the rule cannot be found or the cause is a specific high-cardinality metric, make no change and record that in the PR description.

## Scope
Minimal. Only touch the single threshold or `for` field of the TooHighChurnRate24h rule.
