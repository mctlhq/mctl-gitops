# Design: incident-eb324d16

## Diagnosis
The ArgoCD application for nfc-quirestack-api is reporting Degraded health status without a specific error signature. The most likely root cause is resource constraints (memory or CPU limits too restrictive) preventing pod startup or readiness probe timeout. Less likely causes include RBAC permission drift, image pull errors, or a transient webhook timeout during sync. The incident analysis correctly identifies the need to inspect the resource-tree and sync operation status, but without logs or detailed ArgoCD API access, we diagnose the most common scenario in managed platforms: insufficient resource allocation.

## Proposed Fix
Increase pod resource requests and limits in the ArgoCD application values for the tenant. Specifically:
- File: `helm/charts/quirestack-api/values-nfc.yaml` (or tenant-specific overrides)
- Field: `resources.requests.memory` and `resources.limits.memory`
- Current value: likely 128Mi or 256Mi (too low)
- New value: 512Mi memory minimum, 1Gi recommended for API services
- Also check: `resources.requests.cpu` (should be at least 100m for consistent pod scheduling)

If the above does not resolve the issue, the next step is to inspect ArgoCD app sync logs via `argocd app get nfc-quirestack-api` to identify the exact unhealthy resource.

## Confidence: LOW
This diagnosis is based on the most common pattern of ArgoCD degradation in managed platforms (resource starvation). The actual root cause requires ArgoCD app inspection or pod event logs, which were not available during analysis. Implementer should verify pod readiness and sync status before applying resource increases.
