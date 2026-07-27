# Design: incident-a3ee9850

## Diagnosis
ArgoCD health Degraded for labs-agent-worker-preview indicates the application cannot achieve a Healthy status. Unlike the OutOfSync alerts above, a Degraded health status typically means:
1. Pods are in pending, failed, or crashloopbackoff state
2. Resource quotas or resource limits are preventing pod creation
3. Missing dependencies (PVC, config, secrets) are preventing rollout

Preliminary analysis notes that tenant labs is approaching resource quota limits. This is the likely root cause: agent-worker-preview pods cannot be scheduled due to quota exhaustion.

Fix: Increase the resource quota for tenant labs in the platform-gitops namespace configuration, OR reduce the resource requests for agent-worker-preview service.

## Proposed Fix
Option A (preferred): Increase tenant quota
File: platform-gitops/tenants/labs/kustomization.yaml (or equivalent tenant quota config)
Field: spec.hard.requests.cpu or spec.hard.requests.memory
New value: increase from current limit to accommodate agent-worker-preview replica count

Option B (fallback): Reduce service resource requests
File: platform-gitops/tenants/labs/agent-worker-preview/values.yaml
Fields: resources.requests.cpu, resources.requests.memory
New value: reduce to fit within current quota

## Scope
Minimal. Either adjust a single quota limit OR edit service resource requests.

## Confidence: MEDIUM
The preliminary analysis suggests resource quota exhaustion, but without access to current quota metrics and pod events, confidence is medium. Implementer should verify via: kubectl describe resourcequota -n labs-tenant and kubectl get events -n labs-tenant
