# Requirements: incident-eb324d16

## Incident
- ID: 7bf1229a-7a26-4164-9971-3d953178c6af
- Tenant: nfc
- Service: quirestack-api
- Alert: argocd_app_degraded
- Created: 2026-07-26T18:01:20Z
- Summary: ArgoCD app nfc-quirestack-api health: Degraded

## Evidence
### Labels
- source: polling
- type: argocd_app_degraded
- severity: warning
- status: analyzing
- confidence: LOW

### Analysis
ArgoCD application is Degraded with no auto-recognizable signature. Check `argocd app get` and the latest sync operation for the failure reason. Common causes: failed pod readiness, RBAC drift, image pull errors on a referenced workload, or a transient webhook timeout. Inspect resource-tree health to find the offending child resource.

## Acceptance Criteria
- WHEN ArgoCD app resource limits are verified and pod readiness probes are confirmed healthy THEN the ArgoCD app sync succeeds and health status returns to Healthy.
- WHEN this proposal is applied THEN the alert stops firing for this tenant/service.
