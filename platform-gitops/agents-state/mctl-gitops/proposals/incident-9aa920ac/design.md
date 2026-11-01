# Design: incident-9aa920ac

## Confidence: LOW

## Diagnosis
TooHighChurnRate24h is the standard VictoriaMetrics alert that fires when the number of new time series created in 24h exceeds a fraction of the active series. It signals high series churn (for example frequent pod restarts or rollouts producing new pod-name labels, or a metric with an unbounded label). mctl-agent had no skill for this alert and no logs could be fetched, so the offending metric or label is not identified. This is a warning-level signal with a single occurrence; a rollout-driven one-off is plausible.

## Proposed Fix
The implementer must verify before applying. In mctl-gitops, locate the alert rule definition for TooHighChurnRate24h (VMAlert / VMRule or Helm values for the monitoring stack). Check whether the 24h churn threshold suits current platform activity. Only if churn is explained by normal deploy activity, raise the threshold or lengthen the `for:` duration slightly. Do not silence or delete the rule. If the rule is not found in mctl-gitops, make no change and mark the proposal needs-triage.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
