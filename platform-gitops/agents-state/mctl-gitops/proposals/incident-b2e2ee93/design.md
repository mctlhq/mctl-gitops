# Design: incident-b2e2ee93

## Diagnosis
The monitoring-kube-state-metrics Deployment in the nfc tenant is stuck in a pending rollout state. This typically occurs when: (1) insufficient cluster resources prevent pod scheduling, (2) an image pull fails, (3) a readiness probe is failing, or (4) the pod is waiting for a PVC. The generic alert type and lack of application logs suggest this is a Kubernetes resource constraint or scheduling issue, not an application logic problem. No pattern-matched skill caught this because it is a pure infrastructure incident.

## Proposed Fix
Verify and adjust Deployment resource requests/limits in the nfc tenant's kube-state-metrics configuration. Common causes:
1. Increase memory/CPU requests if the node pool is saturated
2. Verify image tag is correct and registry is accessible
3. Check PVC status and storage class availability
4. Verify pod affinity/anti-affinity rules are not blocking scheduling

Implement a resource profile update or node pool scaling to allow the Deployment to progress.

## Scope
Minimal. Only modify kube-state-metrics resource allocation for the nfc tenant in the monitoring stack.
