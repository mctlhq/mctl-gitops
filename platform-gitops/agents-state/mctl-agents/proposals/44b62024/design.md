# Design: 44b62024

## Diagnosis
The incident-responder workflow in mctl-agents failed after 171 seconds. Without access to detailed logs at incident time, the root cause could be: (1) insufficient resource allocation causing the Python orchestrator to timeout or crash under load, (2) a dependency service (Loki, mctl-gitops, incident state dir) becoming unavailable mid-execution, or (3) the workflow timeout threshold being set too low for the normal incident diagnosis workload. The skill did not catch this because it requires explicit workflow execution observability (Argo logs + container logs) which were unavailable during incident generation.

## Proposed Fix
Increase the incident-responder workflow timeout in Argo Workflows configuration and/or adjust resource requests for mctl-agents pod to ensure sufficient headroom for incident diagnosis operations. If this continues, inspect Argo workflow logs at https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1785107700 for the actual failure reason (OOMKilled, timeout, dep failure).

## Scope
Minimal. Adjust either: (1) the Argo workflow timeout parameter for incident-responder, or (2) the resource limits in the mctl-agents Helm values to add more memory/CPU, or (3) both.

## Confidence: LOW
No service logs were available at query time. The diagnosis is based solely on workflow name and duration. The implementer should verify the Argo workflow log output and mctl-agents pod events before applying any resource increase.
