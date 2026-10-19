# Design: incident-850ddad2

## Diagnosis
KubeJobFailed in namespace admins, reported through monitoring-kube-state-metrics, carries no job name.
The only failing Job visible in logs is admins-umami-retention-29873063, which fails with
`syntax error at or near "$"` on a `DO $` statement (see incident bf3aa5e1-eb02-440a-889c-846542ea82c0).
This alert is most likely the generic form of that same failure.

## Proposed Fix
Apply the same fix as proposal incident-42ea82c0 (fix dollar-quote handling in the Umami retention
CronJob SQL). No separate change is needed unless, after that fix, KubeJobFailed still fires for a
different Job; in that case identify the Job from the alert's `job_name` label first.

## Scope
Minimal. Do not modify the KubeJobFailed alert rule.

## Confidence: LOW
The incident has no job name, so the link to the Umami Job is inferred from timing and namespace.
