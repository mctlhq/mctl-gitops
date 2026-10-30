# Design: incident-66450435

## Confidence: LOW

## Diagnosis
KubeJobFailed fired in the forgejo namespace. The service label is monitoring-kube-state-metrics, which is the exporter that reports the metric, not the failed Job itself, so the failing Job is unidentified. No skill matched and no logs were available. The root cause is unknown.

## Proposed Fix
Do not make speculative changes. The implementer should look in mctl-gitops for Jobs or CronJobs deployed into the forgejo namespace (for example a backup or migration job) and check their spec for an obvious fault (bad image tag, missing secret reference, wrong command). If none is found, make no change and record in the PR that a human must identify the failed Job. A job that has already failed and been replaced may leave the alert firing until the failed Job object is cleaned up; that is an operational step.

## Scope
Minimal. Only touch a single clearly faulty field if one is identified.
