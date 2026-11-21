# Design: incident-8646a75d

## Confidence: LOW

## Diagnosis
KubeJobFailed fired for a Job in the zitadel namespace. The alert's service label is monitoring-kube-state-metrics, which is the exporter that reports the metric, not the failing Job. mctl-agent had no skill for this alert. Logs and events could not be fetched because zitadel is not a registered tenant (it is platform-deployed, and ArgoCD app zitadel is also reported Degraded in a separate, newer incident), so the root cause is not confirmed. The failed Job is likely a ZITADEL setup/init/migration Job, which is probably the same cause as the Degraded zitadel app.

## Proposed Fix
Verify first, do not change blindly:
1. In mctl-gitops, find the zitadel ArgoCD app and Helm values (platform-gitops, zitadel).
2. Identify the failed Job in namespace zitadel (setup/init job), and check its image tag, database connection settings, and resource limits in the values.
3. If the cause is a stale failed Job blocking sync, ensure the chart sets a ttlSecondsAfterFinished / hook-delete-policy so failed Jobs are recreated on sync.
4. If no concrete misconfiguration is found, make no change and report this in the PR description.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
