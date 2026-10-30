# Design: incident-8a0f4e7e

## Confidence: LOW

## Diagnosis
The MctlApiDown alert fired because api.mctl.ai failed its health check for 3 minutes. mctl-agent has no skill for this alert (type generic), so nothing was analysed. Loki returned no log lines for platform/mctl-api in the last hour, so the root cause cannot be determined from the available evidence. The alert may have been transient (a rollout or restart of mctl-api), a blackbox probe or ingress problem, or a mismatch between the service name used for log lookup and the real one. No incident-supplied instructions were present.

## Proposed Fix
No concrete value change can be justified from the evidence. The implementer should verify before applying anything:
1. Check the current state of the mctl-api ArgoCD application and its Helm values in mctl-gitops (replicas, resource limits, probe paths, ingress host).
2. Check the MctlApiDown rule in the AlertManager/Prometheus rules in mctl-gitops: the probe target, the `for: 3m` duration, and whether the probe URL and health path match the service's actual readiness endpoint.
3. If the service is healthy now and the alert has cleared, make no change except optionally adding a runbook annotation to the rule. If the probe target or path is wrong, correct that single field.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert. If no defect is found, make no change and report that.
