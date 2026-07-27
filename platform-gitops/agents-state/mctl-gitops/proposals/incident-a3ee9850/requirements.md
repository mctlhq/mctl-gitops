# Requirements: incident-a3ee9850

## Incident
- ID: a0e3aece-e6d2-4eed-a813-3f7b526aeb3d
- Tenant: labs
- Service: agent-worker-preview
- Alert: argocd_app_degraded
- Created: 2026-07-25T14:59:14Z
- Summary: ArgoCD app labs-agent-worker-preview health: Degraded

## Evidence
### Labels
- source: polling
- severity: warning
- status: analyzing
- occurrence_count: 1
- Analysis note: Tenant labs is approaching resource quota limits. Review current allocation and consider increasing quotas or optimizing service resource requests.

### Log Snippet
ArgoCD app health Degraded status indicates either a sync issue (similar to other incidents) or underlying resource constraints preventing pods from becoming ready. Preliminary analysis suggests tenant labs resource quota limits are being approached.

## Acceptance Criteria
- WHEN either (1) resource quotas are increased for tenant labs or (2) service resource requests are optimized THEN the app health returns to Healthy and the Degraded alert stops firing.
