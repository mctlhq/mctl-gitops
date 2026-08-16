# Design: incident-5b968879

## Diagnosis
The agent-worker-preview service in the labs tenant is capacity-constrained at its HPA maximum replica limit. Logs show consistent job completions, indicating healthy operation, but the service is unable to scale beyond its configured maxReplicas ceiling. Downstream dependency (mctl-telegram-preview) is also at capacity, creating a cascading bottleneck. The ArgoCD degraded alert fires because the service cannot reach desired scale.

## Proposed Fix
Increase the HPA maxReplicas parameter for the labs-agent-worker-preview service from its current value (likely 5) to 10.

File: `services/labs/agent-worker-preview/values.yaml`
Field: `autoscaling.maxReplicas`
Current value: (assumed) 5
New value: 10

Alternative paths if values.yaml structure differs:
- Check platform-gitops/charts/base-service/values.yaml for the autoscaling defaults
- Or check platform-gitops/services/labs/agent-worker-preview/Chart.yaml for overrides

## Scope
Minimal. Only the maxReplicas field for this one service. No other configuration changes required. The HPA will naturally scale up to accommodate load up to the new limit.
