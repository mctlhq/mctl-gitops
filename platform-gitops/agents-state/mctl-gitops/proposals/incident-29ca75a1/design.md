# Design: incident-29ca75a1

## Diagnosis
The alert is not about the worker's own health: its logs are normal and the old pod is Running and ready. The app is Degraded because the new ReplicaSet (image 1.117.0) cannot create its pod. The default Deployment rolling update starts the new pod before stopping the old one, which needs an extra 320Mi of requests.memory. The admins namespace is at requests.memory 1792Mi of a 2Gi quota (admins-quota), so only 256Mi is free and pod creation is rejected with "exceeded quota". It retries on backoff and never succeeds while the old pod holds its 320Mi. mctl-agent had no skill for argocd_app_degraded, hence the escalation. The cause is the surge pod plus quota headroom; the worker is a single-replica, non-HTTP Temporal worker with no traffic to keep up during a rollout.

## Proposed Fix
File: platform-gitops/services/admins/mctl-agents-worker/values.yaml

Make the rollout replace the pod in place instead of surging, so no extra quota is needed. Add at top level (current value: key absent, chart default RollingUpdate with surge):

```yaml
strategy:
  type: Recreate
```

Before editing, check the base-service chart's deployment template for the exact values key that controls the Deployment strategy (it may be `strategy`, `deploymentStrategy` or `rollingUpdate.maxSurge`). If the chart exposes a rollingUpdate knob but not a type, use maxSurge: 0 with maxUnavailable: 1 instead. If the chart exposes no strategy knob at all, do NOT edit the chart in this change; fall back to the alternative below and note it in the PR.

Alternative (only if no strategy knob exists): raise requests.memory quota for the admins tenant from 2Gi to 2560Mi in the tenant definition, leaving all other quota fields unchanged. Prefer the strategy change; it adds no cluster-wide resource use.

Side effect to note in the PR: with Recreate the worker is down for a few seconds per rollout. Temporal retains queued tasks, so this is safe.

## Confidence: LOW
The root cause (quota exceeded during surge) is directly evidenced by repeated FailedCreate events. The exact chart key for the strategy is not verified, and namespace usage (1792Mi) could include other workloads that change over time. Verify the chart template before applying.

## Scope
Minimal. Only the Deployment rollout strategy of admins/mctl-agents-worker (or, as fallback, the single memory-request quota field). Do not change resource requests, image tag or probes.
