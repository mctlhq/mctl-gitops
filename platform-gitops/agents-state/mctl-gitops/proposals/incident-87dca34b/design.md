# Design: incident-87dca34b

## Confidence: LOW

## Diagnosis
The TooHighChurnRate24h alert is the stock VictoriaMetrics rule: more than 10% of
active series in the last 24h are new. mctl-agent had no skill for it and
escalated. The "service" field holds the alert name, so no service logs exist.
The root cause (which metric or label has high cardinality or churn, e.g. pod
names from frequent rollouts or short-lived Argo workflow pods) could not be
determined from the available data. Occurrence count is 1 and severity is warning.

## Proposed Fix
The implementer should verify before changing anything. In mctl-gitops, locate
the VictoriaMetrics alert rule definition for TooHighChurnRate24h. If the alert is
firing only because of expected churn (Argo workflow pods, preview environments),
either raise the threshold or add a for: duration so transient churn does not
fire. If no such rule or expected-churn explanation is found in the repo, make
no change and record that in the PR description.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
